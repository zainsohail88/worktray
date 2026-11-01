import json

import pytest

from worktray.sources.codex_slack import _batch_from_agent_json
from worktray.sources.errors import SourceError


def payload(**overrides):
    item = {
        "key": "slack:C123:1760000000.000100",
        "title": "Review the rollout note",
        "source": "slack",
        "url": "https://team.slack.com/archives/C123/p1760000000000100",
        "status": "proposed",
        "opened_at": "2025-10-09T08:53:20+00:00",
        "reason": "Ask in your conversation",
        "list_name": "Asks",
        "close_suggested": False,
        "references": [],
    }
    item.update(overrides)
    return json.dumps({"items": [item], "detail": "1 Slack follow-up"})


def test_agent_json_becomes_private_slack_batch():
    batch = _batch_from_agent_json(payload())

    assert batch.detail == "1 Slack follow-up"
    assert len(batch.items) == 1
    assert batch.items[0].key == "slack:C123:1760000000.000100"
    assert batch.items[0].live is False


def test_agent_json_rejects_non_slack_items():
    with pytest.raises(SourceError, match="invalid task JSON"):
        _batch_from_agent_json(payload(source="jira", key="jira:ABC-1"))


def test_agent_json_rejects_slack_homepage_urls():
    with pytest.raises(SourceError, match="invalid task JSON"):
        _batch_from_agent_json(payload(url="https://team.slack.com/"))


def test_agent_json_deduplicates_keys():
    data = json.loads(payload())
    data["items"].append(dict(data["items"][0], title="Duplicate"))

    batch = _batch_from_agent_json(json.dumps(data))

    assert [item.title for item in batch.items] == ["Review the rollout note"]


def test_agent_json_keeps_ticket_and_pull_request_references():
    pull = "https://github.com/example-org/app/pull/12"

    batch = _batch_from_agent_json(payload(references=["ABC-123", pull]))

    assert batch.items[0].references == ["ABC-123", pull]


def test_agent_json_drops_references_that_name_nothing():
    batch = _batch_from_agent_json(payload(references=["ABC-123 (In Testing)", "the PR"]))

    assert batch.items[0].references == []
