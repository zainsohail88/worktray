"""The stable surface for third-party sources.

A plugin is a Python package that exposes a `Source`, a list of them, or a function returning
either, under the `worktray.sources` entry point group:

    [project.entry-points."worktray.sources"]
    linear = "worktray_linear:SOURCE"

Import only from this module; everything else in worktray may change between minor versions.
See "Adding a source" in CONTRIBUTING.md for an example.
"""

from worktray.auth.browser import open_sign_in
from worktray.config import Secret, Setting
from worktray.models import Batch, Item
from worktray.sources.errors import NotConnectedError, SignInRequired, SourceError
from worktray.sources.registry import ENTRY_POINT_GROUP, QUICK, SLOW, STEADY, Source
from worktray.store import Store

__all__ = [
    "ENTRY_POINT_GROUP",
    "QUICK",
    "SLOW",
    "STEADY",
    "Batch",
    "Item",
    "NotConnectedError",
    "Secret",
    "Setting",
    "SignInRequired",
    "Source",
    "SourceError",
    "Store",
    "open_sign_in",
]
