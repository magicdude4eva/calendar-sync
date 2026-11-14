# utils.py

import hashlib
import logging
import re
from calendar import (
    FRIDAY,
    MONDAY,
    SATURDAY,
    SUNDAY,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    monthcalendar,
)
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

UTC = ZoneInfo("UTC")

logger = logging.getLogger("calendar_sync")

# Timeout (seconds) for fetching ICS feeds: (connect, read)
FEED_TIMEOUT = (10, 60)

# Feed events that started up to this long ago are still imported
PAST_GRACE = timedelta(weeks=2)


def fetch_all_events(calendar):
    """Fetch all events from the calendar once and reuse for filtering."""
    logger.info("📥 Fetching all events from calendar (once)...")
    events = list(calendar.events())
    logger.info(f"📅 Found {len(events)} events on calendar")
    return events


def extract_uid(event):
    try:
        uid = event.icalendar_component.get("UID")
        if uid:
            return str(uid).strip()
    except Exception as e:
        logger.debug(f"Could not read UID from parsed component: {e}")
    try:
        # Fallback: match a UID property at the start of a line only, so that
        # properties like X-SOMETHING-UID or text inside descriptions are ignored.
        match = re.search(r"^UID:(.+)$", str(event.data), re.MULTILINE)
        if match:
            return match.group(1).strip()
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract UID: {e}")
    return None


def get_existing_events(
    calendar, prefix, cleanup_mode=False, all_events=None, multiple_prefixes=None
):
    """
    Return events or delete them if cleanup_mode=True.
    Supports multiple prefixes in one pass when multiple_prefixes is provided.
    """
    if all_events is None:
        logger.info("Fetching all events from calendar...")
        events = list(calendar.events())
        logger.info(f"Found {len(events)} events on calendar")
    else:
        events = all_events

    uids_to_delete = []
    kept = 0
    prefixes = set(multiple_prefixes) if multiple_prefixes else {prefix}

    for event in events:
        uid = extract_uid(event)
        if uid and any(uid.startswith(p) for p in prefixes):
            if cleanup_mode:
                uids_to_delete.append((uid, event))
            else:
                uids_to_delete.append(uid)
        else:
            if cleanup_mode:
                kept += 1

    if cleanup_mode:
        for uid, event in uids_to_delete:
            try:
                event.delete()
                logger.info(f"🧽 Deleted event with UID {uid}")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete UID {uid}: {e}")

        logger.info(
            f"✅ Deleted {len(uids_to_delete)} events matching prefixes: {', '.join(prefixes)}"
        )
        logger.info(f"🛑 Kept {kept} events without matching prefixes")
        return []
    else:
        return set(uids_to_delete)


def deterministic_uid(prefix, title, start):
    normalized_start = start.astimezone(ZoneInfo("UTC")).replace(
        second=0, microsecond=0
    )
    iso = normalized_start.isoformat(timespec="minutes")
    uid_source = f"{title}-{iso}"
    uid_hash = hashlib.md5(uid_source.encode("utf-8")).hexdigest()
    return f"{prefix}{normalized_start.year}-{uid_hash[:16]}"


WEEKDAYS = {
    "Monday": MONDAY,
    "Tuesday": TUESDAY,
    "Wednesday": WEDNESDAY,
    "Thursday": THURSDAY,
    "Friday": FRIDAY,
    "Saturday": SATURDAY,
    "Sunday": SUNDAY,
}

RULE_FIXED = re.compile(r"^(\d{1,2})\.(\d{1,2})\.fixed$")
RULE_NTH_WEEKDAY = re.compile(r"^(-?\d+)\.([A-Za-z]+)\.(\d{1,2})$")
RULE_RELATIVE = re.compile(r"^(\d+)\.([A-Za-z]+)\.(before|after)\.(\d{1,2})\.(\d{1,2})$")


