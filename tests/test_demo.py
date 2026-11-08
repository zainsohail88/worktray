"""The public demo: sample data on any host name, nothing saved to settings and no real data folder."""

from fastapi.testclient import TestClient
import pytest

from worktray import cli, paths
from worktray.auth.keyring_store import MemoryStore, secret_store
from worktray.demo import create_demo_app

HOST = "https://worktray-demo.example.run.app"
ORIGIN = {"Origin": HOST}


@pytest.fixture
def demo():
    return TestClient(create_demo_app(), base_url=HOST)


def test_demo_shows_sample_work_on_any_host_name(demo):
    state = demo.get("/api/state").json()

    assert state["demo"] is True
    assert {"jira", "github", "calendar", "slack"} <= {item["source"] for item in state["items"]}
    assert state["team"] and state["oncall"] and state["suggestions"] and state["on_call"]


def test_demo_settings_cannot_be_changed_or_used_to_sign_in(demo):
    for path, body in (("/api/config/jira", {"enabled": False}), ("/api/config/jira/check", None), ("/api/config/calendar/connect", None), ("/api/config/calendar/disconnect", None)):
        assert demo.post(path, json=body, headers=ORIGIN).status_code == 403

    assert demo.get("/api/config").json()["demo"] is True


def test_visitors_can_still_use_the_dashboard(demo):
    response = demo.post("/api/items", json={"key": "visitor-1", "title": "Try the demo", "note": "", "list_name": ""}, headers=ORIGIN)

    assert response.status_code == 200 and any(item["title"] == "Try the demo" for item in demo.get("/api/state").json()["items"])


def test_demo_uses_no_keyring_and_no_data_folder(demo):
    assert isinstance(secret_store(), MemoryStore) and not paths.home().exists()


def test_only_the_demo_listens_beyond_this_computer(monkeypatch):
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: pytest.fail("started a public server without --demo"))

    with pytest.raises(SystemExit, match="--demo"):
        cli.serve(8000, False, "0.0.0.0", demo=False)


def test_demo_trusts_the_hosting_proxy_for_https(monkeypatch):
    seen = {}
    monkeypatch.setattr("worktray.demo.create_demo_app", lambda: "app")
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: seen.update(kwargs, app=app))

    cli.serve(8080, False, "0.0.0.0", demo=True)

    assert (seen["app"], seen["host"], seen["proxy_headers"], seen["forwarded_allow_ips"]) == ("app", "0.0.0.0", True, "*")
