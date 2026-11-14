"""Tests for the opt-in update_existing feature (step C)."""

from datetime import timedelta

import icalendar
import pytest

import utils
from conftest import TZ, make_ics, soon, vevent

URL = "https://feed.example/cal.ics"
CONFIG = {"uid_prefix": "ICS-", "timezone": "Europe/Vienna", "future_event_limit_days": 365}


def sync(calendar, feed, events, dry_run=False, update_existing=True, **feed_options):
    feed.serve(URL, make_ics(*events))
    existing = {e.uid_value for e in calendar.stored}
    options = {"url": URL, "update_existing": update_existing, **feed_options}
    return utils.import_ics_feed(calendar, options, "T-", existing, config=CONFIG,
                                 dry_run=dry_run, calendar_events=calendar.events())


def first_sync(calendar, feed, events, **kw):
    sync(calendar, feed, events, **kw)
    calendar.persist_saved()
    [e.__setattr__("saves", 0) for e in calendar.stored]


def stored(calendar):
    [event] = calendar.stored
    return event


def game(start=None, **kw):
    start = start or soon(3)
    return vevent("Game", start, start + timedelta(hours=2), **kw)


@pytest.mark.parametrize(
    "change, field",
    [
        (dict(extra="LOCATION:New arena"), "location"),
        (dict(extra="DESCRIPTION:Updated info"), "description"),
        (dict(extra="URL:https://new.example"), "url"),
        (dict(extra="CATEGORIES:Playoffs"), "categories"),
    ],
)
def test_changed_feed_content_is_updated(calendar, feed, change, field):
    first_sync(calendar, feed, [game(extra="LOCATION:Arena")])
    before = stored(calendar).icalendar_component
    assert sync(calendar, feed, [game(**change)]) == 0
    event = stored(calendar)
    assert event.saves == 1
    assert calendar.saved == []  # updated in place, not re-created
    assert field in utils.changed_fields(before, event.icalendar_component, TZ)


def test_changed_end_time_is_updated(calendar, feed):
    start = soon(3)
    first_sync(calendar, feed, [vevent("Game", start, start + timedelta(hours=2))])
    sync(calendar, feed, [vevent("Game", start, start + timedelta(hours=3))])
    assert stored(calendar).icalendar_component.decoded("DTEND") == start + timedelta(hours=3)


def test_config_changes_are_applied(calendar, feed):
    first_sync(calendar, feed, [game()])
    sync(calendar, feed, [game()], emoji_mapping={"default": "🏒"}, calendar_color="#FF0000",
         default_reminder="1h")
    component = stored(calendar).icalendar_component
    assert str(component["SUMMARY"]) == "🏒 Game"
    assert str(component["COLOR"]) == "#FF0000"
    assert [a.decoded("TRIGGER") for a in component.walk("VALARM")] == [timedelta(hours=-1)]


def test_unchanged_event_is_not_rewritten(calendar, feed):
    first_sync(calendar, feed, [game(extra="LOCATION:Arena\nCATEGORIES:A,B")], default_reminder="15m")
    sync(calendar, feed, [game(extra="LOCATION:Arena\nCATEGORIES:A,B")], default_reminder="15m")
    assert stored(calendar).saves == 0


def test_update_keeps_uid_and_created_and_bumps_sequence(calendar, feed):
    first_sync(calendar, feed, [game()])
    before = stored(calendar).icalendar_component
    uid, created = str(before["UID"]), before["CREATED"].to_ical()
    sync(calendar, feed, [game(extra="LOCATION:Moved")])
    after = stored(calendar).icalendar_component
    assert str(after["UID"]) == uid
    assert after["CREATED"].to_ical() == created
    assert int(after["SEQUENCE"]) == 1
    sync(calendar, feed, [game(extra="LOCATION:Moved again")])
    assert int(stored(calendar).icalendar_component["SEQUENCE"]) == 2


def test_dry_run_does_not_update(calendar, feed):
    first_sync(calendar, feed, [game()])
    sync(calendar, feed, [game(extra="LOCATION:Moved")], dry_run=True)
    assert stored(calendar).saves == 0
    assert "LOCATION" not in stored(calendar).icalendar_component


