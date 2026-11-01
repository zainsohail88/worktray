"""Renew Google credentials with single-use rotation, stored in the system keyring."""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
import fcntl
import os
from pathlib import Path
import time
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from worktray import ENV_PREFIX
from worktray.auth.keyring_store import secret_store
from worktray.paths import oauth_dir
from worktray.sources.errors import SourceError


Profile = Literal["google"]
PROFILES = ("google",)
ENV_TOKENS = {"google": f"{ENV_PREFIX}_GOOGLE_ACCESS_TOKEN"}


class Credential(BaseModel):
    """Keep a rotating credential bundle in one atomic secret-store entry."""

    access_token: str = Field(default="", repr=False)
    refresh_token: str = Field(default="", repr=False)
    client_id: str = Field(default="", repr=False)
    client_secret: str = Field(default="", repr=False)
    expires_at: float = 0


class SecretStore(Protocol):
    """Persist the latest token pair before exposing the renewed access token."""

    def load(self, profile: Profile) -> Credential | None: ...
    def save(self, profile: Profile, credential: Credential) -> None: ...
    def clear(self, profile: Profile) -> None: ...


class KeyringSecrets:
    """Credential bundles as JSON entries in the keyring, next to the plain secrets."""

    def load(self, profile: Profile) -> Credential | None:
        value = secret_store().read(f"oauth:{profile}")
        try:
            return Credential.model_validate_json(value) if value else None
        except ValidationError as error:
            raise SourceError("The saved sign-in is invalid. Sign in again.") from error

    def save(self, profile: Profile, credential: Credential) -> None:
        secret_store().write(f"oauth:{profile}", credential.model_dump_json())

    def clear(self, profile: Profile) -> None:
        secret_store().clear(f"oauth:{profile}")


