"""Run the dashboard in the background at login: a launchd agent on macOS, a systemd user unit on Linux.

The service starts `python -m worktray serve` with the interpreter that installed it, so it keeps
working after `uv tool upgrade`. Only the port, the data directory and PATH are written into the
service file; tokens stay in the keyring, so save settings in the app rather than exporting them.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from worktray import APP_NAME
from worktray.paths import HOME_ENV, config_home, home, log_file

LABEL = f"io.github.{APP_NAME}.server"
PORT_ENV = "WORKTRAY_PORT"
DEFAULT_PORT = 8765
# launchd and systemd do not read shell profiles, so the CLIs sources call must be on PATH explicitly.
TOOLS = ("gh", "bkt", "codex", "uv")
READY_SECONDS = 30


@dataclass(frozen=True)
class ServiceFile:
    path: Path
    content: str


def port() -> int:
    return int(os.environ.get(PORT_ENV) or DEFAULT_PORT)


def agent_path() -> str:
    directories = [str(Path(found).parent) for tool in TOOLS if (found := shutil.which(tool))]
    directories += [str(Path(sys.executable).parent), "/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local/bin")]
    # The PATH of the shell that installs the service finds whatever else the user put there.
    directories += [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry and Path(entry).is_absolute()]
    directories += ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return ":".join(dict.fromkeys(directories))


def environment() -> dict[str, str]:
    return {"PATH": agent_path(), PORT_ENV: str(port()), HOME_ENV: str(home())}


def command() -> list[str]:
    return [sys.executable, "-m", APP_NAME, "serve"]


def render(platform: str = sys.platform) -> ServiceFile:
    if platform == "darwin":
        content = plistlib.dumps(
            {
                "Label": LABEL,
                "ProgramArguments": command(),
                "EnvironmentVariables": environment(),
                "RunAtLoad": True,
                "KeepAlive": True,
                "ThrottleInterval": 10,
                "ProcessType": "Background",
                "StandardOutPath": str(log_file()),
                "StandardErrorPath": str(log_file()),
            }
        ).decode()
        return ServiceFile(Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist", content)
    if platform.startswith("linux"):
        variables = "\n".join(f'Environment="{name}={value}"' for name, value in environment().items())
        content = f"[Unit]\nDescription={APP_NAME} dashboard\n\n[Service]\nExecStart={shlex.join(command())}\n{variables}\nRestart=on-failure\nRestartSec=10\n\n[Install]\nWantedBy=default.target\n"
        return ServiceFile(config_home() / "systemd/user" / f"{APP_NAME}.service", content)
    raise SystemExit("The background service works on macOS and Linux only.")


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a service manager command; a failure stops with that command's own message."""
    try:
        return subprocess.run(args, check=check, text=True, capture_output=True)
    except FileNotFoundError:
        raise SystemExit(f"{args[0]} was not found. The background service needs it.") from None
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip() or f"exit status {error.returncode}"
        raise SystemExit(f"{shlex.join(args)} failed: {detail}") from None


def _answering() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port()}/api/state", timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def port_free() -> bool:
    """Whether nothing listens on the port, so the service can take it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port()))
        except OSError:
            return False
    return True


def _stop_existing() -> None:
    """Stop an earlier install of this service, so a reinstall can take its own port back."""
    if sys.platform == "darwin":
        _run("launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}", check=False)
    else:
        _run("systemctl", "--user", "stop", f"{APP_NAME}.service", check=False)


def _wait_until_answering() -> bool:
    deadline = time.monotonic() + READY_SECONDS
    while time.monotonic() < deadline:
        if _answering():
            return True
        time.sleep(1)
    return False


def install() -> None:
    service = render()
    _stop_existing()
    if not port_free():
        raise SystemExit(f"Port {port()} is in use, probably by worktray serve in a terminal. Stop it or set another port with {PORT_ENV}, then install again.")
    service.path.parent.mkdir(parents=True, exist_ok=True)
    home().mkdir(parents=True, exist_ok=True, mode=0o700)
    service.path.write_text(service.content)
    if sys.platform == "darwin":
        domain = f"gui/{os.getuid()}"
        _run("plutil", "-lint", str(service.path))
        _run("launchctl", "bootstrap", domain, str(service.path))
        _run("launchctl", "kickstart", "-k", f"{domain}/{LABEL}")
    else:
        _run("systemctl", "--user", "daemon-reload")
        _run("systemctl", "--user", "enable", "--now", f"{APP_NAME}.service")
    if not _wait_until_answering():
        raise SystemExit(f"Installed, but nothing answered on port {port()} within {READY_SECONDS} seconds. See worktray service logs.")
    print(f"Installed. {APP_NAME} starts at login and restarts if it crashes: http://localhost:{port()}/")


def uninstall() -> None:
    service = render()
    if sys.platform == "darwin":
        _run("launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}", check=False)
    else:
        _run("systemctl", "--user", "disable", "--now", f"{APP_NAME}.service", check=False)
    service.path.unlink(missing_ok=True)
    if sys.platform != "darwin":
        _run("systemctl", "--user", "daemon-reload", check=False)
    print("Removed the background service.")


def restart() -> None:
    if sys.platform == "darwin":
        _run("launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LABEL}")
    else:
        _run("systemctl", "--user", "restart", f"{APP_NAME}.service")
    if not _wait_until_answering():
        raise SystemExit(f"Restarted, but nothing answered on port {port()} within {READY_SECONDS} seconds. See worktray service logs.")
    print(f"Restarted: http://localhost:{port()}/")


def _manager_state() -> str:
    """What launchd or systemd says about the service."""
    if sys.platform == "darwin":
        found = _run("launchctl", "print", f"gui/{os.getuid()}/{LABEL}", check=False)
        if found.returncode:
            return "not loaded"
        state = next((line.split("=", 1)[1].strip() for line in found.stdout.splitlines() if line.strip().startswith("state =")), "")
        return state or "loaded"
    return _run("systemctl", "--user", "is-active", f"{APP_NAME}.service", check=False).stdout.strip() or "unknown"


def status() -> None:
    service = render()
    installed = service.path.exists()
    print(f"Service file: {service.path} ({'present' if installed else 'not installed'})")
    if installed:
        print(f"Service: {_manager_state()}")
    answering = _answering()
    # Something can answer on the port without being the service, such as worktray serve in a terminal.
    print(f"Answering on http://localhost:{port()}/" if answering else f"Not answering on port {port()}")


def logs() -> None:
    if sys.platform == "darwin":
        os.execvp("tail", ["tail", "-n", "80", "-f", str(log_file())])  # noqa: S606 - hands the terminal to tail
    os.execvp("journalctl", ["journalctl", "--user", "-u", f"{APP_NAME}.service", "-n", "80", "-f"])  # noqa: S606 - hands the terminal to journalctl


def main(action: str) -> None:
    if action == "print":
        service = render()
        print(f"# {service.path}\n{service.content}")
        return
    {"install": install, "uninstall": uninstall, "restart": restart, "status": status, "logs": logs}[action]()
