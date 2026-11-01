"""Google sign-in: find the downloaded OAuth client, run the desktop consent flow, keep the grant renewable."""

import asyncio
import base64
from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from worktray.auth.browser import open_sign_in
from worktray.auth.oauth import ENV_TOKENS, Credential, RefreshAuth, token_manager
from worktray.config import Setting
from worktray.sources.errors import NotConnectedError, SignInRequired, SourceError
from worktray.store import Store

GOOGLE_CLIENT_FILE = Setting(
    "google_client_file",
    "Google OAuth client file",
    help="A Desktop OAuth client from Google Cloud, with the Drive and Calendar APIs turned on. Leave blank to use the client_secret file in your Downloads folder.",
    placeholder="~/Downloads/client_secret_ID.json",
    validate=lambda value: _client_file(value),
)
FIELDS = (GOOGLE_CLIENT_FILE,)
SCOPES = "https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/calendar.events.readonly"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _client_file(value: str) -> str:
    value = value.strip()
    if value:
        try:
            load_client(Path(value).expanduser())
        except SourceError as error:
            raise ValueError(str(error)) from error
    return value


@dataclass(frozen=True)
class GoogleClient:
    """Keep client secrets out of diagnostic representations."""

    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    desktop: bool = False


def load_client(path: Path) -> GoogleClient:
    """Read Google's downloaded client JSON without trusting endpoint URLs."""
    try:
        if path.stat().st_size > 1_000_000:
            raise SourceError("Google client file is too large")
        document = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise SourceError("Cannot read that Google client JSON file") from error
    if not isinstance(document, dict):
        raise SourceError("Choose a Google OAuth client JSON file")
    settings = document.get("installed") or document.get("web")
    if not isinstance(settings, dict) or not isinstance(settings.get("client_id"), str):
        raise SourceError("Choose a Google OAuth client JSON file, not a service-account key")
    secret = settings.get("client_secret", "")
    if not isinstance(secret, str) or not settings["client_id"]:
        raise SourceError("Google client settings are incomplete")
    return GoogleClient(settings["client_id"], secret, "installed" in document)


def find_client(store: Store) -> GoogleClient | None:
    """Use the configured client file, or the one OAuth client download in Downloads."""
    configured = GOOGLE_CLIENT_FILE.read(store)
    if configured:
        return load_client(Path(configured).expanduser())
    candidates = {}
    for path in (Path.home() / "Downloads").glob("client_secret*.json"):
        try:
            client = load_client(path)
        except SourceError:
            continue
        candidates[client.client_id] = client
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def _receive_code(client_id: str, cancelled: threading.Event) -> tuple[str, str, str]:
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def do_GET(self) -> None:
            target = urlsplit(self.path)
            values = parse_qs(target.query)
            valid = target.path == "/callback" and secrets.compare_digest(values.get("state", [""])[0], state)
            status = 400
            if valid and (values.get("code") or values.get("error")):
                received.update(values)
                status = 200
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Google is connected. You can close this tab." if status == 200 else b"Invalid sign-in callback.")

        def log_message(self, format: str, *args: object) -> None:
            # Authorization codes must never reach HTTP access logs.
            return

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/callback"
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": SCOPES,
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
        open_sign_in(url, "Google")
        deadline = time.monotonic() + 180
        while not received and not cancelled.is_set() and time.monotonic() < deadline:
            server.handle_request()
    if received.get("error"):
        raise SourceError("Google sign-in was cancelled. Sign in again when you are ready.")
    if not received.get("code"):
        raise SourceError("Google sign-in timed out. Try again.")
    return received["code"][0], redirect, verifier


