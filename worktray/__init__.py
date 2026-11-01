"""A private queue for work that needs attention."""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "worktray"
ENV_PREFIX = "WORKTRAY"
# worktray is installed from GitHub until it is published to PyPI.
INSTALL_SOURCE = "git+https://github.com/zainsohail88/worktray"


def install_command(extras: tuple[str, ...] | list[str] = ()) -> str:
    """The command that installs worktray with the given optional extras, such as ("mcp",)."""
    name = f"{APP_NAME}[{','.join(extras)}]" if extras else APP_NAME
    return f"uv tool install '{name} @ {INSTALL_SOURCE}'"


try:
    __version__ = version(APP_NAME)
except PackageNotFoundError:  # running from a checkout without an install
    __version__ = "0.0.0"
