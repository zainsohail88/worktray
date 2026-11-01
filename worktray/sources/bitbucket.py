"""Workspace-wide Bitbucket review discovery with bounded concurrency."""

import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from worktray.config import Setting, single_name
from worktray.models import Batch, Item, https_only, idle_reasons, review_lane, within_work_window
from worktray.sources.connections import cli_json, cli_logged_in
from worktray.sources.errors import NotConnectedError, SourceError
from worktray.sources.teamcity import enrich_checks
from worktray.store import Store

BITBUCKET_WORKSPACE = Setting("bitbucket_workspace", "Bitbucket workspace", help="Every repository in it is checked. Leave blank to skip Bitbucket.", placeholder="acme", validate=single_name)
# bkt's --context picks one of its saved logins by the name given at bkt auth login, not a workspace.
BITBUCKET_CONTEXT = Setting(
    "bitbucket_context", "bkt context", help="Optional. The bkt login to use when you have more than one. Run bkt context list to see them. Leave blank for the bkt default.", validate=single_name
)
FIELDS = (BITBUCKET_WORKSPACE, BITBUCKET_CONTEXT)


def bkt_api(path: str, context: str) -> list[str]:
    """The bkt call for one API path, with the chosen login when there is one."""
    return ["bkt", "api", path, *(["--context", context] if context else []), "--json"]


async def _get(path: str, context: str) -> dict:
    if path.startswith("https://api.bitbucket.org/2.0/"):
        path = path.removeprefix("https://api.bitbucket.org/2.0")
    if not path.startswith("/") or path.startswith("//"):
        raise SourceError("Unexpected Bitbucket pagination URL")
    return await cli_json(bkt_api(path, context))


async def _pages(path: str, context: str) -> list[dict]:
    values = []
    seen = set()
    while path:
        if path in seen:
            raise SourceError("Bitbucket pagination repeated a page")
        seen.add(path)
        result = await _get(path, context)
        values.extend(result["values"])
        path = result.get("next", "")
    return values


def unanswered_comments(comments: list[dict], author_id: str) -> bool:
    """A reply closes only its own thread, never another reviewer's thread."""
    by_id = {comment["id"]: comment for comment in comments if not comment.get("deleted")}
    threads: dict[int, list[dict]] = {}
    for comment in by_id.values():
        root = comment
        visited = set()
        while root.get("parent", {}).get("id") in by_id and root["id"] not in visited:
            visited.add(root["id"])
            root = by_id[root["parent"]["id"]]
        threads.setdefault(root["id"], []).append(comment)
    return any(not by_id[root].get("resolution") and max(replies, key=lambda reply: reply["created_on"])["user"]["uuid"] != author_id for root, replies in threads.items())


FAILED_STATUSES = ("FAILED", "STOPPED")


def failing_status(statuses: list[dict]) -> tuple[str, str]:
    """Return the link and name of the first failed build status, or empty strings."""
    failed = next((status for status in statuses if status.get("state") in FAILED_STATUSES), None)
    if failed is None:
        return "", ""
    return https_only(failed.get("url") or ""), failed.get("name") or failed.get("key") or ""


def bitbucket_reasons(pr: dict, my_id: str, statuses: list[dict], comments: list[dict]) -> list[str]:
    """Distinguish requested reviews from an author's outstanding responses."""
    participants = pr.get("participants", [])
    me = next((participant for participant in participants if participant["user"]["uuid"] == my_id), {})
    requested = any(reviewer["uuid"] == my_id for reviewer in pr.get("reviewers", []))
    reviewed = me.get("approved") or me.get("state") in ("approved", "changes_requested")
    reasons = ["Review requested"] if requested and not reviewed else []
    if pr["author"]["uuid"] == my_id:
        if any(participant.get("state") == "changes_requested" for participant in participants):
            reasons.append("Changes requested")
        if any(status.get("state") in FAILED_STATUSES for status in statuses):
            reasons.append("Failing checks")
        approved = any(participant.get("approved") for participant in participants if participant["user"]["uuid"] != my_id)
        if approved and statuses and all(status.get("state") == "SUCCESSFUL" for status in statuses) and "Changes requested" not in reasons:
            reasons.append("Ready to merge")
        if unanswered_comments(comments, my_id):
            reasons.append("Review comments need a reply")
    return reasons


