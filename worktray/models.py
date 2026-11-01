"""Validated data crossing tracker boundaries."""

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


def now() -> str:
    """Return a sortable UTC timestamp for durable history."""
    return datetime.now(timezone.utc).isoformat()


def within_work_window(timestamp: str | None, as_of: datetime | None = None) -> bool:
    """Keep only verified timestamps in the most recent ninety days."""
    if not timestamp:
        return False
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    current = as_of if as_of is not None else datetime.now(timezone.utc)
    return current - timedelta(days=90) <= instant <= current


Lane = Literal["needs_me", "waiting", ""]
WAITING_ON_REVIEW = "Waiting on review"
DRAFT_PR = "Draft"


def idle_reasons(draft: bool) -> list[str]:
    """Why an own PR with nothing else to act on is still listed: a draft is the author's move."""
    return [DRAFT_PR if draft else WAITING_ON_REVIEW]


def review_lane(reasons: list[str]) -> Lane:
    """Only the reviewer's turn is waiting; every other reason is the user's move."""
    if not reasons:
        return ""
    return "waiting" if reasons == [WAITING_ON_REVIEW] else "needs_me"


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
APP_LINKS = ("claude://", "codex://", "cursor://file/")


def web_link_problem(url: str) -> str:
    """Why url is not a safe web link, or "" when it is: https anywhere, plain http only on this machine.

    The host is parsed rather than matched as a prefix, so http://localhost.example.com and
    https://user@host are refused.
    """
    if any(character.isspace() for character in url):
        return "Leave spaces out of the URL"
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError for a port that is not a number
    except ValueError:
        return "That isn't a valid URL"
    if parts.username is not None or parts.password is not None:
        return "Leave the user name and password out of the URL"
    if not host or parts.scheme not in ("https", "http"):
        return "Use an https:// URL"
    if parts.scheme == "http" and host not in LOCAL_HOSTS:
        return "Use an https:// URL; plain http works only for a server on this machine"
    return ""


def https_only(url: str) -> str:
    """Drop source-supplied links that are not plain web links."""
    return url if url.startswith("https://") else ""


class Item(BaseModel):
    """A stream decision or a source-owned item with snapshot freshness."""

    key: str = Field(min_length=1, max_length=1000)
    title: str = Field(min_length=1, max_length=240)
    source: str = Field(min_length=1, max_length=40)
    url: str = Field(default="", max_length=2000)
    status: Literal["proposed", "open", "done", "dismissed"] = "proposed"
    first_seen: str = Field(default_factory=now)
    opened_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    all_day: bool = False
    note: str = Field(default="", max_length=2000)
    list_name: str = Field(default="", max_length=60)
    up_next: bool = False
    close_suggested: bool = False
    live: bool = False
    owner: str = ""
    owner_id: str = ""
    owner_email: str = ""
    owner_active: bool | None = None
    team_member: bool = False
    source_status: str = ""
    source_category: str = ""
    reason: str = ""
    project: str = ""
    personal: bool = True
    lane: Lane = ""
    issue_type: str = Field(default="", max_length=60)
    due_date: str | None = None
    parent_title: str = Field(default="", max_length=240)
    checks_url: str = Field(default="", max_length=2000)
    checks_detail: str = Field(default="", max_length=240)
    snoozed_until: str | None = None
    close_hint: str = Field(default="", max_length=240)
    attention: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    linked_status: str = Field(default="", max_length=240)

    @field_validator("url", "checks_url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        """Permit source navigation without executable URL schemes."""
        if value and not value.startswith(APP_LINKS) and web_link_problem(value):
            raise ValueError("Unsupported source link")
        return value


class ItemEdit(BaseModel):
    """Fields the user owns, independent of an upstream source status."""

    title: str | None = Field(default=None, min_length=1, max_length=240)
    note: str | None = Field(default=None, max_length=2000)
    list_name: str | None = Field(default=None, max_length=60)
    up_next: bool | None = None
    status: Literal["open", "done", "dismissed"] | None = None
    snoozed_until: str | None = Field(default=None, max_length=40)
    due_date: str | None = Field(default=None, max_length=10)

    @field_validator("due_date")
    @classmethod
    def calendar_day(cls, value: str | None) -> str | None:
        """Keep the YYYY-MM-DD shape Jira uses, so both kinds of due date sort and render alike."""
        return date.fromisoformat(value).isoformat() if value else value

    @field_validator("snoozed_until")
    @classmethod
    def aware_timestamp(cls, value: str | None) -> str | None:
        """Accept an ISO instant with a timezone, or an empty string to wake the item."""
        if value and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("Snooze time needs a timezone")
        return value


class SourceState(BaseModel):
    """Health of a complete source refresh, including partial failures."""

    source: str
    last_attempt: str | None = None
    last_success: str | None = None
    stale_since: str | None = None
    state: str = "not_refreshed"
    detail: str = "Refresh to check this source"
    count: int = 0


class Batch(BaseModel):
    """A complete adapter result; errors must raise before returning it."""

    items: list[Item] = Field(default_factory=list)
    detail: str = ""


SuggestionKind = Literal["merge", "link", "retitle", "due", "close"]


class Suggestion(BaseModel):
    """One cleanup an agent proposes for stream items; nothing changes until the user accepts it.

    merge keeps keys[0] and closes the rest into it, link attaches keys[0] to a ticket or
    pull request of yours, retitle and due rewrite keys[0], close finishes every key.
    """

    kind: SuggestionKind
    keys: list[str] = Field(min_length=1, max_length=20)
    title: str = Field(default="", max_length=240)
    reference: str = Field(default="", max_length=300)
    due_date: date | None = None
    why: str = Field(min_length=1, max_length=240)

    @property
    def id(self) -> str:
        """Stable across runs, so a rejected suggestion is recognised when an agent makes it again."""
        content = json.dumps([self.kind, self.keys, self.title, self.reference, str(self.due_date or "")])
        return hashlib.sha256(content.encode()).hexdigest()[:24]
