"""A private queue for work that needs attention."""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "worktray"
ENV_PREFIX = "WORKTRAY"

try:
    __version__ = version(APP_NAME)
except PackageNotFoundError:  # running from a checkout without an install
    __version__ = "0.0.0"
