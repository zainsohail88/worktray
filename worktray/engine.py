"""Independent refreshes with durable, explicitly stale source snapshots."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3

from worktray import install_command
from worktray.config import enabled_sources
from worktray.models import Batch, Item, SourceState, now, within_work_window
from worktray.references import linked_asks
from worktray.sources.cleanup import visible_suggestions
from worktray.sources.errors import NotConnectedError, SourceError
from worktray.sources.github import GITHUB_TEAM
from worktray.sources.oncall import ON_CALL_SETTING, ONCALL_EPIC_SETTING, OnCallShift
from worktray.sources.registry import Source, is_available, registry
from worktray.store import Store


INTERVAL_CHOICES = (600, 1800, 3600, 7200, 14400)
DEFAULT_INTERVAL = 1800
SCOPE_CHANGED = "Its settings changed. Sync to load it."
# Sources whose items fill the Team view; your own GitHub pull requests alone don't.
TEAM_SOURCES = frozenset({"jira", "github_team", "bitbucket"})

logger = logging.getLogger(__name__)


def visible_items(store: Store, live: dict[str, list[Item]], sources: Iterable[str]) -> list[Item]:
    """What the dashboard and the MCP server show: live work from switched-on sources, and every stored item.

    Stored items stay when their source is switched off, proposals included: you or an agent put
    them there, and only you decide them. The web page and the MCP server both call this, so they
    never disagree about what is in the queue.
    """
    on = enabled_sources(store, {*sources, *live})
    return [*store.current_live(batch for name, batch in live.items() if name in on), *store.items()]


def shift_now(raw: str, at: datetime | None = None) -> dict | None:
    """The saved on-call shift with current worked out now, or None once it has ended."""
    try:
        shift = OnCallShift.model_validate_json(raw) if raw else None
    except ValueError:
        return None
    current = at if at is not None else datetime.now(timezone.utc)
    if shift is None or datetime.fromisoformat(shift.ends_at) <= current:
        return None
    return {**shift.model_dump(), "current": datetime.fromisoformat(shift.starts_at) <= current}


class Engine:
    """A failed source cannot replace its last complete saved result."""

    def __init__(self, store: Store, adapters: dict[str, Callable[[], Awaitable[Batch]]], sources: dict[str, Source] | None = None) -> None:
        self.store = store
        self.adapters = adapters
        self.sources = sources if sources is not None else registry()
        self.live: dict[str, list[Item]] = {}
        self.saved = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.states = {state.source: state for state in store.health()}
        snapshots = store.snapshots()
        scopes = self._scopes()
        for name in adapters:
            state = self.states.setdefault(name, SourceState(source=name))
            state.state = "not_refreshed"
            state.detail = "Not synced since worktray started"
            state.stale_since = state.stale_since or state.last_success
            snapshot = snapshots.get(name)
            if snapshot and snapshot.scope == scopes.get(name, ""):
                self.live[name] = snapshot.items
                self.saved[name] = {"saved_at": snapshot.saved_at, "count": len(snapshot.items), "restored": True, "scope": snapshot.scope}
                state.last_success = snapshot.saved_at
                state.stale_since = snapshot.saved_at
                state.count = len(snapshot.items)
                state.detail = "Showing results from the last sync"
            elif snapshot:
                state.count = 0
                state.detail = SCOPE_CHANGED

    def active(self) -> list[str]:
        """Registered sources that are switched on, in registry order."""
        on = enabled_sources(self.store, self.adapters)
        return [name for name in self.adapters if name in on]

    def _scope_keys(self, source: str) -> list[str]:
        spec = self.sources.get(source)
        keys = [field.key for field in spec.settings] if spec else []
        return [*keys, "team_jql"] if source == "jira" else keys

    def _scope_values(self) -> dict[str, dict[str, str]]:
        """What each source's saved result depends on: its own settings, plus the team query for Jira.

        Changing any of them, say a different Jira site or GitHub organisation, means the saved
        result belongs to the old settings, so it is not shown. All sources are read in one query.
        """
        keys = {name: self._scope_keys(name) for name in self.adapters}
        saved = self.store.settings_named(key for found in keys.values() for key in found)
        exported = {field.key: field for spec in self.sources.values() for field in spec.settings if field.locked()}
        return {name: {key: os.environ[exported[key].env].strip() if key in exported else saved.get(key, "") for key in found} for name, found in keys.items()}

    def _scopes(self) -> dict[str, str]:
        return {name: json.dumps(values, sort_keys=True) if any(values.values()) else "" for name, values in self._scope_values().items()}

    def _scope(self, source: str) -> str:
        return self._scopes().get(source, "")

    def _changed_during(self, before: dict[str, str], source: str) -> bool:
        """Whether settings moved while a sync ran. Jira fills in a blank team query itself, which doesn't count."""
        after = self._scope_values().get(source, {})
        return any(after.get(key, "") != value and not (key == "team_jql" and not value) for key, value in before.items())

    def _invalidate_changed_scopes(self) -> None:
        if not self.saved:
            return
        scopes = self._scopes()
        for source, metadata in list(self.saved.items()):
            if metadata["scope"] != scopes.get(source, ""):
                self.live.pop(source, None)
                del self.saved[source]
                state = self.states[source]
                state.state = "not_refreshed"
                state.count = 0
                state.stale_since = state.last_success
                state.detail = SCOPE_CHANGED

    def intervals(self) -> dict[str, int | None]:
        """Seconds between scheduled refreshes per source; None means refresh only on request."""
        saved = json.loads(self.store.setting("refresh_intervals", "{}"))
        return {name: saved[name] if name in saved else (self.sources[name].interval if name in self.sources else DEFAULT_INTERVAL) for name in self.adapters}

    def set_interval(self, source: str, seconds: int | None) -> None:
        """Persist one source's schedule; None turns it off."""
        if source not in self.adapters:
            raise ValueError("Unknown refresh source")
        if seconds is not None and seconds not in INTERVAL_CHOICES:
            raise ValueError("Unsupported refresh interval")
        saved = json.loads(self.store.setting("refresh_intervals", "{}"))
        saved[source] = seconds
        self.store.save_setting("refresh_intervals", json.dumps(saved))

    def auto_refresh(self) -> bool:
        """Whether scheduled refresh runs at all; manual refresh is unaffected."""
        return self.store.setting("auto_refresh", "on") == "on"

    def set_auto_refresh(self, enabled: bool) -> None:
        """Pause or resume every scheduled refresh without losing the per-source intervals."""
        self.store.save_setting("auto_refresh", "on" if enabled else "off")

    def due(self, at: datetime | None = None) -> list[str]:
        """Switched-on sources whose last attempt is older than their interval, ignoring ones already running."""
        if not self.auto_refresh():
            return []
        current = at if at is not None else datetime.now(timezone.utc)
        due = []
        intervals = self.intervals()
        for name in self.active():
            seconds = intervals[name]
            state = self.states[name]
            if seconds is None or state.state == "refreshing":
                continue
            if state.last_attempt is None or (current - datetime.fromisoformat(state.last_attempt)).total_seconds() >= seconds:
                due.append(name)
        return due

    async def run_schedule(self, tick: float = 60) -> None:
        """Refresh due sources until cancelled, through start() so manual clicks never double up."""
        while True:
            try:
                self.start(self.due())
            except (sqlite3.Error, ValueError):
                # A locked database or a bad saved schedule must not end scheduling for the life of the process.
                logger.error("Scheduled refresh tick failed; retrying on the next tick", exc_info=True)
            await asyncio.sleep(tick)

    def start(self, sources: list[str] | None = None) -> list[str]:
        """Deduplicate overlapping button clicks without queuing duplicate work. None means every switched-on source."""
        selected = sources if sources is not None else self.active()
        if set(selected) - set(self.adapters):
            raise ValueError("Unknown refresh source")
        if set(selected) - enabled_sources(self.store, selected):
            raise ValueError("That source is turned off; turn it on in Settings first")
        started = []
        for source in selected:
            if source not in self.tasks or self.tasks[source].done():
                self.tasks[source] = asyncio.create_task(self.refresh(source))
                started.append(source)
        return started

    async def _read(self, source: str) -> Batch | BaseException:
        spec = self.sources.get(source)
        if spec is not None and not is_available(spec):
            return NotConnectedError(f"This needs an extra package. Run {install_command(spec.extras)}, then restart worktray.")
        return (await asyncio.gather(asyncio.wait_for(self.adapters[source](), timeout=900), return_exceptions=True))[0]

    async def refresh(self, source: str) -> None:
        """Capture adapter exceptions as health, never as an empty work list."""
        state = self.states[source]
        spec = self.sources.get(source)
        self._invalidate_changed_scopes()
        requested = self._scope_values().get(source, {})
        state.state = "refreshing"
        state.last_attempt = now()
        state.detail = spec.busy if spec else "Syncing…"
        result = await self._read(source)
        if self._changed_during(requested, source):
            result = SourceError("Its settings changed during the sync. Sync again.")
        if isinstance(result, NotConnectedError):
            # Signed out or set up no more: the old result is someone else's view now, so it goes.
            state.state = "not_connected"
            state.detail = str(result)
            state.count = 0
            state.stale_since = None
            self.live.pop(source, None)
            self.saved.pop(source, None)
            self.store.drop_snapshot(state)
            return
        elif isinstance(result, BaseException):
            state.state = "error"
            state.stale_since = state.stale_since or state.last_attempt
            if not isinstance(result, SourceError):
                logger.warning("Source %s failed", source, exc_info=result)
            state.detail = str(result) if isinstance(result, SourceError) else f"Something went wrong ({type(result).__name__}). Check the connection and try again."
        else:
            streams = [item for item in result.items if not item.live]
            self.store.ingest(streams)
            live = [item for item in result.items if item.live]
            state.state = "ok"
            state.last_success = now()
            state.stale_since = None
            state.count = len(result.items)
            state.detail = result.detail
            if live or (spec is not None and spec.empty_is_valid) or source in self.saved:
                snapshot = self.store.save_snapshot(source, live, state, self._scope(source))
                self.live[source] = snapshot.items
                self.saved[source] = {"saved_at": snapshot.saved_at, "count": len(live), "restored": False, "scope": snapshot.scope}
                return
            self.live[source] = live
        self.store.save_health(state)

    def items(self) -> list[Item]:
        """Live work from switched-on sources, with every stored item; see visible_items."""
        self._invalidate_changed_scopes()
        return visible_items(self.store, self.live, self.sources)

    def _team(self, items: list[Item]) -> list[dict]:
        visible = [item for item in items if item.status not in ("done", "dismissed")]
        eligible = [item for item in visible if item.source == "jira" and item.team_member and item.owner_active is not False and within_work_window(item.updated_at)]
        jira_ids = {item.owner_id for item in eligible if item.owner_id and item.owner_id != "unassigned"}
        email_ids = {item.owner_email.casefold(): item.owner_id for item in eligible if item.owner_email}
        inactive_ids = {item.owner_id for item in items if item.source == "jira" and item.owner_active is False}
        inactive_emails = {item.owner_email.casefold() for item in items if item.source == "jira" and item.owner_active is False and item.owner_email}
        exclusions = json.loads(self.store.setting("team_exclusions", "{}"))
        workload = [*eligible, *(item for item in visible if item.source in ("github", "bitbucket") and (item.team_member or item.owner_id in jira_ids or item.owner_email.casefold() in email_ids))]
        team = {}
        for item in workload:
            owner_id = email_ids.get(item.owner_email.casefold(), item.owner_id)
            if not owner_id or owner_id == "unassigned" or owner_id in inactive_ids or item.owner_email.casefold() in inactive_emails or owner_id in exclusions or item.owner_id in exclusions:
                continue
            owner = team.setdefault(owner_id, {"id": owner_id, "name": item.owner, "items": [], "jira": 0, "prs": 0, "aged": 0, "active": 0})
            owner["items"].append(item.model_dump())
            owner["jira" if item.source == "jira" else "prs"] += 1
            owner["active"] += item.source_category == "indeterminate"
            age = datetime.now(timezone.utc) - datetime.fromisoformat((item.opened_at or item.first_seen).replace("Z", "+00:00"))
            owner["aged"] += age > timedelta(days=7)
        for owner in team.values():
            owner["items"].sort(key=lambda item: (item["source"] != "jira", item["source_category"] != "indeterminate", item["title"].casefold()))
        return sorted(team.values(), key=lambda owner: (-owner["active"], -len(owner["items"]), owner["name"]))

    def set_team_exclusion(self, owner_id: str, excluded: bool) -> None:
        """Keep explicit roster corrections separate from source account status."""
        exclusions = json.loads(self.store.setting("team_exclusions", "{}"))
        if excluded:
            member = next((member for member in self._team(self.items()) if member["id"] == owner_id), None)
            if member is None and owner_id not in exclusions:
                raise ValueError("Member is not in the current team view")
            exclusions[owner_id] = member["name"] if member else exclusions[owner_id]
        else:
            exclusions.pop(owner_id, None)
        self.store.save_setting("team_exclusions", json.dumps(exclusions))

    def coverage(self) -> str:
        """What the team view counts, including the GitHub team it is read from, so the roster is never a guess."""
        try:
            team = GITHUB_TEAM.read(self.store)
        except SourceError:
            team = ""
        members = f", and by members of the {team} GitHub team" if "/" in team else ""
        return (
            "Counts tickets in your Jira scope that were updated in the last 90 days, and pull requests "
            f"opened in the last 90 days by the same people{members}. "
            "Jira doesn't know who has left your team, so hide them with Hide member. "
            "The numbers show visible work, not effort."
        )

    def snapshot(self) -> dict:
        """Expose a compact client snapshot without raw source payloads."""
        items = self.items()
        stored = [item for item in items if not item.live]
        active = self.active()
        # The banner and suggestions come from saved settings, so they follow their source's switch.
        oncall = "oncall" in active
        return {
            "items": [item.model_dump() for item in items if item.personal],
            "team": self._team(items),
            "suggestions": [{**suggestion.model_dump(mode="json"), "id": suggestion.id} for suggestion in visible_suggestions(self.store, stored)] if "cleanup" in active else [],
            "linked": linked_asks(items, self.store.references(stored)),
            "oncall": [item.model_dump() for item in items if item.source == "oncall"],
            "oncall_epic": json.loads(self.store.setting(ONCALL_EPIC_SETTING) or "null") if oncall else None,
            "on_call": shift_now(self.store.setting(ON_CALL_SETTING)) if oncall else None,
            "team_exclusions": [{"id": owner_id, "name": name} for owner_id, name in json.loads(self.store.setting("team_exclusions", "{}")).items()],
            "sources": [self.states[name].model_dump() for name in active],
            "source_labels": {**{name: source.label for name, source in self.sources.items()}, "manual": "Manual"},
            "source_groups": {name: source.group for name, source in self.sources.items() if source.group},
            "views": {"oncall": oncall, "team": bool(TEAM_SOURCES & set(active))},
            "snapshots": {name: saved for name, saved in self.saved.items() if name in active},
            "refresh_intervals": self.intervals(),
            "refresh_choices": list(INTERVAL_CHOICES),
            "auto_refresh": self.auto_refresh(),
            "metrics": self.store.metrics(),
            "refreshing": any(self.states[name].state == "refreshing" for name in active),
            "team_jql": self.store.setting("team_jql"),
            "team_scope_origin": self.store.setting("team_scope_origin"),
            "name": self.store.setting("display_name", "You"),
            "coverage": self.coverage(),
        }


def create_engine(store: Store, home: Path | None = None) -> Engine:
    """Wire every registered source, built in or plugin, once at process startup."""
    folder = home if home is not None else Path.home()
    sources = registry()
    return Engine(store, {name: (lambda source=source: source.read(store, folder)) for name, source in sources.items()}, sources)
