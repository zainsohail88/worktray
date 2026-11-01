"""Terminal setup: ask for each source's settings and tokens once, sign in where needed, check the result.

This is the terminal twin of the Settings page; both write to the same settings table and keyring.
"""

import getpass
import sys

import httpx

from worktray import install_command
from worktray.config import Secret, Setting, enabled_sources, switch_on_if_unset
from worktray.sources.errors import NotConnectedError, SignInRequired, SourceError
from worktray.sources.registry import Source, check_for, is_available, registry
from worktray.store import Store

ATTEMPTS = 3


def _ask_setting(store: Store, field: Setting) -> None:
    """Enter keeps what is saved. A first blank answer is saved as blank, so the default still applies
    (and a later change to the default reaches you) and the next run doesn't ask again."""
    saved = field.saved(store)
    shown = saved or field.default
    if field.help:
        print(f"    {field.help}")
    for _ in range(ATTEMPTS):
        hint = f" [{shown}]" if shown else ""
        answer = input(f"  {field.label}{hint}: ").strip()
        if not answer:
            if not store.has_setting(field.key):
                store.save_setting(field.key, "")
            return
        try:
            field.save(store, answer)
            return
        except ValueError as error:
            print(f"    {error}")
    print(f"    Skipped {field.label}; set it later in Settings or with {field.env}")


def _ask_secret(field: Secret) -> None:
    if field.help:
        print(f"    {field.help}")
    answer = getpass.getpass(f"  {field.label} (input hidden, Enter to skip): ").strip()
    if answer:
        field.save(answer)


def ask(store: Store, source: Source, reconnect: bool) -> None:
    """Ask once per field; a blank answer is remembered so the next run does not ask again."""
    for field in source.settings:
        if not field.locked() and (reconnect or not store.has_setting(field.key)):
            _ask_setting(store, field)
    for secret in source.secrets:
        if not secret.locked() and (reconnect or not secret.is_set()):
            _ask_secret(secret)


async def _sign_in(store: Store, source: Source) -> bool:
    if input("  Open the browser to sign in? [Y/n] ").strip().lower() in ("n", "no"):
        return False
    try:
        print(f"  {await source.connect(store)}")
        return True
    except SourceError as error:
        print(f"  Sign-in failed: {error}")
        return False


READY, NOT_SET_UP, FAILED = "ready", "not set up", "failed"


async def verify(store: Store, sources: dict[str, Source], source: Source, interactive: bool, reconnect: bool) -> str:
    """READY when the login works or there is nothing to check, NOT_SET_UP when it isn't set up, else FAILED.

    A browser sign-in is offered only when the check says one is needed, or straight away with --reconnect.
    """
    can_sign_in = source.connect is not None and interactive
    if reconnect and can_sign_in:
        return READY if await _sign_in(store, source) else FAILED
    check = check_for(sources, source)
    if check is None:
        print("  Nothing to check.")
        return READY
    try:
        print(f"  {await check(store)}")
        return READY
    except SignInRequired as error:
        print(f"  {error}")
        return READY if can_sign_in and await _sign_in(store, source) else FAILED
    except NotConnectedError as error:
        print(f"  Skipped: {error}")
        return NOT_SET_UP
    except SourceError as error:
        print(f"  Not working: {error}")
        return FAILED


async def run(store: Store, names: list[str], check_only: bool = False, reconnect: bool = False) -> int:
    """Set up the named sources, or every switched-on one.

    Exit status 1 when any check failed, or when a source you named still isn't set up.
    """
    sources = registry()
    unknown = [name for name in names if name not in sources]
    if unknown:
        print(f"Unknown source: {', '.join(unknown)}. Run worktray sources to list them.")
        return 2
    on = enabled_sources(store, sources)
    selected = [sources[name] for name in names] if names else [source for source in sources.values() if source.name in on]
    if not selected:
        print("No sources are on yet. Name the ones to set up, as in worktray auth jira github, or turn them on in Settings.")
        return 1
    interactive = sys.stdin.isatty() and not check_only
    if not check_only and not sys.stdin.isatty():
        print("Not a terminal, so only checking. Save values in the Settings page or with worktray config set.")
    outcomes: dict[str, str] = {}
    for source in selected:
        print(f"\n{source.label}")
        if not is_available(source):
            print(f"  Skipped: this needs an extra package. Run {install_command(source.extras)}")
            outcomes[source.name] = NOT_SET_UP
            continue
        if source.uses and not source.check:
            print(f"  Signs in through {sources[source.uses].label}.")
        try:
            if interactive:
                ask(store, source, reconnect)
                # Setting a source up is choosing it; an explicit off stays off.
                if not switch_on_if_unset(store, source.name):
                    print("  It's switched off; turn it on in Settings or with worktray sources enable " + source.name)
            outcomes[source.name] = await verify(store, sources, source, interactive, reconnect)
        except (SourceError, httpx.HTTPError, OSError, ValueError, TimeoutError) as error:
            # One source that breaks must not stop the others from being set up.
            print(f"  Not working: {error or type(error).__name__}")
            outcomes[source.name] = FAILED
    counts = {outcome: sum(found == outcome for found in outcomes.values()) for outcome in (READY, NOT_SET_UP, FAILED)}
    print("\n" + ", ".join(f"{count} {outcome}" for outcome, count in counts.items() if count) + ".")
    unfinished = [name for name in names if outcomes.get(name) == NOT_SET_UP]
    if counts[FAILED] or unfinished:
        return 1
    print("Start the dashboard with worktray serve.")
    return 0
