"""Ask an agent how to shorten the stream lists, and apply what the user accepts."""

from collections.abc import Iterable
import textwrap

from pydantic import BaseModel, Field, ValidationError

from worktray.models import Batch, Item, ItemEdit, Suggestion
from worktray.references import find_references, link_targets
from worktray.sources.codex import DATA_RULE, as_data, run_codex
from worktray.sources.errors import SourceError
from worktray.store import Store

MAX_ITEMS = 200
ACTIVE = ("open", "proposed")


class CleanupResult(BaseModel):
    """The only agent output accepted from a cleanup run."""

    suggestions: list[Suggestion] = Field(default_factory=list, max_length=60)


def _schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["suggestions"],
        "properties": {
            "suggestions": {
                "type": "array",
                "maxItems": 60,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "keys", "title", "reference", "due_date", "why"],
                    "properties": {
                        "kind": {"type": "string", "enum": ["merge", "link", "retitle", "due", "close"]},
                        "keys": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string"}},
                        "title": {"type": "string", "maxLength": 240},
                        "reference": {"type": "string", "maxLength": 300},
                        "due_date": {"type": ["string", "null"], "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                        "why": {"type": "string", "minLength": 1, "maxLength": 240},
                    },
                },
            },
        },
    }


def _stream(items: list[Item]) -> list[Item]:
    active = [item for item in items if not item.live and item.status in ACTIVE]
    return sorted(active, key=lambda item: item.opened_at or item.first_seen, reverse=True)[:MAX_ITEMS]


def _prompt(stream: list[Item], targets: dict[str, Item]) -> str:
    asks = [
        {
            "key": item.key,
            "title": item.title,
            "source": item.source,
            "status": item.status,
            "opened_at": item.opened_at or item.first_seen,
            "meeting": item.project,
            "note": item.note,
            "references": item.references,
            "linked_status": item.linked_status,
            "due_date": item.due_date,
        }
        for item in stream
    ]
    work = [{"reference": reference, "title": item.title, "status": item.source_status} for reference, item in targets.items()]
    return textwrap.dedent(f"""
        You tidy a personal work queue so the owner triages less. {DATA_RULE}

        Stream items (asks from Slack, meeting notes, Confluence and agents):
        {as_data(asks)}

        The owner's open Jira tickets and pull requests:
        {as_data(work)}

        Suggest only changes you are confident about; leave out anything you would describe as likely or possible.
        Return only JSON matching the provided schema.
        - merge: keys are two or more stream items asking for the same outcome, not merely the same topic or meeting;
          put the clearest or most advanced first;
          title is a clear combined title, or empty to keep the first title
        - link: keys has one stream item that is about one ticket or pull request above although it does not name it,
          because both name the same system and the same problem; reference is that ticket key or pull request link
          exactly as listed
        - retitle: keys has one stream item whose title is vague; title says what to do and to what, under 100 characters
        - due: keys has one stream item whose title or meeting implies a deadline; due_date is that day as YYYY-MM-DD,
          counted from opened_at
        - close: keys are stream items that look finished, for example every linked_status entry is done or merged,
          or a later item says the work happened
        - why is one short sentence the owner can check, quoting the words that match
        Use empty strings and null for fields a kind does not use. Never suggest the same key in two suggestions.
    """).strip()


def _valid(suggestion: Suggestion, stream_keys: set[str], targets: dict[str, Item]) -> bool:
    if not set(suggestion.keys) <= stream_keys or len(set(suggestion.keys)) != len(suggestion.keys):
        return False
    single = len(suggestion.keys) == 1
    return {
        "merge": len(suggestion.keys) >= 2,
        "link": single and suggestion.reference in targets,
        "retitle": single and bool(suggestion.title.strip()),
        "due": single and suggestion.due_date is not None,
        "close": True,
    }[suggestion.kind]


def suggestions_from_agent_json(payload: str, stream: list[Item], targets: dict[str, Item]) -> list[Suggestion]:
    """Keep suggestions that touch only the items the agent was shown, one suggestion per item."""
    try:
        result = CleanupResult.model_validate_json(payload)
    except ValidationError as error:
        raise SourceError("Cleanup agent returned invalid suggestion JSON") from error
    stream_keys = {item.key for item in stream}
    claimed: set[str] = set()
    kept = []
    for suggestion in result.suggestions:
        if _valid(suggestion, stream_keys, targets) and not claimed & set(suggestion.keys):
            claimed |= set(suggestion.keys)
            kept.append(suggestion)
    return kept


async def read_cleanup(store: Store) -> Batch:
    """Replace pending suggestions with a fresh agent run over the current stream items."""
    stream = _stream(store.items())
    if not stream:
        store.replace_suggestions([])
        return Batch(detail="Nothing to tidy up")
    targets = link_targets(store.current_live(snapshot.items for snapshot in store.snapshots().values()))
    payload = await run_codex(store, _prompt(stream, targets), _schema(), "Cleanup agent")
    suggestions = suggestions_from_agent_json(payload, stream, targets)
    added = store.replace_suggestions(suggestions)
    return Batch(detail=f"{len(suggestions)} suggestions for {len(stream)} items, {added} of them new")


def visible_suggestions(store: Store, items: Iterable[Item] | None = None) -> list[Suggestion]:
    """Pending suggestions whose items are all still active, so an item closed by hand drops its suggestions.

    Pass the stored items already loaded to skip reading them again.
    """
    active = {item.key for item in (store.items() if items is None else items) if not item.live and item.status in ACTIVE}
    return [suggestion for suggestion in store.pending_suggestions() if set(suggestion.keys) <= active]


def _merged_note(keep: Item, merged: list[Item]) -> str:
    links = [f"Also: {item.url}" for item in merged if item.url and item.url != keep.url]
    return "\n".join([keep.note, *links]).strip()[:2000]


def apply_suggestion(store: Store, suggestion_id: str) -> Suggestion:
    """Apply an accepted suggestion, then record the decision, so a failed apply leaves it pending."""
    suggestion = next((found for found in visible_suggestions(store) if found.id == suggestion_id), None)
    if suggestion is None:
        raise KeyError(suggestion_id)
    items = {item.key: item for item in store.items()}
    first = items[suggestion.keys[0]]
    if suggestion.kind == "merge":
        merged = [items[key] for key in suggestion.keys[1:]]
        references = [reference for item in merged for reference in [*item.references, *find_references(item.title)]]
        store.edit(first.key, ItemEdit(title=suggestion.title or None, note=_merged_note(first, merged)))
        for reference in dict.fromkeys(references):
            store.add_reference(first.key, reference)
        for item in merged:
            store.edit(item.key, ItemEdit(status="dismissed"))
    elif suggestion.kind == "link":
        store.add_reference(first.key, suggestion.reference)
    elif suggestion.kind == "retitle":
        store.edit(first.key, ItemEdit(title=suggestion.title))
    elif suggestion.kind == "due":
        store.edit(first.key, ItemEdit(due_date=suggestion.due_date.isoformat()))
    else:
        for key in suggestion.keys:
            # Accepting a proposal means taking it on, so a finished proposal is dismissed rather than counted as done work.
            store.edit(key, ItemEdit(status="done" if items[key].status == "open" else "dismissed"))
    return store.decide_suggestion(suggestion_id, accepted=True)


def reject_suggestion(store: Store, suggestion_id: str) -> Suggestion:
    """Remember the rejection so the same suggestion from a later run stays hidden."""
    return store.decide_suggestion(suggestion_id, accepted=False)
