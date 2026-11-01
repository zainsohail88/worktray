"""Settings, secrets and the per-source on/off switch.

A `Setting` is a non-secret preference kept in the settings table. A `Secret` is a token kept in
the system keyring. Both are read from a `WORKTRAY_<KEY>` shell variable first, so an export
overrides whatever the Settings page or `worktray auth` saved; the page shows such a field as
locked. Nothing about any particular organisation lives in code: every source declares the
fields it needs and the UI, the CLI and the engine read them from here.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import os
import re
import shlex

from worktray import ENV_PREFIX
from worktray.auth.keyring_store import secret_store
from worktray.models import web_link_problem
from worktray.sources.errors import SourceError
from worktray.store import Store

SOURCES_ENV = f"{ENV_PREFIX}_SOURCES"
OFF_VALUES = frozenset({"0", "off", "false", "no"})
NAME = re.compile(r"[\w.-]+")


def env_name(key: str) -> str:
    return f"{ENV_PREFIX}_{key.upper()}"


def web_url(value: str) -> str:
    """An https URL without a trailing slash; plain http only for a server on this machine."""
    value = value.strip().rstrip("/")
    problem = web_link_problem(value) if value else ""
    if problem:
        raise ValueError(problem)
    return value


def command_line(value: str) -> str:
    """A command and its arguments, quoted the way a shell would."""
    value = value.strip()
    try:
        shlex.split(value)
    except ValueError as error:
        raise ValueError(f"Check the quotes in the command ({error})") from error
    return value


def name_list(value: str) -> str:
    """Comma-separated organisation or workspace names, normalised to "a, b"."""
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if any(not NAME.fullmatch(part) for part in parts):
        raise ValueError("Use names made of letters, digits, dots, dashes and underscores, separated by commas")
    return ", ".join(dict.fromkeys(parts))


def single_name(value: str) -> str:
    value = value.strip()
    if value and not NAME.fullmatch(value):
        raise ValueError("Use one name made of letters, digits, dots, dashes and underscores")
    return value


def team_slug(value: str) -> str:
    value = value.strip()
    if value and not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        raise ValueError("Use org/team-slug, as in acme/platform")
    return value


def plain_text(value: str) -> str:
    """One line of text with no quotes, safe to place inside a query."""
    value = " ".join(value.split())
    if '"' in value or "\\" in value:
        raise ValueError("Leave out quotes and backslashes")
    return value


@dataclass(frozen=True)
class Setting:
    """A non-secret preference: what to read, not how to log in."""

    key: str
    label: str
    default: str = ""
    help: str = ""
    placeholder: str = ""
    validate: Callable[[str], str] | None = None
    # False for a setting that decides which program runs, such as a command line. The browser
    # page can't change those, so a web page that reaches the server can't make it run anything.
    web: bool = True

    @property
    def env(self) -> str:
        return env_name(self.key)

    def locked(self) -> bool:
        """True when a shell variable decides the value, so saving a new one would have no effect."""
        return bool(os.environ.get(self.env, "").strip())

    def clean(self, value: str) -> str:
        """The value as it will be stored, or a ValueError that says what to fix."""
        return self.validate(value) if self.validate else value.strip()

    def read(self, store: Store) -> str:
        """The shell variable, checked the same way as a saved value, else the saved value, else the default."""
        exported = os.environ.get(self.env, "").strip()
        if exported:
            try:
                return self.clean(exported)
            except ValueError as error:
                raise SourceError(f"{self.env} is not valid: {error}") from error
        return (store.setting(self.key) or self.default).strip()

    def saved(self, store: Store) -> str:
        """What the user typed, without the default, so a form shows an empty field rather than a guess."""
        return store.setting(self.key)

    def save(self, store: Store, value: str) -> None:
        store.save_setting(self.key, self.clean(value))

    def items(self, store: Store) -> list[str]:
        """A comma-separated value as a list, in order, without blanks or repeats."""
        return list(dict.fromkeys(part.strip() for part in self.read(store).split(",") if part.strip()))


@dataclass(frozen=True)
class Secret:
    """A token or password. Stored in the keyring, shown to the browser only as set or not set."""

    key: str
    label: str
    help: str = ""

    @property
    def env(self) -> str:
        return env_name(self.key)

    def locked(self) -> bool:
        return bool(os.environ.get(self.env, "").strip())

    def read(self) -> str:
        return (os.environ.get(self.env) or secret_store().read(self.key) or "").strip()

    def is_set(self) -> bool:
        return bool(self.read())

    def save(self, value: str) -> None:
        value = value.strip()
        if not value:
            raise ValueError("Enter a value, or use Clear to remove the saved one")
        secret_store().write(self.key, value)

    def clear(self) -> None:
        secret_store().clear(self.key)


def enabled_key(source: str) -> str:
    return f"source_{source}_enabled"


def source_enabled(store: Store, source: str) -> bool:
    """A source is off until switched on, so nothing is read or run that you didn't choose.

    WORKTRAY_SOURCES, when set, is the complete list of sources that are on.
    """
    return enabled_from(store.setting(enabled_key(source)), source)


def enabled_from(saved: str, source: str) -> bool:
    """The switch given the saved value; the environment wins. An empty variable counts as unset."""
    listed = os.environ.get(SOURCES_ENV, "").strip()
    if listed:
        return source in {part.strip() for part in listed.split(",")}
    value = os.environ.get(env_name(enabled_key(source)), "").strip() or saved or "off"
    return value.strip().lower() not in OFF_VALUES


def enabled_sources(store: Store, names: Iterable[str]) -> set[str]:
    """The switched-on sources among names, read with one query instead of one per source."""
    saved = store.settings_with_prefix("source_")
    return {name for name in names if enabled_from(saved.get(enabled_key(name), ""), name)}


def enabled_locked(source: str) -> bool:
    return bool(os.environ.get(SOURCES_ENV, "").strip() or os.environ.get(env_name(enabled_key(source)), "").strip())


def set_source_enabled(store: Store, source: str, on: bool) -> None:
    if enabled_locked(source):
        raise PermissionError(f"An environment variable decides whether {source} is on. Change {SOURCES_ENV} or {env_name(enabled_key(source))}")
    store.save_setting(enabled_key(source), "on" if on else "off")


def switch_on_if_unset(store: Store, source: str) -> bool:
    """Setting a source up is a clear sign you want it, so it is switched on unless you chose before.

    Returns whether it is on afterwards. An explicit off, and any switch decided by the environment, stay as they are.
    """
    if not enabled_locked(source) and not store.has_setting(enabled_key(source)):
        store.save_setting(enabled_key(source), "on")
    return source_enabled(store, source)
