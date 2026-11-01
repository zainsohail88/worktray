# Sources

Every source starts off. Turn on the ones you use in **Settings**, or with `worktray auth NAME` in a terminal.

| Source | Reads | Needs |
|---|---|---|
| Jira | Tickets assigned to you or reported by you, and your team's tickets | Site URL, email and [API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| On call | Open tickets under your on-call epic, and your shift | The Jira source |
| Confluence | Pages and comments that mention you | The Jira source |
| GitHub | Pull requests waiting for your review, and your own | [`gh`](https://cli.github.com/), signed in |
| GitHub team | Open pull requests of one team's members | `gh` and a team as `org/team-slug` |
| Bitbucket | Pull requests in one workspace | [`bkt`](https://github.com/avivsinai/bitbucket-cli), signed in, and a workspace name |
| Google Calendar | Your meetings for the next 14 days | Your own Google OAuth client (see below) |
| Meeting notes | Your action items from Gemini meeting notes in Google Drive | Google Calendar signed in, the Drive folder, and the names your action items use |
| Slack | Asks and promises in your DMs and threads | [Codex CLI](https://github.com/openai/codex), with Slack access |
| Public Slack | Mentions of you in public channels | An MCP server that searches Slack, and the MCP extra (see below) |
| Finished work | Whether the tickets and pull requests your asks mention are done | Jira, GitHub or Bitbucket |
| Tidy-up suggestions | Suggested merges, titles and closures for your items | Codex CLI |
| TeamCity | Why a TeamCity build failed on your pull requests | TeamCity URL and access token |
| Codex, Claude Code, Cursor, Claude Desktop | Your recent sessions in each app | Nothing; read from local files |

The Slack and Tidy-up sources send item titles and links to the Codex CLI.

## Google

Google needs an OAuth client of your own:

1. In [Google Cloud](https://console.cloud.google.com/apis/credentials), create a project, enable the Google Drive and Google Calendar APIs, and create an OAuth client of type **Desktop**.
2. Download the client JSON file. Put it in `~/Downloads`, or enter its path in the Google Calendar settings.
3. Click **Sign in** on the Google Calendar card, or run `worktray auth calendar`, and approve read-only access.

## Public Slack

This source needs an MCP server that can search your Slack, run by your organisation, and the MCP extra:

```sh
uv tool install 'worktray[mcp] @ git+https://github.com/zainsohail88/worktray'
```

In the Public Slack settings, enter:

- the server URL
- the name of its search tool
- your name as it appears in Slack mentions

Then click **Sign in**.

The search tool must accept `query`, `source_types` and `time_cutoff`, and return `results` where each result has `content`, `url` and `updated_at`.

## Adding a source

Other Python packages can add sources. See [Writing a source plugin](plugins.md).
