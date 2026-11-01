"""The Settings page's routes. The one rule above all: a saved secret never comes back to the browser."""

import pytest
from fastapi.testclient import TestClient

from worktray.engine import Engine
from worktray.models import Batch
from worktray.sources import atlassian
from worktray.sources.registry import registry
from worktray.web.app import create_app

ORIGIN = {"Origin": "http://localhost"}
TOKEN = "atl-very-secret-token-value"


async def empty() -> Batch:
    return Batch()


@pytest.fixture
def client(store):
    sources = registry()
    return TestClient(create_app(store, Engine(store, {name: empty for name in sources}, sources)), base_url="http://localhost")


def jira(client) -> dict:
    return next(source for source in client.get("/api/config").json()["sources"] if source["name"] == "jira")


def save(client, name: str, **body) -> object:
    return client.post(f"/api/config/{name}", json=body, headers=ORIGIN)


def test_config_lists_every_source_with_its_fields(client):
    sources = {source["name"]: source for source in client.get("/api/config").json()["sources"]}

    assert {"jira_url", "jira_email"} == {field["key"] for field in sources["jira"]["settings"]}
    assert [secret["key"] for secret in sources["jira"]["secrets"]] == ["jira_api_token"]
    assert sources["oncall"]["uses_label"] == "Jira"


def test_saving_settings_and_a_token_stores_them(client, store, isolated):
    response = save(client, "jira", settings={"jira_url": "https://acme.atlassian.net/", "jira_email": "me@example.com"}, secrets={"jira_api_token": TOKEN})

    assert response.status_code == 200
    assert (store.setting("jira_url"), isolated.values["jira_api_token"]) == ("https://acme.atlassian.net", TOKEN)


def test_saved_token_is_never_returned(client):
    save(client, "jira", secrets={"jira_api_token": TOKEN})

    responses = [client.get("/api/config").text, client.get("/api/state").text, save(client, "jira", settings={}).text]

    assert all(TOKEN not in text for text in responses)
    assert jira(client)["secrets"][0]["set"] is True


def test_secret_can_be_cleared(client):
    save(client, "jira", secrets={"jira_api_token": TOKEN})

    save(client, "jira", clear=["jira_api_token"])

    assert jira(client)["secrets"][0]["set"] is False


def test_blank_secret_is_refused_rather_than_clearing(client):
    save(client, "jira", secrets={"jira_api_token": TOKEN})

    assert save(client, "jira", secrets={"jira_api_token": " "}).status_code == 400
    assert jira(client)["secrets"][0]["set"] is True


def test_invalid_value_is_refused_with_a_reason(client):
    response = save(client, "jira", settings={"jira_url": "http://plain.example.com"})

    assert response.status_code == 400 and "https" in response.json()["detail"]


def test_setting_of_another_source_is_refused(client):
    assert save(client, "github", settings={"jira_url": "https://acme.atlassian.net"}).status_code == 400


def test_unknown_source_is_not_found(client):
    assert save(client, "nope", settings={}).status_code == 404


def test_field_set_by_the_environment_is_locked(client, monkeypatch):
    monkeypatch.setenv(atlassian.JIRA_URL.env, "https://env.atlassian.net")

    field = next(field for field in jira(client)["settings"] if field["key"] == "jira_url")

    assert (field["locked"], field["value"]) == (True, "https://env.atlassian.net")
    assert save(client, "jira", settings={"jira_url": "https://other.atlassian.net"}).status_code == 409


def test_source_can_be_switched_off_and_on(client):
    save(client, "slack", enabled=False)
    off = client.get("/api/state").json()
    save(client, "slack", enabled=True)

    assert "slack" not in [source["source"] for source in off["sources"]]
    assert "slack" in [source["source"] for source in client.get("/api/state").json()["sources"]]


def test_check_reports_a_missing_connection_as_a_result(client):
    body = client.post("/api/config/jira/check", headers=ORIGIN).json()

    assert (body["ok"], body.get("not_connected")) == (False, True)


def test_source_without_a_connection_has_nothing_to_check(client):
    assert client.post("/api/config/upstream/check", headers=ORIGIN).status_code == 400


def test_source_without_browser_sign_in_cannot_connect(client):
    assert client.post("/api/config/jira/connect", headers=ORIGIN).status_code == 400
