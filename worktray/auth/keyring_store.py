"""Secrets live in the operating system's keyring, never in the database or in files.

macOS gets the native Keychain backend with in-place updates; other systems get whatever keyring
backend is installed (Secret Service, KWallet, Windows Credential Locker). Entries are grouped under
one service name derived from the data directory, so two profiles never see each other's tokens.
"""

import hashlib
from pathlib import Path
import sys
import threading
import time

from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

from worktray import APP_NAME
from worktray.paths import home
from worktray.sources.errors import SourceError

# Seconds a value read from the keyring is reused. Each Settings page load and each sync reads
# several tokens, and some keyrings take a noticeable time to answer.
CACHE_SECONDS = 60
UNAVAILABLE = "Cannot reach your system keyring. Unlock it, or on Linux install one such as GNOME Keyring. You can also set tokens as WORKTRAY_ environment variables."


class KeyringStore:
    """Read, write and clear named secrets for one data directory.

    Reads are kept for CACHE_SECONDS; a write or clear through this store updates the copy at once.
    """

    def __init__(self, directory: Path) -> None:
        identity = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:16]
        self.service = f"{APP_NAME}.{identity}"
        self.native = sys.platform == "darwin"
        self.backend = self._backend()
        self.cache: dict[str, tuple[float, str | None]] = {}
        self.lock = threading.Lock()

    def _backend(self):
        if self.native:
            from keyring.backends.macOS import Keyring

            return Keyring()
        import keyring

        return keyring.get_keyring()

    def _call(self, action):
        """Run one keyring call. With no keyring found, look again once: one may have been unlocked or installed since."""
        try:
            return action(self.backend)
        except NoKeyringError:
            self.backend = self._backend()
            try:
                return action(self.backend)
            except KeyringError as error:
                raise SourceError(UNAVAILABLE) from error
        except KeyringError as error:
            raise SourceError(UNAVAILABLE) from error

    def read(self, name: str) -> str | None:
        with self.lock:
            cached = self.cache.get(name)
            if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
                return cached[1]
        value = self._call(lambda backend: backend.get_password(self.service, name))
        with self.lock:
            self.cache[name] = (time.monotonic(), value)
        return value

    def write(self, name: str, value: str) -> None:
        if self.native:
            from worktray.auth.secure_keychain import save_password

            self._call(lambda backend: save_password(self.service, name, value))
        else:
            self._call(lambda backend: backend.set_password(self.service, name, value))
        with self.lock:
            self.cache[name] = (time.monotonic(), value)

    def clear(self, name: str) -> None:
        with self.lock:
            self.cache.pop(name, None)
        try:
            self._call(lambda backend: backend.delete_password(self.service, name))
        except SourceError as error:
            # Deleting an entry that isn't there is fine. macOS reports other failures, such as a
            # locked keychain, as the same error, so it counts as cleared only if the value is gone.
            if not isinstance(error.__cause__, PasswordDeleteError) or self._call(lambda backend: backend.get_password(self.service, name)) is not None:
                raise


class MemoryStore:
    """A keyring that forgets at exit, for tests and for the settings page's own tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, value: str) -> None:
        self.values[name] = value

    def clear(self, name: str) -> None:
        self.values.pop(name, None)


_store: KeyringStore | MemoryStore | None = None


def secret_store() -> KeyringStore | MemoryStore:
    """One store per process, bound to the data directory in use when it was first needed."""
    global _store
    if _store is None:
        _store = KeyringStore(home())
    return _store


def use_secret_store(store: KeyringStore | MemoryStore | None) -> None:
    """Replace the process-wide store; tests pass a MemoryStore, None goes back to the keyring."""
    global _store
    _store = store
