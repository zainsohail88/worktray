# Commands

| Command | What it does |
|---|---|
| `worktray serve [--port N] [--open]` | Starts the dashboard. This is the default command. |
| `worktray serve --demo` | Starts a demo with made-up data. See [Demo](#demo). |
| `worktray auth [SOURCE ...]` | Sets up sources in the terminal. Add `--check` to only test them, or `--reconnect` to sign in again. |
| `worktray sources` | Lists the sources. `worktray sources enable NAME` and `worktray sources disable NAME` turn one on or off. |
| `worktray config` | Lists the settings. `worktray config set KEY VALUE` saves one and `worktray config unset KEY` clears it. For a token, leave out the value and type it when asked. |
| `worktray mcp` | Runs the MCP server for coding agents |
| `worktray service ACTION` | Manages the background service. Actions: `install`, `uninstall`, `restart`, `status`, `logs`, `print`. |

## Demo

`worktray serve --demo` runs the dashboard with made-up data in a temporary folder. It does not read your data folder, keyring or accounts, and Settings cannot be changed. Changes made in the demo are lost when it stops.

The demo can listen beyond this computer, with `--host 0.0.0.0`. The normal dashboard refuses any address other than this computer.

## Background service

`worktray service install` starts worktray at login and restarts it if it crashes. It uses launchd on macOS and a systemd user service on Linux.

Stop any `worktray serve` you started in a terminal before you install it, as both use the same port.

The service file holds only the port, the data folder and `PATH`. Save tokens in Settings rather than as environment variables when you use the service.

## Coding agents

worktray can run as an MCP server, so a coding agent such as Claude Code can read and update your worktray items. The agent can list your items, add, snooze and propose items, write a standup note, brief a meeting and mark its own tasks as started or finished. An agent cannot close your other items. It can only suggest closing them, and you confirm in worktray.

1. Install the MCP extra:

   ```sh
   uv tool install 'worktray[mcp] @ git+https://github.com/zainsohail88/worktray'
   ```

2. Add worktray to your coding agent's MCP settings:

   ```json
   {
     "mcpServers": {
       "worktray": { "command": "worktray", "args": ["mcp"] }
     }
   }
   ```

The agent starts `worktray mcp` when it needs it. You do not run it yourself.
