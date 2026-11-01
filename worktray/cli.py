"""The worktray command: serve the dashboard, set up sources, run the MCP server, manage the service."""

import argparse
import asyncio
import getpass
import os
import sys

from worktray import APP_NAME, __version__
from worktray.paths import HOME_ENV, database, home


def _store():
    from worktray.store import Store

    return Store(database())


def serve(port: int | None, open_browser: bool) -> None:
    import uvicorn

    from worktray.service import port as default_port
    from worktray.web.app import create_app

    os.umask(0o077)
    chosen = port or default_port()
    url = f"http://localhost:{chosen}/"
    print(f"{APP_NAME} {__version__} on {url} (data in {home()})", flush=True)
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=chosen, access_log=False)


def auth(names: list[str], check_only: bool, reconnect: bool) -> int:
    from worktray.auth.interactive import run

    os.umask(0o077)
    try:
        return asyncio.run(run(_store(), names, check_only, reconnect))
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled. Values already saved are kept.")
        return 1


def mcp() -> None:
    from worktray.mcp_server import main

    main()


def sources(action: str, name: str | None) -> int:
    from worktray.config import set_source_enabled, source_enabled
    from worktray.sources.registry import is_available, registry

    store = _store()
    known = registry()
    if action == "list":
        for source in known.values():
            state = "on " if source_enabled(store, source.name) else "off"
            missing = "" if is_available(source) else f"  (needs worktray[{','.join(source.extras)}])"
            print(f"{state}  {source.name:<16} {source.label}{missing}")
        return 0
    if name not in known:
        print(f"Unknown source {name!r}. Run worktray sources to list them.", file=sys.stderr)
        return 2
    try:
        set_source_enabled(store, name, action == "enable")
    except PermissionError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"{known[name].label} is {'on' if action == 'enable' else 'off'}.")
    return 0


def config(action: str, key: str | None, value: str | None) -> int:
    from worktray.config import Secret, switch_on_if_unset
    from worktray.sources.errors import SourceError
    from worktray.sources.registry import field_index, registry

    store = _store()
    fields = field_index(registry())
    if action == "list":
        print(f"# {HOME_ENV}={home()}")
        for name, (source, field) in fields.items():
            if isinstance(field, Secret):
                try:
                    shown = "set" if field.is_set() else "not set"
                except SourceError:
                    shown = "keyring unavailable"
            else:
                try:
                    shown = field.read(store) or "(blank)"
                except SourceError as error:
                    shown = str(error)
            origin = " (from environment)" if field.locked() else ""
            print(f"{source.name:<14} {name:<22} {field.env:<34} {shown}{origin}")
        return 0
    if key not in fields:
        print(f"Unknown setting {key!r}. Run worktray config to list them.", file=sys.stderr)
        return 2
    source, field = fields[key]
    if action == "set" and value is None and not isinstance(field, Secret):
        print(f"Give a value: worktray config set {key} VALUE. To clear it, use worktray config unset {key}.", file=sys.stderr)
        return 2
    if field.locked():
        print(f"{field.env} is exported in this shell, so a saved value would be ignored.", file=sys.stderr)
        return 1
    try:
        if action == "unset":
            field.clear() if isinstance(field, Secret) else store.save_setting(field.key, "")
        elif isinstance(field, Secret):
            field.save(value if value is not None else getpass.getpass(f"{field.label} (input hidden): "))
        else:
            field.save(store, value)
        if action == "set":
            switch_on_if_unset(store, source.name)
    except (ValueError, SourceError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"{'Cleared' if action == 'unset' else 'Saved'} {key}.")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog=APP_NAME, description="Your work from Jira, GitHub, Bitbucket, Google Calendar, meeting notes, Slack and coding agents, in one local queue.")
    root.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    commands = root.add_subparsers(dest="command", metavar="command")

    serve_command = commands.add_parser("serve", help="start the dashboard (the default)")
    serve_command.add_argument("--port", type=int, help="port to listen on (default WORKTRAY_PORT or 8765)")
    serve_command.add_argument("--open", action="store_true", help="open the dashboard in the browser")

    auth_command = commands.add_parser("auth", help="set up sources in the terminal")
    auth_command.add_argument("source", nargs="*", help="sources to set up; every switched-on source when omitted")
    auth_command.add_argument("--check", action="store_true", help="only check existing connections")
    auth_command.add_argument("--reconnect", action="store_true", help="ask again and sign in again")

    commands.add_parser("mcp", help="serve MCP tools over stdio for coding agents (needs worktray[mcp])")

    sources_command = commands.add_parser("sources", help="list sources, or turn one on or off")
    sources_command.add_argument("action", nargs="?", choices=["list", "enable", "disable"], default="list")
    sources_command.add_argument("name", nargs="?")

    config_command = commands.add_parser("config", help="list settings, or set and clear one")
    config_command.add_argument("action", nargs="?", choices=["list", "set", "unset"], default="list")
    config_command.add_argument("key", nargs="?")
    config_command.add_argument("value", nargs="?", help="omit for a secret to type it hidden")

    service_command = commands.add_parser("service", help="run in the background at login (macOS launchd, Linux systemd)")
    service_command.add_argument("action", choices=["install", "uninstall", "restart", "status", "logs", "print"])
    return root


def main(argv: list[str] | None = None) -> None:
    root = parser()
    args = root.parse_args(argv)
    command = args.command or "serve"
    if command in ("sources", "config") and args.action != "list" and not (args.name if command == "sources" else args.key):
        root.error(f"{command} {args.action} needs a name")
    if command == "serve":
        serve(getattr(args, "port", None), getattr(args, "open", False))
    elif command == "auth":
        raise SystemExit(auth(args.source, args.check, args.reconnect))
    elif command == "mcp":
        mcp()
    elif command == "sources":
        raise SystemExit(sources(args.action, args.name))
    elif command == "config":
        raise SystemExit(config(args.action, args.key, args.value))
    elif command == "service":
        from worktray.service import main as service

        service(args.action)
