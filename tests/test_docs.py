"""The docs must name every variable and every source that worktray has."""

from pathlib import Path

from worktray.sources.registry import BUILTIN

DOCS = Path(__file__).resolve().parents[1] / "docs"
CONFIGURATION = (DOCS / "configuration.md").read_text()
SOURCES = (DOCS / "sources.md").read_text()


def test_configuration_lists_every_setting_and_secret_variable():
    variables = {field.env for source in BUILTIN for field in (*source.settings, *source.secrets)}

    assert sorted(name for name in variables if f"`{name}`" not in CONFIGURATION) == []


def test_sources_page_lists_every_built_in_source():
    assert [source.label for source in BUILTIN if source.label not in SOURCES] == []
