"""SQLite persistence for decisions and the last complete source snapshots."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from worktray.models import Item, ItemEdit, SourceState, Suggestion, now, within_work_window
from worktray.references import find_references


@dataclass
class SavedSnapshot:
    """A complete normalized source result with its original query scope."""

    items: list[Item]
    saved_at: str
    scope: str


class Store:
    """Serialize decisions transactionally so refreshes cannot resurrect work."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS items (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (
                    key TEXT PRIMARY KEY, source TEXT NOT NULL,
                    decision TEXT NOT NULL, decided_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS annotations (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS health (
                    source TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aliases (
                    alias TEXT PRIMARY KEY, canonical TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sightings (
                    key TEXT PRIMARY KEY, first_seen TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS suggestions (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    state TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS live_snapshots (
                    source TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    saved_at TEXT NOT NULL, scope TEXT NOT NULL);
            """)
            # Session links once pointed at a removed worktray page; refresh relinks rediscovered ones.
            connection.execute("UPDATE items SET payload=json_set(payload, '$.url', '') WHERE json_extract(payload, '$.url') LIKE '/session/%'")
        os.chmod(path, 0o600)

    def connect(self) -> sqlite3.Connection:
        """Use a short independent connection for each transaction."""
        return sqlite3.connect(self.path, timeout=15)

    def ingest(self, items: list[Item]) -> int:
        """Insert unseen proposals and preserve every existing human decision."""
        inserted = 0
        with self.connect() as connection:
            for item in items:
                if item.live:
                    raise ValueError("Source-owned items belong in a complete snapshot")
                if connection.execute("SELECT 1 FROM aliases WHERE alias=?", (item.key,)).fetchone():
                    continue
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO items VALUES (?, ?)",
                    (item.key, item.model_dump_json()),
                )
                inserted += cursor.rowcount
                # The link is source-owned, so a changed one replaces the stored one.
                connection.execute(
                    "UPDATE items SET payload=json_set(payload, '$.url', ?) WHERE key=? AND json_extract(payload, '$.url') != ?",
                    (item.url, item.key, item.url),
                )
                if item.references:
                    row = connection.execute("SELECT payload FROM items WHERE key=?", (item.key,)).fetchone()
                    current = Item.model_validate_json(row[0])
                    merged = list(dict.fromkeys([*current.references, *item.references]))
                    if merged != current.references:
                        connection.execute("UPDATE items SET payload=json_set(payload, '$.references', json(?)) WHERE key=?", (json.dumps(merged), item.key))
                if item.close_suggested:
                    row = connection.execute("SELECT payload FROM items WHERE key=?", (item.key,)).fetchone()
                    current = Item.model_validate_json(row[0])
                    if current.status == "open" and not current.close_suggested:
                        current.close_suggested = True
                        connection.execute("UPDATE items SET payload=? WHERE key=?", (current.model_dump_json(), item.key))
        return inserted

    def items(self) -> list[Item]:
        """Return retained stream history without loading source content."""
        with self.connect() as connection:
            return [Item.model_validate_json(row[0]) for row in connection.execute("SELECT payload FROM items")]

    def current_live(self, batches: Iterable[list[Item]]) -> list[Item]:
        """Merge source batches into one annotated item per key, dropping work outside its window.

        Sightings and annotations for the whole batch are read and written in one connection, since
        this runs on every page load and poll.
        """
        live: dict[str, Item] = {}
        for batch in batches:
            for item in batch:
                if item.source in ("github", "bitbucket") and not within_work_window(item.opened_at):
                    continue
                if item.source == "calendar" and (not item.ends_at or datetime.fromisoformat(item.ends_at) <= datetime.now(timezone.utc)):
                    continue
                previous = live.get(item.key)
                if previous:
                    personal = previous if previous.personal else item
                    team = previous if previous.team_member else item
                    item = personal.model_copy(
                        update={
                            "personal": previous.personal or item.personal,
                            "team_member": previous.team_member or item.team_member,
                            "owner_id": team.owner_id,
                            "owner_email": team.owner_email,
                            "owner": team.owner,
                        }
                    )
                live[item.key] = item
        if not live:
            return []
        with self.connect() as connection:
            seen = dict(connection.execute("SELECT key, first_seen FROM sightings"))
            missing = [(key, item.first_seen) for key, item in live.items() if key not in seen]
            if missing:
                connection.executemany("INSERT OR IGNORE INTO sightings VALUES (?, ?)", missing)
                seen.update(missing)
            notes = {key: json.loads(payload) for key, payload in connection.execute("SELECT key, payload FROM annotations")}
        return [item.model_copy(update={**notes.get(key, {}), "first_seen": seen[key]}) for key, item in live.items()]

    def references(self, items: Iterable[Item] | None = None) -> dict[str, list[str]]:
        """Jira keys and pull request links named by each active stream item, in its text or by its source.

        Pass items already loaded to skip reading them again.
        """
        found = {
            item.key: list(dict.fromkeys([*find_references(f"{item.title} {item.note} {item.url}"), *item.references]))
            for item in (self.items() if items is None else items)
            if not item.live and item.status in ("open", "proposed")
        }
        return {key: references for key, references in found.items() if references}

    def add_reference(self, key: str, reference: str) -> None:
        """Attach an item to a ticket or pull request its text never named."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM items WHERE key=?", (key,)).fetchone()
            if row is None:
                raise KeyError(key)
            item = Item.model_validate_json(row[0])
            if reference not in item.references:
                item.references.append(reference)
                connection.execute("UPDATE items SET payload=? WHERE key=?", (item.model_dump_json(), key))

    def replace_suggestions(self, suggestions: list[Suggestion]) -> int:
        """Swap the pending set for a fresh agent run, skipping any the user already accepted or rejected."""
        added = 0
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM suggestions WHERE state='pending'")
            for suggestion in suggestions:
                cursor = connection.execute("INSERT OR IGNORE INTO suggestions VALUES (?, ?, 'pending', ?)", (suggestion.id, suggestion.model_dump_json(), now()))
                added += cursor.rowcount
        return added

    def pending_suggestions(self) -> list[Suggestion]:
        """Suggestions awaiting a decision, oldest run first."""
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM suggestions WHERE state='pending' ORDER BY created_at")
            return [Suggestion.model_validate_json(row[0]) for row in rows]

    def decide_suggestion(self, suggestion_id: str, accepted: bool) -> Suggestion:
        """Record the decision once; a decided suggestion cannot be decided again."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM suggestions WHERE id=? AND state='pending'", (suggestion_id,)).fetchone()
            if row is None:
                raise KeyError(suggestion_id)
            connection.execute("UPDATE suggestions SET state=? WHERE id=?", ("accepted" if accepted else "rejected", suggestion_id))
        return Suggestion.model_validate_json(row[0])

    def link_status(self, key: str, status: str) -> None:
        """Record where the tickets and pull requests an item names stand now."""
        with self.connect() as connection:
            connection.execute(
                "UPDATE items SET payload=json_set(payload, '$.linked_status', ?) WHERE key=? AND json_extract(payload, '$.linked_status') IS NOT ?",
                (status[:240], key, status[:240]),
            )

    def suggest_close(self, key: str, hint: str) -> None:
        """Offer an open item as done and say why; closed items and unchanged hints are left alone."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM items WHERE key=?", (key,)).fetchone()
            if row is None:
                return
            item = Item.model_validate_json(row[0])
            if item.status != "open" or (item.close_suggested and item.close_hint == hint):
                return
            item.close_suggested = True
            item.close_hint = hint
            connection.execute("UPDATE items SET payload=? WHERE key=?", (item.model_dump_json(), key))

    def reconcile_meeting_proposals(self, documents: set[str], candidates: list[Item]) -> None:
        """Replace untouched proposals only after their documents were fully read."""
        current = {item.key: item for item in candidates}
        prefixes = {f"gemini:{document}:" for document in documents}
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for key, payload in connection.execute("SELECT key, payload FROM items WHERE key LIKE 'gemini:%'").fetchall():
                item = Item.model_validate_json(payload)
                if not any(key.startswith(prefix) for prefix in prefixes):
                    continue
                if key in current:
                    # The meeting name and why the line was picked are source-owned like the link, so decided items gain them too.
                    item.project = current[key].project
                    item.reason = current[key].reason
                    connection.execute("UPDATE items SET payload=json_set(payload, '$.project', ?, '$.reason', ?) WHERE key=?", (item.project, item.reason, key))
                if item.status != "proposed" or item.note or item.up_next or item.list_name != "Follow-ups" or item.updated_at:
                    continue
                if key in current:
                    item.title = current[key].title
                    connection.execute("UPDATE items SET payload=? WHERE key=?", (item.model_dump_json(), key))
                else:
                    connection.execute("DELETE FROM items WHERE key=?", (key,))
            for item in candidates:
                connection.execute("INSERT OR IGNORE INTO items VALUES (?, ?)", (item.key, item.model_dump_json()))

    def edit(self, key: str, edit: ItemEdit) -> Item:
        """Count the first triage decision once and make closure irreversible."""
        key = self.resolve(key)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM items WHERE key=?", (key,)).fetchone()
            if row is None:
                raise KeyError(key)
            item = Item.model_validate_json(row[0])
            if edit.status and item.status in ("done", "dismissed") and edit.status != item.status:
                raise ValueError("Closed items stay closed. Create a new item for new work.")
            if item.status == "proposed" and edit.status:
                decision = "dismissed" if edit.status == "dismissed" else "accepted"
                connection.execute("INSERT OR IGNORE INTO decisions VALUES (?, ?, ?, ?)", (key, item.source, decision, now()))
            updated = item.model_copy(update=edit.model_dump(exclude_none=True))
            updated.updated_at = now()
            updated.snoozed_until = updated.snoozed_until or None
            if updated.status in ("done", "dismissed"):
                updated.closed_at = item.closed_at or now()
                updated.close_suggested = False
                updated.close_hint = ""
                updated.up_next = False
                updated.snoozed_until = None
            connection.execute("UPDATE items SET payload=? WHERE key=?", (updated.model_dump_json(), key))
            return updated

    def resolve(self, key: str) -> str:
        """Follow an explicitly recorded import identity, never a title match."""
        with self.connect() as connection:
            row = connection.execute("SELECT canonical FROM aliases WHERE alias=?", (key,)).fetchone()
        return row[0] if row else key

    def merge_import(self, alias: str, canonical: Item) -> None:
        """Reconcile an imported session while preserving terminal decisions."""
        if alias == canonical.key:
            return
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT payload FROM items WHERE key IN (?, ?)", (alias, canonical.key)).fetchall()
            candidates = [Item.model_validate_json(row[0]) for row in rows]
            terminal = [item for item in candidates if item.status in ("done", "dismissed")]
            if terminal:
                retained = min(terminal, key=lambda item: item.closed_at or item.first_seen)
            else:
                retained = next((item for item in candidates if item.status == "open"), candidates[0] if candidates else canonical)
            merged = retained.model_copy(update={"key": canonical.key, "source": canonical.source, "url": canonical.url, "opened_at": canonical.opened_at})
            decisions = connection.execute("SELECT decision, decided_at FROM decisions WHERE key IN (?, ?) ORDER BY decided_at", (alias, canonical.key)).fetchall()
            connection.execute("DELETE FROM items WHERE key=?", (alias,))
            connection.execute("INSERT OR REPLACE INTO items VALUES (?, ?)", (canonical.key, merged.model_dump_json()))
            connection.execute("DELETE FROM decisions WHERE key IN (?, ?)", (alias, canonical.key))
            if decisions:
                connection.execute("INSERT INTO decisions VALUES (?, ?, ?, ?)", (canonical.key, canonical.source, *decisions[0]))
            connection.execute("INSERT OR REPLACE INTO aliases VALUES (?, ?)", (alias, canonical.key))

    def annotate(self, key: str, edit: ItemEdit) -> None:
        """Store local presentation choices for a source-owned item."""
        if edit.title or (edit.status and edit.status != "dismissed"):
            raise ValueError("Live items can only be dismissed locally")
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM annotations WHERE key=?", (key,)).fetchone()
            payload = json.loads(row[0]) if row else {}
            payload.update(edit.model_dump(exclude_none=True))
            if not payload.get("snoozed_until"):
                payload.pop("snoozed_until", None)
            if edit.status == "dismissed":
                payload["closed_at"] = payload.get("closed_at") or now()
                payload["up_next"] = False
            connection.execute("INSERT OR REPLACE INTO annotations VALUES (?, ?)", (key, json.dumps(payload)))

    def annotated(self, item: Item) -> Item:
        """Apply only user-owned metadata to the current source response."""
        with self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO sightings VALUES (?, ?)", (item.key, item.first_seen))
            first_seen = connection.execute("SELECT first_seen FROM sightings WHERE key=?", (item.key,)).fetchone()[0]
            row = connection.execute("SELECT payload FROM annotations WHERE key=?", (item.key,)).fetchone()
        metadata = json.loads(row[0]) if row else {}
        return item.model_copy(update={**metadata, "first_seen": first_seen})

    def metrics(self) -> dict[str, dict[str, int]]:
        """Aggregate immutable proposal decisions by source."""
        with self.connect() as connection:
            rows = connection.execute("SELECT source, decision, count(*) FROM decisions GROUP BY source, decision")
            metrics: dict[str, dict[str, int]] = {}
            for source, decision, count in rows:
                metrics.setdefault(source, {"accepted": 0, "dismissed": 0})[decision] = count
            return metrics

    def health(self) -> list[SourceState]:
        """Retrieve connector health without any ticket or PR status."""
        with self.connect() as connection:
            return [SourceState.model_validate_json(row[0]) for row in connection.execute("SELECT payload FROM health")]

    def snapshots(self) -> dict[str, SavedSnapshot]:
        """Restore only normalized items from each source's last successful read."""
        with self.connect() as connection:
            rows = connection.execute("SELECT source, payload, saved_at, scope FROM live_snapshots")
            return {source: SavedSnapshot([Item.model_validate(item) for item in json.loads(payload)], saved_at, scope) for source, payload, saved_at, scope in rows}

    def save_snapshot(self, source: str, items: list[Item], state: SourceState, scope: str = "") -> SavedSnapshot:
        """Replace a complete result and its health in one SQLite transaction."""
        if state.source != source or state.state != "ok" or not state.last_success or any(not item.live for item in items):
            raise ValueError("Snapshots require successful health and source-owned items")
        saved = []
        with self.connect() as connection:
            for item in items:
                connection.execute("INSERT OR IGNORE INTO sightings VALUES (?, ?)", (item.key, item.first_seen))
                first_seen = connection.execute("SELECT first_seen FROM sightings WHERE key=?", (item.key,)).fetchone()[0]
                normalized = item.model_dump(exclude={"note", "up_next", "close_suggested", "close_hint", "closed_at", "snoozed_until"}, exclude_defaults=True)
                normalized["first_seen"] = first_seen
                saved.append(normalized)
            connection.execute(
                "INSERT OR REPLACE INTO live_snapshots VALUES (?, ?, ?, ?)",
                (source, json.dumps(saved), state.last_success, scope),
            )
            connection.execute("INSERT OR REPLACE INTO health VALUES (?, ?)", (source, state.model_dump_json()))
        return SavedSnapshot([Item.model_validate(item) for item in saved], state.last_success, scope)

    def drop_snapshot(self, state: SourceState) -> None:
        """Forget a source's saved result, for one that is no longer connected, and record why."""
        with self.connect() as connection:
            connection.execute("DELETE FROM live_snapshots WHERE source=?", (state.source,))
            connection.execute("INSERT OR REPLACE INTO health VALUES (?, ?)", (state.source, state.model_dump_json()))

    def save_health(self, state: SourceState) -> None:
        """Persist health so downtime remains visible across restarts."""
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO health VALUES (?, ?)", (state.source, state.model_dump_json()))

    def setting(self, key: str, default: str = "") -> str:
        """Read non-secret user preferences."""
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def settings_with_prefix(self, prefix: str) -> dict[str, str]:
        """Every preference whose key starts with prefix, in one query."""
        with self.connect() as connection:
            return dict(connection.execute("SELECT key, payload FROM settings WHERE substr(key, 1, ?) = ?", (len(prefix), prefix)).fetchall())

    def settings_named(self, keys: Iterable[str]) -> dict[str, str]:
        """The saved preferences among keys, in one query; keys never saved are left out."""
        wanted = list(dict.fromkeys(keys))
        if not wanted:
            return {}
        with self.connect() as connection:
            return dict(connection.execute(f"SELECT key, payload FROM settings WHERE key IN ({','.join('?' * len(wanted))})", wanted).fetchall())  # noqa: S608 - placeholders only

    def has_setting(self, key: str) -> bool:
        """Whether a preference was ever answered, so setup asks once even when the answer was blank."""
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone() is not None

    def save_setting(self, key: str, value: str) -> None:
        """Keep UI scope changes separate from credentials."""
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
