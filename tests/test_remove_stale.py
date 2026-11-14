"""Tests for the opt-in remove_stale feature (issue #13)."""

import json
import sys
from datetime import timedelta

import pytest

import calendar_sync
import utils
from conftest import FakeCalDavEvent, FakeCalendar, make_ics, soon, vevent

URL = "https://feed.example/cal.ics"
CONFIG = {"uid_prefix": "ICS-", "timezone": "Europe/Vienna", "future_event_limit_days": 365}


def sync(calendar, feed, events, dry_run=False, prefix="T-", **feed_options):
    """Import `events` with remove_stale enabled, like main() does."""
    feed.serve(URL, make_ics(*events))
    existing = {e.uid_value for e in calendar.stored}
    return utils.import_ics_feed(
        calendar, {"url": URL, **feed_options}, prefix, existing, config=CONFIG,
        dry_run=dry_run, remove_stale=True, calendar_events=calendar.events(),
    )


def first_sync(calendar, feed, events, **kw):
    sync(calendar, feed, events, **kw)
    calendar.persist_saved()


def titles(calendar):
    return sorted(str(e.icalendar_component["SUMMARY"]) for e in calendar.stored)


def test_event_dropped_from_feed_is_removed(calendar, feed):
    first_sync(calendar, feed, [vevent("Game 1", soon(1)), vevent("Game 2", soon(2))])
    assert sync(calendar, feed, [vevent("Game 1", soon(1))]) == 0
    assert titles(calendar) == ["❓ Game 1"]


def test_rescheduled_event_replaces_old_one(calendar, feed):
    # Issue #13: hockey schedule changes mid-season
    first_sync(calendar, feed, [vevent("Hockey", soon(3))])
    sync(calendar, feed, [vevent("Hockey", soon(5))])
    calendar.persist_saved()
    [event] = calendar.stored
    assert event.icalendar_component.decoded("DTSTART") == soon(5)


def test_past_events_are_kept_even_if_feed_dropped_them(calendar, feed):
    # Feeds often only list upcoming events; history must survive
    first_sync(calendar, feed, [vevent("Yesterday", soon(-1)), vevent("Tomorrow", soon(1))])
    sync(calendar, feed, [vevent("Tomorrow", soon(1))])
    assert titles(calendar) == ["❓ Tomorrow", "❓ Yesterday"]


def test_events_beyond_future_limit_are_kept(calendar, feed):
    calendar.add("T-far", start=soon(400))
    sync(calendar, feed, [vevent("Soon", soon(1))])
    assert "T-far" in calendar.uids()


def test_other_prefixes_and_own_events_are_kept(calendar, feed):
    calendar.add("F1-x", "mine", start=soon(1))
    sync(calendar, feed, [vevent("Soon", soon(2))])
    assert calendar.uids() == ["F1-x", "mine"]


def test_events_excluded_by_new_filter_are_removed(calendar, feed):
    events = [vevent("Final", soon(1)), vevent("Practice", soon(2))]
    first_sync(calendar, feed, events)
    sync(calendar, feed, events, filter={"exclude": ["Practice"]})
    assert titles(calendar) == ["❓ Final"]


def test_dry_run_removes_nothing(calendar, feed):
    first_sync(calendar, feed, [vevent("A", soon(1)), vevent("B", soon(2))])
    sync(calendar, feed, [vevent("A", soon(1))], dry_run=True)
    assert len(calendar.stored) == 2


def test_empty_feed_does_not_wipe_calendar(calendar, feed):
    first_sync(calendar, feed, [vevent("A", soon(1)), vevent("B", soon(2))])
    assert sync(calendar, feed, []) == 0
    assert len(calendar.stored) == 2


