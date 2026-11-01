"""The one Atlassian login that Jira, Confluence and the on-call tab share."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from worktray.config import Secret, Setting, web_url
from worktray.sources.connections import get_json
from worktray.sources.errors import NotConnectedError
from worktray.store import Store

JIRA_URL = Setting("jira_url", "Jira site URL", placeholder="https://your-team.atlassian.net", help="Confluence is read from the same site.", validate=web_url)
JIRA_EMAIL = Setting("jira_email", "Your Atlassian email")
JIRA_API_TOKEN = Secret("jira_api_token", "Atlassian API token", help="Create one at id.atlassian.com under Security, API tokens.")
FIELDS = (JIRA_URL, JIRA_EMAIL)
SECRETS = (JIRA_API_TOKEN,)
NOT_CONFIGURED = "Not set up yet. Add your Jira site URL, email and API token in Settings."


def atlassian_config(store: Store) -> dict[str, str]:
    """Site, email and token for Jira, and the same for Confluence under /wiki.

    The keyring is asked for the token only once a site is set, so a machine without a keyring
    shows Jira as not set up rather than as failing. This can block on the keyring, so async code
    calls it through asyncio.to_thread.
    """
    site = JIRA_URL.read(store).rstrip("/")
    email = JIRA_EMAIL.read(store)
    token = JIRA_API_TOKEN.read() if site else ""
    return {
        "JIRA_URL": site,
        "JIRA_USERNAME": email,
        "JIRA_API_TOKEN": token,
        "CONFLUENCE_URL": f"{site}/wiki" if site else "",
        "CONFLUENCE_USERNAME": email,
        "CONFLUENCE_API_TOKEN": token,
    }


def jira_ready(config: dict[str, str]) -> bool:
    return all(config.get(key) for key in ("JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"))


@asynccontextmanager
async def jira_client(store: Store) -> AsyncIterator[httpx.AsyncClient]:
    """An authenticated client for the Jira site, or NotConnectedError that says what to set."""
    config = await asyncio.to_thread(atlassian_config, store)
    if not jira_ready(config):
        raise NotConnectedError(NOT_CONFIGURED)
    async with httpx.AsyncClient(base_url=config["JIRA_URL"], auth=(config["JIRA_USERNAME"], config["JIRA_API_TOKEN"]), timeout=30) as client:
        yield client


async def check_jira(store: Store) -> str:
    """Confirm the login with the smallest read Jira offers."""
    async with jira_client(store) as client:
        me = await get_json(client, "/rest/api/3/myself")
    return f"Connected to Jira as {me.get('displayName') or me.get('emailAddress') or 'you'}"
