# Security Policy

worktray holds tokens for your work accounts, so security reports are welcome and taken seriously.

## Supported versions

Only the latest release on PyPI, and the code on `main`, get security fixes.

## Reporting a vulnerability

**Please don't open a public issue for security problems.**

Report it privately through GitHub instead: go to the **Security** tab of this repository and click **Report a vulnerability**, or use [this link](https://github.com/zainsohail88/worktray/security/advisories/new). Only the maintainers can see the report.

Please include:

- what the problem is and where it is (file, route, source or workflow)
- steps or an input that reproduces it
- what an attacker could do with it
- the version (`worktray --version`) and your platform

Leave out real tokens and workplace data.

You'll get an acknowledgement within 7 days. Once a fix is released we'll credit you in the advisory, unless you'd rather stay anonymous.

## Scope

In scope:

- the dashboard and its HTTP routes, e.g. a way for a web page or another user to read or change your queue, settings or tokens
- how tokens are stored, read and shown: the keyring, the Settings page, `worktray config`, logs and error messages
- the built-in sources, e.g. a crafted ticket, pull request or meeting note that runs code, escapes into the page or makes worktray contact another host
- the MCP server (`worktray mcp`) and the background service files
- the GitHub Actions workflows in `.github/workflows/` and the release to PyPI

Out of scope:

- third-party source plugins, which run with the same rights as worktray; report those to their authors
- anyone who already has a shell on your machine as you. worktray has no login of its own, so don't run it on a shared machine
- problems in Jira, GitHub, Google or the other services worktray reads, unless worktray makes them worse

## How worktray protects you

- The dashboard listens on `127.0.0.1` only. Requests with any other `Host` are refused, which blocks DNS rebinding, and every write must come from the same origin.
- Tokens are stored in the operating system keyring: API tokens, the Google grant and the Public Slack MCP sign-in. No route returns a saved token, and neither the database nor any file in the data folder holds a secret.
- Sources start switched off. Nothing is read, and no agent runs, until you switch a source on or set it up.
- A setting that decides which program runs, such as the Codex command, can't be changed through the web page, only from the terminal or the environment. Even a page that got past the host and origin checks couldn't make worktray run a program of its choosing.
- URL settings must be `https://`, or plain `http://` to `localhost`, `127.0.0.1` or `::1`. The host is parsed, not prefix-matched, and URLs with a user name or password are refused. Exported values are checked the same way.
- Every source is read-only. Message and document bodies are read in memory and discarded after extraction.
- Responses carry a strict Content-Security-Policy with no inline scripts, `X-Frame-Options: DENY` and `Cache-Control: no-store`.
- Agent-backed sources run the Codex CLI you configure in a read-only sandbox, and treat what it returns as data validated against a schema.
- CI pins every action to a commit SHA, scans the code and the workflows with CodeQL, and audits dependencies on every pull request. Releases reach PyPI through trusted publishing, so no upload token is stored in the repository.
