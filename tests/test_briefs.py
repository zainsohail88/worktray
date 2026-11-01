from datetime import date, datetime, timedelta, timezone

from worktray.briefs import meeting_brief, previous_workday, standup_note
from worktray.models import Item
from worktray.sources.extract import meeting_items, meeting_name
from worktray.store import Store

MONDAY = date(2026, 10, 19)
NOON = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def closed(key: str, title: str, when: datetime, status: str = "done") -> Item:
    return Item(key=key, title=title, source="manual", status=status, closed_at=when.isoformat())


def meeting(title: str, starts: datetime, key: str = "calendar:primary:1") -> Item:
    return Item(key=key, title=title, source="calendar", status="open", live=True, starts_at=starts.isoformat(), ends_at=(starts + timedelta(minutes=30)).isoformat())


def test_monday_reports_from_friday():
    assert previous_workday(MONDAY) == date(2026, 10, 16)


def test_midweek_reports_from_yesterday():
    assert previous_workday(date(2026, 10, 21)) == date(2026, 10, 20)


def test_standup_lists_weekend_closures_on_monday():
    saturday = closed("manual:a", "Wrote the RFC", datetime(2026, 10, 17, 12, tzinfo=timezone.utc))

    note = standup_note([saturday], today=MONDAY, at=NOON)

    assert [item.key for item in note.closed] == ["manual:a"]


def test_standup_skips_dismissed_and_today_closures():
    items = [closed("manual:a", "Dropped", datetime(2026, 10, 16, 12, tzinfo=timezone.utc), "dismissed"), closed("manual:b", "Done this morning", datetime(2026, 10, 19, 1, tzinfo=timezone.utc))]

    assert standup_note(items, today=MONDAY, at=NOON).closed == []


def test_standup_text_says_when_nothing_closed_or_pinned():
    assert standup_note([], today=MONDAY, at=NOON).text == "*Friday*\n• Nothing closed\n*Today*\n• Nothing pinned"


def test_standup_text_links_pinned_work_and_escapes_markup():
    pinned = Item(key="manual:p", title="Fix <retry> & backoff", source="manual", status="open", up_next=True, url="https://x.example/1")

    text = standup_note([pinned], today=MONDAY, at=NOON).text

    assert "• <https://x.example/1|Fix &lt;retry&gt; &amp; backoff>" in text


def test_standup_names_the_next_meeting_not_an_ended_one():
    ended = meeting("Old", NOON - timedelta(hours=3), "calendar:primary:0")
    upcoming = meeting("Design review", NOON + timedelta(hours=2))

    assert standup_note([ended, upcoming], today=MONDAY, at=NOON).next_meeting.title == "Design review"


def test_brief_matches_tickets_by_key_and_project():
    named = Item(key="jira:WEB-7", title="Retry", source="jira", status="open", project="WEB")
    sibling = Item(key="jira:WEB-9", title="Reset", source="jira", status="open", project="WEB")
    other = Item(key="jira:OPS-1", title="Disk", source="jira", status="open", project="OPS")

    brief = meeting_brief(meeting("WEB-7 planning", NOON), [named, sibling, other])

    assert [item.key for item in brief.tickets] == ["jira:WEB-7"]


def test_brief_matches_every_project_ticket_when_the_title_names_the_project():
    items = [Item(key=f"jira:WEB-{n}", title="T", source="jira", status="open", project="WEB") for n in (1, 2)]

    assert len(meeting_brief(meeting("WEB sync", NOON), items).tickets) == 2


def test_brief_matches_pull_requests_by_the_ticket_key_in_their_title():
    pr = Item(key="https://github.com/o/r/pull/1", title="WEB-7: fix the login page", source="github", status="open", live=True)
    unrelated = Item(key="https://github.com/o/r/pull/2", title="Bump deps", source="github", status="open", live=True)

    brief = meeting_brief(meeting("WEB-7 planning", NOON), [pr, unrelated])

    assert [item.key for item in brief.pull_requests] == [pr.key]


def test_brief_matches_meeting_notes_by_meeting_name():
    notes = Item(key="gemini:d:f:1", title="Share costs", source="gemini", project="Team standup")
    elsewhere = Item(key="gemini:e:f:1", title="Other", source="gemini", project="Board review")

    brief = meeting_brief(meeting("Team standup", NOON), [notes, elsewhere])

    assert [item.key for item in brief.action_items] == [notes.key]


def test_brief_ignores_closed_work():
    done = Item(key="jira:WEB-7", title="Retry", source="jira", status="done", project="WEB")

    assert meeting_brief(meeting("WEB-7 planning", NOON), [done]).tickets == []


def test_meeting_name_drops_the_date_and_gemini_suffix():
    assert meeting_name("Team standup - 2026/10/14 10:00 GMT - Notes by Gemini") == "Team standup"


def test_meeting_name_keeps_a_title_without_a_date():
    assert meeting_name("Team standup - Notes by Gemini") == "Team standup"


def test_meeting_items_carry_the_meeting_name():
    text = "Suggested next steps\n[Alex Example] Share the rollout plan with the team.\n"

    [item] = meeting_items("doc1", text, ["Alex Example"], "2026-10-14T00:00:00Z", "Team standup")

    assert item.project == "Team standup"


def test_reconcile_gives_decided_meeting_items_their_meeting_name(tmp_path):
    store = Store(tmp_path / "t.sqlite3")
    text = "Suggested next steps\n[Alex Example] Share the rollout plan with the team.\n"
    [old] = meeting_items("doc1", text, ["Alex Example"], "2026-10-14T00:00:00Z")
    accepted = old.model_copy(update={"status": "open", "note": "mine"})
    store.ingest([accepted])
    [fresh] = meeting_items("doc1", text, ["Alex Example"], "2026-10-14T00:00:00Z", "Team standup")

    store.reconcile_meeting_proposals({"doc1"}, [fresh])

    assert store.items()[0].project == "Team standup"
