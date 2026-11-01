"""Conservative local extraction: proposals require a human decision."""

import hashlib
import re

from worktray.models import Item
from worktray.references import find_references
from worktray.sources.sessions import short_title


ASK = re.compile(r"\b(can|could|would|please|need|review|check|help|investigate|follow up|take a look|let me know|any update)\b", re.I)
PROMISE = re.compile(r"\b(i(?:['’]ll| will| can)|let me|i(?:['’]m| am) (?:going to|working on))\b", re.I)
ACTION = re.compile(r"(?:suggested\s+)?(?:action items?|next steps?|follow[- ]?ups?|to[- ]?do)\s*:?", re.I)
SECTION_END = re.compile(
    r"(?:summary|details|discussion|notes|transcript|meeting transcript|attachments|recording)\s*:?|(?:you should review gemini|please review gemini|\d{1,2}:\d{2}(?::\d{2})?).*", re.I
)


TICKET_WORK = re.compile(r"\b(?:groom\w*|refine\w*|(?:create|raise|open|file|log|write|draft|add)\b[^.;]*?\b(?:tickets?|jiras?|stor(?:y|ies)|epics?|bugs?|issues?))\b", re.I)
NEXT_STEP = "Your action item from a meeting"
TICKET_STEP = "Create or groom a ticket"


DATED_SUFFIX = re.compile(r"\s+-\s+\d{4}[/-]\d{2}[/-]\d{2}.*$")
GEMINI_SUFFIX = re.compile(r"\s+-\s+Notes by Gemini$", re.I)


def meeting_name(document_name: str) -> str:
    """Recover the calendar title from "Title - 2026/10/14 10:00 GMT - Notes by Gemini"."""
    return GEMINI_SUFFIX.sub("", DATED_SUFFIX.sub("", document_name)).strip()


def meeting_items(document_id: str, text: str, aliases: list[str], created: str, meeting: str = "") -> list[Item]:
    """Use content fingerprints so inserting document lines keeps old keys.

    Gemini can write the same next steps twice in one document, so a repeated line is one item.
    """
    items = []
    in_actions = False
    seen: set[str] = set()
    alias_pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(alias.lstrip("@")) for alias in aliases) + r")(?!\w)", re.I)
    for line in text.splitlines():
        stripped = line.strip()
        heading = stripped.strip("#* \t")
        if ACTION.fullmatch(heading):
            in_actions = True
            continue
        if stripped.startswith("#") or SECTION_END.fullmatch(heading):
            in_actions = False
        if not in_actions or not alias_pattern.search(stripped):
            continue
        # Gemini prefixes each item with "[Assignee]", which short_title would reject as markup.
        title = re.sub(r"^(?:[-*•]\s*)?(?:(?:\[[ xX]?\]|[☐☑✓])\s*)?(?:\[[^\]]*\]\s*)?", "", stripped)
        normalized = re.sub(r"\s+", " ", stripped.strip(" *-[]\t")).casefold()
        fingerprint = hashlib.sha256(normalized.encode()).hexdigest()[:20]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        items.append(
            Item(
                # The ":1" suffix keeps keys, and the decisions on them, from when repeats were counted.
                key=f"gemini:{document_id}:{fingerprint}:1",
                source="gemini",
                title=short_title(title),
                url=f"https://docs.google.com/document/d/{document_id}/edit",
                opened_at=created,
                reason=TICKET_STEP if TICKET_WORK.search(title) else NEXT_STEP,
                list_name="Follow-ups",
                project=meeting,
                references=find_references(stripped),
            )
        )
    return items
