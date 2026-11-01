# Security policy

## Reporting a vulnerability

Do not open a public issue for a security problem. Report it privately on the [Security tab](https://github.com/zainsohail88/worktray/security/advisories/new) of this repository. Only the maintainers can see the report.

Include:

- what the problem is and where it is (file, route, source or workflow)
- the steps or input that reproduce it
- what an attacker could do with it
- the version from `worktray --version` and your operating system

Leave out real tokens and workplace data.

You get a reply within 7 days. Fixes go to the code on `main`. Once a fix is released, the advisory credits you unless you ask to stay anonymous.

## Scope

In scope:

- the dashboard and its HTTP routes, such as a way for a web page or another user to read or change your items, settings or tokens
- how tokens are stored, read and shown: the keyring, Settings, `worktray config`, logs and error messages
- the built-in sources, such as a ticket, pull request or meeting note that runs code, injects content into the page or makes worktray contact another host
- the MCP server (`worktray mcp`) and the background service files
- the GitHub Actions workflows in `.github/workflows/`

Out of scope:

- third-party source plugins. Report those to their authors.
- someone who already has a shell on your machine as your user. worktray has no login of its own, so do not run it on a shared machine.
- problems in Jira, GitHub, Google or the other services worktray reads, unless worktray makes them worse

## How worktray protects your data

- The dashboard listens only on `127.0.0.1`. It refuses requests with any other `Host` header, which blocks DNS rebinding. Every change must come from the same origin.
- API tokens, the Google sign-in and the Public Slack sign-in are stored in the system keyring. No route returns a saved token. The database and the data folder hold no tokens.
- Every source is off until you turn it on.
- The Codex command can only be set from the terminal or an environment variable, so a web page cannot make worktray run a program.
- URL settings must use `https://`, or `http://` to `localhost`, `127.0.0.1` or `::1`. worktray parses the host and refuses URLs with a user name or password. Environment variables are checked the same way.
- Every source only reads. worktray reads message and document text in memory and keeps only titles and links.
- Responses carry a strict Content-Security-Policy with no inline scripts, `X-Frame-Options: DENY` and `Cache-Control: no-store`.
- The Slack and Tidy-up suggestions sources run the Codex CLI in a read-only sandbox and check its output against a schema.
- CI pins every action to a commit SHA, scans the code and the workflows with CodeQL and audits the dependencies on every pull request.
