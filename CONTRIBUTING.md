# Contributing to worktray

Thanks for helping. This guide covers local setup, adding a source, and the PR process.

## Local setup

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) on macOS or Linux.

```sh
git clone https://github.com/zainsohail88/worktray && cd worktray
uv sync --all-extras                         # .venv with the app, the optional extras and dev tools
uv run pytest --cov                          # tests, with the coverage floor from pyproject.toml
uv run ruff check worktray tests             # lint
uv run ruff format worktray tests            # format; CI runs it with --check
```

Run the app against a scratch data folder so your real queue and keyring entries stay untouched:

```sh
WORKTRAY_HOME=/tmp/worktray-dev uv run worktray serve --port 8799 --open
```

## Adding a new source

Most new sources fit best as a separate plugin package, so they ship on their own schedule; [docs/plugins.md](docs/plugins.md) has a worked example and the full contract. A source most users of worktray would want can be built in.

Example: adding a built-in Linear source.

1. **Settings.** Declare what the user must provide in `worktray/sources/linear.py`: a `Setting` for each preference and a `Secret` for each token, with a validator where the value has a shape (`web_url`, `name_list`, `single_name`). Nothing organisation-specific goes in code.
2. **Reader.** Write `async def read_linear(store) -> Batch`. Raise `NotConnectedError` when it isn't set up, `SignInRequired` when a browser sign-in would fix it, and `SourceError` with a message the user can act on for anything else. Never return a partial result.
3. **Check.** Add `check_linear(store)`, the smallest read that proves the login works, returning a sentence such as "Connected to Linear as Alex".
4. **Registry.** Add one `Source` row in `worktray/sources/registry.py`. The Settings page, `worktray auth`, `worktray config` and the engine all read it, so nothing else needs editing.
5. **Tests.** Add `tests/test_linear.py`, covering the happy path, not set up, a refused login and a server error, with `httpx.MockTransport` instead of the network. CI fails if coverage drops below the floor.
6. **Docs.** Add a row to the Sources table and each variable to the configuration table in `README.md`. `tests/test_docs.py` fails if a variable is missing.

## Code style

- **ruff** for linting and formatting (`uv run ruff format` fixes most things).
- **Type hints** on all functions.
- **Docstrings** on public functions. Say what it does, and give an example when the input is not obvious.
- **Comments explain why**, not what. Plain words, no buzzwords.

## Ground rules

- **No workplace data.** Code, tests, fixtures, docs and screenshots use neutral names such as `acme`, `ABC-123`, `Alex Example` and `example.com`. No real hostnames, ticket keys, people or tokens.
- **Secrets never reach the browser.** No route, log line or error message may contain a token.
- **Tests don't touch the network, your keyring or your data folder.** `tests/conftest.py` points every test at a temporary folder and an in-memory keyring; use the `store` fixture, which has every source switched on, or `fresh_store` for a first start.

## Pull request process

1. Branch from `main`.
2. Keep each PR to one change: one source, one fix, and so on.
3. Run the commands under [Local setup](#local-setup) before pushing.
4. Open a PR into `main` and fill in the template. CI must pass: lint and format, tests on macOS and Linux with Python 3.12 and 3.13, the core install without extras, the package build, the dependency audit and CodeQL.
5. A maintainer reviews and merges. Changes to `.github/`, `LICENSE` and `SECURITY.md` also need the owner's review (see `.github/CODEOWNERS`).

## Releasing

1. Update `version` in `pyproject.toml` and add a section to `CHANGELOG.md`.
2. Merge to `main`, then push a tag `vX.Y.Z` that matches the version.
3. The release workflow checks, tests and builds, publishes to PyPI with trusted publishing, and creates the GitHub release.

## License

worktray is source available under the [PolyForm Noncommercial License 1.0.0](LICENSE). By contributing, you agree your contributions are licensed the same way.
