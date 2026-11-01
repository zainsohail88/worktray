"""Settings routes: what each source needs, saved values, and connection checks.

Secret values travel one way only. The browser can send a token to be saved in the keyring or
ask for it to be cleared, and it learns whether one is set, but no route ever returns the value.
A field decided by an environment variable is reported as locked and cannot be saved here, and
so is a setting that decides which program runs: that one is set from the terminal only.

The keyring can block for a while (an unlock prompt, a slow Secret Service), so reading and saving
run in a worker thread rather than holding up every other request.
"""

import asyncio
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from worktray.auth.browser import hand_links_to
from worktray.config import Secret, Setting, enabled_locked, set_source_enabled, source_enabled, switch_on_if_unset
from worktray.engine import Engine
from worktray.sources.errors import NotConnectedError, SignInRequired, SourceError
from worktray.sources.registry import Action, Source, check_for, is_available
from worktray.store import Store

CHECK_TIMEOUT = 60
# The browser consent screen waits for a person, so connecting gets as long as Google's own flow.
CONNECT_TIMEOUT = 200


class ConfigUpdate(BaseModel):
    enabled: bool | None = None
    settings: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list)


def describe_setting(store: Store, field: Setting) -> dict:
    problem = ""
    try:
        value = field.read(store) if field.locked() else field.saved(store)
    except SourceError as error:
        # An exported value that fails the check is shown as typed, with what to fix.
        value, problem = os.environ.get(field.env, "").strip(), str(error)
    return {
        "key": field.key,
        "label": field.label,
        "help": field.help,
        "placeholder": field.placeholder,
        "default": field.default,
        "value": value,
        "locked": field.locked(),
        "env": field.env,
        "web": field.web,
        "problem": problem,
    }


def describe_secret(field: Secret) -> dict:
    """Whether a secret is set, never its value."""
    try:
        is_set = field.is_set()
        problem = ""
    except SourceError as error:
        is_set = False
        problem = str(error)
    return {"key": field.key, "label": field.label, "help": field.help, "set": is_set, "locked": field.locked(), "env": field.env, "problem": problem}


def describe(store: Store, sources: dict[str, Source], source: Source) -> dict:
    parent = sources.get(source.uses)
    return {
        "name": source.name,
        "label": source.label,
        "description": source.description,
        "group": source.group,
        "enabled": source_enabled(store, source.name),
        "enabled_locked": enabled_locked(source.name),
        "available": is_available(source),
        "extras": list(source.extras),
        "uses": source.uses,
        "uses_label": parent.label if parent else "",
        "can_check": check_for(sources, source) is not None,
        "can_connect": source.connect is not None,
        "can_disconnect": source.disconnect is not None,
        "settings": [describe_setting(store, field) for field in source.settings],
        "secrets": [describe_secret(field) for field in source.secrets],
    }


async def _outcome(action: Action, store: Store, timeout: float) -> dict:
    """Run a check or sign-in and report it as a sentence; failures are results, not HTTP errors."""
    try:
        return {"ok": True, "detail": await asyncio.wait_for(action(store), timeout)}
    except NotConnectedError as error:
        return {"ok": False, "detail": str(error), "not_connected": True}
    except SignInRequired as error:
        return {"ok": False, "detail": str(error), "not_connected": True, "sign_in": True}
    except SourceError as error:
        return {"ok": False, "detail": str(error)}
    except TimeoutError:
        return {"ok": False, "detail": "No answer in time. Check your connection and try again."}
    except Exception as error:  # noqa: BLE001 - shown to the user, logged nowhere else
        return {"ok": False, "detail": f"Something went wrong ({type(error).__name__})."}


def settings_router(store: Store, engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/config")
    # Sign-in links waiting for the page to open them, by source. The server may run as a service
    # with no display, so the person's own browser opens the link rather than one on the server.
    sign_in_links: dict[str, str] = {}

    def source_named(name: str) -> Source:
        source = engine.sources.get(name)
        if source is None:
            raise HTTPException(404, "Unknown source")
        return source

    def describe_all() -> dict:
        return {"sources": [describe(store, engine.sources, source) for source in engine.sources.values()]}

    @router.get("")
    async def config() -> dict:
        return await asyncio.to_thread(describe_all)

    @router.post("/{name}")
    async def update(name: str, body: ConfigUpdate) -> dict:
        source = source_named(name)
        return await asyncio.to_thread(save, source, body)

    def save(source: Source, body: ConfigUpdate) -> dict:
        name = source.name
        settings = {field.key: field for field in source.settings}
        secrets = {field.key: field for field in source.secrets}
        unknown = (set(body.settings) - set(settings)) | ((set(body.secrets) | set(body.clear)) - set(secrets))
        if unknown:
            raise HTTPException(400, f"{source.label} has no setting named {', '.join(sorted(unknown))}")
        terminal_only = [key for key in body.settings if not settings[key].web]
        if terminal_only:
            raise HTTPException(403, f"For safety this is set from the terminal only: worktray config set {terminal_only[0]} '…'")
        locked = [field.env for key in [*body.settings, *body.secrets, *body.clear] for field in [settings.get(key) or secrets[key]] if field.locked()]
        if locked:
            raise HTTPException(409, f"Set by an environment variable, so it can't be changed here: {', '.join(locked)}")
        cleaned = {}
        for key, value in body.settings.items():
            try:
                cleaned[key] = settings[key].clean(value)
            except ValueError as error:
                raise HTTPException(400, f"{settings[key].label}: {error}") from error
        if any(not value.strip() for value in body.secrets.values()):
            raise HTTPException(400, "Leave a secret field empty to keep the saved value, or use Clear to remove it")
        try:
            if body.enabled is not None:
                set_source_enabled(store, name, body.enabled)
            for key, value in cleaned.items():
                store.save_setting(key, value)
            for key, value in body.secrets.items():
                secrets[key].save(value)
            for key in body.clear:
                secrets[key].clear()
            if body.enabled is None and (any(cleaned.values()) or body.secrets):
                switch_on_if_unset(store, name)
        except PermissionError as error:
            raise HTTPException(409, str(error)) from error
        except SourceError as error:
            raise HTTPException(503, str(error)) from error
        return describe(store, engine.sources, source)

    @router.post("/{name}/check")
    async def check(name: str) -> dict:
        action = check_for(engine.sources, source_named(name))
        if action is None:
            raise HTTPException(400, "This source has no connection to check")
        return await _outcome(action, store, CHECK_TIMEOUT)

    @router.post("/{name}/connect")
    async def connect(name: str) -> dict:
        source = source_named(name)
        if source.connect is None:
            raise HTTPException(400, "This source has no browser sign-in")
        sign_in_links.pop(name, None)
        try:
            with hand_links_to(lambda url: sign_in_links.__setitem__(name, url)):
                return await _outcome(source.connect, store, CONNECT_TIMEOUT)
        finally:
            sign_in_links.pop(name, None)

    @router.get("/{name}/sign-in-link")
    async def sign_in_link(name: str) -> dict:
        """The link a running Connect is waiting on, so the page can offer it; empty until the flow produces one."""
        source_named(name)
        return {"url": sign_in_links.get(name, "")}

    @router.post("/{name}/disconnect")
    async def disconnect(name: str) -> dict:
        source = source_named(name)
        if source.disconnect is None:
            raise HTTPException(400, "This source has no saved sign-in to remove")
        return await _outcome(source.disconnect, store, CHECK_TIMEOUT)

    return router
