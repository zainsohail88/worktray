"""Every source in one table: its name, label, reader, schedule, settings and connection hooks.

Adding a built-in source means writing a `read_<name>` function and one `Source` row here. A
third-party package adds one by publishing a `worktray.sources` entry point that resolves to a
`Source` or an iterable of them. The engine, the Settings page, the Connections tab and the
`worktray auth` command all read this table, so nothing else needs editing.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
import logging
from pathlib import Path
import re

from worktray.auth import google_login
from worktray.config import Secret, Setting
from worktray.models import Batch
from worktray.sources import atlassian, bitbucket, codex, github, oncall, public_slack, streams, teamcity
from worktray.sources.bitbucket import read_bitbucket
from worktray.sources.calendar import read_calendar
from worktray.sources.cleanup import read_cleanup
from worktray.sources.github import read_github, read_github_team
from worktray.sources.jira import read_jira
from worktray.sources.oncall import read_oncall
from worktray.sources.public_slack import read_public_slack
from worktray.sources.sessions import read_claude, read_codex, read_cursor, read_desktop
from worktray.sources.streams import read_confluence, read_gemini, read_slack
from worktray.sources.teamcity import read_teamcity
from worktray.sources.upstream import read_upstream
from worktray.store import Store

Reader = Callable[[Store, Path], Awaitable[Batch]]
Action = Callable[[Store], Awaitable[str]]
ENTRY_POINT_GROUP = "worktray.sources"

# Seconds between scheduled refreshes. Agent-backed sources cost AI tokens on each run, so they default slowest.
QUICK = 600
STEADY = 1800
SLOW = 3600

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    """One adapter, how the engine treats it, and what the user must provide to connect it."""

    name: str
    label: str
    read: Reader
    interval: int = STEADY
    description: str = ""
    # The Type column and filter group this source's items with others of the same kind.
    group: str = ""
    # A live source whose empty result is a real answer ("no open PRs") saves that empty snapshot;
    # a stream source's empty result just means nothing new was proposed.
    empty_is_valid: bool = False
    busy: str = "Reading source"
    settings: tuple[Setting, ...] = ()
    secrets: tuple[Secret, ...] = ()
    # Another source whose login this one reuses, so the Settings page points there instead of repeating fields.
    uses: str = ""
    # Verifies the login with a small read and returns a sentence.
    check: Action | None = None
    # Starts a browser sign-in on this machine and returns a sentence once the grant is saved.
    connect: Action | None = None
    disconnect: Action | None = None
    # Optional dependency extras this source needs, such as ("mcp",).
    extras: tuple[str, ...] = ()
    available: Callable[[], bool] = lambda: True


def _sync(reader: Callable[..., Batch], *extra: object) -> Reader:
    return lambda store, home: asyncio.to_thread(reader, home, 100, *extra)


BUILTIN: tuple[Source, ...] = (
    Source(
        "jira",
        "Jira",
        lambda store, home: read_jira(store),
        QUICK,
        group="jira",
        empty_is_valid=True,
        description="Tickets assigned to you or reported by you, plus your team's tickets for the Team view.",
        settings=atlassian.FIELDS,
        secrets=atlassian.SECRETS,
        check=atlassian.check_jira,
    ),
    Source(
        "oncall",
        "On call",
        lambda store, home: read_oncall(store),
        STEADY,
        group="jira",
        empty_is_valid=True,
        description="Your team's on-call epic and your shift from Jira Service Management.",
        settings=oncall.FIELDS,
        uses="jira",
    ),
    Source("confluence", "Confluence", lambda store, home: read_confluence(store), STEADY, group="confluence", description="Pages and comments that mention you.", uses="jira"),
    Source(
        "github",
        "GitHub",
        lambda store, home: read_github(store),
        QUICK,
        group="pr",
        empty_is_valid=True,
        description="Pull requests waiting for your review and your own pull requests. Uses your gh login.",
        settings=github.FIELDS,
        check=github.check_github,
    ),
    Source(
        "github_team",
        "GitHub team",
        lambda store, home: read_github_team(store),
        STEADY,
        group="pr",
        empty_is_valid=True,
        description="Your team's open pull requests, for the Team view.",
        settings=github.TEAM_FIELDS,
        uses="github",
    ),
    Source(
        "bitbucket",
        "Bitbucket",
        lambda store, home: read_bitbucket(store),
        STEADY,
        group="pr",
        empty_is_valid=True,
        description="Pull requests in one Bitbucket workspace. Uses your bkt login.",
        busy="Going through every repository. This can take a few minutes.",
        settings=bitbucket.FIELDS,
        check=bitbucket.check_bitbucket,
    ),
    Source(
        "calendar",
        "Google Calendar",
        lambda store, home: read_calendar(),
        QUICK,
        group="meeting",
        empty_is_valid=True,
        description="Your meetings for the next two weeks.",
        settings=google_login.FIELDS,
        check=google_login.check_google,
        connect=google_login.connect_google,
        disconnect=google_login.disconnect_google,
    ),
    Source(
        "gemini",
        "Meeting notes",
        lambda store, home: read_gemini(store),
        STEADY,
        group="notes",
        description="Your action items from Gemini meeting notes in Google Drive.",
        settings=streams.FIELDS,
        uses="calendar",
    ),
    Source(
        "slack",
        "Slack",
        lambda store, home: read_slack(store),
        SLOW,
        group="slack",
        description="Asks and promises from your DMs and threads, found by a Codex agent with Slack access.",
        settings=codex.FIELDS,
        check=codex.check_codex,
    ),
    Source(
        "public_slack",
        "Public Slack",
        lambda store, home: read_public_slack(store),
        SLOW,
        group="slack",
        description="Mentions in public channels, through your team's Slack search server.",
        settings=public_slack.FIELDS,
        check=public_slack.check_public_slack,
        connect=public_slack.connect_public_slack,
        disconnect=public_slack.disconnect_public_slack,
        extras=("mcp",),
        available=public_slack.mcp_available,
    ),
    Source("upstream", "Finished work", lambda store, home: read_upstream(store), QUICK, description="Offers to close an ask when the ticket or pull request it mentions is done."),
    Source("cleanup", "Tidy-up suggestions", lambda store, home: read_cleanup(store), SLOW, description="A Codex agent suggests merges, clearer titles, due dates and things to close.", uses="slack"),
    Source(
        "teamcity",
        "TeamCity",
        lambda store, home: read_teamcity(store),
        STEADY,
        description="Shows why a TeamCity build failed on your pull requests.",
        settings=teamcity.FIELDS,
        secrets=teamcity.SECRETS,
        check=teamcity.check_teamcity,
    ),
    Source("codex", "Codex", lambda store, home: asyncio.to_thread(read_codex, home, 100, store), QUICK, group="agent", description="Your recent Codex sessions, so you can track them as work."),
    Source("claude", "Claude Code", _sync(read_claude), QUICK, group="agent", description="Your recent Claude Code sessions, so you can track them as work."),
    Source("cursor", "Cursor", _sync(read_cursor), QUICK, group="agent", description="Your recent Cursor chats, so you can track them as work."),
    Source("claude_desktop", "Claude Desktop", _sync(read_desktop), QUICK, group="agent", description="Your recent Claude Desktop sessions, so you can track them as work."),
)


# Keys worktray keeps for itself: its own environment variables (WORKTRAY_HOME, WORKTRAY_PORT,
# WORKTRAY_SOURCES) and the preferences it stores next to the ones sources declare.
RESERVED_KEYS = frozenset(
    {
        "home",
        "port",
        "sources",
        "auto_refresh",
        "refresh_intervals",
        "team_exclusions",
        "team_jql",
        "team_scope_origin",
        "display_name",
        "jira_account_id",
        oncall.ON_CALL_SETTING,
        oncall.ONCALL_EPIC_SETTING,
        streams.MEETING_BACKFILLED_SETTING,
    }
)
SOURCE_NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")


def _load(entry: EntryPoint) -> list[Source]:
    """A plugin's sources, or none when loading or calling it fails; a broken plugin must not stop the app."""
    try:
        loaded = entry.load()
        found = loaded() if callable(loaded) and not isinstance(loaded, Source) else loaded
        sources = [found] if isinstance(found, Source) else list(found) if isinstance(found, Iterable) else []
    except Exception:  # noqa: BLE001
        logger.exception("Source plugin %s failed to load", entry.name)
        return []
    bad = [source for source in sources if not isinstance(source, Source)]
    if bad or not sources:
        logger.error("Source plugin %s did not return Source objects", entry.name)
        return []
    return sources