def test_failed_feed_removes_nothing(calendar, feed):
    first_sync(calendar, feed, [vevent("A", soon(1))])
    feed.serve(URL, b"", status=503)
    with pytest.raises(Exception):
        utils.import_ics_feed(calendar, {"url": URL}, "T-", set(), config=CONFIG,
                              remove_stale=True, calendar_events=calendar.events())
    assert len(calendar.stored) == 1


def test_all_day_events_are_handled(calendar, feed):
    a, b = soon(1).date(), soon(2).date()
    first_sync(calendar, feed, [vevent("A", a, all_day=True), vevent("B", b, all_day=True)])
    sync(calendar, feed, [vevent("A", a, all_day=True)])
    assert titles(calendar) == ["❓ A"]


def test_event_without_start_is_kept(calendar, feed):
    calendar.add("T-nostart")
    sync(calendar, feed, [vevent("A", soon(1))])
    assert "T-nostart" in calendar.uids()


def test_failed_delete_is_counted(calendar, feed):
    first_sync(calendar, feed, [vevent("A", soon(1)), vevent("B", soon(2))])

    def refuse():
        raise RuntimeError("403 Forbidden")

    calendar.stored[1].delete = refuse
    assert sync(calendar, feed, [vevent("A", soon(1))]) == 1


def test_disabled_by_default(calendar, feed):
    first_sync(calendar, feed, [vevent("A", soon(1)), vevent("B", soon(2))])
    feed.serve(URL, make_ics(vevent("A", soon(1))))
    utils.import_ics_feed(calendar, {"url": URL}, "T-", set(), config=CONFIG,
                          calendar_events=calendar.events())
    assert len(calendar.stored) == 2


# --- prefix safety -----------------------------------------------------------


@pytest.mark.parametrize(
    "feeds, expected",
    [
        ([{"url": "a", "uid_prefix": "A-", "remove_stale": True}, {"url": "b", "uid_prefix": "B-"}], [True, False]),
        ([{"url": "a", "remove_stale": True}], [False]),  # global prefix shared with extra_events
        ([{"url": "a", "uid_prefix": "ICS-X-", "remove_stale": True}], [False]),  # starts with global prefix
        ([{"url": "a", "uid_prefix": "A-", "remove_stale": True}, {"url": "b", "uid_prefix": "A-"}], [False, False]),
        ([{"url": "a", "uid_prefix": "F1-", "remove_stale": True}, {"url": "b", "uid_prefix": "F1-SPRINT-"}], [False, False]),
        ([{"url": "a", "uid_prefix": "A-", "remove_stale": False}], [False]),
    ],
)
def test_stale_removal_allowed(feeds, expected):
    assert utils.stale_removal_allowed({"uid_prefix": "ICS-", "ics_feeds": feeds}) == expected


def test_main_removes_stale_and_refuses_shared_prefix(monkeypatch, tmp_path, feed):
    calendar = FakeCalendar()
    calendar.stored = [
        FakeCalDavEvent("A-old", calendar, start=soon(3)),
        FakeCalDavEvent("ICS-old", calendar, start=soon(3)),  # belongs to extra_events / shared prefix
    ]
    monkeypatch.setattr(calendar_sync, "DAVClient", lambda *a, **k: type("C", (), {"calendar": lambda self, url: calendar})())
    feed.serve("https://a", make_ics(vevent("New", soon(1))))
    feed.serve("https://shared", make_ics(vevent("Other", soon(1))))
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "caldav_url": "x", "username": "u", "password": "p", "uid_prefix": "ICS-",
        "ics_feeds": [
            {"url": "https://a", "uid_prefix": "A-", "remove_stale": True},
            {"url": "https://shared", "remove_stale": True},
        ],
    }))
    monkeypatch.setattr(sys, "argv", ["x", "--import", "--config", str(config)])
    assert calendar_sync.main() == 1  # misconfigured feed is reported
    assert "A-old" not in calendar.uids()  # stale event removed
    assert "ICS-old" in calendar.uids()  # shared prefix untouched
    assert len(calendar.saved) == 2  # both feeds still imported
