# Technical vision

## Principles

- Local. One person on one machine. The dashboard listens on `127.0.0.1`, the database is a file in the user's data folder and tokens stay in the system keyring.
- Read-only. worktray never writes to Jira, GitHub, Slack or any other source. It reads, summarises and links back.
- User decisions win. Once the user accepts, dismisses or closes an item, no sync can undo it. A sync replaces only what the source owns.
- A failed sync never shows as an empty list. The last good result stays on screen with its age.
- Every source is optional and starts off. A source that is not set up shows as not connected, not as an error.

## Decisions

- Each source is one `Source` row that declares its reader, settings, secrets, schedule and checks. The engine, the Settings page and the CLI all read that row, so adding a source touches one place. Plugins add rows through an entry point.
- GitHub and Bitbucket are read through `gh` and `bkt`, so worktray uses the logins people already have.
- Private Slack and tidy-up suggestions are handled by a Codex agent in a read-only sandbox. Its output is checked against a JSON schema before anything is stored.
- Items are Pydantic models stored as JSON in SQLite, so a new field needs no migration. Each store method opens its own short connection.
- The UI is plain HTML, CSS and two script files with no build step, which keeps a strict Content-Security-Policy possible.

## Next

- Windows support: a portable file lock, a Task Scheduler service and Windows session paths.
- More sources as plugins, starting with issue trackers and code hosts that are not covered yet.
- `worktray.plugin` is the API to keep stable.
