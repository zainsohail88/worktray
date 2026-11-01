## What and why

<!-- What this changes and why. Link an issue if there is one, such as Fixes #123. -->

## How it was tested

<!-- The commands you ran and what you tried in the app. For a source change, the service or CLI you tested against. -->

## Checklist

- [ ] `uv run pytest --cov` passes
- [ ] `uv run ruff check worktray tests` and `uv run ruff format --check worktray tests` pass
- [ ] New behaviour has tests, including error cases
- [ ] New settings are declared on their source and listed in `docs/configuration.md`
- [ ] Docs and `CHANGELOG.md` are updated if users see a change
- [ ] No tokens, internal hostnames or workplace data in code, tests or screenshots
