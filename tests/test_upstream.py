import asyncio


from worktray.models import Item, ItemEdit
from worktray.references import find_references, linked_asks
from worktray.sources import upstream
from worktray.sources.upstream import LinkState
from worktray.store import Store

PR = "https://github.com/example-org/app/pull/12"


def ask(store: Store, key: str, title: str, status: str = "open", note: str = "") -> None:
    store.ingest([Item(key=key, title=title, source="slack", status=status, note=note)])


def test_references_find_tickets_and_pull_requests_in_order_without_repeats():
    text = f"Review {PR} for WEB-7, then WEB-7 and OPS-2 again"

    assert find_references(text) == [PR, "WEB-7", "OPS-2"]


def test_references_ignore_text_that_names_nothing():
    assert find_references("Share the rollout plan with the team") == []


def test_store_lists_references_of_active_items_only(store):
    ask(store, "slack:a", "Check WEB-7")
    ask(store, "slack:b", "Check WEB-8", status="proposed")
    ask(store, "slack:c", "Check WEB-9", status="dismissed")

    assert store.references() == {"slack:a": ["WEB-7"], "slack:b": ["WEB-8"]}


def test_store_lists_references_the_source_found_beyond_the_title(store):
    store.ingest([Item(key="slack:a", title="Fix owners on shared projects", source="slack", references=["ABC-123"])])

    assert store.references() == {"slack:a": ["ABC-123"]}


def test_a_later_sync_adds_references_to_a_known_item(store):
    store.ingest([Item(key="slack:a", title="Fix owners on shared projects", source="slack")])
    store.ingest([Item(key="slack:a", title="Fix owners on shared projects", source="slack", references=["ABC-123"])])

    assert store.items()[0].references == ["ABC-123"]


def test_suggest_close_marks_an_open_item_with_the_reason(store):
    ask(store, "slack:a", "Check WEB-7")

    store.suggest_close("slack:a", "WEB-7 is Done")

    item = store.items()[0]
    assert (item.close_suggested, item.close_hint) == (True, "WEB-7 is Done")


def test_suggest_close_leaves_a_proposal_alone(store):
    ask(store, "slack:a", "Check WEB-7", status="proposed")

    store.suggest_close("slack:a", "WEB-7 is Done")

    assert store.items()[0].close_suggested is False


def test_closing_an_item_clears_its_suggestion(store):
    ask(store, "slack:a", "Check WEB-7")
    store.suggest_close("slack:a", "WEB-7 is Done")

    store.edit("slack:a", ItemEdit(status="done"))

    assert store.items()[0].close_hint == ""


JIRA = {"JIRA_URL": "https://j.example", "JIRA_USERNAME": "u", "JIRA_API_TOKEN": "t"}


def state(reference: str, finished: str | None) -> LinkState:
    """A finished reference carries its closing text; None stands for one still open."""
    return LinkState(text=finished, finished=True) if finished else LinkState(text=f"{reference} In Progress", finished=False)


def run_upstream(store: Store, monkeypatch, tickets: dict[str, str | None], pulls: dict[str, str | None] | None = None, config: dict[str, str] = JIRA) -> None:
    async def ticket(client, key):
        return state(key, tickets[key])

    async def pull(reference, *scope):
        return state(reference, (pulls or {})[reference])

    monkeypatch.setattr(upstream, "_ticket_state", ticket)
    monkeypatch.setattr(upstream, "_github_state", pull)
    monkeypatch.setattr(upstream, "atlassian_config", lambda store: config)
    asyncio.run(upstream.read_upstream(store))


def test_item_naming_a_finished_ticket_is_offered_as_done(store, monkeypatch):
    ask(store, "slack:a", "Check WEB-7")

    run_upstream(store, monkeypatch, {"WEB-7": "WEB-7 is Done"})

    assert store.items()[0].close_hint == "WEB-7 is Done"


def test_item_naming_a_merged_pull_request_is_offered_as_done(store, monkeypatch):
    ask(store, "slack:a", f"Please review {PR}")

    run_upstream(store, monkeypatch, {}, {PR: "example-org/app#12 merged"})

    assert store.items()[0].close_hint == "example-org/app#12 merged"


def test_item_with_one_unfinished_reference_is_not_offered(store, monkeypatch):
    ask(store, "slack:a", "Check WEB-7 and WEB-8")

    run_upstream(store, monkeypatch, {"WEB-7": "WEB-7 is Done", "WEB-8": None})

    assert store.items()[0].close_suggested is False


def test_item_with_every_reference_finished_is_offered(store, monkeypatch):
    ask(store, "slack:a", "Check WEB-7 and WEB-8")

    run_upstream(store, monkeypatch, {"WEB-7": "WEB-7 is Done", "WEB-8": "WEB-8 is Done"})

    assert store.items()[0].close_hint == "All 2 linked tickets and PRs are done"


def test_item_shows_where_its_unfinished_ticket_stands(store, monkeypatch):
    ask(store, "slack:a", "Check WEB-7", status="proposed")

    run_upstream(store, monkeypatch, {"WEB-7": None})

    assert store.items()[0].linked_status == "WEB-7 In Progress"


def test_jira_development_summary_reads_as_a_pull_request_count():
    summary = {"summary": {"pullrequest": {"overall": {"count": 1, "state": "MERGED", "open": False}}}}

    assert upstream._pull_summary(summary) == "1 PR merged"


def test_jira_development_summary_without_pull_requests_is_empty():
    assert upstream._pull_summary({"summary": {"pullrequest": {"overall": {"count": 0}}}}) == ""


def test_pull_request_is_checked_when_jira_is_not_connected(store, monkeypatch):
    ask(store, "slack:a", f"Please review {PR}")

    run_upstream(store, monkeypatch, {}, {PR: "example-org/app#12 merged"}, config={})

    assert store.items()[0].close_hint == "example-org/app#12 merged"


def test_ticket_shaped_text_is_skipped_when_jira_is_not_connected(store, monkeypatch):
    ask(store, "slack:a", "Re-encode as UTF-8")

    run_upstream(store, monkeypatch, {}, config={})

    assert store.items()[0].close_suggested is False


def ticket(key: str, **fields: object) -> Item:
    return Item(key=f"jira:{key}", title="Fix ownership", source="jira", status="open", live=True, **fields)


def test_ask_naming_my_open_ticket_folds_under_it():
    assert linked_asks([ticket("ABC-123")], {"slack:a": ["ABC-123"]}) == {"jira:ABC-123": ["slack:a"]}


def test_ask_naming_my_pull_request_folds_under_it():
    pull = Item(key="github:12", title="Fix", source="github", status="open", live=True, url=PR)

    assert linked_asks([pull], {"slack:a": [PR]}) == {"github:12": ["slack:a"]}


def test_ask_naming_a_ticket_outside_my_work_stays_on_its_own():
    assert linked_asks([ticket("ABC-123", personal=False)], {"slack:a": ["ABC-123"]}) == {}
