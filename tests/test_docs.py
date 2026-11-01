"""The README's configuration table must name every variable a built-in source reads."""

from pathlib import Path

from worktray.sources.registry import BUILTIN

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


def test_readme_lists_every_setting_and_secret_variable():
    variables = {field.env for source in BUILTIN for field in (*source.settings, *source.secrets)}

    assert sorted(name for name in variables if f"`{name}`" not in README) == []


def test_readme_lists_every_built_in_source():
    assert [source.label for source in BUILTIN if source.label not in README] == []
