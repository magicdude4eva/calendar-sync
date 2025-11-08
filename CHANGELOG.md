# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Added
- (Nothing yet)

### Changed
- (Nothing yet)

### Fixed
- (Nothing yet)

---

## [v1.4.1] - 2025-11-01
### Fixed
- Fixed edge cases in yearly event expansion for events spanning multiple years.
- Improved error handling for CalDAV API conflicts during event creation.
- Enhanced logging for deduplication and cleanup operations.

---

## [v1.4.0] - 2025-10-15
### Added
- **Multi-prefix cleanup**: Support for cleaning up events with multiple prefixes in a single command (e.g., `--cleanup MUELL-,F1-`).
- **Emoji mapping for extra events**: Added emoji support for custom extra events defined in `config.json`.

### Changed
- Optimized event deduplication logic to reduce API calls.
- Updated `README.md` with clearer Docker Compose examples and setup instructions.

---

## [v1.3.0] - 2025-09-20
### Added
- **Location-based filtering**: Filter ICS events by location (e.g., regional holidays in Austria) using the `import_locations` config option.
- **Custom extra events**: Added support for defining custom events (e.g., Mother’s Day, Advent Sundays) in `config.json`.

### Changed
- Improved logging for dry-run mode to show more detailed previews.
- Refactored `deterministic_uid` function for better performance and consistency.

---

## [v1.2.0] - 2025-08-10
### Added
- **Dry-run mode**: Simulate imports without modifying the calendar using `--dry-run`.
- **Docker support**: Added `Dockerfile` and `docker-compose.yml` for easy deployment.

### Fixed
- Timezone handling for all-day events to prevent incorrect date shifts.

---

## [v1.1.0] - 2025-07-05
### Added
- **Recurring event support**: Automatic expansion of `RRULE:FREQ=YEARLY` events into individual instances.
- **Emoji mapping**: Map emojis to event names for better readability (e.g., "♻️ Papier").

---

## [v1.0.0] - 2025-06-01
### Added
- **Initial release**: Sync ICS feeds (e.g., holidays, waste collection) to CalDAV calendars.
- Basic import and cleanup functionality.
- Deterministic UID generation for deduplication.
- Configurable UID prefixes and timezone support.

---

[Unreleased]: https://github.com/magicdude4eva/calendar-sync/compare/v1.4.1...HEAD
[v1.4.1]: https://github.com/magicdude4eva/calendar-sync/compare/v1.4.0...v1.4.1
[v1.4.0]: https://github.com/magicdude4eva/calendar-sync/compare/v1.3.0...v1.4.0
[v1.3.0]: https://github.com/magicdude4eva/calendar-sync/compare/v1.2.0...v1.3.0
[v1.2.0]: https://github.com/magicdude4eva/calendar-sync/compare/v1.1.0...v1.2.0
[v1.1.0]: https://github.com/magicdude4eva/calendar-sync/compare/v1.0.0...v1.1.0
[v1.0.0]: https://github.com/magicdude4eva/calendar-sync/releases/tag/v1.0.0
