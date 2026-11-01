"""Keep an MCP server's sign-in in the system keyring, next to worktray's other tokens.

fastmcp saves the OAuth grant through any object with the `AsyncKeyValue` methods (get, put,
delete and their bulk and TTL forms). This one writes each entry to the same keyring as every
other secret (`secret_store()`), from a worker thread so a slow keyring never holds up the server.
It uses only that public interface and plain JSON, so it doesn't depend on the storage library's
internals. Only the Public Slack source uses it, through the optional `mcp` extra.

fastmcp records when the access token expires and refreshes it once that time has passed.
`refresh_due` refreshes it a little earlier, so it never expires between the check and the request.
"""

import asyncio
from collections.abc import Mapping, Sequence
import hashlib
import json
import time
from typing import Any, SupportsFloat

from worktray.auth.keyring_store import secret_store

DEFAULT_COLLECTION = "default"
REFRESH_MARGIN = 60


def _name(collection: str, key: str) -> str:
    return "mcp:" + hashlib.sha256(f"{collection}\0{key}".encode()).hexdigest()[:32]


def refresh_due(expires_at: float | None, at: float | None = None) -> bool:
    """Whether a token with this expiry time should be refreshed before it is used."""
    return expires_at is not None and expires_at - (time.time() if at is None else at) <= REFRESH_MARGIN


class KeyringTokens:
    """fastmcp's token storage, backed by worktray's keyring.

    Entries can't be listed, because a keyring can only be asked for a name it already knows,
    so `keys` and `collections` are always empty. fastmcp only reads, writes and deletes by name.
    """

    def __init__(self, default_collection: str = DEFAULT_COLLECTION) -> None:
        self.default_collection = default_collection

    def _entry(self, key: str, collection: str | None) -> str:
        return _name(collection or self.default_collection, key)

    async def ttl(self, key: str, *, collection: str | None = None) -> tuple[dict[str, Any] | None, float | None]:
        raw = await asyncio.to_thread(secret_store().read, self._entry(key, collection))
        try:
            record = json.loads(raw) if raw else None
            value, expires_at = record["value"], record.get("expires_at")
        except (ValueError, KeyError, TypeError):
            return None, None
        if expires_at is not None and expires_at <= time.time():
            return None, None
        return (value if isinstance(value, dict) else None), (None if expires_at is None else expires_at - time.time())

    async def get(self, key: str, *, collection: str | None = None) -> dict[str, Any] | None:
        return (await self.ttl(key, collection=collection))[0]

    async def put(self, key: str, value: Mapping[str, Any], *, collection: str | None = None, ttl: SupportsFloat | None = None) -> None:
        record = {"value": dict(value), "expires_at": None if ttl is None else time.time() + float(ttl)}
        await asyncio.to_thread(secret_store().write, self._entry(key, collection), json.dumps(record))

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        name = self._entry(key, collection)
        existed = bool(await asyncio.to_thread(secret_store().read, name))
        await asyncio.to_thread(secret_store().clear, name)
        return existed

    async def get_many(self, keys: Sequence[str], *, collection: str | None = None) -> list[dict[str, Any] | None]:
        return [await self.get(key, collection=collection) for key in keys]

    async def ttl_many(self, keys: Sequence[str], *, collection: str | None = None) -> list[tuple[dict[str, Any] | None, float | None]]:
        return [await self.ttl(key, collection=collection) for key in keys]

    async def put_many(self, keys: Sequence[str], values: Sequence[Mapping[str, Any]], *, collection: str | None = None, ttl: SupportsFloat | None = None) -> None:
        for key, value in zip(keys, values, strict=True):
            await self.put(key, value, collection=collection, ttl=ttl)

    async def delete_many(self, keys: Sequence[str], *, collection: str | None = None) -> int:
        return sum([await self.delete(key, collection=collection) for key in keys])

    async def cull(self) -> None:
        """Expired entries are skipped when read, so there is nothing to sweep."""

    async def keys(self, collection: str | None = None, *, limit: int | None = None) -> list[str]:
        return []

    async def collections(self, *, limit: int | None = None) -> list[str]:
        return []

    async def destroy(self) -> bool:
        return False

    async def destroy_collection(self, collection: str) -> bool:
        return False
