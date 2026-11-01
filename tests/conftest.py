"""Every test runs against a temporary data folder, an in-memory keyring and no WORKTRAY_* variables."""

import os

import pytest

from worktray import ENV_PREFIX
from worktray.auth.keyring_store import MemoryStore, use_secret_store
from worktray.auth.oauth import reset_token_manager
from worktray.config import enabled_key
from worktray.sources.registry import BUILTIN, use_registry
from worktray.store import Store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith(f"{ENV_PREFIX}_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv(f"{ENV_PREFIX}_HOME", str(tmp_path / "home"))
    secrets = MemoryStore()
    use_secret_store(secrets)
    reset_token_manager()
    use_registry(None)
    yield secrets
    use_secret_store(None)
    reset_token_manager()
    use_registry(None)


def everything_on(store: Store) -> Store:
    """Sources start switched off; most tests are about a person who has switched them all on."""
    for source in BUILTIN:
        store.save_setting(enabled_key(source.name), "on")
    return store


@pytest.fixture
def store(tmp_path):
    return everything_on(Store(tmp_path / "tracker.sqlite3"))


@pytest.fixture
def fresh_store(tmp_path):
    """A first start: nothing chosen yet."""
    return Store(tmp_path / "fresh.sqlite3")
