# Adding a built-in source

Most new sources fit best as a plugin package; see [Writing a source plugin](../plugins.md). The contract below is the same for both.

1. Create `worktray/sources/<name>.py` with `async def read_<name>(store: Store) -> Batch`. Local-file readers can be sync, `def read_<name>(home: Path, days: int = 100) -> Batch`, and are wrapped in `asyncio.to_thread`.
2. Declare what the user must provide as module-level `Setting` and `Secret` objects, with a `validate` function where a value can be checked. Collect them in `FIELDS` and `SECRETS`.
3. Raise `NotConnectedError` when a required value is blank, and `SourceError` with an actionable message when a read fails.
4. Build `Item(key="<name>:<stable id>", source="<name>", ...)`. Source-owned items set `live=True, status="open"`; proposals leave `live=False` and set `list_name`.
5. Optionally write `check_<name>(store) -> str` that makes the smallest read and returns a sentence.
6. Add one `Source` row to `BUILTIN` in `worktray/sources/registry.py`: name, label, reader wrapper, interval, description, `group`, `empty_is_valid` for a live source whose empty answer means "no work", settings, secrets and check. If it signs in through another source, set `uses` instead of repeating fields.
7. Add a row to the README source table and each new variable to the configuration table, then add tests.

The engine, the Settings page, `worktray auth`, `worktray sources` and `worktray config` pick the source up from its row.

## Gotchas

- Only sources with `empty_is_valid=True` save a snapshot for an empty result; for the rest an empty batch leaves the last snapshot alone.
- Every read is cancelled after 900 seconds.
- Setting keys are global: pick a key prefixed with the source name.
