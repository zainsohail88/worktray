## What and why

<!-- What does this change, and what problem does it solve? Link an issue if there is one (Fixes #123). -->

## How it was tested

<!-- Commands you ran and what you tried in the app. For a source change, say which service or CLI you tested against. -->

## Checklist

- [ ] `uv run pytest --cov` passes (coverage stays at or above the floor in `pyproject.toml`)
- [ ] `uv run ruff check worktray tests` and `uv run ruff format --check worktray tests` pass
- [ ] New behaviour has tests, including error cases
- [ ] New settings are declared on their source and listed in `docs/configuration.md`
- [ ] Docs and CHANGELOG updated, if behaviour users see changed
- [ ] No tokens, internal hostnames or workplace data in code, tests, fixtures or screenshots
