import argparse
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from colorlog import ColoredFormatter
from caldav import DAVClient
from utils import (
    get_existing_events,
    import_ics_feed,
    compute_extra_events,
    deterministic_uid
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
    parser.add_argument("--cleanup", action="store_true", help="Delete all events with matching UID prefix")
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

    if args.cleanup:
        get_existing_events(calendar, config["uid_prefix"], cleanup_mode=True)

    if args.import_events:
        existing_uids = get_existing_events(calendar, config["uid_prefix"], cleanup_mode=False)

        # Compute and import extra_events
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

        # Import ICS feeds
        for feed_config in config["ics_feeds"]:
            import_ics_feed(
                calendar,
                feed_config,
                config["uid_prefix"],
                existing_uids,
                config=config,
                dry_run=args.dry_run
            )

if __name__ == "__main__":
    main()
