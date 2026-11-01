import pytest

from worktray.sources.extract import meeting_items


@pytest.mark.parametrize(
    "line",
    [
        "[Alex Example] Onboarding Guide: Draft the onboarding guide for new starters and share it with the team.",
        "* [ ] [Alex Example] Onboarding Guide: Draft the onboarding guide for new starters and share it with the team.",
        "☐ [Alex Example] Onboarding Guide: Draft the onboarding guide for new starters and share it with the team.",
    ],
)
def test_meeting_item_title_drops_assignee(line):
    text = f"Suggested next steps\n{line}\n"

    [item] = meeting_items("doc1", text, ["Alex Example"], "2026-10-14T00:00:00Z")

    assert item.title == "Onboarding Guide: Draft the onboarding guide for new starters and share it with the team."


def test_meeting_item_keeps_the_ticket_it_names():
    text = "Suggested next steps\n[Alex Example] Close out ABC-123 once QA passes.\n"

    [item] = meeting_items("doc1", text, ["Alex Example"], "2026-10-14T00:00:00Z")

    assert item.references == ["ABC-123"]


@pytest.mark.parametrize(
    "line",
    [
        "[Alex Example] Create a ticket for the CI build fix.",
        "[Alex Example] Raise Jira stories for the drift detection work.",
        "[Alex Example] Groom the maintenance backlog before planning.",
        "[Alex Example] Refine ABC-123 with acceptance criteria.",
    ],
)
def test_ticket_work_is_called_out(line):
    [item] = meeting_items("doc1", f"Suggested next steps\n{line}\n", ["Alex Example"], "2026-10-14T00:00:00Z")

    assert item.reason == "Create or groom a ticket"


def test_other_next_steps_keep_the_plain_reason():
    [item] = meeting_items("doc1", "Suggested next steps\n[Alex Example] Share the rollout plan with the team.\n", ["Alex Example"], "2026-10-14T00:00:00Z")

    assert item.reason == "Your action item from a meeting"
