<div align="center">
  <img src="img/logo-mark.png" alt="worktray logo" height="120">
  <h1>worktray</h1>
  <p>Your work, in view.</p>
</div>

worktray is a local, single-user dashboard. It collects your work from Jira, GitHub, Bitbucket, Google Calendar, meeting notes, Slack and AI coding agents into one queue that says whose move each item is. It runs on your own machine, reads every source with your own logins, and keeps only titles and links.

Turn on only the sources you use. Everything is configured in the browser or with environment variables, and other packages can add sources as plugins.

> **License.** worktray is source available under the [PolyForm Noncommercial License 1.0.0](LICENSE). Personal, hobby, research, educational and non-profit use is free. Commercial use is not permitted under this license.

- [Features](#features)
- [Install](#install)
- [Sources](#sources)
- [Configuration](#configuration)
- [Commands](#commands)
- [Connect an agent](#connect-an-agent)
- [Data and privacy](#data-and-privacy)
- [Platform support](#platform-support)
- [Extending](#extending)
- [Documentation](#documentation)

## Features

**My work.** One sortable table of meetings, pull requests, tickets and follow-ups, and a second table to triage proposals from notes, Slack and agent sessions.

- **Needs me** and **Waiting** chips split work you can move from work a reviewer, assignee or build holds.
- Star an item for **Up next**, snooze it until this afternoon, tomorrow or after the next meeting, or dismiss it.
- The strip above the table shows the next meeting, your free time before it, and a **Brief** of the tickets and PRs that name it.
- An ask that names one of your tickets or pull requests folds under that row. Asks naming someone else's ticket show where it stands, such as `ABC-123 In Testing · 1 PR merged`.
- **Tidy-up suggestions** list merges, links, clearer titles, due dates and closures an agent proposes. Nothing changes until you accept.
- Keyboard: `j`/`k` move, `s` star, `a` accept, `d` done, `x` dismiss, `z` snooze, `e` edit, `b` brief, `/` search, `?` for the list.

**On call.** Many teams keep operational work under one open Jira epic, often named KTLO ("keep the lights on"). This tab lists its open children with the ones that need attention first, and shows your Jira Service Management on-call shift.

**Team workload.** Recent tickets and pull requests per person, scoped by a Jira query you can edit.

**History.** Closed work by day, with a standup note you can copy into Slack.

**Connections.** Each source refreshes on its own schedule. A failed refresh keeps the last good result on screen and says when it went stale. A source you have not set up shows as "not connected", never as an error.

## Install

#### Requirements

| Tool | Minimum version | Needed for |
|------|-----------------|------------|
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Any current release | Installing and running worktray; it fetches Python 3.12 or later if needed |
| macOS or Linux | | Windows is not supported yet |
| A system keyring | | Saving tokens (built in on macOS; GNOME Keyring or KWallet on Linux) |
| [gh](https://cli.github.com/) | Any current release | Only the GitHub sources |
| [bkt](https://github.com/avivsinai/bitbucket-cli) | Any current release | Only the Bitbucket source |
| [Codex CLI](https://github.com/openai/codex) | Any current release | Only the Slack and tidy-up sources |

#### Install and run

```sh
uv tool install 'worktray[all]'
worktray serve --open
```

`worktray[all]` includes the optional MCP extra, which the agent MCP server and the Public Slack source need. Plain `worktray` installs everything else.

Then open **Settings**, switch on the sources you use, and fill in their fields. Each source has a **Test connection** button, and Google and Public Slack have **Sign in**.

To run from a clone instead:

```sh
git clone https://github.com/zainsohail88/worktray && cd worktray
uv sync --all-extras
uv run worktray serve --open
```

## Sources

| Source | Reads | Needs |
|---|---|---|
| Jira | Your open tickets, tickets you reported, your team's scope | Site URL, email and API token |
| On call | Open children of your on-call epic and your JSM shift | The Jira connection |
| Confluence | Pages and comments that mention you, as proposals | The Jira connection |
| GitHub | Pull requests waiting on you or authored by you | The `gh` CLI, logged in |
| GitHub team | Open pull requests of one team's members | The `gh` CLI and a team as `org/team-slug` |
| Bitbucket | Pull requests across one workspace | The `bkt` CLI, logged in, and a workspace |
| Google Calendar | The next 14 days of your primary calendar | Your own Google OAuth Desktop client |
| Meeting notes | Action items with your name in Gemini notes on Drive | The Google connection, a Drive folder and your names |
| Slack | Private asks and promises, found by a Slack-connected Codex agent | The `codex` CLI |
| Public Slack | Public-channel mentions, through an MCP server that indexes Slack | The `mcp` extra and that server's URL |
| Finished work | Whether tickets and PRs named by your asks have finished | Jira, GitHub or Bitbucket |
| Tidy-up suggestions | Merges, links, titles and closures for your asks | The `codex` CLI |
| TeamCity | Build status text on failing checks | URL and access token |
| Codex, Claude Code, Cursor, Claude Desktop | Recent local sessions, as proposals | Nothing; read from local files |

### Google

Google requires each user to bring an OAuth client:

1. In [Google Cloud](https://console.cloud.google.com/apis/credentials), create a project, enable the Drive and Calendar APIs, and create an OAuth client of type **Desktop**.
2. Download the client JSON. Put it in `~/Downloads`, or enter its path in the Google Calendar settings.
3. Click **Sign in** on the Google Calendar card, or run `worktray auth calendar`, and approve read-only Drive and Calendar access.

### Public Slack

If your organisation runs an MCP server that indexes Slack, enter its URL and your name as people @-mention you, then click **Sign in** once. The sign-in is kept in the system keyring and renewed before it expires. Also enter the name of the server's search tool. It must accept `query`, `source_types` and `time_cutoff` and return `results` with `content`, `url` and `updated_at`.

## Configuration

Every source starts switched off, so nothing is read or run until you choose it. Saving a source's settings in the Settings page, or setting it up with `worktray auth NAME` or `worktray config set`, switches it on; you can switch it off again at any time.

Every setting can be saved in the Settings page, with `worktray config set`, or exported as an environment variable. An exported variable wins and locks the field in the Settings page. Exported values are checked the same way as saved ones; one that fails shows its problem on the source's card.

The Codex command decides which program runs, so the Settings page shows it but can't change it. Set it with `worktray config set codex_command '...'` or `WORKTRAY_CODEX_COMMAND`.

Tokens are saved to the system keyring and are never sent back to the browser: the page only shows whether one is saved, with **Clear** to remove it.

| Variable | Meaning | Default |
|---|---|---|
| `WORKTRAY_HOME` | Folder for the database, sign-ins and log | Your user data folder (see below) |
| `WORKTRAY_PORT` | Port the dashboard listens on | `8765` |
| `WORKTRAY_SOURCES` | Comma-separated list of the only sources that are on | Unset: the Settings page decides |
| `WORKTRAY_SOURCE_<NAME>_ENABLED` | `on` or `off` for one source, such as `WORKTRAY_SOURCE_SLACK_ENABLED` | `off` until you switch it on |
| `WORKTRAY_JIRA_URL` | Jira site URL, such as `https://your-team.atlassian.net` | |
| `WORKTRAY_JIRA_EMAIL` | Atlassian account email | |
| `WORKTRAY_JIRA_API_TOKEN` | Atlassian API token (secret) | |
| `WORKTRAY_ONCALL_EPIC_NAME` | Word in the name of your on-call epic | `KTLO` |
| `WORKTRAY_GITHUB_ORGS` | Comma-separated GitHub organisations to read | Everything your login can see |
| `WORKTRAY_GITHUB_TEAM` | `org/team-slug` for the team view | Off |
| `WORKTRAY_BITBUCKET_WORKSPACE` | Bitbucket workspace to scan | Off |
| `WORKTRAY_BITBUCKET_CONTEXT` | The `bkt` login to use, by the name in `bkt context list` | bkt's default login |
| `WORKTRAY_GOOGLE_CLIENT_FILE` | Path to your Google OAuth client JSON | The only `client_secret*.json` in `~/Downloads` |
| `WORKTRAY_GOOGLE_ACCESS_TOKEN` | A short-lived Google access token, for testing only (secret) | |
| `WORKTRAY_MEETING_FOLDER` | Drive folder ID or URL with your meeting notes | |
| `WORKTRAY_MEETING_ALIASES` | Names or emails used on your action items, comma-separated | |
| `WORKTRAY_CODEX_COMMAND` | Command that runs Codex; not editable in the Settings page | `codex` |
| `WORKTRAY_CODEX_MODEL` | Model for agent-backed sources | `gpt-6-luna` |
| `WORKTRAY_CODEX_PROFILE` | Codex `--profile` | |
| `WORKTRAY_PUBLIC_SLACK_MCP_URL` | MCP server that searches public Slack | Off |
| `WORKTRAY_PUBLIC_SLACK_MCP_TOOL` | That server's search tool | Off |
| `WORKTRAY_SLACK_DISPLAY_NAME` | Your name as people @-mention you in Slack | Your Jira name, once Jira has synced |
| `WORKTRAY_TEAMCITY_URL` | TeamCity URL | Off |
| `WORKTRAY_TEAMCITY_TOKEN` | TeamCity access token (secret) | |

`worktray config` prints every setting, its variable, and whether it is set.

## Commands

```text
worktray serve [--port N] [--open]   start the dashboard (the default command)
worktray auth [SOURCE ...]           set up sources in the terminal; --check, --reconnect
worktray sources [enable|disable N]  list sources, or switch one on or off
worktray config [set|unset KEY [V]]  list settings, or save and clear one; omit V to type a secret hidden
worktray mcp                         serve MCP tools over stdio for coding agents
worktray service install             run in the background at login; also uninstall, restart, status, logs, print
```

`worktray service install` writes a launchd agent on macOS or a systemd user unit on Linux, and waits until the dashboard answers. It stops first if something else already holds the port, such as `worktray serve` in a terminal. Only the port, data folder and `PATH` (including the `PATH` of the shell you install from) go into that file, so keep tokens in the keyring rather than in exported variables when running as a service.

## Connect an agent

Agents can list your work and live queue, add, snooze and propose items, draft a standup, brief a meeting, report tasks they started, and close them with a result. Register the MCP server:

```json
{
  "mcpServers": {
    "worktray": { "command": "worktray", "args": ["mcp"] }
  }
}
```

## Data and privacy

- Your queue, decisions, settings and last source results live in a SQLite database in your user data folder: `~/Library/Application Support/worktray` on macOS, `~/.local/share/worktray` on Linux, or `WORKTRAY_HOME`.
- Tokens live in the system keyring, keyed by that folder, so two data folders never share a login. That includes the Google grant and the Public Slack sign-in.
- Every source is read-only. Message and document bodies are read to find tasks and then discarded; only titles and links are kept.
- The dashboard listens only on `127.0.0.1`, rejects other hostnames, and refuses writes from other origins. Settings that pick a program to run can only be changed from the terminal.
- Agent-backed sources send item titles and links to the Codex CLI you configure. Turn them off if that is not acceptable.

## Platform support

- macOS and Linux, Python 3.12 or later.
- Tokens need a keyring backend. macOS has one built in. On Linux, `keyring` uses Secret Service (GNOME Keyring, KWallet). On a headless machine without one, export tokens as `WORKTRAY_*` variables instead.
- The local session readers look under `~/Library/Application Support` on macOS and `~/.config` on Linux.
- Windows is not supported yet.

## Extending

A source is one `read` function plus one `Source` row that declares its label, settings, secrets, schedule and connection check. Built-in sources live in `worktray/sources/registry.py`. A separate package can add sources through the `worktray.sources` entry point; see [docs/plugins.md](docs/plugins.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) to work on worktray itself, and [docs/](docs/index.md) for the design notes.

## Documentation

| Topic | |
|-------|-|
| [Architecture](docs/architecture.md) | How the engine, sources, store and web page fit together |
| [Boundaries](docs/boundaries.md) | Every HTTP route and MCP tool, and what each accepts |
| [Data model](docs/data-model.md) | The SQLite tables and what is kept in each |
| [Writing a plugin](docs/plugins.md) | Adding a source from a separate package, with the full contract |
| [Conventions](docs/conventions.md) | Code and test conventions |
| [Glossary](docs/glossary.md) | The words used in the code and the UI |
| [Contributing](CONTRIBUTING.md) | Local setup, adding a source, the PR process |
| [Security](SECURITY.md) | Reporting a vulnerability, and how worktray protects your tokens |
