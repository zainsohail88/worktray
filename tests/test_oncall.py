from datetime import datetime, timezone

from worktray.sources.oncall import attention, current_shift, epic_query, oncall_item

ME = "acc-me"
AT = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)


def issue(
    status: str = "To Do",
    category: str = "new",
    assignee: str | None = None,
    priority: str = "Medium",
    created: str = "2026-09-01T00:00:00.000+0000",
    changed: str = "2026-10-28T00:00:00.000+0000",
    due: str | None = None,
) -> dict:
    return {
        "key": "OPS-1",
        "fields": {
            "summary": "Fix the build",
            "created": created,
            "updated": changed,
            "statuscategorychangedate": changed,
            "status": {"name": status, "statusCategory": {"key": category}},
            "project": {"key": "OPS"},
            "priority": {"name": priority},
            "duedate": due,
            "assignee": {"accountId": assignee, "displayName": "A"} if assignee else None,
        },
    }


def period(start: str, end: str, responder: str = ME) -> dict:
    return {"startDate": start, "endDate": end, "responder": {"id": responder, "type": "user"}}


def timeline(*periods: dict) -> dict:
    return {"finalTimeline": {"rotations": [{"periods": list(periods)}]}}


def test_quiet_backlog_ticket_needs_no_attention():
    assert attention(issue(assignee="acc-other"), ME, AT) == []


def test_my_ticket_in_flight_is_flagged():
    assert attention(issue("In Testing", "indeterminate", assignee=ME), ME, AT) == ["Yours in flight"]


def test_ticket_in_flight_without_a_status_change_for_days_is_stuck():
    stuck = issue("In Review", "indeterminate", assignee="acc-other", changed="2026-10-20T09:00:00.000+0000")

    assert attention(stuck, ME, AT) == ["In Review 9 days"]


def test_past_due_date_is_overdue():
    assert attention(issue(assignee="acc-other", due="2026-10-28"), ME, AT) == ["Overdue"]


def test_urgent_ticket_nobody_owns_is_flagged_with_its_priority():
    assert attention(issue(priority="High"), ME, AT) == ["High, unassigned"]


def test_new_ticket_nobody_owns_is_flagged():
    assert attention(issue(created="2026-10-27T00:00:00.000+0000"), ME, AT) == ["New, unassigned"]


def test_on_call_row_stays_out_of_personal_work():
    item = oncall_item(issue("In Progress", "indeterminate", assignee=ME), "https://jira.example", ME, AT)

    assert (item.key, item.source, item.personal, item.lane) == ("oncall:OPS-1", "oncall", False, "needs_me")


def test_epic_query_names_the_project_and_the_configured_word():
    assert epic_query("OPS", "Maintenance") == 'project = "OPS" AND issuetype = Epic AND summary ~ "Maintenance" AND statusCategory != Done ORDER BY created DESC'


def test_epic_query_drops_quotes_from_the_configured_word():
    assert 'summary ~ "KTLO"' in epic_query("OPS", 'K"TLO')


def test_shift_split_at_the_present_is_one_current_shift():
    split = timeline(period("2026-10-26T02:00:00Z", "2026-10-29T08:00:00Z"), period("2026-10-29T08:00:00Z", "2026-11-02T02:00:00Z"))

    shift = current_shift(split, "Platform", ME, AT)

    assert (shift.starts_at, shift.ends_at, shift.current) == ("2026-10-26T02:00:00+00:00", "2026-11-02T02:00:00+00:00", True)


def test_next_shift_is_reported_when_someone_else_is_on_call():
    later = timeline(period("2026-10-26T02:00:00Z", "2026-11-02T02:00:00Z", "acc-other"), period("2026-11-09T02:00:00Z", "2026-11-16T02:00:00Z"))

    assert current_shift(later, "Platform", ME, AT).current is False


def test_no_shift_when_never_on_call():
    assert current_shift(timeline(period("2026-10-26T02:00:00Z", "2026-11-02T02:00:00Z", "acc-other")), "Platform", ME, AT) is None
