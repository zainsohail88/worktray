# Contributing to worktray

## Development setup

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) on macOS or Linux.

```sh
git clone https://github.com/zainsohail88/worktray && cd worktray
uv sync --all-extras
```

| Command | What it does |
|---|---|
| `uv run pytest --cov` | Runs the tests and fails below the coverage floor in `pyproject.toml` |
| `uv run ruff check worktray tests` | Lint |
| `uv run ruff format worktray tests` | Formats the code. CI runs it with `--check`. |
| `WORKTRAY_HOME=/tmp/worktray-dev uv run worktray serve --port 8799 --open` | Runs the app with a separate data folder, so your own items and keyring entries are not touched |

The design notes in [docs/index.md](docs/index.md) explain how worktray is built.

## Rules

- Use made-up names in code, tests, docs and screenshots, such as `acme`, `ABC-123`, `Alex Example` and `example.com`. No real hostnames, ticket keys, people or tokens.
- Anything that differs between users is a `Setting` or a `Secret` declared on its source, never a value in code.
- No route, log line or error message may contain a token.
- Tests do not use the network, your keyring or your data folder. `tests/conftest.py` gives every test a temporary folder and an in-memory keyring. Use the `store` fixture, which has every source on, or `fresh_store`, which has every source off.
- Add type hints to every function and a docstring to every public one. Comments explain why, not what.

## Adding a source

A source is a `read` function and a `Source` row that declares its label, settings, tokens, schedule and connection check. The engine, Settings, `worktray auth`, `worktray sources` and `worktray config` all read the row, so nothing else needs editing.

You can add a source in two ways:

- Built in: a module in `worktray/sources/` and a row in `BUILTIN` in `worktray/sources/registry.py`.
- As a plugin: a separate Python package that exposes its `Source` rows through the `worktray.sources` entry point. A plugin imports only from `worktray.plugin`, as the rest of worktray can change between versions.

### Plugin example

`pyproject.toml`:

```toml
[project]
name = "worktray-linear"
version = "0.1.0"
dependencies = ["worktray>=0.1", "httpx"]

[project.entry-points."worktray.sources"]
linear = "worktray_linear:SOURCE"
```

`worktray_linear/__init__.py`:

```python
import httpx

from worktray.plugin import QUICK, Batch, Item, NotConnectedError, Secret, Setting, Source, SourceError, Store

TEAM = Setting("linear_team", "Linear team key", placeholder="ENG")
TOKEN = Secret("linear_api_key", "Linear API key", help="Settings, API, Personal API keys in Linear.")


async def read(store: Store, home) -> Batch:
    key = TOKEN.read()
    if not key:
        raise NotConnectedError("Not set up yet. Add a Linear API key in Settings.")
    query = '{ viewer { assignedIssues(filter: {state: {type: {nin: ["completed", "canceled"]}}}) { nodes { identifier title url createdAt } } } }'
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.linear.app/graphql", json={"query": query}, headers={"Authorization": key})
    if response.status_code != 200:
        raise SourceError(f"Linear returned HTTP {response.status_code}. Check the API key.")
    issues = response.json()["data"]["viewer"]["assignedIssues"]["nodes"]
    return Batch(
        items=[
            Item(key=f"linear:{issue['identifier']}", source="linear", title=issue["title"][:240], url=issue["url"],
                 status="open", live=True, opened_at=issue["createdAt"], lane="needs_me")
            for issue in issues
        ],
        detail=f"{len(issues)} open Linear issues assigned to you",
    )


async def check(store: Store) -> str:
    await read(store, None)
    return "Connected to Linear"


SOURCE = Source(
    "linear", "Linear", read, QUICK,
    description="Open Linear issues assigned to you.",
    group="jira", empty_is_valid=True,
    settings=(TEAM,), secrets=(TOKEN,), check=check,
)
```

Install it next to worktray and restart worktray:

```sh
uv tool install 'worktray @ git+https://github.com/zainsohail88/worktray' --with worktray-linear
```

Linear then shows in Settings, `worktray sources` and `worktray config`. Its variables are `WORKTRAY_LINEAR_TEAM` and `WORKTRAY_LINEAR_API_KEY`.

### What a source must do

