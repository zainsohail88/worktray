import pytest

from worktray.config import (
    switch_on_if_unset,
    ENV_PREFIX,
    SOURCES_ENV,
    Secret,
    Setting,
    enabled_locked,
    name_list,
    plain_text,
    set_source_enabled,
    single_name,
    source_enabled,
    team_slug,
    web_url,
)
from worktray.paths import database, home

ORGS = Setting("github_orgs", "Organisations", validate=name_list)
EPIC = Setting("oncall_epic_name", "Epic word", default="KTLO")
TOKEN = Secret("jira_api_token", "Token")


def test_defaults_apply_when_nothing_was_saved(store):
    assert (ORGS.read(store), EPIC.read(store)) == ("", "KTLO")


def test_saved_value_is_cleaned_and_read_as_a_list(store):
    ORGS.save(store, " acme,acme-labs,, acme ")

    assert (store.setting("github_orgs"), ORGS.items(store)) == ("acme, acme-labs", ["acme", "acme-labs"])


def test_shell_variable_wins_over_the_saved_value_and_locks_the_field(store, monkeypatch):
    ORGS.save(store, "acme")
    monkeypatch.setenv(ORGS.env, "other-org")

    assert (ORGS.items(store), ORGS.locked()) == (["other-org"], True)


def test_variable_names_carry_the_app_prefix():
    assert (ORGS.env, TOKEN.env) == (f"{ENV_PREFIX}_GITHUB_ORGS", f"{ENV_PREFIX}_JIRA_API_TOKEN")


def test_secret_is_kept_in_the_keyring_not_the_database(store, isolated):
    TOKEN.save("s3cret")

    assert (TOKEN.read(), isolated.values["jira_api_token"], store.setting("jira_api_token")) == ("s3cret", "s3cret", "")


def test_cleared_secret_is_not_set():
    TOKEN.save("s3cret")
    TOKEN.clear()

    assert TOKEN.is_set() is False


def test_blank_secret_is_refused_so_clear_is_explicit():
    with pytest.raises(ValueError):
        TOKEN.save("  ")


def test_secret_from_the_environment_wins(monkeypatch):
    TOKEN.save("saved")
    monkeypatch.setenv(TOKEN.env, "from-env")

    assert (TOKEN.read(), TOKEN.locked()) == ("from-env", True)


@pytest.mark.parametrize(
    "validate, value, cleaned",
    [
        (web_url, "https://jira.example.com/", "https://jira.example.com"),
        (web_url, "http://localhost:8080", "http://localhost:8080"),
        (web_url, "", ""),
        (team_slug, "acme/platform", "acme/platform"),
        (single_name, " acme ", "acme"),
        (plain_text, "  keep   the lights  on ", "keep the lights on"),
    ],
)
def test_validators_normalise_good_values(validate, value, cleaned):
    assert validate(value) == cleaned


@pytest.mark.parametrize(
    "validate, value",
    [
        (web_url, "http://jira.example.com"),
        (web_url, "javascript:alert(1)"),
        (team_slug, "platform"),
        (name_list, "acme corp"),
        (single_name, "a/b"),
        (plain_text, 'KTLO" OR project = X'),
    ],
)
def test_validators_reject_bad_values(validate, value):
    with pytest.raises(ValueError):
        validate(value)


def test_sources_are_off_until_switched_on(fresh_store):
    set_source_enabled(fresh_store, "jira", True)

    assert (source_enabled(fresh_store, "jira"), source_enabled(fresh_store, "slack")) == (True, False)


def test_setting_a_source_up_switches_it_on_unless_you_turned_it_off(fresh_store):
    set_source_enabled(fresh_store, "slack", False)

    assert (switch_on_if_unset(fresh_store, "jira"), switch_on_if_unset(fresh_store, "slack")) == (True, False)


def test_source_list_variable_names_exactly_the_sources_that_are_on(store, monkeypatch):
    monkeypatch.setenv(SOURCES_ENV, "jira, github")

    assert [source_enabled(store, name) for name in ("jira", "github", "slack")] == [True, True, False]


def test_switch_decided_by_the_environment_cannot_be_changed(store, monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}_SOURCE_SLACK_ENABLED", "off")

    assert (source_enabled(store, "slack"), enabled_locked("slack")) == (False, True)
    with pytest.raises(PermissionError):
        set_source_enabled(store, "slack", True)


def test_data_folder_follows_the_home_variable(tmp_path, monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}_HOME", str(tmp_path / "elsewhere"))

    assert (home(), database()) == (tmp_path / "elsewhere", tmp_path / "elsewhere" / "tracker.sqlite3")
