# Configuration

## Where settings come from

worktray uses the first value it finds:

1. An environment variable, such as `WORKTRAY_JIRA_URL`. This locks the field in Settings.
2. The value saved in Settings, or with `worktray config set`.
3. The default.

Tokens are saved in the system keyring. Settings shows whether a token is saved.

Set the Codex command with `worktray config set codex_command '...'` or `WORKTRAY_CODEX_COMMAND`. Settings shows it read-only, as it decides which program worktray runs.

`worktray config` lists every setting with its variable and current value.

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `WORKTRAY_HOME` | Folder for the database and log | See [Data](#data) |
| `WORKTRAY_PORT` | Port the dashboard listens on | `8765` |
| `WORKTRAY_SOURCES` | Comma-separated list of the sources that are on. All others are off. | Not set |
| `WORKTRAY_SOURCE_<NAME>_ENABLED` | `on` or `off` for one source, such as `WORKTRAY_SOURCE_SLACK_ENABLED` | `off` |
| `WORKTRAY_JIRA_URL` | Jira site URL, such as `https://your-team.atlassian.net` | |
| `WORKTRAY_JIRA_EMAIL` | Atlassian account email | |
| `WORKTRAY_JIRA_API_TOKEN` | Atlassian API token | |
| `WORKTRAY_ONCALL_EPIC_NAME` | A word in the name of your on-call epic | `KTLO` |
| `WORKTRAY_GITHUB_ORGS` | GitHub organisations to read, comma-separated | All repositories you can see |
| `WORKTRAY_GITHUB_TEAM` | Team for the Team tab, as `org/team-slug` | |
| `WORKTRAY_BITBUCKET_WORKSPACE` | Bitbucket workspace to read | |
| `WORKTRAY_BITBUCKET_CONTEXT` | The `bkt` login to use, from `bkt context list` | The `bkt` default |
| `WORKTRAY_GOOGLE_CLIENT_FILE` | Path to your Google OAuth client JSON | The only `client_secret*.json` in `~/Downloads` |
| `WORKTRAY_GOOGLE_ACCESS_TOKEN` | A Google access token, for testing only | |
| `WORKTRAY_MEETING_FOLDER` | Drive folder ID or URL with your meeting notes | |
| `WORKTRAY_MEETING_ALIASES` | Names or emails on your action items, comma-separated | |
| `WORKTRAY_CODEX_COMMAND` | Command that runs Codex | `codex` |
| `WORKTRAY_CODEX_MODEL` | Model for the Slack and Tidy-up suggestions sources | `gpt-6-luna` |
| `WORKTRAY_CODEX_PROFILE` | Codex `--profile` to use | |
| `WORKTRAY_PUBLIC_SLACK_MCP_URL` | URL of the MCP server that searches Slack | |
| `WORKTRAY_PUBLIC_SLACK_MCP_TOOL` | Name of that server's search tool | |
| `WORKTRAY_SLACK_DISPLAY_NAME` | Your name as it appears in Slack mentions | Your Jira name |
| `WORKTRAY_TEAMCITY_URL` | TeamCity URL | |
| `WORKTRAY_TEAMCITY_TOKEN` | TeamCity access token | |

## Data

worktray keeps its database in:

- macOS: `~/Library/Application Support/worktray`
- Linux: `~/.local/share/worktray`
- The folder in `WORKTRAY_HOME`, if set

The database holds your items, decisions, settings and the last result from each source. From messages and documents, worktray keeps only titles and links.

Tokens stay in the system keyring, separately for each data folder. On a Linux machine with no keyring, set tokens as environment variables.

The dashboard listens only on `127.0.0.1`.