async def sign_in(credential: Credential) -> Credential:
    """Use Google's desktop loopback flow with state validation and PKCE.

    https://developers.google.com/identity/protocols/oauth2/native-app
    """
    cancelled = threading.Event()
    receiving = asyncio.create_task(asyncio.to_thread(_receive_code, credential.client_id, cancelled))
    try:
        code, redirect, verifier = await asyncio.shield(receiving)
    except asyncio.CancelledError:
        cancelled.set()
        await asyncio.gather(receiving, return_exceptions=True)
        raise
    fields = {"code": code, "client_id": credential.client_id, "redirect_uri": redirect, "code_verifier": verifier, "grant_type": "authorization_code"}
    if credential.client_secret:
        fields["client_secret"] = credential.client_secret
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://oauth2.googleapis.com/token", data=fields)
    try:
        tokens = response.json()
    except ValueError as error:
        raise SourceError("Google returned an invalid sign-in response") from error
    if response.status_code != 200 or not isinstance(tokens, dict):
        raise SourceError("Google sign-in did not work. Check the OAuth client file and try again.")
    try:
        lifetime = float(tokens.get("expires_in", 0))
    except (TypeError, ValueError):
        lifetime = 0
    if not isinstance(tokens.get("refresh_token"), str) or not tokens["refresh_token"] or not isinstance(tokens.get("access_token"), str) or not 60 < lifetime < 366 * 86400:
        raise SourceError("Google did not give lasting access. Sign in again and allow Drive and Calendar access.")
    return credential.model_copy(update={"access_token": tokens["access_token"], "refresh_token": tokens["refresh_token"], "expires_at": time.time() + lifetime})


def google_read_error(response: httpx.Response, service: str, scope: str) -> None:
    """Distinguish missing consent from quota and disabled-API failures."""
    if response.status_code < 400:
        return
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error", {}) if isinstance(body, dict) else {}
    error = error if isinstance(error, dict) else {}
    groups = [error.get(group) for group in ("errors", "details") if isinstance(error.get(group), list)]
    reasons = {entry.get("reason") for group in groups for entry in group if isinstance(entry, dict) and isinstance(entry.get("reason"), str)}
    if response.status_code == 429 or reasons & {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded", "quotaExceeded", "RATE_LIMIT_EXCEEDED"}:
        raise SourceError(f"{service} quota reached. Try again later. Your sign-in is unchanged.")
    if reasons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
        raise SourceError(f"Google needs more access for {service}. Sign in again and allow it.")
    if response.status_code == 403:
        raise SourceError(f"{service} returned HTTP 403. Check your account access and that the {service} API is enabled.")
    raise SourceError(f"{service} returned HTTP {response.status_code}. Try again later.")


async def check_google(store: Store) -> str:
    """Verify Drive and Calendar access with the smallest reads."""
    if not google_connected():
        raise SignInRequired("Not signed in to Google yet. Use Sign in.")
    async with httpx.AsyncClient(auth=RefreshAuth(token_manager(), "google"), timeout=30) as client:
        response = await client.get(DRIVE_FILES, params={"pageSize": 1, "fields": "files(id)"})
        google_read_error(response, "Drive", "drive.readonly")
        response = await client.get(EVENTS_URL, params={"maxResults": 1, "fields": "items(id)"})
        google_read_error(response, "Calendar", "calendar.events.readonly")
    return "Connected to Google Drive and Calendar"


def google_connected() -> bool:
    return token_manager().configured("google") or bool(os.environ.get(ENV_TOKENS["google"]))


def require_google() -> None:
    """Sources that read Google stay neutral, not failed, until the account is connected."""
    if not google_connected():
        raise NotConnectedError("Not set up yet. Sign in to Google from the Google Calendar settings.")


async def connect_google(store: Store) -> str:
    """Open the browser consent flow and keep the resulting grant in the keyring for renewal.

    Google's desktop flow needs an OAuth client of your own; the browser step happens on this
    machine, which is where the dashboard runs.
    """
    client = find_client(store)
    if client is None:
        raise SourceError("Could not find your Google OAuth client file. Add its path in Settings or put it in your Downloads folder.")
    if not client.desktop:
        raise SourceError("That is a web OAuth client. Create a Desktop client in Google Cloud.")
    credential = await sign_in(Credential(client_id=client.client_id, client_secret=client.client_secret))
    await token_manager().enroll("google", credential)
    return await check_google(store)


async def disconnect_google(store: Store) -> str:
    await token_manager().forget("google")
    return "Signed out of Google"
