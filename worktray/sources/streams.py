"""Read Slack and meeting streams with transient bodies and local extraction."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import re
from urllib.parse import urlsplit

import httpx

from worktray.auth.google_login import DRIVE_FILES, require_google
from worktray.auth.oauth import RefreshAuth, token_manager
from worktray.config import Setting
from worktray.models import Batch, Item, now
from worktray.sources.atlassian import atlassian_config, jira_ready
from worktray.sources.codex_slack import read_slack_via_codex
from worktray.sources.connections import get_json
from worktray.sources.errors import NotConnectedError, SourceError
from worktray.sources.extract import meeting_items, meeting_name
from worktray.sources.sessions import short_title
from worktray.store import Store


MEETING_FOLDER = Setting(
    "meeting_folder",
    "Meeting notes folder",
    help="The Google Drive folder, or its link. Subfolders are included too.",
    placeholder="https://drive.google.com/drive/folders/…",
    validate=lambda value: _folder(value),
)
MEETING_ALIASES = Setting(
    "meeting_aliases",
    "Your name in meeting notes",
    help="The names or emails your action items use, separated by commas.",
    placeholder="Alex Example, alex@example.com",
    validate=lambda value: ", ".join(dict.fromkeys(part.strip() for part in value.split(",") if part.strip())),
)
FIELDS = (MEETING_FOLDER, MEETING_ALIASES)
DOCUMENT = "application/vnd.google-apps.document"
FOLDER = "application/vnd.google-apps.folder"
MEETING_BACKFILLED_SETTING = "google_meeting_backfilled_at"
BACKFILL_DAYS = 90
SYNC_DAYS = 7
EXPORT_CONCURRENCY = 8
EXPORT_TIMEOUT = 90

logger = logging.getLogger(__name__)


def drive_folder_id(value: str) -> str:
    """Accept a Drive folder ID or URL without retaining the full URL."""
    value = value.strip()
    if not value:
        return ""
    path = urlsplit(value).path.rstrip("/")
    if "/folders/" in path:
        value = path.rsplit("/folders/", 1)[-1].split("/", 1)[0]
    if not value or not all(character.isalnum() or character in "_-" for character in value):
        raise SourceError("Use a Google Drive folder link or folder ID.")
    return value


def _folder(value: str) -> str:
    try:
        return drive_folder_id(value)
    except SourceError as error:
        raise ValueError(str(error)) from error


async def read_slack(store: Store) -> Batch:
    """Collect private Slack items through a Slack-connected Codex agent."""
    return await read_slack_via_codex(store)


async def _drive_files(client: httpx.AsyncClient, query: str) -> list[dict]:
    files = []
    page_token = ""
    while True:
        data = await get_json(client, DRIVE_FILES, params={"q": query, "pageSize": 100, "pageToken": page_token, "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType,createdTime)"})
        if data.get("incompleteSearch"):
            raise SourceError("Google Drive returned incomplete results. Try again later.")
        files.extend(data.get("files", []))
        next_token = data.get("nextPageToken", "")
        if not next_token:
            return files
        if next_token == page_token:
            raise SourceError("Google Drive's results stopped paging. Try again later.")
        page_token = next_token


async def _meeting_documents(client: httpx.AsyncClient, folder_id: str, cutoff: str) -> list[dict]:
    shared = await _drive_files(client, f"name contains 'Notes by Gemini' and mimeType = '{DOCUMENT}' and trashed = false and modifiedTime >= '{cutoff}'")
    documents = {document["id"]: document for document in shared}
    folders = [folder_id]
    visited = set()
    while folders:
        folder = folders.pop()
        if folder in visited:
            continue
        visited.add(folder)
        for document in await _drive_files(client, f"'{folder}' in parents and trashed = false and (mimeType = '{FOLDER}' or modifiedTime >= '{cutoff}')"):
            if document["mimeType"] == FOLDER:
                folders.append(document["id"])
            elif document["mimeType"] == DOCUMENT:
                documents[document["id"]] = document
    return list(documents.values())


async def read_gemini(store: Store) -> Batch:
    """Read your meeting folder plus Gemini notes shared with you; discard full text afterward.

    Notes for meetings someone else organized belong to that organizer and never enter
    your folder, so they are found by Gemini's "Notes by Gemini" title suffix instead.
    The first sync reaches back BACKFILL_DAYS once, even if some exports fail; later ones SYNC_DAYS.
    """
    folder_id = drive_folder_id(MEETING_FOLDER.read(store))
    aliases = MEETING_ALIASES.items(store)
    if not folder_id or not aliases:
        raise NotConnectedError("Not set up yet. Add your meeting notes folder and your name in Settings.")
    require_google()
    days = SYNC_DAYS if store.setting(MEETING_BACKFILLED_SETTING) else BACKFILL_DAYS
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient(auth=RefreshAuth(token_manager(), "google"), timeout=30) as client:
        documents = await _meeting_documents(client, folder_id, cutoff)
        # Shared notes number in the hundreds, and full transcripts make single exports slow.
        limit = asyncio.Semaphore(EXPORT_CONCURRENCY)

        async def export(document: dict) -> list[Item] | None:
            try:
                async with limit:
                    response = await client.get(f"{DRIVE_FILES}/{document['id']}/export", params={"mimeType": "text/plain"}, timeout=EXPORT_TIMEOUT)
            except httpx.HTTPError as error:
                logger.warning("Drive export of %s failed: %s", document["id"], error)
                return None
            if response.status_code != 200:
                logger.warning("Drive export of %s returned HTTP %s", document["id"], response.status_code)
                return None
            return meeting_items(document["id"], response.text, aliases, document["createdTime"], meeting_name(document.get("name", "")))

        exported = await asyncio.gather(*map(export, documents))
    # A failed export must not count as read, or reconcile would delete its proposals.
    read = {document["id"] for document, found in zip(documents, exported, strict=True) if found is not None}
    items = [item for found in exported if found for item in found]
    store.reconcile_meeting_proposals(read, items)
    store.save_setting(MEETING_BACKFILLED_SETTING, store.setting(MEETING_BACKFILLED_SETTING) or now())
    failed = len(documents) - len(read)
    detail = f"Read {len(read)} meeting notes from the last {days} days and found {len(items)} action items for you"
    return Batch(items=items, detail=f"{detail}. {failed} couldn't be read" if failed else detail)


async def read_confluence(store: Store) -> Batch:
    """Propose recently modified pages or comments mentioning the account."""
    config = await asyncio.to_thread(atlassian_config, store)
    base = config["CONFLUENCE_URL"]
    if not jira_ready(config):
        raise NotConnectedError("Not set up yet. Confluence uses your Jira sign-in, so set up Jira in Settings first.")
    async with httpx.AsyncClient(auth=(config["CONFLUENCE_USERNAME"], config["CONFLUENCE_API_TOKEN"]), timeout=30) as client:
        identity = await client.get(f"{base}/rest/api/user/current")
        if identity.status_code != 200:
            raise SourceError(f"Confluence didn't accept the sign-in (HTTP {identity.status_code}).")
        # Confluence names you itself, so this works without syncing Jira first.
        account_id = identity.json().get("accountId", "") or store.setting("jira_account_id")
        if not re.fullmatch(r"[\w:-]+", account_id or ""):
            raise SourceError("Confluence didn't say which account you are. Check the email in the Jira settings.")
        query = f'mention = "{account_id}" AND lastmodified >= now("-100d")'
        start = 0
        items = []
        while True:
            result = await get_json(client, f"{base}/rest/api/content/search", params={"cql": query, "start": start, "limit": 100, "expand": "history"})
            for content in result.get("results", []):
                url = content.get("_links", {}).get("webui", "")
                if url:
                    items.append(
                        Item(
                            key=f"confluence:{content['id']}",
                            source="confluence",
                            title=short_title(content.get("title") or "Check your Confluence mention"),
                            url=f"{base}{url}",
                            opened_at=content.get("history", {}).get("createdDate", now()),
                            reason="Mentioned you",
                            list_name="Follow-ups",
                        )
                    )
            if not result.get("_links", {}).get("next"):
                break
            start += len(result["results"])
    return Batch(items=items, detail="Recent pages and comments that mention you")
