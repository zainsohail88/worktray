# Architecture

worktray is one Python package with one command.

- `worktray serve` runs the web server. It is the only process that syncs sources.
- `worktray mcp` runs an MCP server over stdio. It reads and writes the same SQLite file but never syncs.
- `worktray auth`, `worktray sources` and `worktray config` change settings from a terminal.

## Components

| Component | Does | File |
|---|---|---|
| CLI | Parses commands and starts the right part | `worktray/cli.py` |
| Paths | The data folder, from the platform default or `WORKTRAY_HOME` | `worktray/paths.py` |
| Config | `Setting`, `Secret` and the on/off switch per source, each read from `WORKTRAY_*` first | `worktray/config.py` |
| Keyring | Secrets in the system keyring, one service name per data folder | `worktray/auth/keyring_store.py` |
| Registry | Every source, built in or plugin, with its label, reader, settings, secrets, schedule and checks | `worktray/sources/registry.py` |
| Sources | One reader per system, each returning a `Batch` | `worktray/sources/` |
| Engine | One task per source that is on, the scheduler, the last good snapshots and the team view | `worktray/engine.py` |
| Store | SQLite storage and the item lifecycle rules | `worktray/store.py` |
| Web app | Routes, Host and Origin checks, static UI | `worktray/web/app.py` |
| Settings routes | Describe sources, save settings and secrets, run checks and browser sign-ins | `worktray/web/settings.py` |
| MCP server | Lets agents list, add, propose, snooze, start and finish items | `worktray/mcp_server.py` |
| Service | launchd agent on macOS, systemd user service on Linux | `worktray/service.py` |

## Sync flow

```
scheduler tick or POST /api/refresh
        │
Engine.start ─▶ one asyncio task per source that is on (900 s timeout)
        │
   Source.read(store, home) ─▶ Batch
        │
   ┌────┴─────────────────────────────┐
 live items                      stream items
 Store.save_snapshot             Store.ingest
 (replaced on each success)      (inserted if new, decisions kept)
   └────┬─────────────────────────────┘
        │
 Engine.items / snapshot ─▶ GET /api/state ─▶ UI
```

- `NotConnectedError` marks the source "not connected", not as an error. Its saved snapshot is dropped.
- Any other exception records `error` health and keeps the previous snapshot, with `stale_since` set.
- Only `SourceError` text reaches the user. Other exceptions are logged and shown by type with a generic message.
- A source that is off is never scheduled or started and its live items leave the queue. Stored items stay, proposals included, in the dashboard and in the MCP server (`worktray/engine.py::visible_items`).

## Settings flow

The Settings page calls `GET /api/config`. It describes each source from its registry row: fields with their saved values, secrets as set or not set and whether an environment variable locks a field.

`POST /api/config/{source}` checks and saves values. Secrets go to the keyring. Keyring calls run in a worker thread. Saving a non-empty value switches the source on, unless it was switched off before.

`check`, `connect` and `disconnect` run the source's own functions and return a sentence. `worktray auth` and `worktray config` use the same declarations from the terminal.

## Entry points

- `worktray.cli:main`: the `worktray` command and `python -m worktray`
- `worktray.web.app:create_app`: the FastAPI app
- `worktray.engine:create_engine`: wires every registered source
- `worktray.sources.registry:discover`: built-in sources plus `worktray.sources` entry points

To add a source, see "Adding a source" in [CONTRIBUTING.md](../CONTRIBUTING.md).
