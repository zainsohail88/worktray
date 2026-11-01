"""Collect private Slack follow-ups through a Codex agent with Slack access."""

from datetime import datetime, timedelta, timezone
import json
import textwrap

from pydantic import BaseModel, Field, ValidationError, field_validator

from worktray.models import Batch, Item, now
from worktray.references import find_references
from worktray.sources.codex import DATA_RULE, as_data, run_codex
from worktray.sources.errors import SourceError
from worktray.store import Store


class CodexSlackResult(BaseModel):
    """The only agent output accepted by the source adapter."""

    items: list[Item] = Field(default_factory=list)
    detail: str = Field(default="", max_length=500)

    @field_validator("items")
    @classmethod
    def private_slack_items(cls, items: list[Item]) -> list[Item]:
        for item in items:
            if item.source != "slack" or not item.key.startswith("slack:"):
                raise ValueError("Codex Slack items must use the slack source and key prefix")
            if item.live:
                raise ValueError("Codex Slack returns stream items, not live snapshots")
            if item.status not in ("proposed", "open"):
                raise ValueError("Codex Slack can only return active items")
            if item.url and "slack.com/archives/" not in item.url:
                raise ValueError("Codex Slack URLs must point to Slack message archives")
        # A stray word in references costs only that reference, not the whole Slack sync.
        return [item.model_copy(update={"references": [reference for reference in item.references if find_references(reference) == [reference]]}) for item in items]


def _schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items", "detail"],
        "properties": {
            "detail": {"type": "string", "maxLength": 500},
            "items": {
                "type": "array",
                "maxItems": 200,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["key", "title", "source", "url", "status", "opened_at", "reason", "list_name", "close_suggested", "references"],
                    "properties": {
                        "key": {"type": "string", "pattern": "^slack:[A-Z0-9]+:[0-9]+\\.[0-9]+$"},
                        "title": {"type": "string", "minLength": 1, "maxLength": 240},
                        "source": {"type": "string", "const": "slack"},
                        "url": {"type": "string", "pattern": "^https://[^\\s]+slack\\.com/archives/.+"},
                        "status": {"type": "string", "enum": ["proposed", "open"]},
                        "opened_at": {"type": "string", "minLength": 1},
                        "reason": {"type": "string", "minLength": 1, "maxLength": 200},
                        "list_name": {"type": "string", "const": "Asks"},
                        "close_suggested": {"type": "boolean"},
                        "references": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 300}},
                    },
                },
            },
        },
    }


def _prompt(store: Store) -> str:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=100)).date().isoformat()
    open_items = [
        {
            "key": item.key,
            "title": item.title,
            "url": item.url,
            "opened_at": item.opened_at,
        }
        for item in store.items()
        if item.source == "slack" and item.status == "open"
    ][:100]
    return textwrap.dedent(f"""
        Use your Slack connection to find private Slack follow-ups for the worktray app.

        Search messages after {cutoff} where any of these conditions hold:
        - someone asked me to do something in a DM, group DM, thread I joined, or message that mentions me
        - I promised to do something
        - an existing open Slack item below has a later reply from me that suggests it can be closed

        {DATA_RULE}

        Existing open Slack items:
        {as_data(open_items)}

        Return only JSON matching the provided schema.
        Item rules:
        - key is slack:CHANNEL_ID:MESSAGE_TS
        - source is slack
        - status is proposed for new asks or promises, open for existing open items that need close_suggested
        - opened_at is the message timestamp as an ISO-8601 UTC datetime
        - title is a short action summary without Slack mention markup
        - url is the Slack message permalink
        - reason is "You promised" or "Asked of you"
        - list_name is "Asks"
        - close_suggested is true only when I replied after the ask or promise
        - references lists every Jira key (like ABC-123) and GitHub or Bitbucket pull request link anywhere in the
          message or its thread replies, exactly as written; use an empty list when there are none
    """).strip()


def _batch_from_agent_json(payload: str) -> Batch:
    try:
        data = json.loads(payload)
        result = CodexSlackResult.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as error:
        raise SourceError("Codex Slack returned invalid task JSON") from error
    seen = set()
    items = []
    for item in result.items:
        if item.key in seen:
            continue
        seen.add(item.key)
        items.append(item.model_copy(update={"first_seen": item.first_seen or now()}))
    detail = result.detail or f"Found {len(items)} asks and promises in Slack"
    return Batch(items=items, detail=detail)


async def read_slack_via_codex(store: Store) -> Batch:
    """Ask a Slack-connected Codex agent for normalized private Slack items."""
    return _batch_from_agent_json(await run_codex(store, _prompt(store), _schema(), "Codex Slack agent"))
