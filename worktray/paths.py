"""Where the app keeps its database, OAuth markers and log.

The default is the per-user application directory of the platform. `WORKTRAY_HOME` overrides
it, so a second profile or a test run points somewhere else; keyring entries are keyed by the
same directory, so two homes never share a login. Paths are computed on each call rather than
at import, so an override set after import still applies.
"""

import os
from pathlib import Path
import sys

from worktray import APP_NAME, ENV_PREFIX

HOME_ENV = f"{ENV_PREFIX}_HOME"


def _variable(name: str) -> str:
    """An environment variable, with an empty or relative value counted as unset, as the XDG spec says."""
    value = os.environ.get(name, "").strip()
    return value if value and Path(value).expanduser().is_absolute() else ""


def home() -> Path:
    """Always an absolute path, so the service file and the keyring name the same folder from anywhere."""
    override = os.environ.get(HOME_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        return Path(_variable("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME
    return Path(_variable("XDG_DATA_HOME") or Path.home() / ".local" / "share").expanduser() / APP_NAME


def config_home() -> Path:
    return Path(_variable("XDG_CONFIG_HOME") or Path.home() / ".config").expanduser()


def database() -> Path:
    return home() / "tracker.sqlite3"


def oauth_dir() -> Path:
    return home() / "oauth"


def log_file() -> Path:
    return home() / f"{APP_NAME}.log"
