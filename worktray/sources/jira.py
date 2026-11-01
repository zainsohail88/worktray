"""Live Jira work and a visibly scoped team backlog."""

from collections import Counter

import httpx

from worktray.models import Batch, Item, Lane, within_work_window
from worktray.sources.atlassian import jira_client
from worktray.sources.connections import get_json
from worktray.sources.errors import SourceError
from worktray.store import Store


ISSUE_FIELDS = "summary,status,assignee,created,updated,project,priority,parent,issuetype,duedate"


async def search_issues(client: httpx.AsyncClient, query: str, fields: str = ISSUE_FIELDS) -> list[dict]:
    """Follow Jira search pages to the end, failing rather than returning a partial list."""
    issues = []
    token = None
    for _ in range(100):
        params = {"jql": query, "maxResults": 100, "fields": fields}
        if token:
            params["nextPageToken"] = token
        page = await get_json(client, "/rest/api/3/search/jql", params=params)
        issues.extend(page.get("issues", []))
        next_token = page.get("nextPageToken")
        if page.get("isLast", not next_token):
            return issues
        if not next_token or next_token == token:
            raise SourceError("Jira's results stopped paging. Showing the last results.")
        token = next_token
    raise SourceError("The team scope matches more than 10,000 tickets. Narrow it on the Team page.")


HANDED_OFF_STATUSES = frozenset({"in review", "code review", "qa", "blocked", "waiting"})


def jira_item(issue: dict, base_url: str, my_id: str, reported: bool = False) -> Item:
    """Use Jira's status category and account ID, not a status-name guess.

    Tickets assigned to someone else that I reported stay with that assignee, so they wait.
    """
    fields = issue["fields"]
    owner = fields.get("assignee") or {}
    mine = owner.get("accountId") == my_id
    lane: Lane = ""
    if mine:
        lane = "waiting" if fields["status"]["name"].casefold() in HANDED_OFF_STATUSES else "needs_me"
    elif reported:
        lane = "waiting"
    return Item(
        key=f"jira:{issue['key']}",
        source="jira",
        title=fields["summary"][:240],
        url=f"{base_url}/browse/{issue['key']}",
        status="open",
        live=True,
        opened_at=fields["created"],
        owner=owner.get("displayName", "Unassigned"),
        updated_at=fields.get("updated"),
        owner_active=owner.get("active"),
        owner_id=owner.get("accountId", "unassigned"),
        personal=mine or reported,
        lane=lane,
        owner_email=owner.get("emailAddress", ""),
        source_status=fields["status"]["name"],
        source_category=fields["status"]["statusCategory"]["key"],
        project=fields["project"]["key"],
        reason=(fields.get("priority") or {}).get("name", ""),
        list_name=(fields.get("parent") or {}).get("key", ""),
        issue_type=(fields.get("issuetype") or {}).get("name", ""),
        due_date=fields.get("duedate"),
        parent_title=((fields.get("parent") or {}).get("fields") or {}).get("summary", "")[:240],
    )


async def read_jira(store: Store) -> Batch:
    """Fetch all personal work and infer an editable initial team scope."""
    async with jira_client(store) as client:
        base_url = str(client.base_url).rstrip("/")
        identity = await get_json(client, "/rest/api/3/myself")
        personal = await search_issues(client, "assignee = currentUser() AND statusCategory != Done ORDER BY created ASC")
        # Jira's != never matches an empty field, so unassigned tickets need their own clause.
        reported = await search_issues(client, "reporter = currentUser() AND (assignee != currentUser() OR assignee is EMPTY) AND statusCategory != Done ORDER BY created ASC")
        scope = store.setting("team_jql")
        if not scope:
            projects = Counter(issue["fields"]["project"]["key"] for issue in personal)
            if projects:
                project = projects.most_common(1)[0][0]
                scope = f'project = "{project}" AND statusCategory != Done'
                store.save_setting("team_jql", scope)
                store.save_setting("team_scope_origin", "Guessed from the project most of your tickets are in. Change it to match your team.")
        team = await search_issues(client, scope) if scope else []
    team_keys = {issue["key"] for issue in team}
    reported_keys = {issue["key"] for issue in reported}
    all_issues = {issue["key"]: issue for issue in [*personal, *reported, *team]}
    items = [jira_item(issue, base_url, identity["accountId"], issue["key"] in reported_keys) for issue in all_issues.values() if issue["fields"]["status"]["statusCategory"]["key"] != "done"]
    for item in items:
        item.team_member = item.key.removeprefix("jira:") in team_keys and item.owner_id != "unassigned" and item.owner_active is not False and within_work_window(item.updated_at)
    store.save_setting("jira_account_id", identity["accountId"])
    store.save_setting("display_name", identity["displayName"])
    return Batch(
        items=items,
        detail=f"{len(personal)} assigned to you, {len(reported)} you reported for someone else, {sum(item.team_member for item in items)} team tickets updated in the last 90 days. Team scope: {scope or 'not set yet'}",
    )
