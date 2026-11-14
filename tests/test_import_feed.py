"""Behavioural tests for utils.import_ics_feed against a fake feed and calendar."""

from datetime import date, datetime, timedelta

import pytest

import utils
from conftest import TZ, FakeCalendar, make_ics, soon, vevent

URL = "https://feed.example/cal.ics"
CONFIG = {"timezone": "Europe/Vienna", "future_event_limit_days": 365}


def run(calendar, feed, events, existing=None, dry_run=False, config=CONFIG, **feed_options):
    """Serve `events` at URL and import them with the given per-feed options."""
    if isinstance(events, (str, bytes)):
        body = events
    else:
        body = make_ics(*events)
    feed.serve(URL, body)
    feed_config = {"url": URL, **feed_options}
    return utils.import_ics_feed(
        calendar, feed_config, "T-", existing if existing is not None else set(),
        config=config, dry_run=dry_run,
    )


def summaries(calendar):
    return [str(e["SUMMARY"]) for e in calendar.saved_events()]


# --- basic import ------------------------------------------------------------


def test_imports_event_with_prefixed_uid_and_fields(calendar, feed):
    start = soon()
    failures = run(
        calendar, feed,
        [vevent("Game", start, start + timedelta(hours=2),
                extra="LOCATION:Arena\nDESCRIPTION:Bring snacks\nURL:https://x.example/g")],
    )
    assert failures == 0
    [ev] = calendar.saved_events()
    assert str(ev["SUMMARY"]) == "❓ Game"  # no emoji mapping -> ❓
    assert str(ev["UID"]) == utils.deterministic_uid("T-", "Game", start)
    assert str(ev["LOCATION"]) == "Arena"
    assert str(ev["DESCRIPTION"]) == "Bring snacks"
    assert ev.decoded("DTSTART") == start
    assert ev.decoded("DTEND") == start + timedelta(hours=2)


def test_uses_request_timeout(calendar, feed):
    run(calendar, feed, [vevent("Game", soon())])
    assert feed.calls[0][1]["timeout"] == utils.FEED_TIMEOUT


def test_http_error_propagates(calendar, feed):
    feed.serve(URL, b"", status=500)
    with pytest.raises(Exception, match="500"):
        utils.import_ics_feed(calendar, {"url": URL}, "T-", set(), config=CONFIG)


def test_works_without_config(calendar, feed):
    assert run(calendar, feed, [vevent("Game", soon())], config=None) == 0
    assert len(calendar.saved) == 1


def test_zero_length_event_has_no_end(calendar, feed):
    start = soon()
    run(calendar, feed, [vevent("Instant", start, start)])
    [ev] = calendar.saved_events()
    assert "DTEND" not in ev


def test_malformed_events_do_not_break_the_feed(calendar, feed):
    start = soon()
    no_start = "BEGIN:VEVENT\nUID:x\nSUMMARY:No start\nEND:VEVENT"
    run(calendar, feed, [vevent("Good", start, start + timedelta(hours=1)),
                         vevent("Backwards", start, start - timedelta(hours=1)),
                         no_start])
    assert summaries(calendar) == ["❓ Good", "❓ Backwards"]
    backwards = calendar.saved_events()[1]
    assert backwards.decoded("DTSTART") == start  # original start kept
    assert "DTEND" not in backwards


def test_saved_event_is_a_valid_vcalendar(calendar, feed):
    run(calendar, feed, [vevent("Game", soon())])
    [data] = calendar.saved
    assert data.startswith("BEGIN:VCALENDAR")
    [ev] = calendar.saved_events()
    assert "DTSTAMP" in ev and "CREATED" in ev


def test_floating_time_uses_configured_timezone(calendar, feed):
    local = soon().replace(tzinfo=None)
    body = make_ics(f"BEGIN:VEVENT\nUID:f\nDTSTART:{local:%Y%m%dT%H%M%S}\nSUMMARY:Local\nEND:VEVENT")
    run(calendar, feed, body)
    [ev] = calendar.saved_events()
    assert ev.decoded("DTSTART") == local.replace(tzinfo=TZ)


def test_all_day_event_stays_all_day(calendar, feed):
    day = soon().date()
    run(calendar, feed, [vevent("Holiday", day, day + timedelta(days=1), all_day=True)])
    [ev] = calendar.saved_events()
    assert ev.decoded("DTSTART") == day


def test_latin1_feed_is_decoded(calendar, feed):
    body = make_ics(vevent("Müll", soon())).encode("iso-8859-1")
    run(calendar, feed, body)
    assert summaries(calendar) == ["❓ Müll"]


