"""Regression tests for the issues found in the pre-release review."""

import asyncio
import subprocess
import warnings

import httpx
import pytest

from worktray import ENV_PREFIX, service
from worktray.auth import browser, interactive
from worktray.config import SOURCES_ENV, enabled_locked, set_source_enabled, source_enabled
from worktray.engine import Engine
from worktray.models import Batch, Item
from worktray.sources import teamcity, upstream
from worktray.sources.errors import SignInRequired, SourceError
from worktray.sources.registry import Source
from worktray.store import Store

PR = "https://github.com/example-org/app/pull/12"


async def empty() -> Batch:
    return Batch()


def ask(store: Store, title: str) -> None:
    store.ingest([Item(key="slack:a", title=title, source="slack", status="open")])


def test_finished_work_checks_pull_requests_when_the_keyring_is_unavailable(store, monkeypatch):
    def no_keyring(store):
        raise SourceError("No usable system keyring")

    async def pull(reference, organisations=()):
        return upstream.LinkState(text="example-org/app#12 merged", finished=True)

    monkeypatch.setattr(upstream, "atlassian_config", no_keyring)
    monkeypatch.setattr(upstream, "_github_state", pull)
    ask(store, f"Review {PR} and ABC-1")

    batch = asyncio.run(upstream.read_upstream(store))

    assert "Skipped 1 ticket because Jira isn't set up" in batch.detail
    assert store.items()[0].linked_status == "example-org/app#12 merged"


def test_finished_work_leaves_switched_off_sources_alone(store, monkeypatch):
    async def never(*args):
        raise AssertionError("a switched-off source was contacted")

    monkeypatch.setattr(upstream, "_github_state", never)
    monkeypatch.setattr(upstream, "atlassian_config", never)
    set_source_enabled(store, "github", False)
    set_source_enabled(store, "jira", False)
    ask(store, f"Review {PR} and ABC-1")

    batch = asyncio.run(upstream.read_upstream(store))

    assert "Skipped 1 GitHub link because GitHub is off" in batch.detail


def test_switched_off_teamcity_is_never_called(store):
    teamcity.TEAMCITY_URL.save(store, "https://ci.example.com")
    teamcity.TEAMCITY_TOKEN.save("t")
    set_source_enabled(store, "teamcity", False)
    items = [Item(key=PR, title="Fix", source="github", live=True, status="open", checks_url="https://ci.example.com/viewLog.html?buildId=1")]

    def refuse(request):
        raise AssertionError("TeamCity was called while switched off")

    assert asyncio.run(teamcity.enrich_checks(store, items, httpx.MockTransport(refuse))) is items


def test_queue_reads_the_switches_once_not_once_per_proposal(store, monkeypatch):
    store.ingest([Item(key=f"slack:{index}", title=f"Ask {index}", source="slack") for index in range(200)])
    engine = Engine(store, {"slack": empty, "jira": empty})
    calls = []
    original = Store.setting
    monkeypatch.setattr(Store, "setting", lambda self, *args: calls.append(args) or original(self, *args))

    assert len(engine.items()) == 200
    assert len(calls) < 5


def test_empty_source_list_variable_counts_as_unset(store, monkeypatch):
    monkeypatch.setenv(SOURCES_ENV, "  ")
    monkeypatch.setenv(f"{ENV_PREFIX}_SOURCE_SLACK_ENABLED", "")

    assert (source_enabled(store, "jira"), enabled_locked("jira"), enabled_locked("slack")) == (True, False, False)


def test_sign_in_link_goes_to_the_page_not_a_browser_on_the_server(monkeypatch):
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: pytest.fail("opened a browser on the server"))
    received = []

    async def flow() -> None:
        # Google's flow opens the link from a worker thread; the handler must follow it there.
        await asyncio.to_thread(browser.open_sign_in, "https://accounts.example.com/auth", "Google")

    with browser.hand_links_to(received.append):
        asyncio.run(flow())

    assert received == ["https://accounts.example.com/auth"]


def test_settings_page_can_fetch_the_sign_in_link(store):
    from fastapi.testclient import TestClient

    from worktray.web.app import create_app

    async def connect(store) -> str:
        browser.open_sign_in("https://accounts.example.com/auth", "Fake")
        return "Connected"

    fake = Source("fake", "Fake", lambda store, home: empty(), connect=connect)
    client = TestClient(create_app(store, Engine(store, {"fake": empty}, {"fake": fake})), base_url="http://localhost")

    outcome = client.post("/api/config/fake/connect", headers={"Origin": "http://localhost"}).json()

    assert outcome == {"ok": True, "detail": "Connected"}
    assert client.get("/api/config/fake/sign-in-link").json() == {"url": ""}


def test_service_command_failure_shows_the_tools_message():
    with pytest.raises(SystemExit, match="boom"):
        service._run("sh", "-c", "echo boom >&2; exit 3")


def test_missing_service_tool_is_named():
    with pytest.raises(SystemExit, match="was not found"):
        service._run("worktray-no-such-tool")


def test_service_command_success_returns_the_result():
    assert isinstance(service._run("true"), subprocess.CompletedProcess)


def test_mcp_import_leaves_deprecation_warnings_on():
    pytest.importorskip("fastmcp")
    from worktray.sources.public_slack import _mcp

    before = list(warnings.filters)
    _mcp()

    assert warnings.filters == before


def test_reconnect_goes_straight_to_browser_sign_in(store, monkeypatch):
    async def check(store) -> str:
        raise AssertionError("reconnect should not check first")

    async def connect(store) -> str:
        return "Connected"

    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    source = Source("fake", "Fake", lambda store, home: empty(), check=check, connect=connect)

    assert asyncio.run(interactive.verify(store, {}, source, interactive=True, reconnect=True)) == interactive.READY


def test_check_that_needs_a_sign_in_offers_the_browser(store, monkeypatch):
    async def check(store) -> str:
        raise SignInRequired("needs browser sign-in")

    async def connect(store) -> str:
        return "Connected"

    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    source = Source("fake", "Fake", lambda store, home: empty(), check=check, connect=connect)

    assert asyncio.run(interactive.verify(store, {}, source, interactive=True, reconnect=False)) == interactive.READY


def test_other_check_failures_do_not_open_the_browser(store, monkeypatch):
    async def check(store) -> str:
        raise SourceError("the server is down")

    async def connect(store) -> str:
        raise AssertionError("a sign-in can't fix a server that is down")

    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    source = Source("fake", "Fake", lambda store, home: empty(), check=check, connect=connect)

    assert asyncio.run(interactive.verify(store, {}, source, interactive=True, reconnect=False)) == interactive.FAILED
