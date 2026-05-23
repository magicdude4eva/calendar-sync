# utils.py

import hashlib
import logging
import re
import warnings
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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from ics import Calendar, Event, alarm
from ics.alarm import DisplayAlarm
from ics.grammar.parse import ContentLine

# Suppress FutureWarnings from ics package
warnings.filterwarnings("ignore", category=FutureWarning)

logger = logging.getLogger("calendar_sync")


def fetch_all_events(calendar):
    """Fetch all events from the calendar once and reuse for filtering."""
    logger.info("📥 Fetching all events from calendar (once)...")
    events = list(calendar.events())
    logger.info(f"📅 Found {len(events)} events on calendar")
    return events


def extract_uid(event):
    try:
        if hasattr(event, "uid") and event.uid:
            return event.uid
        serialized = (
            event.data.serialize()
            if hasattr(event.data, "serialize")
            else str(event.data)
        )
        match = re.search(r"UID:(.+)", serialized)
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


def expand_yearly_events(event, until_date):
    current_year = datetime.now().year
    end_year = until_date.year
    expanded_dates = [
        event.begin.replace(year=year).datetime
        for year in range(current_year, end_year + 1)
    ]
    logger.debug(f"Expanding yearly event '{event.name}': {expanded_dates}")
    return expanded_dates


def compute_extra_events(config, uid_prefix, tz, now, until_date):
    extra_events = []
    weekday_map = {
        "Sunday": SUNDAY,
        "Monday": MONDAY,
        "Tuesday": TUESDAY,
        "Wednesday": WEDNESDAY,
        "Thursday": THURSDAY,
        "Friday": FRIDAY,
        "Saturday": SATURDAY,
    }

    for entry in config.get("extra_events", []):
        try:
            emoji, rest = entry.split(" ", 1)
            title, rule = rest.split(":")

            # Fixed date like 21.6.fixed
            if re.match(r"^\d{1,2}\.\d{1,2}\.fixed$", rule):
                day, month, _ = rule.split(".")
                day = int(day)
                month = int(month)
                for year in range(now.year, until_date.year + 1):
                    dt = datetime(year, month, day, tzinfo=tz)
                    if now <= dt <= until_date:
                        event = Event()
                        event.name = f"{emoji} {title}".strip()
                        event.begin = dt.date()
                        event.make_all_day()
                        event.uid = deterministic_uid(uid_prefix, title, dt)
                        event.created = now
                        extra_events.append(event)

            # Nth weekday of month like 2.Sunday.5 or -1.Sunday.3
            elif re.match(r"^-?\d+\.[A-Za-z]+\.-?\d+$", rule):
                week, weekday_str, month = rule.split(".")
                weekday = weekday_map.get(weekday_str)
                month = int(month)
                n = int(week)
                for year in range(now.year, until_date.year + 1):
                    cal = monthcalendar(year, month)
                    days = [week[weekday] for week in cal if week[weekday] != 0]
                    if n > 0 and len(days) >= n:
                        day = days[n - 1]
                    elif n < 0 and len(days) >= abs(n):
                        day = days[n]
                    else:
                        continue
                    dt = datetime(year, month, day, tzinfo=tz)
                    if now <= dt <= until_date:
                        event = Event()
                        event.name = f"{emoji} {title}".strip()
                        event.begin = dt.date()
                        event.make_all_day()
                        event.uid = deterministic_uid(uid_prefix, title, dt)
                        event.created = now
                        extra_events.append(event)
            else:
                logger.warning(f"⚠️ Unsupported rule format in extra_event: '{entry}'")

        except Exception as e:
            logger.warning(f"⚠️ Failed to process extra_event '{entry}': {e}")

    return extra_events


def parse_alarm(offset):
    """
    parse the alarm strings like '1d', '10m' into a timedelta
    """

    regex = re.match(r"^(\d+)([dhm])$", offset.lower())

    if not regex:
        raise ("Error, invalid reminder value")

    val = int(regex.group(1))
    unit = regex.group(2)
    if unit == "d":
        return timedelta(days=-val)
    elif unit == "h":
        return timedelta(hours=-val)
    elif unit == "m":
        return timedelta(minutes=-val)


