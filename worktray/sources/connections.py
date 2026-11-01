"""Read-only transport boundaries shared by every source."""

import asyncio
import json
import re
import shutil
from typing import Any

import httpx

from worktray.sources.errors import NotConnectedError, SourceError


async def cli_json(command: list[str], payload: str | None = None) -> Any:
    """Invoke a fixed read command, suppressing upstream error content."""
    if shutil.which(command[0]) is None:
        raise NotConnectedError(f"Not set up yet. Install the {command[0]} command line tool first.")
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if payload else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(payload.encode() if payload else None), timeout=45)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        codes = re.findall(rb"\b(?:401|403|404|429|5[0-9]{2})\b", stderr)
        status = f" (HTTP {codes[0].decode()})" if codes else ""
        raise SourceError(f"{command[0]} could not read from the server{status}. Check that it is signed in and you are online.")
    result = json.loads(stdout)
    if isinstance(result, dict) and result.get("errors"):
        raise SourceError(f"{command[0]} returned an incomplete result. Try again.")
    return result


async def cli_logged_in(command: str) -> bool:
    """Whether a CLI such as gh or bkt has a working login, without printing anything."""
    if shutil.which(command) is None:
        raise SourceError(f"Install the {command} CLI first")
    process = await asyncio.create_subprocess_exec(command, "auth", "status", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    return await process.wait() == 0


async def get_json(client: httpx.AsyncClient, url: str, **kwargs: Any) -> dict:
    """Keep HTTP status failures distinct from valid empty results."""
    for attempt in range(3):
        response = await client.get(url, **kwargs)
        if response.status_code != 429 or attempt == 2:
            break
        retry_after = response.headers.get("Retry-After", "5")
        delay = float(retry_after) if retry_after.isdigit() else 5
        if delay > 60:
            raise SourceError("The service is rate limiting worktray. It will try again on the next sync.")
        await asyncio.sleep(delay)
    if response.status_code >= 400:
        raise SourceError(f"The server answered with HTTP {response.status_code}. Check your sign-in and that you have access.")
    return response.json()