def rule_date(rule, year):
    """
    Resolve an extra_events rule to a date in the given year, or None if the
    rule yields no date that year (e.g. a 5th Sunday that does not exist).
    Raises ValueError for unsupported or invalid rules.

    Supported rules:
      DD.MM.fixed               fixed date              31.10.fixed
      N.Weekday.MM              Nth weekday of month    2.Sunday.5
      -N.Weekday.MM             Nth weekday from end    -1.Sunday.3
      N.Weekday.before.DD.MM    Nth weekday strictly    1.Sunday.before.25.12
      N.Weekday.after.DD.MM       before/after a date   (4th Advent)
    """
    if m := RULE_FIXED.match(rule):
        day, month = int(m[1]), int(m[2])
        return date(year, month, day)

    if m := RULE_NTH_WEEKDAY.match(rule):
        n, weekday, month = int(m[1]), _weekday(m[2]), int(m[3])
        days = [week[weekday] for week in monthcalendar(year, month) if week[weekday]]
        if n == 0 or abs(n) > len(days):
            return None
        return date(year, month, days[n - 1 if n > 0 else n])

    if m := RULE_RELATIVE.match(rule):
        n, weekday, direction = int(m[1]), _weekday(m[2]), m[3]
        anchor = date(year, int(m[5]), int(m[4]))
        if n == 0:
            raise ValueError("N must be at least 1")
        if direction == "before":
            back = (anchor.weekday() - weekday - 1) % 7 + 1  # 1..7 days back
            return anchor - timedelta(days=back + 7 * (n - 1))
        forward = (weekday - anchor.weekday() - 1) % 7 + 1  # 1..7 days forward
        return anchor + timedelta(days=forward + 7 * (n - 1))

    raise ValueError(f"unsupported rule format '{rule}'")


def _weekday(name):
    try:
        return WEEKDAYS[name.capitalize()]
    except KeyError:
        raise ValueError(f"unknown weekday '{name}'") from None


def compute_extra_events(config, uid_prefix, tz, now, until_date):
    extra_events = []

    for entry in config.get("extra_events", []):
        try:
            emoji, rest = entry.split(" ", 1)
            title, rule = rest.rsplit(":", 1)
            rule = rule.strip()
            for year in range(now.year, until_date.year + 1):
                day = rule_date(rule, year)
                if day is None:
                    continue
                dt = datetime(day.year, day.month, day.day, tzinfo=tz)
                if now <= dt <= until_date:
                    uid = deterministic_uid(uid_prefix, title, dt)
                    event = new_event(uid, f"{emoji} {title}".strip(), now)
                    event.add("DTSTART", day)
                    extra_events.append(event)
        except Exception as e:
            logger.warning(f"⚠️ Failed to process extra_event '{entry}': {e}")

    return extra_events


def parse_alarm(offset):
    """
    parse the alarm strings like '1d', '10m' into a timedelta
    """

    regex = re.match(r"^(\d+)([dhm])$", offset.lower())

    if not regex:
        raise ValueError(
            f"invalid reminder value '{offset}' (expected e.g. '1d', '2h', '15m')"
        )

    val = int(regex.group(1))
    unit = regex.group(2)
    if unit == "d":
        return timedelta(days=-val)
    elif unit == "h":
        return timedelta(hours=-val)
    elif unit == "m":
        return timedelta(minutes=-val)


# ---------------------------------------------------------------------------
# Building events
# ---------------------------------------------------------------------------

PRODID = "-//magicdude4eva//calendar-sync//EN"


def new_event(uid, summary, now):
    """Create a VEVENT with the properties every synced event carries."""
    event = icalendar.Event()
    event.add("UID", uid)
    event.add("SUMMARY", summary)
    event.add("DTSTAMP", now.astimezone(UTC))
    event.add("CREATED", now.astimezone(UTC))
    return event


def to_ics(event):
    """Wrap a single VEVENT in a VCALENDAR, ready for calendar.save_event()."""
    cal = icalendar.Calendar()
    cal.add("PRODID", PRODID)
    cal.add("VERSION", "2.0")
    cal.add_component(event)
    return cal.to_ical().decode("utf-8")


def display_alarm(trigger, description):
    alarm = icalendar.Alarm()
    alarm.add("ACTION", "DISPLAY")
    alarm.add("DESCRIPTION", description)
    alarm.add("TRIGGER", trigger)
    return alarm


# ---------------------------------------------------------------------------
# Reading feeds
# ---------------------------------------------------------------------------