def test_cleanup_regex_is_applied_before_parsing(calendar, feed):
    run(calendar, feed, [vevent("Old name", soon())],
        cleanup_regex=[{"pattern": "SUMMARY:Old", "replacement": "SUMMARY:New"}])
    assert summaries(calendar) == ["❓ New name"]


# --- skipping ----------------------------------------------------------------


def test_existing_uid_is_skipped(calendar, feed):
    start = soon()
    existing = {utils.deterministic_uid("T-", "Game", start)}
    run(calendar, feed, [vevent("Game", start), vevent("Other", start)], existing=existing)
    assert summaries(calendar) == ["❓ Other"]


def test_dry_run_saves_nothing(calendar, feed):
    run(calendar, feed, [vevent("Game", soon())], dry_run=True)
    assert calendar.saved == []


def test_time_window(calendar, feed):
    run(calendar, feed, [
        vevent("Long ago", soon(days=-30)),
        vevent("Last week", soon(days=-7)),  # within the 2-week grace period
        vevent("Next week", soon(days=7)),
        vevent("Too far", soon(days=400)),
    ])
    assert summaries(calendar) == ["❓ Last week", "❓ Next week"]


def test_future_limit_is_configurable(calendar, feed):
    run(calendar, feed, [vevent("Soon", soon(days=5)), vevent("Later", soon(days=20))],
        config={**CONFIG, "future_event_limit_days": 10})
    assert summaries(calendar) == ["❓ Soon"]


def test_events_are_imported_in_start_order(calendar, feed):
    run(calendar, feed, [vevent("B", soon(days=9)), vevent("A", soon(days=3))])
    assert summaries(calendar) == ["❓ A", "❓ B"]


@pytest.mark.parametrize(
    "location, imported",
    [("K", True), ("St, W", True), ("W", False), ("", True)],
)
def test_import_locations(calendar, feed, location, imported):
    extra = f"LOCATION:{location}" if location else ""
    run(calendar, feed, [vevent("Feiertag", soon(), extra=extra)], import_locations="K,St")
    assert (len(calendar.saved) == 1) is imported


# --- title filters -----------------------------------------------------------


EVENTS = ["Grand Slam Final", "Qualifying Round", "Practice Session"]


def _filtered(calendar, feed, **filter_config):
    run(calendar, feed, [vevent(t, soon(days=i + 1)) for i, t in enumerate(EVENTS)],
        filter=filter_config)
    return [s.removeprefix("❓ ") for s in summaries(calendar)]


def test_include_filter(calendar, feed):
    assert _filtered(calendar, feed, include=["Final", "^Practice"]) == ["Grand Slam Final", "Practice Session"]


def test_exclude_filter(calendar, feed):
    assert _filtered(calendar, feed, exclude=["Qualifying|Practice"]) == ["Grand Slam Final"]


def test_include_and_exclude_together_disables_both(calendar, feed):
    assert _filtered(calendar, feed, include=["Final"], exclude=["Final"]) == EVENTS


def test_invalid_regex_does_not_filter(calendar, feed):
    assert _filtered(calendar, feed, include=["(unclosed"]) == EVENTS


# --- emoji mapping -----------------------------------------------------------


def test_emoji_first_matching_key_wins_then_default(calendar, feed):
    mapping = {"Sprint Qualifying": "⏱️", "Sprint": "⚡", "default": "🏎️"}
    run(calendar, feed, [
        vevent("Sprint Qualifying", soon(days=1)),
        vevent("Sprint", soon(days=2)),
        vevent("Race", soon(days=3)),
    ], emoji_mapping=mapping)
    assert summaries(calendar) == ["⏱️ Sprint Qualifying", "⚡ Sprint", "🏎️ Race"]


# --- categories --------------------------------------------------------------


def _categories(calendar):
    [ev] = calendar.saved_events()
    if "CATEGORIES" not in ev:
        return []
    cats = ev["CATEGORIES"]
    cats = cats if isinstance(cats, list) else [cats]
    return [str(c) for item in cats for c in item.cats]


def test_categories_pipeline(calendar, feed):
    run(calendar, feed, [vevent("G", soon(), extra="CATEGORIES:Sports,Spam")],
        categories={"prepend": ["Feed"], "append": ["Sports", "Synced"], "remove": ["Spam"]})
    # prepend, append, remove, then deduplicate (default) keeps first occurrence
    assert _categories(calendar) == ["Feed", "Sports", "Synced"]


