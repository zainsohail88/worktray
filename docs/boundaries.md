# Boundaries

Every write route needs `Origin` equal to `{scheme}://{Host}` or it returns 403, and any `Host` other than `localhost` or `127.0.0.1` returns 400 (`worktray/web/app.py`). There is no token or cookie auth. `/docs` and `/openapi.json` are disabled.

## HTTP routes

| Route | Description |
|---|---|
| `GET /` and `/static/*` | Single-page UI: `index.html`, `app.js`, `settings.js`, `style.css`, manifest and icons |
| `GET /api/state` | Personal items, team view, health of switched-on sources, labels, groups, views, metrics, intervals |
| `POST /api/refresh` | `{"sources": [..] \| null}`. 202 with started names; `null` starts every switched-on source; unknown or switched-off names are 400 |
| `GET /api/standup` | Slack-formatted note: closures since the last working day, starred work, next meeting |
| `GET /api/brief?key=` | Open tickets, PRs and action items naming a calendar event. 404 for an unknown event |
| `POST /api/items` | Creates `manual:<key>`; an existing key is a silent no-op |
| `PATCH /api/items` | Edits a stream item or annotates a live one. 404 when not in view, 409 on a forbidden transition |
| `POST /api/suggestions` | Accepts or rejects a cleanup suggestion |
| `POST /api/settings` | `{"team_jql"}`: saves the team scope and refreshes Jira |
| `POST /api/settings/refresh-interval` | `{source, seconds \| null}`; seconds in 600, 1800, 3600, 7200, 14400 |
| `POST /api/settings/auto-refresh` | `{enabled}`: pauses or resumes scheduled refreshes |
| `POST /api/team/exclusions` | `{owner_id, excluded}` |
| `GET /api/config` | Every source with its fields, secrets (set or not, never the value), lock state and abilities |
| `POST /api/config/{source}` | `{enabled?, settings?, secrets?, clear?}`. 400 for unknown or invalid fields, 403 for a terminal-only setting such as `codex_command`, 409 for a field an environment variable decides, 503 when the keyring is unavailable. Saving a non-empty value switches the source on unless it was switched off explicitly |
| `POST /api/config/{source}/check` | Runs the source's login check. Always 200 with `{ok, detail}` |
| `POST /api/config/{source}/connect` | Runs a browser sign-in, up to 200 seconds. The sign-in link is handed to the page rather than opened on the server, which may have no display |
| `GET /api/config/{source}/sign-in-link` | `{url}`: the link a running Connect waits on, empty otherwise; the page polls it and offers the link |
| `POST /api/config/{source}/disconnect` | Removes a saved browser sign-in |

## MCP tools

`tracker_list`, `tracker_queue`, `tracker_snooze`, `standup_note`, `meeting_brief`, `tracker_started`, `tracker_finished`, `tracker_add`, `tracker_propose` (`worktray/mcp_server.py`). The queue leaves out live work from sources that are switched off; stored items stay, as in the dashboard (`worktray/engine.py::visible_items`).

## Command line

`worktray serve | auth | sources | config | mcp | service` (`worktray/cli.py`).

## Environment

`WORKTRAY_HOME`, `WORKTRAY_PORT`, `WORKTRAY_SOURCES`, `WORKTRAY_SOURCE_<NAME>_ENABLED`, and `WORKTRAY_<KEY>` for every setting and secret a source declares. The README lists them all; a test keeps that list complete.

## External calls

| Target | Used by |
|---|---|
| Jira REST v3, Jira dev-status, JSM Ops API | jira, oncall, upstream |
| Confluence REST | confluence |
| Google Calendar and Drive APIs, Google OAuth | calendar, gemini |
| `gh api` | github, github_team, upstream |
| `bkt api --context <workspace>` | bitbucket, upstream |
| `codex exec` in a read-only sandbox | slack, cleanup |
| The configured MCP server's search tool | public_slack |
| TeamCity REST | teamcity, and failing-check detail for github and bitbucket |

## Local files

| Path | Holds |
|---|---|
| `<data folder>/tracker.sqlite3` | Items, decisions, annotations, snapshots, health, settings, suggestions |
| `<data folder>/oauth/` | `google.enabled` marker, lock files, the public Slack MCP token store |
| `<data folder>/worktray.log` | Service log on macOS |
| System keyring, service `worktray.<hash of data folder>` | Secrets and the Google grant |
| `~/.codex`, `~/.claude`, Cursor and Claude app folders | Read-only session lists |
| `~/Library/LaunchAgents/io.github.worktray.server.plist` or `~/.config/systemd/user/worktray.service` | Written by `worktray service install` |