def _keys(source: Source) -> list[str]:
    return [field.key for field in (*source.settings, *source.secrets)]


def _problem(source: Source, found: dict[str, Source], taken: set[str]) -> str:
    keys = _keys(source)
    if not SOURCE_NAME.fullmatch(source.name):
        return f"its name {source.name!r} is not lower-case letters, digits and underscores"
    if source.name in found or source.name == "manual":
        return f"the name {source.name!r} is taken"
    clash = sorted((taken | RESERVED_KEYS) & set(keys) | {key for key in keys if key.startswith("source_")})
    if clash:
        return f"the settings {', '.join(clash)} are taken"
    if len(set(keys)) != len(keys):
        return "it declares the same setting twice"
    return ""


def discover(plugins: Iterable[EntryPoint] | None = None) -> dict[str, Source]:
    """Built-in sources first, then plugins; a plugin cannot replace a built-in name or reuse a setting key."""
    found = {source.name: source for source in BUILTIN}
    taken = {key for source in BUILTIN for key in _keys(source)}
    for entry in entry_points(group=ENTRY_POINT_GROUP) if plugins is None else plugins:
        for source in _load(entry):
            problem = _problem(source, found, taken)
            if problem:
                logger.error("Source plugin %s skipped: %s", entry.name, problem)
                continue
            found[source.name] = source
            taken |= set(_keys(source))
    # A source that borrows another's sign-in needs that one to exist; plugins may name each other in any order.
    while missing := [name for name, source in found.items() if source.uses and source.uses not in found]:
        for name in missing:
            logger.error("Source %s skipped: it signs in through %s, which is not installed", name, found[name].uses)
            del found[name]
    return found


def is_available(source: Source) -> bool:
    """Whether the source's optional packages are installed; a check that fails counts as not available."""
    try:
        return bool(source.available())
    except Exception:  # noqa: BLE001 - a plugin's check must not break the Settings page
        logger.exception("Source %s failed its availability check", source.name)
        return False


def field_index(sources: dict[str, Source]) -> dict[str, tuple[Source, Setting | Secret]]:
    """Every setting and secret by key, with the source that declares it."""
    return {field.key: (source, field) for source in sources.values() for field in (*source.settings, *source.secrets)}


def check_for(sources: dict[str, Source], source: Source) -> Action | None:
    """A source that signs in through another one is checked through that one."""
    if source.check:
        return source.check
    parent = sources.get(source.uses)
    return parent.check if parent else None


_registry: dict[str, Source] | None = None


def registry() -> dict[str, Source]:
    global _registry
    if _registry is None:
        _registry = discover()
    return _registry


def use_registry(sources: dict[str, Source] | None) -> None:
    """Replace the process-wide registry; tests pass their own, None rediscovers."""
    global _registry
    _registry = sources
