# Writing a source plugin

A plugin is an ordinary Python package that adds one or more sources. worktray finds it through the `worktray.sources` entry point group, lists it in Settings with its own switch and fields, schedules it, and shows its items in the queue.

Import only from `worktray.plugin`. Everything else in worktray may change between minor versions.

## A complete example

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
        raise NotConnectedError("Not connected. Add a Linear API key in Settings.")
    query = '{ viewer { assignedIssues(filter: {state: {type: {nin: ["completed", "canceled"]}}}) { nodes { identifier title url createdAt } } } }'
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.linear.app/graphql", json={"query": query}, headers={"Authorization": key})
    if response.status_code != 200:
        raise SourceError(f"Linear returned HTTP {response.status_code}; check the API key")
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

Install it next to worktray (`uv tool install 'worktray[all]' --with worktray-linear`) and restart. Linear appears in Settings, in `worktray sources` and in `worktray config`, and its variables are `WORKTRAY_LINEAR_TEAM` and `WORKTRAY_LINEAR_API_KEY`.

## The contract

- **`read(store, home)`** is async and returns a `Batch`. `home` is the user's home folder, for sources that read local files. Run blocking work with `asyncio.to_thread`.
- **Raise, never return partial results.** An empty `Batch` means "nothing to do". With `empty_is_valid=True` it also replaces the previous snapshot. Raise `SourceError` with a message the user can act on, and `NotConnectedError` when the source is simply not set up yet. Keep tokens and raw response bodies out of messages; they are shown in the UI.
- **Live or proposed.** Items with `live=True, status="open"` belong to the source and are replaced on each successful refresh. Items with `live=False` are proposals the user accepts or dismisses; their decisions are kept forever, keyed by `key`, so keys must be stable.
- **Keys** start with the source name and a colon, such as `linear:ENG-12`.
- **Links** must be `https://`, or `http://` to `localhost`, `127.0.0.1` or `::1`. Other schemes and hosts are rejected.
- **Names** are lower-case letters, digits and underscores, starting with a letter, such as `linear`.
- **Settings and secrets** declare everything the user must provide. Setting keys must be unique across all sources, and worktray keeps some for itself: `home`, `port`, `sources`, anything starting with `source_`, and its own preferences such as `team_jql` and `display_name`. A plugin that breaks one of these rules, or reuses a source name, is skipped with a log message. `Setting.read(store)` and `Secret.read()` return the environment value first, checked with the setting's `validate`, then the saved one. Give a setting `web=False` when it decides which program runs; the Settings page then shows it without letting the browser change it.
- **`uses`** names another source whose sign-in this one shares. A plugin whose `uses` names a source that isn't installed is skipped.
- **Off until chosen.** Every source starts switched off. It switches on when the user saves its settings or sets it up with `worktray auth`.
- **`group`** picks the Type label and colour: `meeting`, `pr`, `jira`, `slack`, `notes`, `confluence` or `agent`. Any other word shows as itself.
- **`check(store)`**, optional, returns a sentence when the login works and raises otherwise. Raise `SignInRequired` when a browser sign-in would fix it; `worktray auth` then offers one. **`connect(store)`** and **`disconnect(store)`**, optional, run a browser sign-in and remove it. Hand the sign-in link to `open_sign_in(url, label)`, which passes it to the Settings page, since the server may have no screen.
- **`extras` and `available`** let a source depend on an optional package and say so instead of failing. An `available` that raises counts as not available.

A plugin that fails to import, whose factory raises, or that exports something other than `Source` objects, is skipped and logged; the rest of the app keeps working.
