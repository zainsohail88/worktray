# Commands

```text
worktray serve [--port N] [--open]   start the dashboard (the default command)
worktray auth [SOURCE ...]           set up sources in the terminal; --check, --reconnect
worktray sources [enable|disable N]  list sources, or turn one on or off
worktray config [set|unset KEY [V]]  list settings, or save or clear one; leave out V to type a token hidden
worktray mcp                         run the MCP server for coding agents
worktray service install             run worktray in the background at login
```

## Background service

`worktray service install` starts worktray at login and restarts it if it crashes. It uses launchd on macOS and a systemd user service on Linux.

Stop any `worktray serve` you started in a terminal first, because both use the same port.

Other actions: `uninstall`, `restart`, `status`, `logs`, `print`.

The service file contains only the port, the data folder and `PATH`. Save tokens in the Settings page, not as environment variables, when using the service.

## Coding agents

Coding agents can read and update your worktray items over MCP: list your items, add and snooze items, propose new ones, draft a standup, brief a meeting, and mark their own tasks as started or finished.

This needs the `mcp` extra, which `worktray[all]` includes. Add worktray to your agent's MCP configuration:

```json
{
  "mcpServers": {
    "worktray": { "command": "worktray", "args": ["mcp"] }
  }
}
```
