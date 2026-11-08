import asyncio

import httpx
import pytest

from worktray.models import Item
from worktray.sources import teamcity
from worktray.sources.errors import NotConnectedError, SourceError

BASE = "https://ci.example.com"


@pytest.fixture
def connected(store):
    teamcity.TEAMCITY_URL.save(store, BASE)
    teamcity.TEAMCITY_TOKEN.save("t")
    return store


def failing(url: str) -> Item:
    return Item(key="https://github.com/o/r/pull/1", title="Fix", source="github", live=True, status="open", checks_url=url, checks_detail="Pull Request")


def test_build_id_reads_both_teamcity_link_shapes():
    assert [teamcity.build_id(f"{BASE}/buildConfiguration/app_Pr/394024", BASE), teamcity.build_id(f"{BASE}/viewLog.html?buildId=555&x=1", BASE)] == ["394024", "555"]


def test_build_id_ignores_other_hosts():
    assert teamcity.build_id("https://github.com/o/r/actions/runs/1", BASE) is None


def test_failing_teamcity_check_gets_the_build_status_text(connected):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"statusText": "Tests failed: 3 (2 new)", "buildType": {"name": "PR build"}}))

    [item] = asyncio.run(teamcity.enrich_checks(connected, [failing(f"{BASE}/buildConfiguration/app_Pr/9")], transport))

    assert item.checks_detail == "PR build: Tests failed: 3 (2 new)"


def test_failed_teamcity_lookup_keeps_the_check_name(connected):
    transport = httpx.MockTransport(lambda request: httpx.Response(403))

    [item] = asyncio.run(teamcity.enrich_checks(connected, [failing(f"{BASE}/buildConfiguration/app_Pr/9")], transport))

    assert item.checks_detail == "Pull Request"


def test_unreadable_teamcity_credentials_keep_the_check_name(store, monkeypatch):
    def locked(store) -> dict[str, str]:
        raise SourceError("Unlock the keyring")

    monkeypatch.setattr(teamcity, "teamcity_config", locked)
    items = [failing(f"{BASE}/buildConfiguration/app_Pr/9")]

    assert asyncio.run(teamcity.enrich_checks(store, items)) is items


def test_checks_are_untouched_without_teamcity_credentials(store):
    items = [failing(f"{BASE}/buildConfiguration/app_Pr/9")]

    assert asyncio.run(teamcity.enrich_checks(store, items)) is items


def test_teamcity_without_credentials_is_not_connected_rather_than_failed(store):
    with pytest.raises(NotConnectedError):
        asyncio.run(teamcity.read_teamcity(store, httpx.MockTransport(lambda request: httpx.Response(200))))


def test_teamcity_connection_reports_host_and_version(connected):
    batch = asyncio.run(teamcity.read_teamcity(connected, httpx.MockTransport(lambda request: httpx.Response(200, json={"version": "2026.1"}))))

    assert batch.detail == "Connected to ci.example.com, TeamCity 2026.1. Failed checks on your pull requests now show why."


def test_teamcity_rejected_token_says_how_to_replace_it(connected):
    with pytest.raises(SourceError, match="Replace it in Settings"):
        asyncio.run(teamcity.read_teamcity(connected, httpx.MockTransport(lambda request: httpx.Response(401))))