def test_disabled_by_default(calendar, feed):
    first_sync(calendar, feed, [game()])
    sync(calendar, feed, [game(extra="LOCATION:Moved")], update_existing=False)
    assert stored(calendar).saves == 0


def test_failed_update_is_counted(calendar, feed):
    first_sync(calendar, feed, [game()])
    stored(calendar).save_error = RuntimeError("412 Precondition Failed")
    assert sync(calendar, feed, [game(extra="LOCATION:Moved")]) == 1


def test_new_events_are_still_created(calendar, feed):
    first_sync(calendar, feed, [game()])
    sync(calendar, feed, [game(), vevent("Other", soon(5))])
    assert [str(e["SUMMARY"]) for e in calendar.saved_events()] == ["❓ Other"]
    assert stored(calendar).saves == 0


# --- fingerprint normalisation (events written by older versions) ------------


def _component(text):
    [event] = icalendar.Calendar.from_ical(make_ics(text)).walk("VEVENT")
    return event


def test_fingerprint_equal_for_utc_and_local_times():
    a = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nEND:VEVENT")
    b = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART;TZID=Europe/Vienna:20261201T100000\nEND:VEVENT")
    assert utils.changed_fields(a, b, TZ) == []


def test_fingerprint_all_day_missing_end_equals_one_day():
    a = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART;VALUE=DATE:20261201\nEND:VEVENT")
    b = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART;VALUE=DATE:20261201\nDTEND;VALUE=DATE:20261202\nEND:VEVENT")
    assert utils.changed_fields(a, b, TZ) == []


def test_fingerprint_duration_equals_dtend():
    a = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nDURATION:PT1H\nEND:VEVENT")
    b = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nDTEND:20261201T100000Z\nEND:VEVENT")
    assert utils.changed_fields(a, b, TZ) == []


def test_fingerprint_ignores_timestamps_sequence_and_server_properties():
    a = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nDTSTAMP:20200101T000000Z\n"
                   "SEQUENCE:4\nX-MOZ-GENERATION:3\nDESCRIPTION:\nEND:VEVENT")
    b = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nDTSTAMP:20261114T000000Z\nEND:VEVENT")
    assert utils.changed_fields(a, b, TZ) == []


def test_fingerprint_alarm_extra_properties_ignored_trigger_compared():
    alarm = "BEGIN:VALARM\nACTION:DISPLAY\nTRIGGER:-PT15M\n{extra}END:VALARM\n"
    base = "BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\n{alarm}END:VEVENT"
    a = _component(base.format(alarm=alarm.format(extra="X-WR-ALARMUID:abc\nDESCRIPTION:r\n")))
    b = _component(base.format(alarm=alarm.format(extra="")))
    c = _component(base.format(alarm=alarm.format(extra="").replace("15M", "30M")))
    assert utils.changed_fields(a, b, TZ) == []
    assert utils.changed_fields(a, c, TZ) == ["alarms"]


def test_fingerprint_reports_each_changed_field():
    a = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nLOCATION:A\nEND:VEVENT")
    b = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:y\nDTSTART:20261201T090000Z\nDTEND:20261201T100000Z\nLOCATION:B\nEND:VEVENT")
    assert utils.changed_fields(a, b, TZ) == ["end", "summary", "location"]


def test_all_day_vs_timed_is_a_change():
    a = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART;VALUE=DATE:20261201\nEND:VEVENT")
    b = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T000000Z\nEND:VEVENT")
    assert "start" in utils.changed_fields(a, b, TZ)


def test_color_ignored_when_server_dropped_it():
    # mailbox.org strips COLOR; that must not make every event look changed
    stored_by_server = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nEND:VEVENT")
    ours = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nCOLOR:#B0E0E6\nEND:VEVENT")
    assert utils.changed_fields(stored_by_server, ours, TZ) == []


def test_color_change_detected_when_server_keeps_it():
    old = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nCOLOR:#000000\nEND:VEVENT")
    new = _component("BEGIN:VEVENT\nUID:u\nSUMMARY:x\nDTSTART:20261201T090000Z\nCOLOR:#B0E0E6\nEND:VEVENT")
    assert utils.changed_fields(old, new, TZ) == ["color"]