def fetch_feed(url, cleanup_rules=()):
    """Download an ICS feed and apply the configured cleanup_regex rules."""
    response = requests.get(url, timeout=FEED_TIMEOUT)
    response.raise_for_status()

    try:
        ics_data = response.content.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("⚠️ UTF-8 decode failed, falling back to ISO-8859-1")
        ics_data = response.content.decode("iso-8859-1")

    for rule in cleanup_rules:
        ics_data = re.sub(rule["pattern"], rule["replacement"], ics_data)
    return ics_data


def _sanitize(cal):
    """
    Repair problems that would otherwise break or distort recurrence expansion:
    - events without DTSTART are dropped
    - all-day values that also carry a TZID (e.g. DTSTART;TZID=X;VALUE=DATE) are
      turned back into plain dates; icalendar would read them as midnight datetimes
    - a DTEND that is not after DTSTART is removed (the event keeps its start)
    """
    kept = []
    for component in cal.subcomponents:
        if component.name == "VEVENT":
            summary = component.get("SUMMARY", "Untitled")
            if "DTSTART" not in component:
                logger.info(f"⏭️ Skipping event '{summary}' due to missing begin date.")
                continue
            for prop in ("DTSTART", "DTEND", "RECURRENCE-ID"):
                _force_date_value(component, prop)
            if "DTEND" in component:
                try:
                    start, end = component.decoded("DTSTART"), component.decoded("DTEND")
                    start_utc, end_utc = _as_utc(start, UTC), _as_utc(end, UTC)
                except (TypeError, ValueError):
                    start_utc = end_utc = None
                if end_utc is None or end_utc <= start_utc:
                    if end_utc is not None and end_utc < start_utc:
                        logger.warning(f"⚠️ Ignoring end time of '{summary}': it is before the start")
                    del component["DTEND"]
        kept.append(component)
    cal.subcomponents = kept
    return cal


def _force_date_value(component, prop):
    """Honour VALUE=DATE even when a TZID parameter is present."""
    if prop not in component:
        return
    value = component[prop]
    if value.params.get("VALUE", "").upper() != "DATE":
        return
    decoded = component.decoded(prop)
    if isinstance(decoded, datetime):
        del component[prop]
        component.add(prop, decoded.date())


def _as_utc(value, tz):
    """
    Normalise a DTSTART/DTEND value to an aware UTC datetime.
    All-day dates map to midnight UTC and floating times are interpreted
    in `tz`. This is the value deterministic_uid() hashes, so it must stay
    stable to avoid creating duplicates of already-synced events.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def feed_occurrences(ics_data, tz, window_start, window_end):
    """
    Parse a feed and return every event occurrence that starts inside
    [window_start, window_end], sorted by start. Recurring events (RRULE,
    RDATE, EXDATE and moved instances via RECURRENCE-ID) are expanded into
    individual occurrences.

    Returns a list of (start_utc, all_day, component) tuples.
    """
    cal = _sanitize(icalendar.Calendar.from_ical(ics_data))
    logger.info(f"📅 Found {len(cal.walk('VEVENT'))} events in feed")

    occurrences = []
    query = recurring_ical_events.of(cal, skip_bad_series=True)
    for component in query.between(window_start, window_end):
        start = component.decoded("DTSTART")
        start_utc = _as_utc(start, tz)
        if not window_start <= start_utc <= window_end:
            continue  # overlaps the window but starts outside it
        all_day = not isinstance(start, datetime)
        occurrences.append((start_utc, all_day, component))

    occurrences.sort(key=lambda o: o[0])
    return occurrences


def _categories(component):
    value = component.get("CATEGORIES")
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [str(cat) for item in items for cat in item.cats]


def apply_category_rules(categories, rules):
    """Apply a feed's 'categories' configuration (see README for the order)."""
    if rules.get("replace_if_empty") and not categories:
        categories = list(rules["replace_if_empty"])
    if "prepend" in rules:
        categories = list(rules["prepend"]) + categories
    if "append" in rules:
        categories = categories + list(rules["append"])
    if "remove" in rules:
        categories = [cat for cat in categories if cat not in rules["remove"]]
    if rules.get("deduplicate", True):
        categories = list(dict.fromkeys(categories))
    return categories


