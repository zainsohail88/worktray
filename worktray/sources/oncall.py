"""The current on-call epic and the shift that turns it into the week's work.

Many teams keep operational work under one open Jira epic per quarter, often named KTLO
("keep the lights on"). The word to look for is a setting, so any naming convention works.
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

import httpx
from pydantic import BaseModel

from worktray.config import Setting, plain_text
from worktray.models import Batch, Item
from worktray.sources.atlassian import jira_client
from worktray.sources.connections import get_json
from worktray.sources.errors import SourceError
from worktray.sources.jira import ISSUE_FIELDS, jira_item, search_issues
from worktray.store import Store

ONCALL_EPIC = Setting(
    "oncall_epic_name",
    "On-call epic name",
    default="KTLO",
    help="worktray uses the newest open epic whose name contains this, in the project where most of your tickets are. Many teams call it KTLO.",
    validate=plain_text,
)
FIELDS = (ONCALL_EPIC,)
ON_CALL_SETTING = "on_call_shift"
ONCALL_EPIC_SETTING = "oncall_current_epic"
OPS_API = "https://api.atlassian.com/jsm/ops/api/{cloud_id}/v1"
ONCALL_FIELDS = f"{ISSUE_FIELDS},statuscategorychangedate"
URGENT_PRIORITIES = frozenset({"blocker", "critical", "highest", "high"})
STUCK_DAYS = 5
NEW_DAYS = 7
TIMELINE_WEEKS = 3
SCHEDULE_PAGE = 50


class OnCallEpic(BaseModel):
    """The open epic the On call tab lists children of."""

    key: str
    title: str
    url: str


class OnCallShift(BaseModel):
    """The shift in progress, or the next one, merged across back-to-back timeline periods."""

    schedule: str
    starts_at: str
    ends_at: str
    current: bool


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def attention(issue: dict, my_id: str, at: datetime) -> list[str]:
    """Signals an on-call engineer acts on: own work in flight, stuck work, overdue work and urgent work nobody owns."""
    fields = issue["fields"]
    owner = (fields.get("assignee") or {}).get("accountId")
    in_flight = fields["status"]["statusCategory"]["key"] == "indeterminate"
    priority = (fields.get("priority") or {}).get("name", "")
    reasons = []
    if in_flight and owner == my_id:
        reasons.append("Yours in flight")
    changed = fields.get("statuscategorychangedate")
    if in_flight and changed and (at - _instant(changed)).days >= STUCK_DAYS:
        reasons.append(f"{fields['status']['name']} {(at - _instant(changed)).days} days")
    if fields.get("duedate") and date.fromisoformat(fields["duedate"]) < at.date():
        reasons.append("Overdue")
    if not owner and priority.casefold() in URGENT_PRIORITIES:
        reasons.append(f"{priority}, unassigned")
    elif not owner and at - _instant(fields["created"]) <= timedelta(days=NEW_DAYS):
        reasons.append("New, unassigned")
    return reasons


def oncall_item(issue: dict, base_url: str, my_id: str, at: datetime) -> Item:
    """Keep on-call rows apart from personal Jira rows so the same ticket can sit in both views."""
    item = jira_item(issue, base_url, my_id)
    reasons = attention(issue, my_id, at)
    return item.model_copy(
        update={
            "key": f"oncall:{issue['key']}",
            "source": "oncall",
            "personal": False,
            "team_member": False,
            "attention": reasons,
            "lane": "needs_me" if reasons else "",
        }
    )


def current_shift(timeline: dict, schedule: str, my_id: str, at: datetime) -> OnCallShift | None:
    """Join contiguous periods, since the timeline splits a shift at overrides and at the present moment."""
    periods = sorted(
        (_instant(period["startDate"]), _instant(period["endDate"]))
        for rotation in timeline.get("finalTimeline", {}).get("rotations", [])
        for period in rotation.get("periods", [])
        if my_id in {responder["id"] for responder in [period.get("responder") or {}, *period.get("flattenedResponders", [])] if responder}
    )
    shifts: list[list[datetime]] = []
    for start, end in periods:
        if shifts and start <= shifts[-1][1]:
            shifts[-1][1] = max(shifts[-1][1], end)
        else:
            shifts.append([start, end])
    upcoming = [shift for shift in shifts if shift[1] > at]
    if not upcoming:
        return None
    start, end = upcoming[0]
    return OnCallShift(schedule=schedule, starts_at=start.isoformat(), ends_at=end.isoformat(), current=start <= at)


def epic_query(project: str, keyword: str) -> str:
    """JQL for the newest open epic in the project whose name contains the keyword."""
    safe = keyword.replace("\\", "").replace('"', "")
    return f'project = "{project}" AND issuetype = Epic AND summary ~ "{safe}" AND statusCategory != Done ORDER BY created DESC'


async def _on_call(base_url: str, auth: httpx.Auth | tuple[str, str] | None, my_id: str, at: datetime) -> OnCallShift | None:
    async with httpx.AsyncClient(auth=auth, timeout=30) as client:
        cloud_id = (await get_json(client, f"{base_url}/_edge/tenant_info"))["cloudId"]
        api = OPS_API.format(cloud_id=cloud_id)
        schedules = []
        page = f"{api}/schedules?size={SCHEDULE_PAGE}"
        while page:
            listing = await get_json(client, page)
            schedules.extend(listing["values"])
            page = (listing.get("links") or {}).get("next")
        shifts = []
        for schedule in (schedule for schedule in schedules if schedule.get("enabled")):
            timeline = await get_json(client, f"{api}/schedules/{schedule['id']}/timeline", params={"interval": TIMELINE_WEEKS, "intervalUnit": "weeks"})
            shift = current_shift(timeline, schedule["name"], my_id, at)
            if shift:
                shifts.append(shift)
    return min(shifts, key=lambda shift: shift.starts_at, default=None)


async def read_oncall(store: Store) -> Batch:
    """List open children of the on-call epic in the project holding most of the open work assigned to you."""
    keyword = ONCALL_EPIC.read(store)
    if not keyword:
        raise SourceError("Add the on-call epic name in Settings.")
    at = datetime.now(timezone.utc)
    async with jira_client(store) as client:
        base_url = str(client.base_url).rstrip("/")
        auth = client.auth
        my_id = (await get_json(client, "/rest/api/3/myself"))["accountId"]
        mine = await search_issues(client, "assignee = currentUser() AND statusCategory != Done", fields="project")
        projects = Counter(issue["fields"]["project"]["key"] for issue in mine)
        if not projects:
            raise SourceError("No open tickets are assigned to you, so worktray cannot tell which project is yours.")
        project = projects.most_common(1)[0][0]
        epics = await search_issues(client, epic_query(project, keyword), fields="summary")
        if not epics:
            raise SourceError(f'No open epic with "{keyword}" in its name in {project}. Change the name in Settings.')
        epic = OnCallEpic(key=epics[0]["key"], title=epics[0]["fields"]["summary"], url=f"{base_url}/browse/{epics[0]['key']}")
        children = await search_issues(client, f"parent = {epic.key} AND statusCategory != Done", fields=ONCALL_FIELDS)
    try:
        shift = await _on_call(base_url, auth, my_id, at)
        shift_detail = ""
    except SourceError as error:
        # The epic list is useful without the rotation, so an unreadable schedule only blanks the shift.
        shift = None
        shift_detail = f". Could not read the on-call schedule: {error}"
    store.save_setting(ONCALL_EPIC_SETTING, epic.model_dump_json())
    store.save_setting(ON_CALL_SETTING, shift.model_dump_json() if shift else "")
    items = [oncall_item(issue, base_url, my_id, at) for issue in children]
    flagged = sum(bool(item.attention) for item in items)
    return Batch(items=items, detail=f"{len(items)} open tickets in {epic.key}, {flagged} needing attention{shift_detail}")
