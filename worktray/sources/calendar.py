"""Read upcoming primary-calendar events through the existing Google grant."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from worktray.auth.google_login import EVENTS_URL, google_read_error, require_google
from worktray.auth.oauth import RefreshAuth, token_manager
from worktray.models import Batch, Item
from worktray.sources.errors import SourceError


def _instant(value: dict, calendar_zone: str) -> datetime:
    instant = datetime.fromisoformat((value.get("dateTime") or value["date"]).replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=ZoneInfo(value.get("timeZone") or calendar_zone))
    return instant


async def read_calendar() -> Batch:
    """Expand recurring events shared with others, excluding ended, declined and cancelled ones.

    With maxAttendees=1 Google returns only the caller and sets attendeesOmitted when
    anyone else is invited. Events organized by someone else also count, since a hidden
    guest list (e.g. All Hands) omits nobody. Focus time, out of office and location drop out.

    https://developers.google.com/calendar/api/v3/reference/events/list
    """
    require_google()
    current = datetime.now(timezone.utc)
    until = current + timedelta(days=14)
    params = {
        "timeMin": current.isoformat(),
        "timeMax": until.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "showDeleted": "false",
        "maxResults": 250,
        "maxAttendees": 1,
        "fields": "nextPageToken,timeZone,items(id,summary,htmlLink,status,start,end,attendeesOmitted,organizer(self),attendees(self,responseStatus))",
    }
    items = {}
    seen_pages = set()
    async with httpx.AsyncClient(auth=RefreshAuth(token_manager(), "google"), timeout=30) as client:
        while True:
            response = await client.get(EVENTS_URL, params=params)
            google_read_error(response, "Calendar", "calendar.events.readonly")
            data = response.json()
            for event in data.get("items", []):
                shared = event.get("attendeesOmitted") or not event.get("organizer", {}).get("self")
                if event.get("status") == "cancelled" or not shared:
                    continue
                own_reply = next((person.get("responseStatus") for person in event.get("attendees", []) if person.get("self")), "")
                if own_reply == "declined":
                    continue
                start = _instant(event["start"], data.get("timeZone", "UTC"))
                end = _instant(event["end"], data.get("timeZone", "UTC"))
                if end <= current or start >= until:
                    continue
                key = f"calendar:primary:{event['id']}"
                items[key] = Item(
                    key=key,
                    source="calendar",
                    title=" ".join((event.get("summary") or "Calendar event").split()),
                    url=event["htmlLink"],
                    status="open",
                    live=True,
                    starts_at=start.isoformat(),
                    ends_at=end.isoformat(),
                    all_day="date" in event["start"],
                    source_status="RSVP needed" if own_reply == "needsAction" else "Tentative" if own_reply == "tentative" else "",
                    lane="needs_me" if own_reply == "needsAction" else "",
                    reason="Primary calendar",
                )
            page = data.get("nextPageToken")
            if not page:
                break
            if page in seen_pages:
                raise SourceError("Calendar pagination did not advance")
            seen_pages.add(page)
            params["pageToken"] = page
    return Batch(items=sorted(items.values(), key=lambda item: item.starts_at), detail="Your meetings for the next two weeks. Declined, cancelled and solo events are left out.")
