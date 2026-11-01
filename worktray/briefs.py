"""Standup notes and meeting briefs built from the local queue.

Both carry internal titles and links, so they are only ever served to this
machine: the localhost web view and the stdio MCP server.
"""

from datetime import date, datetime, timedelta, timezone
import re

from pydantic import BaseModel

from worktray.models import Item
from worktray.references import JIRA_KEY

PROJECT_KEY = re.compile(r"\b[A-Z][A-Z0-9]+\b")
OPEN_STATUSES = ("open", "proposed")
MIN_MEETING_NAME = 4


class StandupNote(BaseModel):
    """What closed since the last working day, what is pinned, and what meeting is next."""

    closed: list[Item]
    planned: list[Item]
    next_meeting: Item | None
    text: str


class MeetingBrief(BaseModel):
    """Open work that names the same ticket, project or meeting as a calendar event."""

    event: Item
    tickets: list[Item]
    pull_requests: list[Item]
    action_items: list[Item]


def previous_workday(today: date) -> date:
    """Step back over weekends so Monday's standup reports Friday."""
    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def next_meeting(items: list[Item], at: datetime) -> Item | None:
    """Earliest timed calendar event that has not ended."""
    upcoming = [item for item in items if item.source == "calendar" and item.status == "open" and not item.all_day and item.ends_at and datetime.fromisoformat(item.ends_at) > at]
    upcoming.sort(key=lambda item: item.starts_at or "")
    return upcoming[0] if upcoming else None


def _local_date(timestamp: str) -> date:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().date()


def _slack_line(item: Item) -> str:
    title = item.title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"• <{item.url}|{title}>" if item.url else f"• {title}"


def standup_note(items: list[Item], today: date | None = None, at: datetime | None = None) -> StandupNote:
    """Summarise yesterday's closures, today's pinned work and the next meeting as Slack text."""
    today = today if today is not None else date.today()
    at = at if at is not None else datetime.now(timezone.utc)
    since = previous_workday(today)
    closed = sorted((item for item in items if item.status == "done" and item.closed_at and since <= _local_date(item.closed_at) < today), key=lambda item: item.closed_at or "")
    planned = [item for item in items if item.status == "open" and item.up_next]
    meeting = next_meeting(items, at)
    label = "Yesterday" if since == today - timedelta(days=1) else since.strftime("%A")
    lines = [f"*{label}*", *([_slack_line(item) for item in closed] or ["• Nothing closed"]), "*Today*", *([_slack_line(item) for item in planned] or ["• Nothing pinned"])]
    if meeting and meeting.starts_at:
        lines += ["*Next meeting*", f"• {meeting.title} at {datetime.fromisoformat(meeting.starts_at).astimezone().strftime('%H:%M')}"]
    return StandupNote(closed=closed, planned=planned, next_meeting=meeting, text="\n".join(lines))


def meeting_brief(event: Item, items: list[Item]) -> MeetingBrief:
    """Match on Jira keys, Jira project keys and meeting names, never on loose title similarity."""
    keys = set(JIRA_KEY.findall(event.title))
    # A ticket key already names its project; counting it again would pull in every sibling ticket.
    projects = set(PROJECT_KEY.findall(JIRA_KEY.sub("", event.title)))
    name = event.title.casefold().strip()
    open_items = [item for item in items if item.status in OPEN_STATUSES and item.key != event.key]
    tickets = [item for item in open_items if item.source == "jira" and (item.key.removeprefix("jira:") in keys or item.project in projects)]
    wanted = keys | {item.key.removeprefix("jira:") for item in tickets}
    pull_requests = [item for item in open_items if item.source in ("github", "bitbucket") and set(JIRA_KEY.findall(item.title)) & wanted]
    action_items = [
        item
        for item in open_items
        if not item.live and ((item.source == "gemini" and len(name) >= MIN_MEETING_NAME and name in item.project.casefold()) or set(JIRA_KEY.findall(f"{item.title} {item.note}")) & wanted)
    ]
    return MeetingBrief(event=event, tickets=tickets, pull_requests=pull_requests, action_items=action_items)
