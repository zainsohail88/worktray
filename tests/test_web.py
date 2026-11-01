"""The web routes, in process. These replace the old probe tests that needed a running server."""

import pytest
from fastapi.testclient import TestClient

from worktray.engine import Engine
from worktray.models import Batch
from worktray.sources.registry import registry
from worktray.web.app import create_app

ORIGIN = {"Origin": "http://localhost"}


async def empty() -> Batch:
    return Batch()


@pytest.fixture
def client(store):
    sources = registry()
    engine = Engine(store, {name: empty for name in sources}, sources)
    # Without a context manager the lifespan, and so the scheduler, never starts.
    return TestClient(create_app(store, engine), base_url="http://localhost")


def test_index_serves_html(client):
    response = client.get("/")

    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/static/app.js", "/static/settings.js", "/static/style.css"])
def test_static_files_are_served(client, path):
    assert client.get(path).status_code == 200


def test_state_exposes_client_snapshot(client):
    body = client.get("/api/state").json()

    assert {"items", "team", "sources", "metrics", "refreshing", "team_jql", "source_labels", "views"} <= body.keys()


def test_empty_refresh_starts_nothing(client):
    response = client.post("/api/refresh", json={"sources": []}, headers=ORIGIN)

    assert (response.status_code, response.json()) == (202, {"started": []})


def test_unknown_refresh_source_is_rejected(client):
    assert client.post("/api/refresh", json={"sources": ["nope"]}, headers=ORIGIN).status_code == 400


def test_blank_item_title_is_rejected(client):
    assert client.post("/api/items", json={"title": ""}, headers=ORIGIN).status_code == 422


def test_editing_unknown_item_is_not_found(client):
    assert client.patch("/api/items", json={"key": "probe:missing", "note": "x"}, headers=ORIGIN).status_code == 404


def test_excluding_unknown_member_is_rejected(client):
    assert client.post("/api/team/exclusions", json={"owner_id": "probe:missing", "excluded": True}, headers=ORIGIN).status_code == 400


def test_refresh_interval_outside_the_choices_is_rejected(client):
    assert client.post("/api/settings/refresh-interval", json={"source": "jira", "seconds": 5}, headers=ORIGIN).status_code == 400


def test_snooze_time_without_timezone_is_rejected(client):
    assert client.patch("/api/items", json={"key": "probe:missing", "snoozed_until": "2026-10-22T09:00:00"}, headers=ORIGIN).status_code == 422


def test_standup_note_is_slack_text(client):
    text = client.get("/api/standup").json()["text"]

    assert text.startswith("*") and "*Today*" in text


def test_brief_for_unknown_meeting_is_not_found(client):
    assert client.get("/api/brief", params={"key": "probe:missing"}).status_code == 404


def test_write_without_origin_is_forbidden(client):
    assert client.post("/api/refresh", json={"sources": []}).status_code == 403


def test_settings_write_from_another_origin_is_forbidden(client):
    response = client.post("/api/config/jira", json={"secrets": {"jira_api_token": "x"}}, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


def test_foreign_host_is_rejected(client):
    assert client.get("/api/state", headers={"Host": "evil.example"}).status_code == 400


def test_responses_carry_security_headers(client):
    headers = client.get("/").headers

    assert headers["x-frame-options"] == "DENY" and headers["cache-control"] == "no-store" and "frame-ancestors 'none'" in headers["content-security-policy"]


def test_api_docs_are_disabled(client):
    assert client.get("/openapi.json").status_code == 404
