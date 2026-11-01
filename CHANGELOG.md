# Changelog

## 0.1.0

First public release.

- Dashboard for Jira, Confluence, GitHub, Bitbucket, Google Calendar, Gemini meeting notes, Slack, TeamCity and local coding agent sessions.
- Each source is off until you turn it on. Settings live in the Settings page, `worktray config` or `WORKTRAY_*` environment variables. Tokens are kept in the system keyring.
- Sources from other packages through the `worktray.sources` entry point.
- The `worktray` command: `serve`, `auth`, `sources`, `config`, `mcp` and `service`.
- Background service with launchd on macOS and systemd on Linux.
- MCP server for coding agents, in the `mcp` extra.
