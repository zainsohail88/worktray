"""Find the Jira tickets and pull requests a piece of text points at."""

import re

from worktray.models import Item

JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
GITHUB_PR = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
BITBUCKET_PR = re.compile(r"https://bitbucket\.org/[\w.-]+/[\w.-]+/pull-requests/\d+")
# Pull request links come first so a ticket-like repository name inside one is not read as a ticket.
REFERENCE = re.compile(f"{GITHUB_PR.pattern}|{BITBUCKET_PR.pattern}|{JIRA_KEY.pattern}")


def find_references(text: str) -> list[str]:
    """Return Jira keys and pull request URLs in order of appearance, without repeats."""
    return list(dict.fromkeys(REFERENCE.findall(text)))


def link_targets(items: list[Item]) -> dict[str, Item]:
    """Your open tickets and pull requests, by the Jira key or link an ask would name them with."""
    targets = {}
    for item in items:
        if not (item.live and item.personal and item.status == "open"):
            continue
        if item.source == "jira":
            targets[item.key.removeprefix("jira:")] = item
        elif item.source in ("github", "bitbucket"):
            targets[item.url] = item
    return targets


def linked_asks(items: list[Item], references: dict[str, list[str]]) -> dict[str, list[str]]:
    """Group asks under the open ticket or pull request of yours they name, so one piece of work is one row.

    An ask naming several of them sits under the first one it names.
    """
    targets = link_targets(items)
    grouped: dict[str, list[str]] = {}
    for key, found in references.items():
        parent = next((targets[reference].key for reference in found if reference in targets), None)
        if parent:
            grouped.setdefault(parent, []).append(key)
    return grouped