def test_categories_replace_if_empty(calendar, feed):
    run(calendar, feed, [vevent("G", soon())], categories={"replace_if_empty": ["Default"]})
    assert _categories(calendar) == ["Default"]


def test_categories_replace_if_empty_keeps_existing(calendar, feed):
    run(calendar, feed, [vevent("G", soon(), extra="CATEGORIES:Own")],
        categories={"replace_if_empty": ["Default"]})
    assert _categories(calendar) == ["Own"]


def test_categories_deduplicate_can_be_disabled(calendar, feed):
    run(calendar, feed, [vevent("G", soon(), extra="CATEGORIES:A")],
        categories={"append": ["A"], "deduplicate": False})
    assert _categories(calendar) == ["A", "A"]


def test_no_categories_by_default(calendar, feed):
    run(calendar, feed, [vevent("G", soon())])
    assert _categories(calendar) == []


# --- colour and reminders ----------------------------------------------------


def test_calendar_color(calendar, feed):
    run(calendar, feed, [vevent("G", soon())], calendar_color="#FFBDD1")
    [ev] = calendar.saved_events()
    assert str(ev["COLOR"]) == "#FFBDD1"


def test_default_reminder_added(calendar, feed):
    run(calendar, feed, [vevent("G", soon())], default_reminder="2h")
    [ev] = calendar.saved_events()
    [alarm] = ev.walk("VALARM")
    assert alarm.decoded("TRIGGER") == timedelta(hours=-2)


def test_feed_alarm_takes_precedence_over_default(calendar, feed):
    alarm = "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:x\nTRIGGER:-PT10M\nEND:VALARM"
    run(calendar, feed, [vevent("G", soon(), extra=alarm)], default_reminder="2h")
    [ev] = calendar.saved_events()
    assert [a.decoded("TRIGGER") for a in ev.walk("VALARM")] == [timedelta(minutes=-10)]


def test_invalid_default_reminder_still_imports(calendar, feed):
    run(calendar, feed, [vevent("G", soon())], default_reminder="soon")
    [ev] = calendar.saved_events()
    assert ev.walk("VALARM") == []


# --- recurrence (issue #15) -------------------------------------------------


def _starts(calendar):
    return [ev.decoded("DTSTART") for ev in calendar.saved_events()]


def utc_soon(days):
    """Feed times in these tests are UTC, so recurrences keep the UTC time across DST."""
    return soon(days).astimezone(utils.UTC)


def test_weekly_event_is_expanded(calendar, feed):
    start = utc_soon(1)
    run(calendar, feed, [vevent("Training", start, start + timedelta(hours=1), extra="RRULE:FREQ=WEEKLY;COUNT=4")])
    assert _starts(calendar) == [start + timedelta(weeks=i) for i in range(4)]
    uids = {str(ev["UID"]) for ev in calendar.saved_events()}
    assert len(uids) == 4
    assert all("RRULE" not in ev for ev in calendar.saved_events())


def test_unbounded_rule_stops_at_future_limit(calendar, feed):
    run(calendar, feed, [vevent("Daily", soon(days=1), extra="RRULE:FREQ=DAILY")],
        config={**CONFIG, "future_event_limit_days": 10})
    assert 8 <= len(calendar.saved) <= 10


def test_recurrence_respects_until_interval_and_exdate(calendar, feed):
    start = utc_soon(1)
    until = (start + timedelta(weeks=8)).astimezone(utils.UTC).strftime("%Y%m%dT%H%M%SZ")
    exdate = (start + timedelta(weeks=4)).astimezone(utils.UTC).strftime("%Y%m%dT%H%M%SZ")
    run(calendar, feed, [vevent("Biweekly", start,
                                extra=f"RRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL={until}\nEXDATE:{exdate}")])
    assert _starts(calendar) == [start + timedelta(weeks=w) for w in (0, 2, 6, 8)]


def test_moved_occurrence_uses_new_time(calendar, feed):
    start = utc_soon(1)
    second = start + timedelta(weeks=1)
    moved = second + timedelta(hours=3)
    recurrence_id = second.astimezone(utils.UTC).strftime("%Y%m%dT%H%M%SZ")
    run(calendar, feed, [
        vevent("Meeting", start, uid="m@x", extra="RRULE:FREQ=WEEKLY;COUNT=3"),
        vevent("Meeting", moved, uid="m@x", extra=f"RECURRENCE-ID:{recurrence_id}"),
    ])
    assert _starts(calendar) == [start, moved, start + timedelta(weeks=2)]


