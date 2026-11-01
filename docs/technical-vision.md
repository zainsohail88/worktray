# Technical vision

## Design philosophy

- **Local first.** One person, one machine. The dashboard listens on `127.0.0.1`, the database is a file in the user's data folder, and tokens stay in the system keyring. There is no server to trust.
- **Read-only.** worktray never writes to Jira, GitHub, Slack or any other source. It reads, summarises and links back.
- **Human decisions win.** Once a person accepts, dismisses or closes an item, no refresh can undo it. Source data replaces only what the source owns.
- **Honest freshness.** A failed refresh never turns into an empty list. The last good result stays on screen and says how old it is.
- **Pick what you use.** Every source is optional, configured in the browser or the environment, and absent sources stay quiet rather than red.

## Key decisions

- **Sources are data.** Each source is one `Source` row declaring its reader, settings, secrets, schedule and checks. The engine, the Settings page, the CLI and the docs table all derive from that row, so adding a source touches one place. Plugins use the same row through an entry point.
- **Existing CLIs for code hosts.** GitHub and Bitbucket are read through `gh` and `bkt`, reusing logins people already have instead of asking for another token.
- **Agents for unstructured text.** Private Slack and cleanup suggestions are delegated to a Codex agent in a read-only sandbox, and its output is validated against a JSON schema before anything is stored.
- **SQLite with JSON payloads.** Items are Pydantic models stored as JSON, so new fields need no migration. Each store method opens its own short connection.
- **No build step for the UI.** Plain HTML, CSS and two script files served as static assets, which keeps a strict Content-Security-Policy possible.

## Future direction

- Windows support: a portable file lock, a Task Scheduler service, and Windows session paths.
- More sources as plugins, starting with issue trackers and code hosts that are not covered today.
- The plugin API in `worktray.plugin` is the surface to keep stable.
