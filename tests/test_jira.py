import pytest

from worktray.sources.jira import jira_item

ME = "acc-me"


def issue(status: str = "In Progress", assignee: str | None = ME, **fields: object) -> dict:
    return {
        "key": "WEB-1",
        "fields": {
            "summary": "Fix the login page",
            "created": "2026-10-01T00:00:00.000+0000",
            "updated": "2026-10-02T00:00:00.000+0000",
            "status": {"name": status, "statusCategory": {"key": "indeterminate"}},
            "project": {"key": "WEB"},
            "assignee": {"accountId": assignee, "displayName": "A"} if assignee else None,
            **fields,
        },
    }


def test_my_active_ticket_needs_me():
    assert jira_item(issue(), "https://jira.example", ME).lane == "needs_me"


@pytest.mark.parametrize("status", ["In Review", "code review", "QA", "Blocked", "Waiting"])
def test_my_ticket_in_a_handoff_status_waits(status):
    assert jira_item(issue(status), "https://jira.example", ME).lane == "waiting"


def test_ticket_i_reported_and_assigned_away_waits_and_is_mine_to_watch():
    item = jira_item(issue(assignee="acc-other"), "https://jira.example", ME, reported=True)

    assert (item.lane, item.personal) == ("waiting", True)


def test_team_ticket_has_no_lane():
    item = jira_item(issue(assignee="acc-other"), "https://jira.example", ME)

    assert (item.lane, item.personal) == ("", False)


def test_ticket_exposes_type_due_date_and_parent_title():
    fields = {"issuetype": {"name": "Bug"}, "duedate": "2026-10-30", "parent": {"key": "WEB-0", "fields": {"summary": "Login epic"}}}

    item = jira_item(issue(**fields), "https://jira.example", ME)

    assert (item.issue_type, item.due_date, item.parent_title, item.list_name) == ("Bug", "2026-10-30", "Login epic", "WEB-0")


def test_ticket_without_type_or_parent_leaves_them_empty():
    item = jira_item(issue(issuetype=None, parent=None, duedate=None), "https://jira.example", ME)

    assert (item.issue_type, item.due_date, item.parent_title) == ("", None, "")


def test_unassigned_ticket_i_reported_waits_and_is_mine_to_watch():
    item = jira_item(issue(assignee=None), "https://jira.example", ME, reported=True)

    assert (item.lane, item.personal) == ("waiting", True)
