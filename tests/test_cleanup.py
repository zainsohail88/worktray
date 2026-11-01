import json

import pytest

from worktray.models import Item, ItemEdit, Suggestion
from worktray.sources.cleanup import apply_suggestion, reject_suggestion, suggestions_from_agent_json, visible_suggestions
from worktray.sources.errors import SourceError
from worktray.store import Store

TICKET = Item(key="jira:ABC-123", title="Search results show the wrong owner", source="jira", status="open", live=True)


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "tracker.sqlite3")
    store.ingest(
        [
            Item(key="slack:a", title="Look at search ownership", source="slack", url="https://x.slack.com/archives/C/p1"),
            Item(key="gemini:b", title="Fix owners on shared projects", source="gemini", status="open", url="https://docs.google.com/document/d/b/edit"),
            Item(key="slack:c", title="Thing from standup", source="slack"),
        ]
    )
    return store


def suggestion(kind: str, keys: list[str], **fields: object) -> dict:
    return {"kind": kind, "keys": keys, "title": "", "reference": "", "due_date": None, "why": "Same work", **fields}


def parse(store: Store, *suggestions: dict) -> list[Suggestion]:
    payload = json.dumps({"suggestions": list(suggestions)})
    return suggestions_from_agent_json(payload, store.items(), {"ABC-123": TICKET})


def pending(store: Store, *suggestions: dict) -> Suggestion:
    store.replace_suggestions(parse(store, *suggestions))
    return visible_suggestions(store)[0]


def test_suggestion_naming_an_item_the_agent_was_not_shown_is_dropped(store):
    assert parse(store, suggestion("close", ["slack:zzz"])) == []


def test_link_to_a_ticket_outside_your_work_is_dropped(store):
    assert parse(store, suggestion("link", ["slack:a"], reference="WEB-1")) == []


def test_an_item_claimed_by_one_suggestion_is_not_touched_by_another(store):
    kept = parse(store, suggestion("merge", ["gemini:b", "slack:a"]), suggestion("close", ["slack:a"]))

    assert [found.kind for found in kept] == ["merge"]


def test_malformed_agent_json_fails_the_run(store):
    with pytest.raises(SourceError):
        suggestions_from_agent_json('{"suggestions": [{"kind": "explode"}]}', store.items(), {})


def test_accepted_merge_keeps_the_first_item_and_closes_the_rest(store):
    found = pending(store, suggestion("merge", ["gemini:b", "slack:a"], title="Show every owner on shared projects"))

    apply_suggestion(store, found.id)

    items = {item.key: item for item in store.items()}
    assert (items["gemini:b"].title, items["slack:a"].status) == ("Show every owner on shared projects", "dismissed")


def test_accepted_merge_keeps_the_link_of_each_merged_item(store):
    found = pending(store, suggestion("merge", ["gemini:b", "slack:a"]))

    apply_suggestion(store, found.id)

    assert "https://x.slack.com/archives/C/p1" in next(item for item in store.items() if item.key == "gemini:b").note


def test_accepted_link_attaches_the_ticket(store):
    found = pending(store, suggestion("link", ["slack:a"], reference="ABC-123"))

    apply_suggestion(store, found.id)

    assert store.references()["slack:a"] == ["ABC-123"]


def test_accepted_due_date_is_set(store):
    found = pending(store, suggestion("due", ["slack:c"], due_date="2026-10-31"))

    apply_suggestion(store, found.id)

    assert next(item for item in store.items() if item.key == "slack:c").due_date == "2026-10-31"


def test_accepted_close_finishes_open_work_and_dismisses_proposals(store):
    found = pending(store, suggestion("close", ["gemini:b", "slack:c"]))

    apply_suggestion(store, found.id)

    assert {item.key: item.status for item in store.items()} == {"slack:a": "proposed", "gemini:b": "done", "slack:c": "dismissed"}


def test_rejected_suggestion_does_not_return_on_the_next_run(store):
    found = pending(store, suggestion("retitle", ["slack:c"], title="Send the release notes to Sam"))
    reject_suggestion(store, found.id)

    store.replace_suggestions(parse(store, suggestion("retitle", ["slack:c"], title="Send the release notes to Sam")))

    assert visible_suggestions(store) == []


def test_suggestion_for_an_item_closed_by_hand_is_hidden(store):
    pending(store, suggestion("retitle", ["slack:c"], title="Send the release notes"))
    store.edit("slack:c", ItemEdit(status="dismissed"))

    assert visible_suggestions(store) == []
