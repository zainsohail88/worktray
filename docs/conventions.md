# Conventions

## Sources

- A reader raises on failure. An empty `Batch` means there is no work (`worktray/engine.py::Engine.refresh`).
- A source that is not set up raises `NotConnectedError`. The page shows it as not connected.
- `SourceError` text is shown to the user as written. Keep tokens and raw API responses out of it.
- HTTP calls go through `connections.get_json`, which retries a 429 up to three times. CLI calls go through `connections.cli_json`, which times out after 45 seconds and hides stderr.
- A pagination loop fails when the cursor stops moving.
- Titles go through `short_title`, which redacts text that looks like a secret.
- Nothing about one organisation is hard-coded. Organisations, workspaces, URLs, epic names and servers are `Setting`s on the source that needs them.

## Settings and secrets

- Each `Setting` and `Secret` is declared once on its source and read through it. Keys are unique across all sources.
- `WORKTRAY_<KEY>` overrides a saved value and locks the field in the Settings page.
- A setting with a `validate` function normalises the value or raises `ValueError` with a sentence the user can act on.
- Secrets are written only to the keyring. No route, CLI listing or log line prints one.

## Store

- User decisions win. Inserts use `INSERT OR IGNORE`, so a stored item keeps the user's decisions (`worktray/store.py::Store.ingest`).
- Each method's docstring states the invariant it protects. Keep that when adding methods.

## Auth

- Google counts as connected only when `<data folder>/oauth/google.enabled` exists.
- Token renewals are serialised across processes with `flock` on `<data folder>/oauth/<profile>.lock`.
- On macOS, keychain writes update the entry in place, because the `keyring` setter deletes before adding (`worktray/auth/secure_keychain.py`). That module loads Apple frameworks, so it is imported only on macOS.

## Web

- Blocking I/O runs in `asyncio.to_thread`.
- `ValueError` maps to 400 or 409 and `KeyError` to 404.
- The UI has no build step and no inline script, so the Content-Security-Policy stays `script-src 'self'`.

## Tests

- Tests live in `tests/test_<module>.py`. `tests/conftest.py` gives every test a temporary data folder, an in-memory keyring and no `WORKTRAY_*` variables.
- Use the `store` fixture, which has every built-in source switched on, or `fresh_store` for a first start with every source off.
- Web routes are tested in process with FastAPI's `TestClient`, without starting the scheduler.
- Tests that need the `mcp` extra skip when it is not installed, so the suite runs without it.
- Fixtures use made-up names: `acme`, `ABC-123`, `Alex Example`, `example.com`.
