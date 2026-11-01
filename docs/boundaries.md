# Boundaries

Every write route needs `Origin` equal to `{scheme}://{Host}`, or it returns 403. Any `Host` other than `localhost` or `127.0.0.1` returns 400 (`worktray/web/app.py`). There is no token or cookie authentication. `/docs`, `/redoc` and `/openapi.json` are turned off.

## HTTP routes

| Route | Does |
|---|---|
| `GET /` and `/static/*` | The single-page UI: `index.html`, `app.js`, `settings.js`, `style.css`, the manifest and icons |
| `GET /api/state` | Personal items, team view, health of the sources that are on, labels, groups, views, metrics and intervals |
| `POST /api/refresh` | `{"sources": [..] \| null}`. Returns 202 with the names started. `null` starts every source that is on. An unknown or switched-off name returns 400 |
| `GET /api/standup` | A Slack-formatted note: items closed since the last working day, starred work and the next meeting |
| `GET /api/brief?key=` | Open tickets, pull requests and action items that name a calendar event. 404 for an unknown event |
| `POST /api/items` | Creates `manual:<key>`. An existing key is ignored |
| `PATCH /api/items` | Edits a stream item or annotates a live one. 404 when the item is not in view, 409 on a forbidden status change |
| `POST /api/suggestions` | Accepts or rejects a tidy-up suggestion. 404 when it is no longer pending |
| `POST /api/settings` | `{"team_jql"}`. Saves the team scope and syncs Jira if Jira is on. Returns the sources started |
| `POST /api/settings/refresh-interval` | `{source, seconds \| null}`. Seconds is one of 600, 1800, 3600, 7200 or 14400 |
| `POST /api/settings/auto-refresh` | `{enabled}`. Pauses or resumes scheduled syncs |
| `POST /api/team/exclusions` | `{owner_id, excluded}` |
| `GET /api/config` | Every source with its fields, secrets (set or not, never the value), lock state and actions |
| `POST /api/config/{source}` | `{enabled?, settings?, secrets?, clear?}`. 400 for an unknown or invalid field, 403 for a terminal-only setting such as `codex_command`, 409 for a field set by an environment variable, 503 when the keyring is unavailable |
| `POST /api/config/{source}/check` | Runs the source's login check. Always 200 with `{ok, detail}` |
| `POST /api/config/{source}/connect` | Runs a browser sign-in, for up to 200 seconds. The sign-in link goes to the page, not to a browser on the server |
| `GET /api/config/{source}/sign-in-link` | `{url}`. The link a running sign-in is waiting on, or empty. The page polls it |
| `POST /api/config/{source}/disconnect` | Removes a saved browser sign-in |

## MCP tools

`tracker_list`, `tracker_queue`, `tracker_snooze`, `standup_note`, `meeting_brief`, `tracker_started`, `tracker_finished`, `tracker_add` and `tracker_propose` (`worktray/mcp_server.py`). The queue leaves out live items from sources that are off and keeps stored items, the same as the dashboard.

## Command line

`worktray serve | auth | sources | config | mcp | service` (`worktray/cli.py`).

## Environment

`WORKTRAY_HOME`, `WORKTRAY_PORT`, `WORKTRAY_SOURCES`, `WORKTRAY_SOURCE_<NAME>_ENABLED` and `WORKTRAY_<KEY>` for every setting and secret a source declares. [Configuration](configuration.md) lists them all and `tests/test_docs.py` keeps that list complete.

## External calls

| Target | Used by |
|---|---|
| Jira REST v3, Jira dev-status, Jira Service Management Ops API | jira, oncall, upstream |
| Confluence REST | confluence |
| Google Calendar and Drive APIs, Google OAuth | calendar, gemini |
| `gh api` | github, github_team, upstream |
| `bkt api`, with `--context` only when `bitbucket_context` is set | bitbucket, upstream |
| `codex exec` in a read-only sandbox, run in a temporary folder | slack, cleanup |
| The configured MCP server's search tool | public_slack |
| TeamCity REST | teamcity, plus the failing-check detail for github and bitbucket |

## Local files

| Path | Holds |
|---|---|
| `<data folder>/tracker.sqlite3` | Items, decisions, annotations, snapshots, health, settings and suggestions |
| `<data folder>/oauth/` | The `google.enabled` marker and the Google lock file |
| `<data folder>/worktray.log` | Service log on macOS. On Linux the log is in the systemd journal |
| System keyring, service `worktray.<hash of data folder>` | Secrets, the Google grant and the Public Slack MCP sign-in |
| `~/.codex`, `~/.claude`, Cursor and Claude app folders | Session lists, read only |
| `~/Library/LaunchAgents/io.github.worktray.server.plist` or `~/.config/systemd/user/worktray.service` | Written by `worktray service install` |
