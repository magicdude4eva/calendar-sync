"""Unit tests for the pure helper functions in utils.py."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import utils
from conftest import TZ, FakeCalDavEvent, FakeCalendar

# --- deterministic_uid -------------------------------------------------------


def test_uid_is_stable_and_prefixed():
    start = datetime(2026, 5, 10, 18, 0, tzinfo=TZ)
    uid = utils.deterministic_uid("F1-", "Race", start)
    assert uid == utils.deterministic_uid("F1-", "Race", start)
    assert uid.startswith("F1-2026-")
    assert len(uid) == len("F1-2026-") + 16


def test_uid_is_timezone_independent():
    vienna = datetime(2026, 5, 10, 18, 0, tzinfo=TZ)
    utc = vienna.astimezone(ZoneInfo("UTC"))
    assert utils.deterministic_uid("X-", "T", vienna) == utils.deterministic_uid("X-", "T", utc)


def test_uid_ignores_seconds():
    a = datetime(2026, 5, 10, 18, 0, 0, tzinfo=TZ)
    b = datetime(2026, 5, 10, 18, 0, 59, 999, tzinfo=TZ)
    assert utils.deterministic_uid("X-", "T", a) == utils.deterministic_uid("X-", "T", b)


@pytest.mark.parametrize(
    "other",
    [
        ("X-", "Other title", datetime(2026, 5, 10, 18, 0, tzinfo=TZ)),
        ("X-", "T", datetime(2026, 5, 10, 18, 1, tzinfo=TZ)),
        ("Y-", "T", datetime(2026, 5, 10, 18, 0, tzinfo=TZ)),
    ],
)
def test_uid_changes_with_title_start_or_prefix(other):
    base = utils.deterministic_uid("X-", "T", datetime(2026, 5, 10, 18, 0, tzinfo=TZ))
    assert utils.deterministic_uid(*other) != base


# --- parse_alarm -------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1d", timedelta(days=-1)),
        ("2h", timedelta(hours=-2)),
        ("15m", timedelta(minutes=-15)),
        ("10M", timedelta(minutes=-10)),
    ],
)
def test_parse_alarm(value, expected):
    assert utils.parse_alarm(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "1w", "-1d", "1.5h", "d1"])
def test_parse_alarm_rejects_invalid(value):
    with pytest.raises(ValueError, match="invalid reminder"):
        utils.parse_alarm(value)


# --- extract_uid -------------------------------------------------------------


def test_extract_uid_from_parsed_component():
    assert utils.extract_uid(FakeCalDavEvent("ABC-1")) == "ABC-1"


def test_extract_uid_falls_back_to_raw_data_line_start_only():
    class Raw:
        data = "BEGIN:VEVENT\nX-WR-UID:wrong\nDESCRIPTION:see UID:wrong\nUID:right\nEND:VEVENT"

        @property
        def icalendar_component(self):
            raise ValueError("unparseable")

    assert utils.extract_uid(Raw()) == "right"


def test_extract_uid_returns_none_without_uid():
    class NoUid:
        data = "BEGIN:VEVENT\nSUMMARY:x\nEND:VEVENT"
        icalendar_component = {}

    assert utils.extract_uid(NoUid()) is None


# --- get_existing_events -----------------------------------------------------


def test_get_existing_events_filters_by_prefix():
    cal = FakeCalendar(["F1-a", "F1-b", "MUELL-c", "other"])
    assert utils.get_existing_events(cal, "F1-", all_events=cal.events()) == {"F1-a", "F1-b"}


def test_get_existing_events_fetches_when_not_given():
    cal = FakeCalendar(["F1-a"])
    assert utils.get_existing_events(cal, "F1-") == {"F1-a"}


def test_cleanup_deletes_only_matching_prefixes():
    cal = FakeCalendar(["F1-a", "MUELL-b", "HOLIDAY-c", "mine"])
    events = cal.events()
    result = utils.get_existing_events(
        cal, "F1-", cleanup_mode=True, all_events=events, multiple_prefixes=["F1-", "MUELL-"]
    )
    assert result == []
    assert [e.uid_value for e in events if e.deleted] == ["F1-a", "MUELL-b"]
    assert sorted(e.uid_value for e in cal.stored) == ["HOLIDAY-c", "mine"]


def test_cleanup_continues_when_a_delete_fails():
    cal = FakeCalendar(["X-1", "X-2"])
    events = cal.events()

    def boom():
        raise RuntimeError("server said no")

    events[0].delete = boom
    utils.get_existing_events(cal, "X-", cleanup_mode=True, all_events=events)
    assert events[1].deleted


# --- compute_extra_events ----------------------------------------------------

NOW = datetime(2026, 1, 1, tzinfo=TZ)
UNTIL = datetime(2026, 12, 31, 23, 59, tzinfo=TZ)


def _extra(*entries, now=NOW, until=UNTIL):
    events = utils.compute_extra_events({"extra_events": list(entries)}, "ICS-", TZ, now, until)
    return [(str(e["SUMMARY"]), e.decoded("DTSTART")) for e in events]


def test_extra_fixed_date():
    assert _extra("🎃 Halloween:31.10.fixed") == [("🎃 Halloween", date(2026, 10, 31))]


@pytest.mark.parametrize(
    "rule, expected",
    [
        ("2.Sunday.5", date(2026, 5, 10)),  # Muttertag
        ("2.Sunday.6", date(2026, 6, 14)),  # Vatertag (AT)
        ("-1.Sunday.3", date(2026, 3, 29)),  # DST starts
        ("-1.Sunday.10", date(2026, 10, 25)),  # DST ends
        ("1.Monday.6", date(2026, 6, 1)),
        ("4.Thursday.11", date(2026, 11, 26)),  # US Thanksgiving
    ],
)
def test_extra_nth_weekday(rule, expected):
    assert _extra(f"⭐ Day:{rule}") == [("⭐ Day", expected)]


def test_extra_fifth_weekday_skipped_when_month_has_only_four():
    # February 2026 has four Sundays
    assert _extra("⭐ Day:5.Sunday.2") == []


def test_extra_events_are_all_day_with_stable_uid():
    a = utils.compute_extra_events({"extra_events": ["🎃 H:31.10.fixed"]}, "ICS-", TZ, NOW, UNTIL)
    b = utils.compute_extra_events({"extra_events": ["🎃 H:31.10.fixed"]}, "ICS-", TZ, NOW, UNTIL)
    assert type(a[0].decoded("DTSTART")) is date  # all-day
    assert str(a[0]["UID"]) == str(b[0]["UID"])
    assert str(a[0]["UID"]).startswith("ICS-2026-")
    assert "DTSTAMP" in a[0]


def test_extra_events_respect_window_across_years():
    now = datetime(2026, 11, 1, tzinfo=TZ)
    until = datetime(2027, 11, 1, tzinfo=TZ)
    assert _extra("🎃 H:31.10.fixed", "🎅 N:6.12.fixed", now=now, until=until) == [
        ("🎃 H", date(2027, 10, 31)),
        ("🎅 N", date(2026, 12, 6)),
    ]


def test_extra_title_may_contain_colon():
    assert _extra("⏰ Meeting: Planning:24.12.fixed") == [("⏰ Meeting: Planning", date(2026, 12, 24))]


@pytest.mark.parametrize("entry", ["no-emoji-or-rule", "🎃 Bad:31-10", "🎃 Bad:32.13.fixed", "🎃 Bad:1.Funday.5"])
def test_extra_invalid_entries_are_skipped(entry):
    assert _extra(entry, "🎃 Halloween:31.10.fixed") == [("🎃 Halloween", date(2026, 10, 31))]


# --- rule_date: relative weekday rules (e.g. Advent) -------------------------

ADVENT = {  # year: (1. Advent, 4. Advent)
    2022: (date(2022, 11, 27), date(2022, 12, 18)),  # 25.12. is a Sunday
    2023: (date(2023, 12, 3), date(2023, 12, 24)),  # 4. Advent on Christmas Eve
    2024: (date(2024, 12, 1), date(2024, 12, 22)),
    2025: (date(2025, 11, 30), date(2025, 12, 21)),
    2026: (date(2026, 11, 29), date(2026, 12, 20)),
    2027: (date(2027, 11, 28), date(2027, 12, 19)),
}


@pytest.mark.parametrize("year", sorted(ADVENT))
def test_advent_sundays(year):
    first, fourth = ADVENT[year]
    assert utils.rule_date("4.Sunday.before.25.12", year) == first
    assert utils.rule_date("3.Sunday.before.25.12", year) == first + timedelta(weeks=1)
    assert utils.rule_date("2.Sunday.before.25.12", year) == first + timedelta(weeks=2)
    assert utils.rule_date("1.Sunday.before.25.12", year) == fourth


@pytest.mark.parametrize(
    "rule, expected",
    [
        ("1.Wednesday.before.23.11", date(2026, 11, 18)),  # Buß- und Bettag
        ("1.Monday.before.23.11", date(2026, 11, 16)),  # anchor itself is excluded
        ("1.Thursday.after.20.11", date(2026, 11, 26)),
        ("1.Friday.after.20.11", date(2026, 11, 27)),  # anchor itself is excluded
        ("2.Friday.after.20.11", date(2026, 12, 4)),
        ("1.Sunday.before.3.1", date(2025, 12, 28)),  # may cross into previous year
        ("1.sunday.before.25.12", date(2026, 12, 20)),  # weekday is case-insensitive
    ],
)
def test_relative_rules(rule, expected):
    assert utils.rule_date(rule, 2026) == expected


@pytest.mark.parametrize("rule", ["0.Sunday.before.25.12", "1.Funday.before.25.12", "1.Sunday.around.25.12", "1.Sunday.before.30.2"])
def test_relative_rule_errors(rule):
    with pytest.raises(ValueError):
        utils.rule_date(rule, 2026)


def test_old_advent_rules_were_a_week_late():
    # Documents why the example config changed: the last Sunday of December is
    # always on or after Christmas Day.
    for year in ADVENT:
        assert utils.rule_date("-1.Sunday.12", year) >= date(year, 12, 25)


def test_extra_events_with_relative_rule():
    assert _extra("🕯️ 4. Advent:1.Sunday.before.25.12") == [("🕯️ 4. Advent", date(2026, 12, 20))]
