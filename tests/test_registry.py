import asyncio
from importlib.metadata import EntryPoint
import sys
import types

import pytest

from worktray.config import set_source_enabled
from worktray.engine import Engine
from worktray.models import Batch, Item
from worktray.plugin import Setting, Source
from worktray.sources.bitbucket import read_bitbucket
from worktray.sources.errors import NotConnectedError
from worktray.sources.github import read_github_team, search_scope
from worktray.sources.jira import read_jira
from worktray.sources.public_slack import read_public_slack
from worktray.sources.registry import BUILTIN, check_for, discover, field_index, registry


async def empty() -> Batch:
    return Batch()


async def plugin_read(store, home) -> Batch:
    return Batch(items=[Item(key="linear:1", title="Plugin work", source="linear", status="open", live=True)])


PLUGIN = Source("linear", "Linear", plugin_read, group="jira", empty_is_valid=True, settings=(Setting("linear_team", "Linear team"),))


def entry(monkeypatch, value: object, name: str = "linear") -> EntryPoint:
    module = types.ModuleType("worktray_test_plugin")
    module.SOURCE = value
    monkeypatch.setitem(sys.modules, "worktray_test_plugin", module)
    return EntryPoint(name=name, value="worktray_test_plugin:SOURCE", group="worktray.sources")


def test_every_built_in_source_has_a_label_a_schedule_and_unique_setting_keys():
    keys = [field.key for source in BUILTIN for field in (*source.settings, *source.secrets)]

    assert all(source.label and source.interval > 0 for source in BUILTIN)
    assert len(keys) == len(set(keys))


def test_sources_that_reuse_a_login_point_at_a_real_source():
    sources = registry()

    assert all(source.uses in sources for source in sources.values() if source.uses)


def test_a_source_signing_in_through_another_is_checked_through_it():
    sources = registry()

    assert check_for(sources, sources["oncall"]) is sources["jira"].check


def test_plugin_source_is_discovered_after_the_built_in_ones(monkeypatch):
    found = discover([entry(monkeypatch, PLUGIN)])

    assert list(found)[-1] == "linear" and "linear_team" in field_index(found)


def test_plugin_may_export_a_function_returning_several_sources(monkeypatch):
    found = discover([entry(monkeypatch, lambda: [PLUGIN])])

    assert "linear" in found


def test_plugin_cannot_replace_a_built_in_source(monkeypatch):
    impostor = Source("jira", "Not Jira", plugin_read)

    assert discover([entry(monkeypatch, impostor)])["jira"].label == "Jira"


def test_plugin_cannot_reuse_a_built_in_setting_key(monkeypatch):
    clash = Source("linear", "Linear", plugin_read, settings=(Setting("jira_url", "Sneaky"),))

    assert "linear" not in discover([entry(monkeypatch, clash)])


def test_broken_plugin_is_skipped_instead_of_stopping_the_app():
    broken = EntryPoint(name="broken", value="worktray_missing_module:SOURCE", group="worktray.sources")

    assert set(discover([broken])) == {source.name for source in BUILTIN}


def test_plugin_that_returns_something_else_is_skipped(monkeypatch):
    assert "linear" not in discover([entry(monkeypatch, "not a source")])


def test_plugin_items_reach_the_queue_like_built_in_ones(store):
    set_source_enabled(store, "linear", True)
    engine = Engine(store, {"linear": lambda: plugin_read(store, None)}, {"linear": PLUGIN})

    asyncio.run(engine.refresh("linear"))

    assert [item.title for item in engine.items()] == ["Plugin work"]


def test_search_scope_without_organisations_covers_everything_the_login_sees():
    assert search_scope([], "2026-01-01") == "is:pr is:open created:>=2026-01-01"


def test_search_scope_names_each_organisation():
    assert search_scope(["acme", "acme-labs"], "2026-01-01") == "is:pr is:open org:acme org:acme-labs created:>=2026-01-01"


@pytest.mark.parametrize(
    "reader, message",
    [
        (read_github_team, "org/team-slug"),
        (read_bitbucket, "workspace"),
        (read_public_slack, "MCP server"),
        (read_jira, "site URL"),
    ],
)
def test_unconfigured_source_is_not_connected_rather_than_failed(store, reader, message):
    with pytest.raises(NotConnectedError, match=message):
        asyncio.run(reader(store))


def test_empty_result_is_saved_only_for_sources_whose_empty_answer_means_no_work(store):
    engine = Engine(store, {"github": empty, "slack": empty})

    asyncio.run(engine.refresh("github"))
    asyncio.run(engine.refresh("slack"))

    assert ("github" in engine.saved, "slack" in engine.saved) == (True, False)


def test_switched_off_source_is_not_scheduled_or_started(store):
    engine = Engine(store, {"github": empty, "slack": empty})
    set_source_enabled(store, "slack", False)

    assert engine.due() == ["github"]
    with pytest.raises(ValueError, match="turned off"):
        engine.start(["slack"])


def test_switched_off_source_leaves_the_queue_and_health_list(store):
    engine = Engine(store, {"github": empty, "jira": empty})
    engine.live["github"] = [Item(key="https://github.com/o/r/pull/1", title="PR", source="github", status="open", live=True, opened_at="2099-01-01T00:00:00+00:00")]
    set_source_enabled(store, "github", False)

    snapshot = engine.snapshot()

    assert (snapshot["items"], [source["source"] for source in snapshot["sources"]]) == ([], ["jira"])


def test_stored_work_stays_when_its_source_is_switched_off(store):
    # An agent's proposal through MCP carries a source name such as claude, which may well be off.
    store.ingest([Item(key="slack:a", title="Ask", source="slack"), Item(key="slack:b", title="Mine", source="slack", status="open")])
    engine = Engine(store, {"slack": empty})
    set_source_enabled(store, "slack", False)

    assert [item.key for item in engine.items()] == ["slack:a", "slack:b"]


def test_source_missing_its_optional_extra_is_not_connected(store):
    missing = Source("extra", "Extra", plugin_read, extras=("mcp",), available=lambda: False)
    engine = Engine(store, {"extra": empty}, {"extra": missing})

    asyncio.run(engine.refresh("extra"))

    assert engine.states["extra"].state == "not_connected" and "worktray[mcp]" in engine.states["extra"].detail


def test_state_carries_labels_groups_and_views_for_the_ui(store):
    engine = Engine(store, {"github": empty})

    snapshot = engine.snapshot()

    assert (snapshot["source_labels"]["github"], snapshot["source_groups"]["github"], snapshot["views"]) == ("GitHub", "pr", {"oncall": False, "team": False})