def _title_filter(feed_config):
    """Return a predicate title -> bool implementing the feed's include/exclude filter."""
    filter_config = feed_config.get("filter", {})
    include = filter_config.get("include")
    exclude = filter_config.get("exclude")
    url = feed_config.get("url")

    if include and exclude:
        logger.warning(
            f"⚠️ Filter error for feed {url}: cannot use both 'include' and 'exclude'. "
            "Ignoring both filters."
        )
        return lambda title: True

    patterns = include or exclude
    if not patterns:
        return lambda title: True
    try:
        compiled = [re.compile(p) for p in patterns]
    except re.error as e:
        kind = "include" if include else "exclude"
        logger.warning(f"⚠️ Invalid {kind} regex pattern for feed {url}: {e}")
        return lambda title: True

    def matches(title):
        hit = any(p.search(title) for p in compiled)
        if include and not hit:
            logger.info(f"⏩ Skipping event '{title}' – does not match include filter")
            return False
        if exclude and hit:
            logger.info(f"⏩ Skipping event '{title}' – matches exclude filter")
            return False
        return True

    return matches


def _location_allowed(component, import_locations):
    location = str(component.get("LOCATION", "")).replace(" ", "")
    if not import_locations or not location:
        return True
    return any(loc in location.split(",") for loc in import_locations.split(","))


def build_feed_event(component, uid, title, start_utc, all_day, feed_config, now):
    """Turn one feed occurrence into the VEVENT we store in the calendar."""
    emoji_map = feed_config.get("emoji_mapping", {})
    emoji = next(
        (symbol for key, symbol in emoji_map.items() if key != "default" and key in title),
        emoji_map.get("default", "❓"),
    )
    event = new_event(uid, f"{emoji} {title}".strip(), now)

    if all_day:
        start = component.decoded("DTSTART")
        event.add("DTSTART", start)
        end = component.decoded("DTEND") if "DTEND" in component else None
        if isinstance(end, date) and not isinstance(end, datetime) and end > start:
            event.add("DTEND", end)
    else:
        event.add("DTSTART", start_utc)
        if "DTEND" in component:
            end_utc = _as_utc(component.decoded("DTEND"), start_utc.tzinfo)
            if end_utc > start_utc:
                event.add("DTEND", end_utc)

    for prop in ("DESCRIPTION", "LOCATION", "ORGANIZER", "URL"):
        if component.get(prop):
            event[prop] = component[prop]

    categories = apply_category_rules(_categories(component), feed_config.get("categories", {}))
    if categories:
        event.add("CATEGORIES", categories)

    if "calendar_color" in feed_config:
        event.add("COLOR", feed_config["calendar_color"])

    alarms = component.walk("VALARM")
    if alarms:
        for alarm in alarms:
            event.add_component(alarm)
    elif feed_config.get("default_reminder") is not None:
        reminder = feed_config["default_reminder"]
        try:
            event.add_component(display_alarm(parse_alarm(reminder), str(event["SUMMARY"])))
        except ValueError as e:
            logger.warning(f"⚠️ Invalid reminder format '{reminder}': {e}")

    return event


# ---------------------------------------------------------------------------
# Importing
# ---------------------------------------------------------------------------


def save_event(calendar, event, uid, label):
    """Save an event; on 409 Conflict replace the existing copy. Returns True on success."""
    try:
        calendar.save_event(to_ics(event))
        logger.info(f"✅ Created {label}")
        return True
    except Exception as e:
        if "409" not in str(e):
            logger.error(f"❌ Failed to create {label}: {e}")
            return False

    logger.warning(f"⚠️ Event already exists (409 Conflict): {label}. Attempting deduplication.")
    try:
        existing = next((ev for ev in calendar.events() if extract_uid(ev) == uid), None)
        if not existing:
            logger.error(f"❌ Could not find existing event with UID {uid} to deduplicate")
            return False
        existing.delete()
        calendar.save_event(to_ics(event))
        logger.info(f"♻️ Replaced duplicate event {label} after deduplication")
        return True
    except Exception as dedup_error:
        logger.error(f"❌ Deduplication failed for {label}: {dedup_error}")
        return False


COMPARED_TEXT_PROPERTIES = ("SUMMARY", "DESCRIPTION", "LOCATION", "URL", "ORGANIZER", "COLOR")


