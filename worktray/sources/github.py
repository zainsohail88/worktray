"""Read pull request attention signals through the existing GitHub CLI login."""

import json
from datetime import datetime, timedelta, timezone

from worktray.config import Setting, name_list, team_slug
from worktray.models import Batch, Item, https_only, idle_reasons, review_lane, within_work_window
from worktray.sources.connections import cli_json, cli_logged_in
from worktray.sources.errors import NotConnectedError, SourceError
from worktray.sources.teamcity import enrich_checks
from worktray.store import Store

GITHUB_ORGS = Setting("github_orgs", "GitHub organisations", help="Separate with commas. Leave blank to include every repository you can see.", placeholder="acme, acme-labs", validate=name_list)
GITHUB_TEAM = Setting("github_team", "GitHub team", help="As org/team-slug, for the Team view. Leave blank to skip.", placeholder="acme/platform", validate=team_slug)
FIELDS = (GITHUB_ORGS,)
TEAM_FIELDS = (GITHUB_TEAM,)

QUERY_FIELDS = """
  id title url createdAt updatedAt isDraft author { login } repository { nameWithOwner }
  reviewDecision statusCheckRollup { state contexts(first:50) { nodes { __typename
    ...on StatusContext { context state targetUrl }
    ...on CheckRun { name conclusion detailsUrl } } } }
  reviewThreads(first:100) { pageInfo { hasNextPage endCursor }
    nodes { isResolved comments(last:1) { nodes { author { login } } } } }
"""


FAILED_CHECK_RUNS = ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")
FAILED_STATUSES = ("FAILURE", "ERROR")


def failing_check(pr: dict) -> tuple[str, str]:
    """Return the link and name of the first failed check, or empty strings."""
    for context in ((pr.get("statusCheckRollup") or {}).get("contexts") or {}).get("nodes", []):
        if context["__typename"] == "CheckRun" and context["conclusion"] in FAILED_CHECK_RUNS:
            return https_only(context["detailsUrl"] or ""), context["name"]
        if context["__typename"] == "StatusContext" and context["state"] in FAILED_STATUSES:
            return https_only(context["targetUrl"] or ""), context["context"]
    return "", ""


def github_reasons(pr: dict, own: bool, requested: bool) -> list[str]:
    """Only unresolved comments whose last author is someone else need reply."""
    reasons = ["Review requested"] if requested else []
    if own:
        rollup = (pr.get("statusCheckRollup") or {}).get("state")
        if pr.get("reviewDecision") == "CHANGES_REQUESTED":
            reasons.append("Changes requested")
        if rollup in FAILED_STATUSES:
            reasons.append("Failing checks")
        if pr.get("reviewDecision") == "APPROVED" and rollup == "SUCCESS":
            reasons.append("Ready to merge")
        if any(
            not thread["isResolved"] and thread["comments"]["nodes"] and (thread["comments"]["nodes"][-1].get("author") or {}).get("login") != pr["author"]["login"]
            for thread in pr["reviewThreads"]["nodes"]
        ):
            reasons.append("Review comments need a reply")
    return reasons


def search_scope(organisations: list[str], cutoff: str) -> str:
    """Open pull requests since the cutoff, limited to the chosen organisations; none means everything the login can see."""
    qualifiers = ["is:pr", "is:open", *(f"org:{organisation}" for organisation in organisations), f"created:>={cutoff}"]
    return " ".join(qualifiers)


def _where(organisations: list[str]) -> str:
    return ", ".join(organisations) if organisations else "every repository you can see"


async def _query(query: str, **variables: object) -> dict:
    return await cli_json(["gh", "api", "graphql", "--input", "-"], json.dumps({"query": query, "variables": variables}))


async def _search(search: str) -> list[dict]:
    query = "query($search:String!,$cursor:String){search(query:$search,type:ISSUE,first:50,after:$cursor){issueCount pageInfo{hasNextPage endCursor} nodes{...on PullRequest{" + QUERY_FIELDS + "}}}}"
    cursor = None
    found = []
    while True:
        result = (await _query(query, search=search, cursor=cursor))["data"]["search"]
        if result["issueCount"] > 1000:
            raise SourceError("GitHub found more than 1,000 pull requests. Pick fewer organisations in Settings.")
        found.extend(result["nodes"])
        if not result["pageInfo"]["hasNextPage"]:
            break
        cursor = result["pageInfo"]["endCursor"]
    for pr in found:
        connection = pr["reviewThreads"]
        while connection["pageInfo"]["hasNextPage"]:
            query = "query($id:ID!,$cursor:String){node(id:$id){...on PullRequest{reviewThreads(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{isResolved comments(last:1){nodes{author{login}}}}}}}}"
            connection = (await _query(query, id=pr["id"], cursor=connection["pageInfo"]["endCursor"]))["data"]["node"]["reviewThreads"]
            pr["reviewThreads"]["nodes"].extend(connection["nodes"])
    return found


