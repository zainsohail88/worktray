import asyncio

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client  # noqa: E402

from worktray.mcp_server import create_mcp  # noqa: E402
from worktray.models import Item, SourceState, now  # noqa: E402
from worktray.store import Store  # noqa: E402


def call(store: Store, tool: str, arguments: dict | None = None):
    async def run():
        async with Client(create_mcp(store)) as client:
            return await client.call_tool(tool, arguments or {})

    return asyncio.run(run()).data


def save_jira(store: Store, *items: Item, last_success: str | None = None) -> None:
    state = SourceState(source="jira", state="ok", last_success=last_success or now())
    store.save_snapshot("jira", list(items), state)


def test_queue_lists_live_work_from_the_saved_snapshot(store):
    save_jira(store, Item(key="jira:WEB-1", title="Retry", source="jira", status="open", live=True))

    assert [item.key for item in call(store, "tracker_queue").items] == ["jira:WEB-1"]


def test_queue_leaves_out_work_that_belongs_to_teammates(store):
    save_jira(store, Item(key="jira:WEB-2", title="Theirs", source="jira", status="open", live=True, personal=False))

    assert call(store, "tracker_queue").items == []


def test_queue_reports_when_each_source_last_succeeded(store):
    save_jira(store, last_success="2026-10-21T01:00:00+00:00")

    [source] = call(store, "tracker_queue").sources

    assert (source.source, source.last_success) == ("jira", "2026-10-21T01:00:00+00:00")


def test_queue_applies_a_snooze_set_on_live_work(store):
    save_jira(store, Item(key="jira:WEB-1", title="Retry", source="jira", status="open", live=True))
    call(store, "tracker_snooze", {"key": "jira:WEB-1", "until": "2099-01-01T00:00:00+00:00"})

    assert call(store, "tracker_queue").items[0].snoozed_until == "2099-01-01T00:00:00+00:00"


def test_meeting_brief_rejects_an_unknown_meeting(store):
    with pytest.raises(Exception, match="Meeting is not in the saved calendar snapshot"):
        call(store, "meeting_brief", {"event_key": "calendar:primary:nope"})


def test_snooze_reaches_a_stream_item(store):
    store.ingest([Item(key="manual:a", title="Write the RFC", source="manual", status="open")])

    call(store, "tracker_snooze", {"key": "manual:a", "until": "2099-01-01T00:00:00+00:00"})

    assert store.items()[0].snoozed_until == "2099-01-01T00:00:00+00:00"


def test_queue_leaves_out_work_from_a_switched_off_source(store):
    from worktray.config import set_source_enabled

    save_jira(store, Item(key="jira:WEB-1", title="Retry", source="jira", status="open", live=True))
    set_source_enabled(store, "jira", False)

    assert call(store, "tracker_queue").items == []


def test_agent_closes_work_it_started(store):
    started = call(store, "tracker_started", {"title": "Fix the login page", "session_id": "s1", "agent": "claude"})

    finished = call(store, "tracker_finished", {"key": started["key"], "result": "Tests pass"})

    assert finished["status"] == "done" and finished["outcome"] == "closed"


def test_agent_only_suggests_closing_work_it_did_not_start(store):
    store.ingest([Item(key="slack:a", title="Review the rollout plan", source="slack", status="open")])

    finished = call(store, "tracker_finished", {"key": "slack:a", "result": "Reviewed and approved"})

    [item] = store.items()
    assert finished["outcome"].startswith("close suggested")
    assert (item.status, item.close_suggested, item.close_hint) == ("open", True, "Reviewed and approved")


def test_agents_do_not_receive_other_peoples_emails_or_ids(store):
    store.ingest([Item(key="slack:a", title="Ask", source="slack", status="open", owner_email="sam@example.com", owner_id="u-1")])
    save_jira(store, Item(key="jira:WEB-1", title="Retry", source="jira", status="open", live=True, owner_email="sam@example.com", owner_id="u-1"))

    listed = call(store, "tracker_list")
    queued = call(store, "tracker_queue").items

    assert all("owner_email" not in item and "owner_id" not in item for item in listed)
    assert not hasattr(queued[0], "owner_email") and not hasattr(queued[0], "owner_id")
