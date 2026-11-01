"""Track the Jira tickets and pull requests that asks name, and offer the asks as done once those finish."""

import asyncio

import httpx
from pydantic import BaseModel

from worktray.config import enabled_sources
from worktray.models import Batch
from worktray.references import BITBUCKET_PR, GITHUB_PR
from worktray.sources.atlassian import atlassian_config, jira_ready
from worktray.sources.bitbucket import BITBUCKET_CONTEXT, BITBUCKET_WORKSPACE, bkt_api
from worktray.sources.connections import cli_json, get_json
from worktray.sources.errors import SourceError
from worktray.sources.github import GITHUB_ORGS
from worktray.store import Store

BITBUCKET_FINISHED = {"MERGED": "merged", "DECLINED": "declined", "SUPERSEDED": "superseded"}
CONCURRENCY = 5


class LinkState(BaseModel):
    """Where one linked ticket or pull request stands; finished ones let the asks that wait on them close."""

    text: str
    finished: bool


def _not_found(error: SourceError) -> bool:
    return "HTTP 404" in str(error)


def _pull_summary(summary: dict) -> str:
    pulls = summary.get("summary", {}).get("pullrequest", {}).get("overall", {})
    count = pulls.get("count", 0)
    if not count:
        return ""
    return f"{count} PR{'s' if count > 1 else ''} {'open' if pulls.get('open') else pulls.get('state', '').lower()}".strip()


async def _ticket_state(client: httpx.AsyncClient, key: str) -> LinkState | None:
    response = await client.get(f"/rest/api/3/issue/{key}", params={"fields": "status"})
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise SourceError(f"Jira answered with HTTP {response.status_code}. Check your sign-in and access to the ticket.")
    issue = response.json()
    status = issue["fields"]["status"]
    if status["statusCategory"]["key"] == "done":
        return LinkState(text=f"{key} is {status['name']}", finished=True)
    # Development info is what Jira shows in its Development panel, so it covers PRs whose titles omit the key.
    pulls = _pull_summary(await get_json(client, "/rest/dev-status/latest/issue/summary", params={"issueId": issue["id"]}))
    return LinkState(text=f"{key} {status['name']}" + (f" · {pulls}" if pulls else ""), finished=False)


async def _github_state(reference: str, organisations: list[str] = ()) -> LinkState | None:
    """Look a pull request up through gh; with organisations configured, links elsewhere are left alone."""
    repo, number = reference.removeprefix("https://github.com/").split("/pull/")
    if organisations and repo.split("/")[0] not in organisations:
        return None
    try:
        pull = await cli_json(["gh", "api", f"repos/{repo}/pulls/{number}"])
    except SourceError as error:
        if _not_found(error):
            return None
        raise
    if pull.get("merged"):
        return LinkState(text=f"{repo}#{number} merged", finished=True)
    if pull.get("state") == "closed":
        return LinkState(text=f"{repo}#{number} closed", finished=True)
    return LinkState(text=f"{repo}#{number} {'draft' if pull.get('draft') else 'open'}", finished=False)


async def _bitbucket_state(reference: str, workspace: str, context: str = "") -> LinkState | None:
    """Look a pull request up through bkt; only links in the configured workspace are checked."""
    repo, number = reference.removeprefix("https://bitbucket.org/").split("/pull-requests/")
    if not workspace or repo.split("/")[0] != workspace:
        return None
    try:
        pull = await cli_json(bkt_api(f"/repositories/{repo}/pullrequests/{number}", context))
    except SourceError as error:
        if _not_found(error):
            return None
        raise
    outcome = BITBUCKET_FINISHED.get(pull.get("state", ""))
    return LinkState(text=f"{repo}#{number} {outcome or 'open'}", finished=bool(outcome))


async def read_upstream(store: Store) -> Batch:
    """Show where each linked ticket and pull request stands, and offer open items as done once all of them finished."""
    named = store.references()
    references = sorted({reference for found in named.values() for reference in found})
    if not references:
        return Batch(detail="None of your asks mention a ticket or pull request yet")
    limit = asyncio.Semaphore(CONCURRENCY)
    # A source the user switched off is never contacted, even to look up a link that names it.
    on = enabled_sources(store, ("jira", "github", "bitbucket"))
    organisations = GITHUB_ORGS.items(store)
    workspace = BITBUCKET_WORKSPACE.read(store)
    context = BITBUCKET_CONTEXT.read(store)
    github = [reference for reference in references if GITHUB_PR.fullmatch(reference)]
    bitbucket = [reference for reference in references if BITBUCKET_PR.fullmatch(reference)]
    tickets = [reference for reference in references if reference not in github and reference not in bitbucket]
    pulls = [*(github if "github" in on else []), *(bitbucket if "bitbucket" in on else [])]

    failures: dict[str, list[str]] = {}

    async def pull_state(reference: str) -> tuple[str, LinkState | None]:
        # One link that can't be read, or gh or bkt missing or signed out, leaves the others to be checked.
        tool = "GitHub" if GITHUB_PR.fullmatch(reference) else "Bitbucket"
        try:
            async with limit:
                if tool == "GitHub":
                    return reference, await _github_state(reference, organisations)
                return reference, await _bitbucket_state(reference, workspace, context)
        except SourceError as error:
            failures.setdefault(tool, []).append(str(error))
            return reference, None

    results = list(await asyncio.gather(*map(pull_state, pulls)))
    # Text often holds ticket-shaped words such as UTF-8, so a missing Jira login, or a machine
    # without a keyring to hold its token, must not stop the pull request checks.
    try:
        config = await asyncio.to_thread(atlassian_config, store) if tickets and "jira" in on else {}
    except SourceError:
        config = {}
    ready = jira_ready(config)
    if tickets and ready:
        async with httpx.AsyncClient(base_url=config["JIRA_URL"], auth=(config["JIRA_USERNAME"], config["JIRA_API_TOKEN"]), timeout=30) as client:

            async def ticket_state(key: str) -> tuple[str, LinkState | None]:
                try:
                    async with limit:
                        return key, await _ticket_state(client, key)
                except (SourceError, httpx.HTTPError) as error:
                    failures.setdefault("Jira", []).append(str(error) or type(error).__name__)
                    return key, None

            results += await asyncio.gather(*map(ticket_state, tickets))
    states = {reference: state for reference, state in results if state}
    suggested = 0
    for key, found in named.items():
        store.link_status(key, "; ".join(states[reference].text for reference in found if reference in states))
        if all(reference in states and states[reference].finished for reference in found):
            store.suggest_close(key, states[found[0]].text if len(found) == 1 else f"All {len(found)} linked tickets and PRs are done")
            suggested += 1
    finished = sum(state.finished for state in states.values())
    skipped = f". Skipped {_count(len(tickets), 'ticket')} because Jira is not set up" if tickets and not ready else ""
    skipped += "".join(f". Skipped {_count(len(found), f'{name} link')} because {name} is off" for name, found in (("GitHub", github), ("Bitbucket", bitbucket)) if found and name.lower() not in on)
    skipped += "".join(f". Could not check {_count(len(errors), f'{name} link')}: {errors[0]}" for name, errors in failures.items())
    return Batch(detail=f"Checked {len(references)} linked tickets and pull requests: {finished} done, {_count(suggested, 'ask')} ready to close{skipped}")


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"
