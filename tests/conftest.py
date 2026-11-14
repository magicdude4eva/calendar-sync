"""Shared fixtures: an in-memory CalDAV calendar and a fake ICS feed server."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar
import pytest

import utils

TZ = ZoneInfo("Europe/Vienna")


def ics_dt(dt):
    """Format an aware datetime as an iCalendar UTC timestamp."""
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def vevent(summary, start, end=None, uid=None, all_day=False, extra=""):
    """Build a VEVENT block. `start`/`end` are datetimes (or dates if all_day)."""
    if all_day:
        dtstart = f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}"
        dtend = f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}" if end else ""
    else:
        dtstart = f"DTSTART:{ics_dt(start)}"
        dtend = f"DTEND:{ics_dt(end)}" if end else ""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid or summary + '@feed'}",
        dtstart,
        dtend,
        f"SUMMARY:{summary}",
        extra.strip(),
        "END:VEVENT",
    ]
    return "\n".join(line for line in lines if line)


def make_ics(*events):
    return "\n".join(
        ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//test//EN", *events, "END:VCALENDAR"]
    )


def soon(days=7, hour=10):
    """An aware datetime `days` from now, at a fixed hour."""
    return (datetime.now(TZ) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


class FakeCalDavEvent:
    """Stands in for caldav.Event: exposes data, icalendar_component and delete()."""

    def __init__(self, uid, calendar=None, start=None, summary="x", component=None):
        if component is None:
            component = icalendar.Event()
            component.add("UID", uid)
            component.add("SUMMARY", summary)
            if start is not None:
                component.add("DTSTART", start)
        self.uid_value = uid
        self.icalendar_component = component
        self.deleted = False
        self.saves = 0
        self.save_error = None
        self._calendar = calendar

    @property
    def data(self):
        return self.icalendar_component.to_ical().decode()

    @data.setter
    def data(self, value):
        [self.icalendar_component] = icalendar.Calendar.from_ical(value).walk("VEVENT")

    def save(self):
        """Like caldav: store the object and increase its SEQUENCE."""
        if self.save_error:
            raise self.save_error
        component = self.icalendar_component
        sequence = int(component.get("SEQUENCE", 0)) + 1
        component.pop("SEQUENCE", None)
        component.add("SEQUENCE", sequence)
        self.saves += 1

    def delete(self):
        self.deleted = True
        if self._calendar is not None:
            self._calendar.stored.remove(self)


class FakeCalendar:
    """In-memory calendar recording every save_event() call."""

    url = "https://dav.example/cal"

    def __init__(self, existing_uids=()):
        self.stored = [FakeCalDavEvent(uid, self) for uid in existing_uids]
        self.saved = []  # serialized VEVENT strings passed to save_event
        self.save_errors = []  # exceptions to raise on successive saves

    def events(self):
        return list(self.stored)

    def save_event(self, data):
        if self.save_errors:
            raise self.save_errors.pop(0)
        self.saved.append(data)

    def add(self, *uids, start=None):
        self.stored.extend(FakeCalDavEvent(uid, self, start=start) for uid in uids)

    def persist_saved(self):
        """Simulate the server storing everything saved so far (for a second run)."""
        self.stored.extend(
            FakeCalDavEvent(str(ev["UID"]), self, component=ev) for ev in self.saved_events()
        )
        self.saved = []

    def uids(self):
        return sorted(e.uid_value for e in self.stored)

    def saved_events(self):
        """Parse saved events back into icalendar components."""
        events = []
        for data in self.saved:
            [event] = icalendar.Calendar.from_ical(data).walk("VEVENT")
            events.append(event)
        return events


@pytest.fixture
def calendar():
    return FakeCalendar()


class FakeResponse:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error")


@pytest.fixture
def feed(monkeypatch):
    """Serve ICS content by URL. Use: feed.serve(url, text_or_bytes)."""

    class FeedServer:
        def __init__(self):
            self.content = {}
            self.calls = []

        def serve(self, url, body, status=200):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.content[url] = FakeResponse(body, status)

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url not in self.content:
                import requests

                raise requests.ConnectionError(f"cannot reach {url}")
            return self.content[url]

    server = FeedServer()
    monkeypatch.setattr(utils.requests, "get", server.get)
    return server
