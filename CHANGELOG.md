# Changelog

## 0.1.0

First public release.

- Local dashboard for Jira, Confluence, GitHub, Bitbucket, Google Calendar, Gemini meeting notes, Slack, TeamCity and local coding-agent sessions.
- Every source can be switched on or off, and configured in the Settings page, with `worktray config`, or with `WORKTRAY_*` environment variables. Sources start off and switch on when you set them up. Tokens, including the Google and Public Slack sign-ins, are kept in the system keyring and never sent back to the browser.
- Third-party sources through the `worktray.sources` entry point.
- One `worktray` command: `serve`, `auth`, `sources`, `config`, `mcp` and `service`.
- Data lives in the per-user data folder, or `WORKTRAY_HOME`.
- Background service through launchd on macOS and systemd on Linux.
- MCP server for coding agents, in the optional `mcp` extra.