async def check_github(store: Store) -> str:
    """The gh CLI holds the login; this only confirms it works."""
    if not await cli_logged_in("gh"):
        raise SourceError("You are not signed in to gh. Run gh auth login in a terminal.")
    identity = await cli_json(["gh", "api", "user"])
    return f"Connected to GitHub as {identity['login']}"


async def read_github(store: Store) -> Batch:
    """Pull requests that wait on you or that you authored, through the gh CLI's own login."""
    identity = await cli_json(["gh", "api", "user"])
    login = identity["login"]
    organisations = GITHUB_ORGS.items(store)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
    scope = search_scope(organisations, cutoff)
    requested = await _search(f"{scope} review-requested:{login}")
    authored = await _search(f"{scope} author:{login}")
    requested_ids = {pr["id"] for pr in requested}
    items = []
    for pr in {pr["id"]: pr for pr in [*requested, *authored]}.values():
        if not within_work_window(pr["createdAt"]):
            continue
        own = pr["author"]["login"] == login
        reasons = github_reasons(pr, own, pr["id"] in requested_ids) or (idle_reasons(pr["isDraft"]) if own else [])
        if reasons:
            checks_url, checks_detail = failing_check(pr)
            items.append(
                Item(
                    key=pr["url"],
                    source="github",
                    title=pr["title"][:240],
                    url=pr["url"],
                    status="open",
                    live=True,
                    opened_at=pr["createdAt"],
                    owner=pr["author"]["login"],
                    updated_at=pr.get("updatedAt"),
                    owner_id=f"github:{pr['author']['login']}",
                    reason=", ".join(reasons),
                    source_status="Open",
                    project=pr["repository"]["nameWithOwner"],
                    lane=review_lane(reasons),
                    checks_url=checks_url,
                    checks_detail=checks_detail[:240],
                )
            )
    return Batch(items=await enrich_checks(store, items), detail=f"Your reviews and pull requests from the last 90 days, in {_where(organisations)}")


async def read_github_team(store: Store) -> Batch:
    """Open pull requests of the configured GitHub team's verified members."""
    team = GITHUB_TEAM.read(store)
    if "/" not in team:
        raise NotConnectedError("Not set up yet. Add a GitHub team, as org/team-slug, in Settings.")
    organisation, slug = team.split("/", 1)
    pages = await cli_json(["gh", "api", f"orgs/{organisation}/teams/{slug}/members?per_page=100", "--paginate", "--slurp"])
    members = {member["login"] for page in pages for member in page}
    identity = await cli_json(["gh", "api", "user"])
    # Without an explicit organisation list, a teammate's open-source pull requests would count as team work.
    organisations = GITHUB_ORGS.items(store) or [organisation]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
    scope = search_scope(organisations, cutoff)
    items = []
    for login in sorted(members):
        profile = await cli_json(["gh", "api", f"users/{login}"])
        owner_id = store.setting("jira_account_id") if login == identity["login"] else ""
        for pr in await _search(f"{scope} author:{login}"):
            if not within_work_window(pr["createdAt"]):
                continue
            items.append(
                Item(
                    key=pr["url"],
                    source="github",
                    title=pr["title"][:240],
                    url=pr["url"],
                    status="open",
                    live=True,
                    opened_at=pr["createdAt"],
                    updated_at=pr.get("updatedAt"),
                    owner=profile.get("name") or login,
                    owner_id=owner_id or f"github:{login}",
                    owner_email=profile.get("email") or "",
                    personal=False,
                    team_member=True,
                    source_status="Open",
                    project=pr["repository"]["nameWithOwner"],
                    reason=", ".join(github_reasons(pr, own=True, requested=False)) or "Open team PR",
                )
            )
    return Batch(items=items, detail=f"{len(members)} people in {team}. Open pull requests from the last 90 days, in {_where(organisations)}")