class TokenManager:
    """Serialize renewals across app instances and setup commands."""

    def __init__(self, secrets: SecretStore, directory: Path, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.secrets = secrets
        self.directory = directory
        self.transport = transport
        self.cached: dict[Profile, Credential] = {}
        self.pending: dict[Profile, tuple[Credential, Credential]] = {}

    def configured(self, profile: Profile) -> bool:
        """A secret-free marker limits keyring reads to enrolled profiles."""
        self._validate(profile)
        return (self.directory / f"{profile}.enabled").exists()

    @staticmethod
    def _validate(profile: Profile) -> None:
        if profile not in PROFILES:
            raise ValueError("Unknown credential profile")

    @asynccontextmanager
    async def _lock(self, profile: Profile) -> AsyncIterator[None]:
        self._validate(profile)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.directory / f"{profile}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + 60
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise SourceError("Another worktray process is renewing the sign-in. Try again shortly.") from None
                    await asyncio.sleep(0.05)
            yield
        finally:
            os.close(descriptor)

    async def enroll(self, profile: Profile, credential: Credential) -> None:
        """Save an explicitly supplied grant without consuming its refresh token."""
        if not credential.refresh_token or not credential.client_id:
            raise SourceError("Refresh token and the issuing OAuth client ID are required")
        await self._complete(self._enroll_locked(profile, credential))

    async def forget(self, profile: Profile) -> None:
        """Drop the grant and its marker so the profile reads as not connected."""
        async with self._lock(profile):
            await asyncio.to_thread(self.secrets.clear, profile)
            (self.directory / f"{profile}.enabled").unlink(missing_ok=True)
            self.cached.pop(profile, None)
            self.pending.pop(profile, None)

    async def _enroll_locked(self, profile: Profile, credential: Credential) -> None:
        async with self._lock(profile):
            await asyncio.to_thread(self.secrets.save, profile, credential)
            (self.directory / f"{profile}.enabled").touch(mode=0o600)
            self.cached.pop(profile, None)
            self.pending.pop(profile, None)

    async def access_token(self, profile: Profile, rejected: str | None = None) -> str:
        """Renew near expiry or once after the provider rejects a cached token."""
        if not self.configured(profile):
            token = os.environ.get(ENV_TOKENS[profile], "")
            if token and not rejected:
                return token
            raise SourceError(f"{profile}: sign in for lasting access. {ENV_TOKENS[profile]} only gives temporary access.")
        cached = self.cached.get(profile)
        if profile not in self.pending and self._usable(cached, rejected):
            return cached.access_token
        return await self._complete(self._access_locked(profile, rejected))

    @staticmethod
    async def _complete[Result](operation: Coroutine[Any, Any, Result]) -> Result:
        task = asyncio.create_task(operation)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # A background keyring save must finish before the file lock releases.
            await asyncio.gather(task, return_exceptions=True)
            raise

    async def _access_locked(self, profile: Profile, rejected: str | None) -> str:
        async with self._lock(profile):
            credential = await asyncio.to_thread(self.secrets.load, profile)
            if profile in self.pending:
                original, rotated = self.pending[profile]
                if credential == original:
                    await asyncio.to_thread(self.secrets.save, profile, rotated)
                    credential = rotated
                self.pending.pop(profile)
            if credential is None:
                raise SourceError(f"{profile}: the keyring entry is missing. Sign in again.")
            if not self._usable(credential, rejected):
                original = credential
                credential = await self._renew(profile, original)
                self.pending[profile] = (original, credential)
                await asyncio.to_thread(self.secrets.save, profile, credential)
                self.pending.pop(profile)
            self.cached[profile] = credential
            return credential.access_token

    @staticmethod
    def _usable(credential: Credential | None, rejected: str | None) -> bool:
        return bool(credential and credential.access_token and credential.access_token != rejected and credential.expires_at > time.time() + 60)

    async def _renew(self, profile: Profile, credential: Credential) -> Credential:
        endpoint = "https://oauth2.googleapis.com/token"
        fields = {"grant_type": "refresh_token", "refresh_token": credential.refresh_token, "client_id": credential.client_id}
        if credential.client_secret:
            fields["client_secret"] = credential.client_secret
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
                response = await client.post(endpoint, data=fields)
        except httpx.RequestError as error:
            raise SourceError(f"{profile}: cannot reach the sign-in service. Try again when you are online.") from error
        try:
            data = response.json()
        except ValueError as error:
            raise SourceError(f"{profile}: the sign-in service returned an invalid response") from error
        if not isinstance(data, dict):
            raise SourceError(f"{profile}: the sign-in service returned an invalid response")
        if response.status_code != 200:
            code = data.get("error")
            known = {"invalid_grant", "invalid_client", "ratelimited"}
            reason = code if isinstance(code, str) and code in known else f"HTTP {response.status_code}"
            raise SourceError(f"{profile}: renewing the sign-in failed ({reason}). Check the OAuth client file or sign in again.")
        tokens = data
        refresh = tokens.get("refresh_token") or credential.refresh_token
        try:
            lifetime = float(tokens.get("expires_in", 0))
        except (TypeError, ValueError):
            lifetime = 0
        if not tokens.get("access_token") or not refresh or not 60 < lifetime < 366 * 86400:
            raise SourceError(f"{profile}: the sign-in service did not return a new token. Sign in again.")
        return credential.model_copy(update={"access_token": tokens["access_token"], "refresh_token": refresh, "expires_at": time.time() + lifetime})


class RefreshAuth(httpx.Auth):
    """Retry a rejected API request once with the newly renewed credential."""

    requires_response_body = True

    def __init__(self, manager: TokenManager, profile: Profile) -> None:
        self.manager = manager
        self.profile = profile

    async def async_auth_flow(self, request: httpx.Request) -> AsyncIterator[httpx.Request]:
        token = await self.manager.access_token(self.profile)
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401:
            token = await self.manager.access_token(self.profile, rejected=token)
            request.headers["Authorization"] = f"Bearer {token}"
            yield request


_manager: TokenManager | None = None


def token_manager() -> TokenManager:
    """Share renewed credentials between readers in this application process."""
    global _manager
    if _manager is None:
        _manager = TokenManager(KeyringSecrets(), oauth_dir())
    return _manager


def reset_token_manager() -> None:
    """Forget the process-wide manager so the next call binds to the current data directory."""
    global _manager
    _manager = None