- `read(store, home)` is async and returns a `Batch`. `home` is the user's home folder, for sources that read local files. Run blocking work with `asyncio.to_thread`. worktray cancels a read after 900 seconds.
- Raise instead of returning a partial result. Raise `NotConnectedError` when the source is not set up, `SignInRequired` when a browser sign-in would fix it and `SourceError` for anything else. The message shows in the app, so make it something the user can act on and keep tokens and response bodies out of it.
- An empty `Batch` means there is nothing to do. It replaces the last saved result when `empty_is_valid=True` or when the source already has a saved result.
- Items with `live=True, status="open"` belong to the source and are replaced on every successful sync. Items with `live=False` are proposals that the user accepts or dismisses. worktray keeps those decisions by `key`, so keys must not change between syncs.
- Keys start with the source name and a colon, such as `linear:ENG-12`.
- Links must use `https://`, or `http://` to `localhost`, `127.0.0.1` or `::1`.
- Source names use lower-case letters, digits and underscores and start with a letter.
- Setting keys must be unique across all sources. Start them with the source name. worktray keeps `home`, `port`, `sources`, every key that starts with `source_` and its own preferences such as `team_jql` and `display_name`.
- `Setting.read(store)` and `Secret.read()` return the environment variable first, checked with the setting's `validate`, then the saved value. Validators for common shapes are in `worktray/config.py`: `web_url`, `name_list`, `single_name`, `team_slug`, `plain_text` and `command_line`.
- Set `web=False` on a setting that decides which program runs. Settings then shows it but cannot change it.
- `uses` names another source whose sign-in this one shares, instead of repeating its fields.
- `group` sets the type label and colour: `meeting`, `pr`, `jira`, `slack`, `notes`, `confluence` or `agent`. Any other word shows as itself.
- `check(store)` is optional. It makes the smallest read that proves the login works and returns a sentence such as "Connected to Linear".
- `connect(store)` and `disconnect(store)` are optional and add a browser sign-in. Pass the sign-in link to `open_sign_in(url, label)`, which hands it to the Settings page.
- `extras` and `available` declare an optional package the source needs. If `available()` returns false or raises, the source shows as not connected with the install command.

worktray skips a plugin and logs the reason when the plugin fails to import, its factory raises, it returns something other than `Source` rows or it breaks a naming rule above.

### Built-in source checklist

1. Write the reader in `worktray/sources/NAME.py`. A reader of local files can be a plain function, which the registry runs with `asyncio.to_thread`.
2. Declare the settings and tokens as module-level `Setting` and `Secret` objects.
3. Add the `Source` row to `BUILTIN` in `worktray/sources/registry.py`.
4. Add `tests/test_NAME.py` covering a working read, not set up, a refused login and a server error. Use `httpx.MockTransport` instead of the network.
5. Add a row to `docs/sources.md` and each new variable to `docs/configuration.md`. `tests/test_docs.py` fails if either is missing.

## Pull requests

1. Branch from `main`.
2. Keep each pull request to one change.
3. Run the tests, lint and format check before you push.
4. Open the pull request against `main` and fill in the template. CI must pass: lint and format, tests on macOS and Linux with Python 3.12 and 3.13, the install without extras, the package build, the dependency audit and CodeQL.
5. Changes to `.github/`, `LICENSE` and `SECURITY.md` also need the owner's review. See `.github/CODEOWNERS`.

## Releasing

1. Update `version` in `pyproject.toml` and add a section to `CHANGELOG.md`.
2. Merge to `main`, then push a tag `vX.Y.Z` that matches the version.
3. The release workflow tests and builds the package, publishes it to PyPI and creates the GitHub release.

## Publishing the demo

The `Dockerfile` builds the demo: worktray with made-up data and read-only settings. CI builds and tests the image on every pull request.

To publish it on Google Cloud Run:

1. Create a Google Cloud project with billing turned on. Cloud Run needs billing even when use stays within the free allowance.
2. Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install) and sign in with `gcloud auth login`.
3. From the repository folder, run:

   ```sh
   gcloud run deploy worktray-demo --source . --region us-central1 --allow-unauthenticated --max-instances 1 --project PROJECT_ID
   ```

   The first run asks to turn on the APIs it needs. Cloud Build builds the image from the `Dockerfile`.

`--max-instances 1` keeps one copy running at most, so every visitor sees the same data and use cannot grow past one instance. Set a budget alert on the project as well.

## License

By contributing, you agree that your contributions are licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE).