def _workspace(store: Store) -> str:
    workspace = BITBUCKET_WORKSPACE.read(store)
    if not workspace:
        raise NotConnectedError("Not set up yet. Add your Bitbucket workspace in Settings.")
    return workspace


async def check_bitbucket(store: Store) -> str:
    """The bkt CLI holds the login; confirm it and that the workspace answers."""
    workspace = _workspace(store)
    context = BITBUCKET_CONTEXT.read(store)
    if not await cli_logged_in("bkt"):
        raise SourceError("You are not signed in to bkt. Run bkt auth login in a terminal.")
    identity = await _get("/user", context)
    return f"Connected to Bitbucket as {identity.get('display_name') or identity.get('username') or 'you'}, workspace {workspace}"


async def read_bitbucket(store: Store) -> Batch:
    """Scan every repository in the configured workspace, because Bitbucket reviews have no feed."""
    workspace = _workspace(store)
    context = BITBUCKET_CONTEXT.read(store)
    identity = await _get("/user", context)
    my_id = identity["uuid"]
    repositories = await _pages(f"/repositories/{workspace}?pagelen=100&fields=next,values.full_name", context)
    semaphore = asyncio.Semaphore(5)
    stopped = asyncio.Event()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

    async def read_repo(repo: dict) -> list[Item]:
        async with semaphore:
            if stopped.is_set():
                raise SourceError("Scan stopped after a repository read failure")
            base = f"/repositories/{repo['full_name']}/pullrequests"
            query = urlencode({"pagelen": 50, "fields": "+values.reviewers,+values.participants", "q": f'state = "OPEN" AND created_on >= "{cutoff}"'})
            prs = await _pages(f"{base}?{query}", context)
            items = []
            for summary in prs:
                if summary.get("state") != "OPEN" or not within_work_window(summary.get("created_on")):
                    continue
                pr = summary if "reviewers" in summary and "participants" in summary else await _get(f"{base}/{summary['id']}", context)
                if pr.get("state") != "OPEN":
                    continue
                own = pr["author"]["uuid"] == my_id
                statuses = await _pages(f"{base}/{pr['id']}/statuses?pagelen=100", context) if own else []
                comments = await _pages(f"{base}/{pr['id']}/comments?pagelen=100", context) if own and pr.get("comment_count") else []
                reasons = bitbucket_reasons(pr, my_id, statuses, comments) or (idle_reasons(bool(pr.get("draft"))) if own else [])
                checks_url, checks_detail = failing_status(statuses)
                url = pr["links"]["html"]["href"]
                items.append(
                    Item(
                        key=url,
                        source="bitbucket",
                        title=pr["title"][:240],
                        url=url,
                        status="open",
                        live=True,
                        opened_at=pr["created_on"],
                        updated_at=pr.get("updated_on"),
                        owner=pr["author"]["display_name"],
                        owner_id=pr["author"].get("account_id") or f"bitbucket:{pr['author']['uuid']}",
                        project=repo["full_name"],
                        source_status="Open",
                        reason=", ".join(reasons),
                        personal=bool(reasons),
                        lane=review_lane(reasons),
                        checks_url=checks_url,
                        checks_detail=checks_detail[:240],
                    )
                )
            return items

    async def guarded_read(repo: dict) -> list[Item]:
        try:
            return await read_repo(repo)
        except (SourceError, TimeoutError):
            stopped.set()
            raise

    tasks = [asyncio.create_task(guarded_read(repo)) for repo in repositories]
    try:
        results = await asyncio.gather(*tasks)
    except (SourceError, TimeoutError) as error:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        detail = str(error) if isinstance(error, SourceError) else "A repository read timed out"
        raise SourceError(f"Bitbucket sync stopped partway. {detail} If Bitbucket is rate limiting you, try again later.") from error
    return Batch(
        items=await enrich_checks(store, [item for result in results for item in result]), detail=f"Checked {len(repositories)} repositories in {workspace} for pull requests from the last 90 days"
    )
