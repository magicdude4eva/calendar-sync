import argparse
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from colorlog import ColoredFormatter
from caldav import DAVClient
from utils import (
    fetch_all_events,
    get_existing_events,
    import_ics_feed,
    compute_extra_events,
)

LOGFORMAT = "%(log_color)s%(levelname)8s:%(reset)s %(message)s"
formatter = ColoredFormatter(LOGFORMAT)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger("calendar_sync")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent duplicate log lines


def main():
    parser = argparse.ArgumentParser(description="Sync ICS feeds to CalDAV calendar.")
    parser.add_argument("--import", dest="import_events", action="store_true", help="Import events from ICS feeds")
    parser.add_argument(
        "--cleanup",
        nargs="?",
        const=True,
        help="Delete events. Without arguments: cleans up global UID prefix. With comma-separated prefixes: cleans only those prefixes."
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate import without modifying calendar")
    args = parser.parse_args()

    config_path = Path("config.json")
    if not config_path.exists():
        logger.error("❌ config.json not found.")
        return

    with open(config_path, "r") as f:
        config = json.load(f)

    logger.info("Connecting to calendar...")
    client = DAVClient(config["caldav_url"], username=config["username"], password=config["password"])
    calendar = client.calendar(url=config["caldav_url"])
    logger.info(f"Connected to calendar at {calendar.url}")

    # Handle cleanup (multi-prefix support)
    if args.cleanup:
        if isinstance(args.cleanup, str):
            prefixes = [p.strip() for p in args.cleanup.split(",") if p.strip()]
        else:
            prefixes = [config["uid_prefix"]]

        all_events = fetch_all_events(calendar)
        logger.info(f"🧹 Cleaning up events for prefixes: {', '.join(prefixes)}")
        get_existing_events(calendar, prefixes[0], cleanup_mode=True, all_events=all_events, multiple_prefixes=prefixes)

    # Handle imports
    if args.import_events:
        all_events = fetch_all_events(calendar)

        # Collect existing UIDs for all feeds
        existing_uids = set()
        for feed in config["ics_feeds"]:
            feed_prefix = feed.get("uid_prefix", config["uid_prefix"])
            existing_uids.update(get_existing_events(calendar, feed_prefix, cleanup_mode=False, all_events=all_events))

        # Also collect existing UIDs for extra events (global prefix)
        existing_uids.update(get_existing_events(calendar, config["uid_prefix"], cleanup_mode=False, all_events=all_events))

        # Compute and import extra_events (global prefix)
        tz = ZoneInfo(config.get("timezone", "Europe/Vienna"))
        now = datetime.now(tz)
        future_limit_days = config.get("future_event_limit_days", 365)
        until_date = now + timedelta(days=future_limit_days)
        extra_events = compute_extra_events(config, config["uid_prefix"], tz, now, until_date)

        for event in extra_events:
            if event.uid in existing_uids:
                logger.info(f"⏭️ Skipping extra event '{event.name}' (UID {event.uid}) – already exists.")
                continue
            if args.dry_run:
                logger.info(f"💡 [Dry-run] Would create extra event '{event.name}' on {event.begin} (UID {event.uid})")
            else:
                try:
                    calendar.save_event(event.serialize())
                    logger.info(f"✅ Created extra event '{event.name}' on {event.begin}")
                except Exception as e:
                    logger.error(f"❌ Failed to create extra event '{event.name}': {e}")

        # Import ICS feeds (respect per-feed uid_prefix)
        for feed_config in config["ics_feeds"]:
            feed_prefix = feed_config.get("uid_prefix", config["uid_prefix"])
            import_ics_feed(
                calendar,
                feed_config,
                feed_prefix,
                existing_uids,
                config=config,
                dry_run=args.dry_run
            )


if __name__ == "__main__":
    main()
