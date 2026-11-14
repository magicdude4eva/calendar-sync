import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from caldav import DAVClient
from colorlog import ColoredFormatter

from utils import (
    compute_extra_events,
    fetch_all_events,
    get_existing_events,
    import_ics_feed,
    save_event,
    stale_removal_allowed,
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
    parser.add_argument(
        "--import",
        dest="import_events",
        action="store_true",
        help="Import events from ICS feeds",
    )
    parser.add_argument(
        "--cleanup",
        nargs="?",
        const=True,
        help="Delete events. Without arguments: cleans up global UID prefix. With comma-separated prefixes: cleans only those prefixes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate import without modifying calendar",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to the config file (default: config.json)",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"❌ Config file '{args.config}' not found.")
        return 1

    with open(config_path, "r") as f:
        config = json.load(f)

    logger.info(f"Using config file: {args.config}")
    logger.info("Connecting to calendar...")
    client = DAVClient(
        config["caldav_url"], username=config["username"], password=config["password"]
    )
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
        get_existing_events(
            calendar,
            prefixes[0],
            cleanup_mode=True,
            all_events=all_events,
            multiple_prefixes=prefixes,
        )

    failures = 0

    # Handle imports
    if args.import_events:
        all_events = fetch_all_events(calendar)

        # Collect existing UIDs for all feeds
        existing_uids = set()
        for feed in config["ics_feeds"]:
            feed_prefix = feed.get("uid_prefix", config["uid_prefix"])
            existing_uids.update(
                get_existing_events(
                    calendar, feed_prefix, cleanup_mode=False, all_events=all_events
                )
            )

        # Also collect existing UIDs for extra events (global prefix)
        existing_uids.update(
            get_existing_events(
                calendar,
                config["uid_prefix"],
                cleanup_mode=False,
                all_events=all_events,
            )
        )

        # Compute and import extra_events (global prefix)
        tz = ZoneInfo(config.get("timezone", "Europe/Vienna"))
        now = datetime.now(tz)
        future_limit_days = config.get("future_event_limit_days", 365)
        until_date = now + timedelta(days=future_limit_days)
        extra_events = compute_extra_events(
            config, config["uid_prefix"], tz, now, until_date
        )

        for event in extra_events:
            uid = str(event["UID"])
            label = f"extra event '{event['SUMMARY']}' on {event.decoded('DTSTART')}"
            if uid in existing_uids:
                logger.info(f"⏭️ Skipping {label} (UID {uid}) – already exists.")
            elif args.dry_run:
                logger.info(f"💡 [Dry-run] Would create {label} (UID {uid})")
            elif not save_event(calendar, event, uid, label):
                failures += 1

        # Import ICS feeds (respect per-feed uid_prefix)
        remove_stale = stale_removal_allowed(config)
        failures += sum(
            1 for feed, ok in zip(config["ics_feeds"], remove_stale) if feed.get("remove_stale") and not ok
        )
        for feed_config, feed_remove_stale in zip(config["ics_feeds"], remove_stale):
            feed_prefix = feed_config.get("uid_prefix", config["uid_prefix"])
            # A broken feed must not prevent the remaining feeds from syncing
            try:
                failures += import_ics_feed(
                    calendar,
                    feed_config,
                    feed_prefix,
                    existing_uids,
                    config=config,
                    dry_run=args.dry_run,
                    remove_stale=feed_remove_stale,
                    calendar_events=all_events,
                )
            except Exception as e:
                logger.error(f"❌ Failed to import feed {feed_config.get('url')}: {e}")
                failures += 1

    if failures:
        logger.error(f"❌ Finished with {failures} error(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
