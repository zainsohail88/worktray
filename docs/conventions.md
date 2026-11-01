# Conventions

## Sources

- A reader raises on failure rather than returning a partial or empty `Batch`, because an empty batch means "no work" (`worktray/engine.py::Engine.refresh`).
- A source that is not set up raises `NotConnectedError`, which shows as "not connected" rather than an error.
- `SourceError` text is shown to the user verbatim; keep secrets and raw API bodies out of it.
- HTTP goes through `connections.get_json` (retries 429 up to three times) and CLI calls through `connections.cli_json` (45 second timeout, stderr hidden).
- Pagination loops fail when the cursor stops advancing.
- Titles pass through `short_title`, which redacts things that look like secrets.
- Nothing organisation-specific is hard-coded. Organisations, workspaces, URLs, epic names and servers are `Setting`s on the source that needs them.

## Settings and secrets

- Each `Setting` and `Secret` is declared once, on its source, and read through it. Keys are unique across all sources.
- The environment wins: `WORKTRAY_<KEY>` overrides a saved value and locks the field in the UI.
- Settings that can be checked have a `validate` function that normalises the value or raises `ValueError` with a sentence the user can act on.
- Secrets are written to the keyring only. No route, CLI listing or log line prints one.

## Store

- Human decisions win: inserts use `INSERT OR IGNORE`, and source data never overwrites a stream item (`worktray/store.py::Store.ingest`).
- Docstrings state the invariant each method protects; keep that when adding methods.

## Auth

- A Google grant counts as connected only when `<data folder>/oauth/google.enabled` exists.
- Token renewals are serialised across processes with `flock` on `<data folder>/oauth/<profile>.lock`.
- On macOS, keychain writes update in place, because keyring's setter deletes before adding (`worktray/auth/secure_keychain.py`). That module loads Apple frameworks and is imported only on macOS.

## Web

- Blocking I/O runs in `asyncio.to_thread`.
- `ValueError` maps to 400 or 409 and `KeyError` to 404.
- The UI has no build step and no inline script, so the Content-Security-Policy stays `script-src 'self'`.

## Tests

- Tests live in `tests/test_<module>.py`. `tests/conftest.py` gives every test a temporary data folder, an in-memory keyring and no `WORKTRAY_*` variables; use its `store` fixture.
- Web routes are tested in process with FastAPI's `TestClient`, without starting the scheduler.
- Tests that need the optional `mcp` extra skip when it is missing, so the core suite runs without it.
- Fixtures use neutral names: `acme`, `ABC-123`, `Alex Example`, `example.com`.
