"""Turn a failing TeamCity check on a pull request into the build's own status text."""

import asyncio
import logging
import re
from urllib.parse import urlsplit

import httpx

from worktray.config import Secret, Setting, source_enabled, web_url
from worktray.models import Batch, Item
from worktray.sources.errors import NotConnectedError, SourceError
from worktray.store import Store

TEAMCITY_URL = Setting("teamcity_url", "TeamCity URL", placeholder="https://ci.example.com", validate=web_url)
TEAMCITY_TOKEN = Secret("teamcity_token", "TeamCity access token", help="In TeamCity, open your profile and create an access token. Read access is enough.")
FIELDS = (TEAMCITY_URL,)
SECRETS = (TEAMCITY_TOKEN,)
BUILD_ID = re.compile(r"/buildConfiguration/[^/]+/(\d+)|[?&]buildId=(\d+)")
CONCURRENCY = 5

logger = logging.getLogger(__name__)


def teamcity_config(store: Store) -> dict[str, str]:
    """URL and token; empty values mean not connected. The token is read only once a URL is set.

    This can block on the keyring, so async code calls it through asyncio.to_thread.
    """
    url = TEAMCITY_URL.read(store).rstrip("/")
    return {"TEAMCITY_URL": url, "TEAMCITY_TOKEN": TEAMCITY_TOKEN.read() if url else ""}


def _client(config: dict[str, str], transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {config['TEAMCITY_TOKEN']}", "Accept": "application/json"}
    return httpx.AsyncClient(base_url=config["TEAMCITY_URL"], headers=headers, timeout=20, transport=transport)


async def read_teamcity(store: Store, transport: httpx.AsyncBaseTransport | None = None) -> Batch:
    """Report whether the TeamCity login works; it adds build detail to PR checks and has no items of its own."""
    return Batch(detail=await check_teamcity(store, transport) + " Failed checks on your pull requests now show why.")


async def check_teamcity(store: Store, transport: httpx.AsyncBaseTransport | None = None) -> str:
    config = await asyncio.to_thread(teamcity_config, store)
    if not all(config.values()):
        raise NotConnectedError("Not set up. Add your TeamCity URL and token in Settings to see why builds failed.")
    async with _client(config, transport) as client:
        response = await client.get("/app/rest/server", params={"fields": "version"})
    if response.status_code in (401, 403):
        raise SourceError("TeamCity didn't accept the access token. Replace it in Settings.")
    if response.status_code >= 400:
        raise SourceError(f"TeamCity answered with HTTP {response.status_code}. Check the URL and that the server is reachable.")
    return f"Connected to {urlsplit(config['TEAMCITY_URL']).netloc}, TeamCity {response.json().get('version', 'unknown version')}."


def build_id(url: str, base_url: str) -> str | None:
    """Return the TeamCity build number in a check link, or None for any other host."""
    if urlsplit(url).netloc != urlsplit(base_url).netloc:
        return None
    match = BUILD_ID.search(url)
    return (match.group(1) or match.group(2)) if match else None


async def enrich_checks(store: Store, items: list[Item], transport: httpx.AsyncBaseTransport | None = None) -> list[Item]:
    """Describe failing TeamCity checks; when TeamCity is off, not set up, or a lookup fails, the check name stays."""
    if not source_enabled(store, "teamcity"):
        return items
    try:
        config = await asyncio.to_thread(teamcity_config, store)
    except (SourceError, ValueError) as error:
        logger.warning("TeamCity credentials unreadable; keeping check names: %s", error)
        return items
    if not all(config.values()):
        return items
    limit = asyncio.Semaphore(CONCURRENCY)

    async def describe(client: httpx.AsyncClient, item: Item) -> Item:
        build = build_id(item.checks_url, config["TEAMCITY_URL"]) if item.checks_url else None
        if build is None:
            return item
        try:
            async with limit:
                response = await client.get(f"/app/rest/builds/id:{build}", params={"fields": "statusText,buildType(name)"})
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("TeamCity build %s lookup failed: %s", build, error)
            return item
        status = body.get("statusText", "")
        name = body.get("buildType", {}).get("name", "")
        return item.model_copy(update={"checks_detail": f"{name}: {status}"[:240] if name and status else item.checks_detail})

    async with _client(config, transport) as client:
        return list(await asyncio.gather(*(describe(client, item) for item in items)))
