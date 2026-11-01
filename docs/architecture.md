# Architecture

worktray is one Python package with one command. `worktray serve` runs the web server, which is the only process that refreshes sources. `worktray mcp` runs a stdio MCP server that reads and writes the same SQLite file but never refreshes. `worktray auth`, `sources` and `config` change settings from a terminal.

## Components

| Component | Responsibility | Source |
|---|---|---|
| CLI | Parses commands and starts the right part | `worktray/cli.py` |
| Paths | The data folder: per-user default or `WORKTRAY_HOME` | `worktray/paths.py` |
| Config | `Setting`, `Secret` and the per-source on/off switch, each read from `WORKTRAY_*` first | `worktray/config.py` |
| Keyring | Secret storage in the system keyring, one service name per data folder | `worktray/auth/keyring_store.py` |
| Registry | Every source, built in or plugin, with its label, reader, settings, secrets, schedule and checks | `worktray/sources/registry.py` |
| Sources | One reader per system, each returning a `Batch` | `worktray/sources/` |
| Engine | One task per switched-on source, the scheduler, last good snapshots, the team view | `worktray/engine.py` |
| Store | SQLite persistence and item lifecycle rules | `worktray/store.py` |
| Web app | Routes, Host and Origin checks, static UI | `worktray/web/app.py` |
| Settings routes | Describe sources, save settings and secrets, run checks and browser sign-ins | `worktray/web/settings.py` |
| MCP server | Lets agents list, add, propose, snooze, start and finish items | `worktray/mcp_server.py` |
| Service | launchd agent on macOS, systemd user unit on Linux | `worktray/service.py` |

## Refresh flow

```
scheduler tick or POST /api/refresh
        │
Engine.start ─▶ one asyncio task per switched-on source (900 s timeout)
        │
   Source.read(store, home) ─▶ Batch
        │
   ┌────┴─────────────────────────────┐
 live items                      stream items
 Store.save_snapshot             Store.ingest
 (replaced on each success)      (insert if new; human decisions kept)
   └────┬─────────────────────────────┘
        │
 Engine.items / snapshot ─▶ GET /api/state ─▶ UI
```

A source that raises `NotConnectedError` is shown as "not connected" and is not an error; its saved snapshot is dropped, since it no longer reflects a working login. Any other exception records `error` health and keeps the previous snapshot with `stale_since` set. Only `SourceError` text reaches the user; other exceptions show their type and a generic message and are logged.

A source that is switched off is never scheduled or started, its live items leave the queue, and its unanswered proposals leave triage. Items the user already accepted stay.

## Settings flow

The Settings page calls `GET /api/config`, which describes each source from its registry row: fields with their saved values, secrets as set or not set, and whether an environment variable locks a field. `POST /api/config/{source}` validates and saves values; secrets go to the keyring. `check`, `connect` and `disconnect` run the source's own functions and report a sentence. `worktray auth` and `worktray config` use the same declarations from the terminal.

## Entry points

- `worktray.cli:main`: the `worktray` command and `python -m worktray`
- `worktray.web.app:create_app`: the FastAPI app
- `worktray.engine:create_engine`: wires every registered source
- `worktray.sources.registry:discover`: built-in sources plus `worktray.sources` entry points
