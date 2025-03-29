import argparse
import json
import logging
from pathlib import Path

from colorlog import ColoredFormatter

from caldav import DAVClient
from utils import (
    get_existing_events,
    import_ics_feed
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
    principal = client.principal()
    calendars = principal.calendars()
    calendar = calendars[0]

    logger.info(f"Connected to calendar at {calendar.url}")

    if args.cleanup:
        get_existing_events(calendar, config["uid_prefix"], cleanup_mode=True)

    if args.import_events:
        existing_uids = get_existing_events(calendar, config["uid_prefix"], cleanup_mode=False)
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