def event_fingerprint(component, tz):
    """
    The parts of an event that update_existing compares, normalised so that
    equivalent encodings compare equal (UTC vs. local times, a missing DTEND vs.
    the implied one-day end of an all-day event, missing vs. empty text, ...).
    DTSTAMP, CREATED, SEQUENCE and server-added properties are ignored.
    """
    start = component.decoded("DTSTART")
    all_day = not isinstance(start, datetime)

    end = component.decoded("DTEND") if "DTEND" in component else None
    if end is None and "DURATION" in component:
        end = start + component.decoded("DURATION")
    if end is None:
        end = start + timedelta(days=1) if all_day else start

    def norm(value):
        return value if all_day and not isinstance(value, datetime) else _as_utc(value, tz)

    fingerprint = {"start": norm(start), "end": norm(end)}
    for prop in COMPARED_TEXT_PROPERTIES:
        fingerprint[prop.lower()] = str(component.get(prop, "")).strip()
    fingerprint["categories"] = _categories(component)

    alarms = []
    for alarm in component.walk("VALARM"):
        try:
            trigger = alarm.decoded("TRIGGER")
        except (KeyError, ValueError):
            continue
        if isinstance(trigger, datetime):
            trigger = _as_utc(trigger, tz)
        alarms.append((str(alarm.get("ACTION", "")).upper(), str(trigger)))
    fingerprint["alarms"] = sorted(alarms)
    return fingerprint


def changed_fields(existing_component, new_component, tz):
    """Names of the fingerprint fields that differ, or [] if the event is unchanged."""
    try:
        old = event_fingerprint(existing_component, tz)
    except Exception:
        return ["unreadable"]
    new = event_fingerprint(new_component, tz)
    changed = [key for key in new if old.get(key) != new[key]]
    if "COLOR" not in existing_component:
        # Some servers (e.g. mailbox.org) silently drop COLOR. Without this,
        # every event would look changed and be rewritten on every run.
        changed = [key for key in changed if key != "color"]
    return changed


def update_event(existing, event, label):
    """Overwrite an existing calendar object in place. Returns True on success."""
    old = existing.icalendar_component
    if "CREATED" in old:
        event["CREATED"] = old["CREATED"]
    if "SEQUENCE" in old:
        event["SEQUENCE"] = old["SEQUENCE"]  # caldav's save() increments it
    try:
        existing.data = to_ics(event)
        existing.save()
        logger.info(f"🔄 Updated {label}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update {label}: {e}")
        return False


def stale_removal_allowed(config):
    """
    Decide, per feed, whether remove_stale may run. Removal deletes events by
    UID prefix, so it is refused when the feed's prefix is shared with (or is a
    prefix of / prefixed by) another feed's prefix or the global uid_prefix used
    by extra_events -- otherwise it would delete the other source's events.
    Returns a list of booleans parallel to config["ics_feeds"].
    """
    global_prefix = config["uid_prefix"]
    feeds = config.get("ics_feeds", [])
    prefixes = [feed.get("uid_prefix", global_prefix) for feed in feeds]

    def overlaps(a, b):
        return a.startswith(b) or b.startswith(a)

    allowed = []
    for i, feed in enumerate(feeds):
        if not feed.get("remove_stale"):
            allowed.append(False)
            continue
        prefix = prefixes[i]
        others = [global_prefix] + [p for j, p in enumerate(prefixes) if j != i]
        clash = next((other for other in others if overlaps(prefix, other)), None)
        if clash is not None:
            logger.error(
                f"❌ remove_stale disabled for feed {feed['url']}: its uid_prefix '{prefix}' "
                f"overlaps with '{clash}' used by another source. Give the feed a unique uid_prefix."
            )
        allowed.append(clash is None)
    return allowed


def _event_start_utc(event, tz):
    """Start of a calendar (caldav) event as aware UTC datetime, or None if unknown."""
    try:
        return _as_utc(event.icalendar_component.decoded("DTSTART"), tz)
    except Exception:
        return None


