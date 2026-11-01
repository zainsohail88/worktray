"""Read local session metadata without interpreting chat endings as completion."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from worktray.models import Batch, Item
from worktray.sources.errors import NotConnectedError, SourceError
from worktray.store import Store


def short_title(text: str) -> str:
    """Keep one useful line and suppress common credential patterns."""
    lines = [line.strip(" #*-\t") for line in text.splitlines() if line.strip()]
    title = next((line for line in lines if not line.startswith(("<", "[", "/", "```"))), "Session work")
    title = re.sub(r"(?i)(?:bearer\s+\S+|(?:token|password|secret|api[_-]?key)\s*[:=]\s*\S+)", "[redacted]", title)
    title = re.sub(r"(?:sk-[A-Za-z0-9_-]{15,}|xox[baprs]-\S+|gh[pousr]_\S+)", "[redacted]", title)
    return re.sub(r"\s+", " ", title)[:200] or "Session work"


def session_url(source: str, session_id: str, workspace: str = "") -> str:
    """Link into the app that owns a session.

    Routes come from each app's URL handler: Claude Desktop's resume and local_sessions
    routes and Codex's threads route. Cursor has no per-chat link, so its workspace opens
    with the chat in its history.
    """
    if source == "claude":
        return f"claude://resume?session={quote(session_id)}"
    if source == "claude_desktop":
        return f"claude://claude.ai/local_sessions/{quote(session_id)}"
    if source == "codex":
        return f"codex://threads/{quote(session_id)}"
    if source == "cursor" and workspace:
        return f"cursor://file{quote(workspace)}"
    return ""


def _item(source: str, session_id: str, title: str, timestamp: float, workspace: str = "") -> Item:
    key = f"{source}:{session_id}"
    return Item(
        key=key,
        source=source,
        title=short_title(title),
        url=session_url(source, session_id, workspace),
        opened_at=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        reason="Recent agent session",
        list_name="Agent work",
    )


def read_codex(home: Path, days: int = 100, store: Store | None = None) -> Batch:
    """Read top-level Codex thread titles from its local metadata database."""
    path = home / ".codex/state_5.sqlite"
    if not path.exists():
        raise NotConnectedError("No Codex sessions on this computer yet.")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3) as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at FROM threads
            WHERE updated_at >= ? AND coalesce(thread_source, '') != 'subagent'
            AND id NOT IN (SELECT child_thread_id FROM thread_spawn_edges)
        """,
            (cutoff,),
        )
        items = [_item("codex", session_id, title or "Codex work", created) for session_id, title, created in rows]
    imports_path = home / ".codex/external_agent_session_imports.json"
    if not imports_path.exists():
        return Batch(items=items, detail="Your recent Codex sessions")
    imports = {}
    for record in json.loads(imports_path.read_text()).get("records", []):
        original = Path(record["source_path"])
        for source, root in (("claude", home / ".claude/projects"), ("cursor", home / ".cursor/projects")):
            if original.is_relative_to(root):
                imports[f"codex:{record['imported_thread_id']}"] = f"{source}:{original.stem}"
    originals = {}
    for reader in (read_claude, read_cursor):
        try:
            batch = reader(home, days)
        except (OSError, sqlite3.Error, ValueError, KeyError, SourceError):
            continue
        originals.update({item.key: item for item in batch.items})
    reconciled = {}
    imported = 0
    for item in items:
        canonical = originals.get(imports.get(item.key, ""))
        if canonical:
            imported += 1
            if store:
                store.merge_import(item.key, canonical)
            item = canonical
        reconciled[item.key] = item
    return Batch(items=list(reconciled.values()), detail=f"{len(items) - imported} Codex sessions, plus {imported} matched to the chat they were imported from")


def _first_existing(home: Path, candidates: tuple[str, ...], missing: str) -> Path:
    """Apps keep their state under macOS's Application Support or Linux's ~/.config; take whichever exists."""
    for candidate in candidates:
        if (home / candidate).exists():
            return home / candidate
    raise NotConnectedError(missing)


CURSOR_STATE = ("Library/Application Support/Cursor/User/globalStorage/state.vscdb", ".config/Cursor/User/globalStorage/state.vscdb")
CLAUDE_CODE_SESSIONS = ("Library/Application Support/Claude/claude-code-sessions", ".config/Claude/claude-code-sessions")
CLAUDE_DESKTOP_SESSIONS = ("Library/Application Support/Claude/local-agent-mode-sessions", ".config/Claude/local-agent-mode-sessions")


def read_cursor(home: Path, days: int = 100) -> Batch:
    """Read Cursor's composer headers, leaving transcript bodies untouched."""
    path = _first_existing(home, CURSOR_STATE, "No Cursor chats on this computer yet.")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3) as connection:
        rows = connection.execute("SELECT composerId, createdAt, value FROM composerHeaders WHERE lastUpdatedAt >= ? AND coalesce(isSubagent, 0)=0", (cutoff,))
        items = [_cursor_item(session_id, created, json.loads(value)) for session_id, created, value in rows]
    return Batch(items=items, detail="Your recent Cursor chats")


def _cursor_item(session_id: str, created: float, header: dict) -> Item:
    workspace = header.get("workspaceIdentifier") or {}
    path = workspace.get("uri", {}).get("fsPath", "") if isinstance(workspace, dict) else ""
    return _item("cursor", session_id, header.get("name") or "Cursor work", created / 1000, path)


def read_claude(home: Path, days: int = 100) -> Batch:
    """Merge Desktop Code and CLI sessions by their shared session ID."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
    path = home / ".claude/history.jsonl"
    if not path.exists():
        raise NotConnectedError("No Claude Code sessions on this computer yet.")
    items: dict[str, Item] = {}
    with path.open() as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = record.get("sessionId")
            text = record.get("display", "").strip()
            timestamp = record.get("timestamp", 0)
            command = text.split(maxsplit=1)[0] if text else ""
            housekeeping = command in ("/clear", "/exit", "/compact", "/model", "/help", "/login", "/status", "/cost")
            if session_id and timestamp >= cutoff and text and not text.startswith("<") and not housekeeping:
                items.setdefault(session_id, _item("claude", session_id, text.lstrip("/"), timestamp / 1000))
    root = next((home / candidate for candidate in CLAUDE_CODE_SESSIONS if (home / candidate).exists()), home / CLAUDE_CODE_SESSIONS[0])
    for path in root.glob("*/*/local_*.json"):
        record = json.loads(path.read_text())
        session_id = record.get("cliSessionId")
        if session_id and record.get("lastActivityAt", 0) >= cutoff and record.get("title"):
            items[session_id] = _item("claude", session_id, record["title"], record["createdAt"] / 1000)
    return Batch(items=list(items.values()), detail="Your recent Claude Code sessions")


def read_desktop(home: Path, days: int = 100) -> Batch:
    """Discover Cowork sessions; regular web chats need explicit MCP reports."""
    root = _first_existing(home, CLAUDE_DESKTOP_SESSIONS, "No Claude Desktop sessions on this computer yet.")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
    items = []
    for path in root.glob("*/*/local_*.json"):
        record = json.loads(path.read_text())
        if record.get("lastActivityAt", 0) >= cutoff and record.get("sessionId"):
            items.append(_item("claude_desktop", record["sessionId"], record.get("title") or "Cowork work", record["createdAt"] / 1000))
    return Batch(items=items, detail="Your recent Claude Desktop Cowork sessions")
