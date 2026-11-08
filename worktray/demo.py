"""A public demo: the dashboard with made-up data and read-only settings.

`worktray serve --demo` starts it. The data lives in a new temporary folder and tokens in memory.
Every name, link and ticket below is made up.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from fastapi import FastAPI

from worktray.auth.keyring_store import MemoryStore, use_secret_store
from worktray.config import enabled_key
from worktray.engine import Engine
from worktray.models import Batch, Item, Suggestion
from worktray.sources.extract import NEXT_STEP, TICKET_STEP
from worktray.sources.oncall import ON_CALL_SETTING, ONCALL_EPIC_SETTING, OnCallEpic, OnCallShift
from worktray.sources.registry import registry
from worktray.store import Store

ME = ("Alex Example", "acc-alex", "alex@example.com")
SAM = ("Sam Lee", "acc-sam", "sam@example.com")
PRIYA = ("Priya Shah", "acc-priya", "priya@example.com")
JORDAN = ("Jordan Kim", "acc-jordan", "jordan@example.com")
JIRA = "https://jira.example.com/browse/"
GIT = "https://git.example.com/acme/"
CHAT = "https://chat.example.com/archives/"
SETTINGS = {
    "display_name": ME[0],
    "jira_account_id": ME[1],
    "jira_url": "https://jira.example.com",
    "jira_email": ME[2],
    "github_orgs": "acme",
    "team_jql": 'project = "WEB" AND statusCategory != Done',
    "team_scope_origin": "Set for the demo",
}


def _at(moment: datetime) -> str:
    return moment.isoformat()


def _owner(person: tuple[str, str, str]) -> dict:
    return {"owner": person[0], "owner_id": person[1], "owner_email": person[2], "owner_active": True}


def jira(now: datetime) -> Batch:
    def ticket(key: str, title: str, person: tuple, status: str, category: str, lane: str, priority: str, days: int, personal: bool = True) -> Item:
        return Item(
            key=f"jira:{key}",
            source="jira",
            title=title,
            url=JIRA + key,
            status="open",
            live=True,
            opened_at=_at(now - timedelta(days=days)),
            updated_at=_at(now - timedelta(hours=days)),
            source_status=status,
            source_category=category,
            project="WEB",
            reason=priority,
            lane=lane,
            personal=personal,
            team_member=True,
            issue_type="Task",
            **_owner(person),
        )

    return Batch(
        items=[
            ticket("WEB-142", "Add a retry to the checkout payment call", ME, "In Progress", "indeterminate", "needs_me", "High", 4),
            ticket("WEB-151", "Fix the date format on invoices", ME, "To Do", "new", "needs_me", "Medium", 2),
            ticket("WEB-133", "Rank search results by recent activity", ME, "In Review", "indeterminate", "waiting", "Medium", 9),
            ticket("WEB-160", "Show the order number in confirmation emails", SAM, "To Do", "new", "waiting", "Low", 1),
            ticket("WEB-120", "Move image uploads to the new storage bucket", SAM, "In Progress", "indeterminate", "", "Medium", 6, personal=False),
            ticket("WEB-125", "Add keyboard shortcuts to the editor", PRIYA, "In Progress", "indeterminate", "", "Low", 3, personal=False),
            ticket("WEB-128", "Remove the old billing page", JORDAN, "To Do", "new", "", "Low", 12, personal=False),
        ],
        detail="Sample tickets for the demo",
    )


def github(now: datetime) -> Batch:
    def pull(number: int, title: str, person: tuple, reason: str, lane: str, days: int, **extra: object) -> Item:
        return Item(
            key=f"{GIT}web/pull/{number}",
            source="github",
            title=title,
            url=f"{GIT}web/pull/{number}",
            status="open",
            live=True,
            opened_at=_at(now - timedelta(days=days)),
            updated_at=_at(now - timedelta(hours=days * 3)),
            reason=reason,
            lane=lane,
            source_status="Open",
            project="acme/web",
            **_owner(person),
            **extra,
        )

    return Batch(
        items=[
            pull(
                42,
                "Add a retry to the checkout payment call",
                ME,
                "Failing checks",
                "needs_me",
                2,
                checks_url="https://ci.example.com/build/9001",
                checks_detail="Unit tests: 2 failed",
                references=["WEB-142"],
            ),
            pull(45, "Update the onboarding emails", SAM, "Review requested", "needs_me", 1),
            pull(38, "Rank search results by recent activity", ME, "Waiting on review", "waiting", 8),
            pull(47, "Move image uploads to the new storage bucket", SAM, "Open team PR", "", 3, personal=False, team_member=True),
        ],
        detail="Sample pull requests for the demo",
    )


def calendar(now: datetime) -> Batch:
    def meeting(number: int, title: str, starts_in: timedelta, minutes: int) -> Item:
        start = now + starts_in
        return Item(
            key=f"calendar:demo-{number}",
            source="calendar",
            title=title,
            url=f"https://calendar.example.com/event/{number}",
            status="open",
            live=True,
            starts_at=_at(start),
            ends_at=_at(start + timedelta(minutes=minutes)),
        )

    return Batch(
        items=[
            meeting(1, "Checkout planning: WEB-142 retries", timedelta(minutes=50), 30),
            meeting(2, "1:1 with Sam", timedelta(hours=3), 30),
            meeting(3, "Sprint review", timedelta(days=1, hours=1), 60),
        ],
        detail="Sample meetings for the demo",
    )


def oncall(now: datetime) -> Batch:
    def ticket(key: str, title: str, person: tuple | None, status: str, category: str, attention: list[str], priority: str) -> Item:
        owner = _owner(person) if person else {"owner": "Unassigned", "owner_id": "unassigned"}
        return Item(
            key=f"oncall:{key}",
            source="oncall",
            title=title,
            url=JIRA + key,
            status="open",
            live=True,
            personal=False,
            opened_at=_at(now - timedelta(days=2)),
            source_status=status,
            source_category=category,
            project="OPS",
            reason=priority,
            attention=attention,
            lane="needs_me" if attention else "",
            list_name="OPS-1",
            **owner,
        )

    return Batch(
        items=[
            ticket("OPS-12", "Checkout errors above 1% since the last deploy", None, "To Do", "new", ["High, unassigned"], "High"),
            ticket("OPS-9", "Rotate the staging certificates", ME, "In Progress", "indeterminate", ["Yours in flight"], "Medium"),
            ticket("OPS-7", "Clean up unused load balancers", SAM, "In Progress", "indeterminate", [], "Low"),
        ],
        detail="Sample on-call tickets for the demo",
    )


def slack(now: datetime) -> Batch:
    def ask(number: int, title: str, reason: str, days: int, **extra: object) -> Item:
        return Item(
            key=f"slack:demo-{number}",
            source="slack",
            title=title,
            url=f"{CHAT}C1/p{number}",
            reason=reason,
            list_name="Asks",
            opened_at=_at(now - timedelta(days=days)),
            **extra,
        )

    return Batch(
        items=[
            ask(1, "Share when the WEB-142 retry fix is out", "Asked of you", 1, references=["WEB-142"]),
            ask(2, "Check if image uploads still fail after WEB-120", "Asked of you", 2, references=["WEB-120"], linked_status="WEB-120 In Progress · 1 PR open"),
            ask(3, "Send Priya the invoice date examples", "You promised", 3),
            ask(4, "Send the invoice date examples to Priya", "You promised", 1),
            ask(5, "Write up the search ranking results for the team", "Asked of you", 5, status="open"),
        ],
        detail="Sample Slack asks for the demo",
    )


def gemini(now: datetime) -> Batch:
    def action(number: int, title: str, reason: str) -> Item:
        return Item(
            key=f"gemini:demo:{number}:1",
            source="gemini",
            title=title,
            url=f"https://docs.example.com/notes/{number}",
            opened_at=_at(now - timedelta(days=1)),
            reason=reason,
            list_name="Follow-ups",
            project="Sprint review",
        )

    return Batch(
        items=[
            action(1, "Create a ticket for the flaky checkout test", TICKET_STEP),
            action(2, "Ask design for the new invoice layout", NEXT_STEP),
        ],
        detail="Sample meeting notes for the demo",
    )


def agents(now: datetime) -> Batch:
    return Batch(
        items=[
            Item(key="claude:demo-1", source="claude", title="Investigate slow search index build", reason="Recent agent session", list_name="Agent work", opened_at=_at(now - timedelta(hours=5))),
            Item(key="codex:demo-1", source="codex", title="Draft migration for the new storage bucket", reason="Recent agent session", list_name="Agent work", opened_at=_at(now - timedelta(days=1))),
        ],
        detail="Sample agent sessions for the demo",
    )


async def tidy_up(_: datetime) -> Batch:
    return Batch(detail="Sample suggestions for the demo")


READERS: dict[str, Callable[[datetime], Batch]] = {
    "jira": jira,
    "github": github,
    "calendar": calendar,
    "oncall": oncall,
    "slack": slack,
    "gemini": gemini,
    "claude": agents,
}


def _adapter(read: Callable[[datetime], Batch]) -> Callable[[], Awaitable[Batch]]:
    async def adapter() -> Batch:
        return read(datetime.now(timezone.utc))

    return adapter


def seed(store: Store, now: datetime) -> None:
    """Settings, switches and items that do not come from a source: your own items, history and suggestions."""
    for key, value in SETTINGS.items():
        store.save_setting(key, value)
    for name in [*READERS, "cleanup"]:
        store.save_setting(enabled_key(name), "on")
    store.save_setting(ONCALL_EPIC_SETTING, OnCallEpic(key="OPS-1", title="KTLO Q4", url=JIRA + "OPS-1").model_dump_json())
    shift = OnCallShift(schedule="Platform on call", starts_at=_at(now - timedelta(days=1)), ends_at=_at(now + timedelta(days=3)), current=True)
    store.save_setting(ON_CALL_SETTING, shift.model_dump_json())
    yesterday = now - timedelta(days=1)
    store.ingest(
        [
            Item(key="manual:demo-1", source="manual", title="Book travel for the team offsite", status="open", up_next=True, list_name="Personal"),
            Item(key="manual:demo-2", source="manual", title="Rotate the staging API keys", status="done", closed_at=_at(yesterday), note="Done with Sam"),
            Item(key="manual:demo-3", source="manual", title="Answer the security questionnaire", status="done", closed_at=_at(yesterday)),
        ]
    )
    store.ingest(slack(now).items + gemini(now).items)
    store.replace_suggestions(
        [
            Suggestion(kind="merge", keys=["slack:demo-3", "slack:demo-4"], title="Send Priya the invoice date examples", why="Both ask for the invoice date examples for Priya"),
            Suggestion(kind="link", keys=["gemini:demo:1:1"], reference="WEB-142", why="The flaky checkout test is the retry work in WEB-142"),
        ]
    )


def create_demo_app() -> FastAPI:
    """The dashboard over a new temporary folder filled with sample data."""
    from worktray.web.app import create_app

    use_secret_store(MemoryStore())
    folder = Path(tempfile.mkdtemp(prefix="worktray-demo-"))
    store = Store(folder / "demo.sqlite3")
    now = datetime.now(timezone.utc)
    seed(store, now)
    adapters = {name: _adapter(read) for name, read in READERS.items()}
    adapters["cleanup"] = lambda: tidy_up(now)
    engine = Engine(store, adapters, registry())

    async def first_sync() -> None:
        await asyncio.gather(*(engine.refresh(name) for name in adapters))

    asyncio.run(first_sync())
    return create_app(store, engine, demo=True)