def remove_stale_events(calendar_events, uid_prefix, expected_uids, tz, now, window_end, dry_run=False):
    """
    Delete events with `uid_prefix` that start between now and window_end but
    whose UID the feed no longer produces. Events that already started are kept,
    so history is never removed. Returns the number of failed deletions.
    """
    failures = 0
    removed = 0
    for event in calendar_events:
        uid = extract_uid(event)
        if not uid or not uid.startswith(uid_prefix) or uid in expected_uids:
            continue
        start = _event_start_utc(event, tz)
        if start is None or not now <= start <= window_end:
            continue
        summary = event.icalendar_component.get("SUMMARY", uid)
        label = f"'{summary}' on {start.astimezone(tz).date()} (UID {uid})"
        if dry_run:
            logger.info(f"💡 [Dry-run] Would remove stale event {label}")
            removed += 1
            continue
        try:
            event.delete()
            logger.info(f"🧽 Removed stale event {label}")
            removed += 1
        except Exception as e:
            logger.error(f"❌ Could not remove stale event {label}: {e}")
            failures += 1
    if removed:
        logger.info(f"🧹 {'Would remove' if dry_run else 'Removed'} {removed} stale event(s) for prefix {uid_prefix}")
    return failures


def import_ics_feed(
    calendar,
    feed_config,
    uid_prefix,
    existing_uids,
    config=None,
    dry_run=False,
    remove_stale=False,
    calendar_events=None,
):
    """
    Import one ICS feed. Returns the number of events that failed to save,
    update or delete.

    With feed option update_existing=true, events that are already on the
    calendar but whose content changed in the feed (or whose emoji, colour,
    categories or reminder changed in the config) are updated in place.

    With remove_stale=True, events with this feed's prefix that are no longer in
    the feed are removed afterwards (see remove_stale_events). `calendar_events`
    is the list of events already on the calendar; it is fetched if not given.
    """
    config = config or {}
    url = feed_config["url"]
    logger.info(f"📥 Fetching ICS feed: {url}")
    ics_data = fetch_feed(url, feed_config.get("cleanup_regex", []))

    tz = ZoneInfo(config.get("timezone", "Europe/Vienna"))
    now = datetime.now(tz)
    window_start = now - PAST_GRACE
    window_end = now + timedelta(days=config.get("future_event_limit_days", 365))

    title_allowed = _title_filter(feed_config)
    import_locations = feed_config.get("import_locations")
    failures = 0
    expected_uids = set()  # every UID this feed currently produces (after filters)
    update_existing = bool(feed_config.get("update_existing"))
    by_uid = None  # uid -> calendar object, built on first use

    for start_utc, all_day, component in feed_occurrences(ics_data, tz, window_start, window_end):
        day = start_utc.astimezone(tz).date() if not all_day else component.decoded("DTSTART")
        title = str(component.get("SUMMARY") or "Untitled").strip() or "Untitled"

        if not _location_allowed(component, import_locations):
            location = str(component.get("LOCATION", "")).replace(" ", "")
            logger.info(f"⏩ Skipping '{title}' ({day}) due to unmatched location: {location}")
            continue
        if not title_allowed(title):
            continue

        uid = deterministic_uid(uid_prefix, title, start_utc)
        expected_uids.add(uid)
        if uid in existing_uids and not update_existing:
            logger.info(f"⏩ Skipped existing event '{title}' on {day} (UID {uid})")
            continue

        event = build_feed_event(component, uid, title, start_utc, all_day, feed_config, now)
        label = f"event '{event['SUMMARY']}' on {day}"

        if uid in existing_uids:
            if by_uid is None:
                if calendar_events is None:
                    calendar_events = fetch_all_events(calendar)
                by_uid = {}
                for obj in calendar_events:
                    by_uid.setdefault(extract_uid(obj), obj)
            existing = by_uid.get(uid)
            changes = changed_fields(existing.icalendar_component, event, tz) if existing else []
            if not changes:
                logger.info(f"⏩ Skipped unchanged event '{title}' on {day} (UID {uid})")
            elif dry_run:
                logger.info(f"💡 [Dry-run] Would update {label} (changed: {', '.join(changes)})")
            elif not update_event(existing, event, f"{label} (changed: {', '.join(changes)})"):
                failures += 1
            continue

        if dry_run:
            logger.info(f"💡 [Dry-run] Would create {label} (UID {uid})")
        elif not save_event(calendar, event, uid, label):
            failures += 1

    if remove_stale:
        if not expected_uids:
            logger.warning(
                f"⚠️ Not removing stale events for {url}: the feed has no events in the sync "
                "window, which usually means a temporary problem with the feed."
            )
        else:
            if calendar_events is None:
                calendar_events = fetch_all_events(calendar)
            failures += remove_stale_events(
                calendar_events, uid_prefix, expected_uids, tz, now, window_end, dry_run
            )

    return failures
