from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from worktray.models import Item, ItemEdit, SourceState, now
from worktray.store import Store

LATER = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "tracker.sqlite3")


def stream_item(store: Store, key: str = "manual:a") -> Item:
    item = Item(key=key, title="Write the RFC", source="manual", status="open")
    store.ingest([item])
    return item


def test_snooze_time_without_a_timezone_is_rejected():
    with pytest.raises(ValidationError):
        ItemEdit(snoozed_until="2026-10-22T09:00:00")


def test_stream_item_keeps_its_snooze_time(store):
    stream_item(store)

    store.edit("manual:a", ItemEdit(snoozed_until=LATER))

    assert store.items()[0].snoozed_until == LATER


def test_empty_snooze_time_wakes_a_stream_item(store):
    stream_item(store)
    store.edit("manual:a", ItemEdit(snoozed_until=LATER))

    store.edit("manual:a", ItemEdit(snoozed_until=""))

    assert store.items()[0].snoozed_until is None


def test_closing_a_snoozed_item_clears_the_snooze(store):
    stream_item(store)
    store.edit("manual:a", ItemEdit(snoozed_until=LATER))

    store.edit("manual:a", ItemEdit(status="done"))

    assert store.items()[0].snoozed_until is None


def test_live_item_snooze_survives_a_snapshot_rewrite(store):
    live = Item(key="jira:WEB-1", title="Retry", source="jira", status="open", live=True)
    store.annotate(live.key, ItemEdit(snoozed_until=LATER))
    state = SourceState(source="jira", state="ok", last_success=now())

    store.save_snapshot("jira", [live], state)

    assert store.annotated(store.snapshots()["jira"].items[0]).snoozed_until == LATER


def test_empty_snooze_time_wakes_a_live_item(store):
    store.annotate("jira:WEB-1", ItemEdit(snoozed_until=LATER))

    store.annotate("jira:WEB-1", ItemEdit(snoozed_until=""))

    item = store.annotated(Item(key="jira:WEB-1", title="Retry", source="jira", live=True))
    assert item.snoozed_until is None
