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