def import_ics_feed(
    calendar, feed_config, uid_prefix, existing_uids, config=None, dry_run=False
):
    url = feed_config["url"]
    logger.info(f"📥 Fetching ICS feed: {url}")
    response = requests.get(url)
    response.raise_for_status()

    ics_data = response.content.decode("utf-8")
    for rule in feed_config.get("cleanup_regex", []):
        pattern = rule["pattern"]
        replacement = rule["replacement"]
        ics_data = re.sub(pattern, replacement, ics_data)

    try:
        cal = Calendar(ics_data)
    except UnicodeDecodeError:
        logger.warning("⚠️ UTF-8 decode failed, falling back to ISO-8859-1")
        cal = Calendar(response.content.decode("iso-8859-1"))

    logger.info(f"📅 Found {len(cal.events)} events in feed")

    tz = ZoneInfo(config.get("timezone", "Europe/Vienna"))
    now = datetime.now(tz)
    future_limit_days = config.get("future_event_limit_days", 365) if config else 365
    until_date = now + timedelta(days=future_limit_days)
    emoji_map = feed_config.get("emoji_mapping", {})
    import_locations = feed_config.get("import_locations", None)

    for event in sorted(cal.events, key=lambda e: e.begin):
        if not event.begin:
            logger.info(f"⏭️ Skipping event '{event.name}' due to missing begin date.")
            continue

        raw_extras = str(event.extra).upper()
        is_yearly = "RRULE:FREQ=YEARLY" in raw_extras

        if is_yearly:
            logger.info(f"🔁 Detected yearly recurring event: {event.name}")
        dates = (
            expand_yearly_events(event, until_date)
            if is_yearly
            else [event.begin.datetime]
        )

        for event_dt in dates:
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=tz)

            if event_dt < now - timedelta(weeks=2):
                logger.info(
                    f"⏩ Skipping event '{event.name}' on {event_dt.date()} – event is in the past."
                )
                continue

            if event_dt > until_date:
                logger.info(
                    f"⏩ Skipping event '{event.name}' on {event_dt.date()} – exceeds future limit."
                )
                continue

            location = (event.location or "").replace(" ", "")
            if import_locations and location:
                if not any(
                    loc in location.split(",") for loc in import_locations.split(",")
                ):
                    logger.info(
                        f"⏩ Skipping '{event.name}' ({event_dt.date()}) due to unmatched location: {location}"
                    )
                    continue

            original_title = (event.name or "Untitled").strip()
            emoji = next(
                (
                    symbol
                    for key, symbol in emoji_map.items()
                    if key != "default" and key in original_title
                ),
                emoji_map.get("default", "❓"),
            )

            emoji_title = f"{emoji} {original_title}".strip()
            uid = deterministic_uid(uid_prefix, original_title, event_dt)

            if uid in existing_uids:
                logger.info(
                    f"⏩ Skipped existing event '{emoji_title}' on {event_dt.date()} (UID {uid})"
                )
                continue

            new_event = Event()
            new_event.name = emoji_title
            new_event.uid = uid
            new_event.created = now
            new_event.description = event.description or ""
            new_event.location = event.location or None
            new_event.organizer = event.organizer or None

            # Handle categories with comprehensive configuration support
            categories = list(event.categories) if event.categories else []

            # Apply category transformations from feed configuration
            categories_config = feed_config.get("categories", {})

            # Replace if empty (useful for events without categories)
            if categories_config.get("replace_if_empty") and not categories:
                categories = categories_config["replace_if_empty"]

            # Prepend categories (add to beginning of list)
            if "prepend" in categories_config:
                categories = categories_config["prepend"] + categories

            # Append categories (add to end of list)
            if "append" in categories_config:
                categories.extend(categories_config["append"])

            # Remove unwanted categories
            if "remove" in categories_config:
                categories = [
                    cat for cat in categories if cat not in categories_config["remove"]
                ]

            # Deduplicate if enabled (default: true)
            if categories_config.get("deduplicate", True):
                seen = set()
                unique_categories = []
                for cat in categories:
                    if cat not in seen:
                        seen.add(cat)
                        unique_categories.append(cat)
                categories = unique_categories

            new_event.categories = categories if categories else None

            # Set event color if configured (RFC 7986 color property)
            if "calendar_color" in feed_config:
                color = feed_config["calendar_color"]
                new_event.extra.append(ContentLine(name="COLOR", value=color))
                logger.debug(f"Set event color to {color} for {new_event.name}")

            new_event.url = event.url or None

            if event.all_day:
                new_event.begin = event_dt.date()
                new_event.make_all_day()
            else:
                new_event.begin = event_dt

            if event.end:
                end_dt = event.end.datetime
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=tz)
                if end_dt > event_dt:
                    new_event.end = end_dt

            if hasattr(event, "alarms") and event.alarms:
                new_event.alarms = list(event.alarms)
            else:
                reminder = feed_config.get("default_reminder", None)
                if reminder is not None:
                    try:
                        reminder_delta = parse_alarm(reminder)
                        new_event.alarms = [DisplayAlarm(trigger=reminder_delta)]
                    except Exception as e:
                        logger.warning(f"⚠️ Invalid reminder format '{reminder}': {e}")

            if dry_run:
                logger.info(
                    f"💡 [Dry-run] Would create event '{emoji_title}' on {event_dt.date()} (UID {uid})"
                )
            else:
                try:
                    calendar.save_event(new_event.serialize())
                    logger.info(
                        f"✅ Created event '{emoji_title}' on {event_dt.date()}"
                    )
                except Exception as e:
                    if "409" in str(e):
                        logger.warning(
                            f"⚠️ Event already exists (409 Conflict): '{emoji_title}' on {event_dt.date()}. Attempting deduplication."
                        )
                        try:
                            existing = next(
                                (
                                    ev
                                    for ev in calendar.events()
                                    if extract_uid(ev) == uid
                                ),
                                None,
                            )
                            if existing:
                                existing.delete()
                                calendar.save_event(new_event.serialize())
                                logger.info(
                                    f"♻️ Replaced duplicate event '{emoji_title}' after deduplication"
                                )
                            else:
                                logger.warning(
                                    f"⚠️ Could not find existing event with UID {uid} to deduplicate"
                                )
                        except Exception as dedup_error:
                            logger.error(
                                f"❌ Deduplication failed for '{emoji_title}': {dedup_error}"
                            )
                    else:
                        logger.error(f"❌ Failed to create event '{emoji_title}': {e}")