def test_occurrences_before_grace_period_are_skipped(calendar, feed):
    start = utc_soon(-30)
    run(calendar, feed, [vevent("Weekly", start, extra="RRULE:FREQ=WEEKLY;COUNT=8")])
    # occurrences at -30, -23, -16, -9, -2, +5, +12, +19 days; grace period is 14 days
    assert _starts(calendar) == [start + timedelta(weeks=w) for w in (3, 4, 5, 6, 7)]


def test_recurring_event_keeps_alarm_on_every_occurrence(calendar, feed):
    alarm = "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:x\nTRIGGER:-PT10M\nEND:VALARM"
    run(calendar, feed, [vevent("W", soon(days=1), extra=f"RRULE:FREQ=WEEKLY;COUNT=2\n{alarm}")])
    assert [len(ev.walk("VALARM")) for ev in calendar.saved_events()] == [1, 1]


def test_yearly_all_day_event_is_expanded(calendar, feed):
    start = soon(days=30).date().replace(year=2001)
    run(calendar, feed, [vevent("Bday", start, all_day=True, extra="RRULE:FREQ=YEARLY")],
        config={**CONFIG, "future_event_limit_days": 800})
    dates = _starts(calendar)
    assert len(dates) >= 2
    assert {(d.month, d.day) for d in dates} == {(start.month, start.day)}
    assert all(type(d) is date for d in dates)


def test_yearly_feb_29_only_in_leap_years(calendar, feed):
    run(calendar, feed, [vevent("Leap", date(2024, 2, 29), all_day=True, extra="RRULE:FREQ=YEARLY")],
        config={**CONFIG, "future_event_limit_days": 365 * 8})
    dates = _starts(calendar)
    assert dates and all(d.year % 4 == 0 and (d.month, d.day) == (2, 29) for d in dates)


# --- UID compatibility with versions that used the `ics` library -------------


def test_uid_compat_timed_event(calendar, feed):
    start = soon()
    run(calendar, feed, [vevent("Game", start)])
    assert str(calendar.saved_events()[0]["UID"]) == utils.deterministic_uid("T-", "Game", start)


def test_uid_compat_all_day_event_hashes_utc_midnight(calendar, feed):
    day = soon().date()
    run(calendar, feed, [vevent("Holiday", day, all_day=True)])
    expected = utils.deterministic_uid("T-", "Holiday", datetime(day.year, day.month, day.day, tzinfo=utils.UTC))
    assert str(calendar.saved_events()[0]["UID"]) == expected


# --- save failures -----------------------------------------------------------


def test_save_failure_is_counted_and_import_continues(calendar, feed):
    calendar.save_errors = [RuntimeError("500 Internal Server Error")]
    failures = run(calendar, feed, [vevent("A", soon(days=1)), vevent("B", soon(days=2))])
    assert failures == 1
    assert summaries(calendar) == ["❓ B"]


def test_409_conflict_replaces_existing_event(feed):
    # The UID exists on the server but was not in existing_uids (e.g. stale cache)
    start = soon()
    calendar = FakeCalendar([utils.deterministic_uid("T-", "Game", start)])
    calendar.save_errors = [RuntimeError("409 Conflict")]
    assert run(calendar, feed, [vevent("Game", start)]) == 0
    assert calendar.stored == []  # old copy deleted
    assert summaries(calendar) == ["❓ Game"]  # new copy saved


def test_409_without_matching_event_counts_as_failure(calendar, feed):
    calendar.save_errors = [RuntimeError("409 Conflict")]
    assert run(calendar, feed, [vevent("Game", soon())]) == 1
    assert calendar.saved == []


def test_all_day_date_with_tzid_stays_all_day(calendar, feed):
    # Seen in the wild (muellapp.com): DTSTART;TZID=...;VALUE=DATE with DTEND == DTSTART.
    # Must import as an all-day event with the same UID the `ics`-based version produced.
    day = soon().date()
    body = make_ics(
        "BEGIN:VEVENT\nUID:m\nSUMMARY:Restmüll\n"
        f"DTSTART;TZID=europe/vienna;VALUE=DATE:{day:%Y%m%d}\n"
        f"DTEND;TZID=europe/vienna;VALUE=DATE:{day:%Y%m%d}\nEND:VEVENT"
    )
    run(calendar, feed, body)
    [ev] = calendar.saved_events()
    assert ev.decoded("DTSTART") == day and type(ev.decoded("DTSTART")) is date
    assert ev.decoded("DTEND") == day + timedelta(days=1)  # a one-day event
    expected = utils.deterministic_uid("T-", "Restmüll", datetime(day.year, day.month, day.day, tzinfo=utils.UTC))
    assert str(ev["UID"]) == expected
