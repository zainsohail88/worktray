import plistlib
import sys

import pytest

from worktray import cli, service
from worktray.config import source_enabled
from worktray.paths import database
from worktray.sources import atlassian
from worktray.store import Store


def run(capsys, *argv: str) -> tuple[int, str]:
    with pytest.raises(SystemExit) as stopped:
        cli.main(list(argv))
    return stopped.value.code, capsys.readouterr().out


def test_version_flag_prints_the_version(capsys):
    code, output = run(capsys, "--version")

    assert code == 0 and output.startswith("worktray ")


def test_sources_lists_every_built_in_source(capsys):
    code, output = run(capsys, "sources")

    assert code == 0 and "jira" in output and "claude_desktop" in output


def test_sources_disable_switches_a_source_off(capsys):
    code, _ = run(capsys, "sources", "disable", "slack")

    assert code == 0 and source_enabled(Store(database()), "slack") is False


def test_unknown_source_is_an_error(capsys):
    assert run(capsys, "sources", "enable", "nope")[0] == 2


def test_config_set_saves_a_setting(capsys):
    code, _ = run(capsys, "config", "set", "jira_url", "https://acme.atlassian.net/")

    assert code == 0 and Store(database()).setting("jira_url") == "https://acme.atlassian.net"


def test_config_set_rejects_an_invalid_value(capsys):
    assert run(capsys, "config", "set", "jira_url", "ftp://nope")[0] == 1


def test_config_set_saves_a_secret_to_the_keyring(capsys, isolated):
    code, _ = run(capsys, "config", "set", "jira_api_token", "t0ken")

    assert code == 0 and isolated.values["jira_api_token"] == "t0ken"


def test_config_list_never_prints_a_secret(capsys):
    atlassian.JIRA_API_TOKEN.save("t0ken-value")

    code, output = run(capsys, "config")

    assert code == 0 and "t0ken-value" not in output and "jira_api_token" in output


def test_config_refuses_a_value_the_environment_decides(capsys, monkeypatch):
    monkeypatch.setenv(atlassian.JIRA_URL.env, "https://env.atlassian.net")

    assert run(capsys, "config", "set", "jira_url", "https://other.atlassian.net")[0] == 1


def test_auth_check_without_a_terminal_only_checks(capsys, monkeypatch):
    monkeypatch.setenv("WORKTRAY_SOURCES", "jira")

    code, output = run(capsys, "auth", "--check")

    assert code == 0 and "Skipped" in output


def test_launchd_agent_runs_this_interpreter_and_keeps_tokens_out(monkeypatch):
    monkeypatch.setenv("WORKTRAY_PORT", "9000")

    rendered = plistlib.loads(service.render("darwin").content.encode())

    assert rendered["ProgramArguments"] == [sys.executable, "-m", "worktray", "serve"]
    assert set(rendered["EnvironmentVariables"]) == {"PATH", "WORKTRAY_PORT", "WORKTRAY_HOME"}
    assert rendered["EnvironmentVariables"]["WORKTRAY_PORT"] == "9000"


def test_systemd_unit_runs_this_interpreter():
    rendered = service.render("linux")

    assert rendered.path.name == "worktray.service" and f"ExecStart={sys.executable} -m worktray serve" in rendered.content


def test_service_is_refused_on_other_platforms():
    with pytest.raises(SystemExit):
        service.render("win32")
