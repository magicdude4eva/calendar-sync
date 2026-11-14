"""End-to-end tests for calendar_sync.main() with a fake CalDAV server and feeds."""

import json
import sys
from datetime import datetime, timedelta

import pytest

import calendar_sync
import utils
from conftest import TZ, FakeCalendar, make_ics, soon, vevent


@pytest.fixture
def server(monkeypatch):
    """Replace DAVClient so main() talks to an in-memory calendar."""
    cal = FakeCalendar()

    class FakeClient:
        def __init__(self, url, username, password):
            self.args = (url, username, password)

        def calendar(self, url):
            return cal

    monkeypatch.setattr(calendar_sync, "DAVClient", FakeClient)
    return cal


@pytest.fixture
def write_config(tmp_path):
    def write(**overrides):
        config = {
            "caldav_url": "https://dav.example/cal",
            "username": "u",
            "password": "p",
            "uid_prefix": "ICS-",
            "timezone": "Europe/Vienna",
            "ics_feeds": [],
            **overrides,
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        return str(path)

    return write


def main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["calendar_sync.py", *args])
    return calendar_sync.main()


def test_missing_config_exits_1(monkeypatch, tmp_path):
    assert main(monkeypatch, "--import", "--config", str(tmp_path / "nope.json")) == 1


def test_no_action_connects_and_exits_0(monkeypatch, server, write_config):
    assert main(monkeypatch, "--config", write_config()) == 0
    assert server.saved == []


def test_import_feeds_with_per_feed_prefix(monkeypatch, server, feed, write_config):
    feed.serve("https://a", make_ics(vevent("A", soon())))
    feed.serve("https://b", make_ics(vevent("B", soon())))
    config = write_config(ics_feeds=[{"url": "https://a", "uid_prefix": "A-"}, {"url": "https://b"}])
    assert main(monkeypatch, "--import", "--config", config) == 0
    uids = sorted(str(e["UID"]) for e in server.saved_events())
    assert uids[0].startswith("A-") and uids[1].startswith("ICS-")


def test_second_import_creates_nothing(monkeypatch, server, feed, write_config):
    feed.serve("https://a", make_ics(vevent("A", soon())))
    config = write_config(ics_feeds=[{"url": "https://a", "uid_prefix": "A-"}])
    main(monkeypatch, "--import", "--config", config)
    server.persist_saved()
    assert main(monkeypatch, "--import", "--config", config) == 0
    assert server.saved == []


def test_broken_feed_does_not_stop_others_and_exits_1(monkeypatch, server, feed, write_config):
    feed.serve("https://good", make_ics(vevent("Good", soon())))
    config = write_config(ics_feeds=[{"url": "https://unreachable"}, {"url": "https://good"}])
    assert main(monkeypatch, "--import", "--config", config) == 1
    assert [str(e["SUMMARY"]) for e in server.saved_events()] == ["❓ Good"]


def test_dry_run_saves_nothing(monkeypatch, server, feed, write_config):
    feed.serve("https://a", make_ics(vevent("A", soon())))
    config = write_config(ics_feeds=[{"url": "https://a"}], extra_events=["🎃 H:31.10.fixed"])
    assert main(monkeypatch, "--import", "--dry-run", "--config", config) == 0
    assert server.saved == []


def test_extra_events_imported_once(monkeypatch, server, write_config):
    tomorrow = datetime.now(TZ) + timedelta(days=1)
    entry = f"⭐ Tomorrow:{tomorrow.day}.{tomorrow.month}.fixed"
    config = write_config(extra_events=[entry])
    assert main(monkeypatch, "--import", "--config", config) == 0
    [ev] = server.saved_events()
    assert str(ev["SUMMARY"]) == "⭐ Tomorrow"
    assert str(ev["UID"]).startswith("ICS-")

    server.persist_saved()
    assert main(monkeypatch, "--import", "--config", config) == 0
    assert server.saved == []


def test_extra_event_save_failure_exits_1(monkeypatch, server, write_config):
    tomorrow = datetime.now(TZ) + timedelta(days=1)
    server.save_errors = [RuntimeError("500")]
    config = write_config(extra_events=[f"⭐ T:{tomorrow.day}.{tomorrow.month}.fixed"])
    assert main(monkeypatch, "--import", "--config", config) == 1


def test_cleanup_without_argument_uses_global_prefix(monkeypatch, server, write_config):
    server.add("ICS-1", "F1-2", "mine")
    assert main(monkeypatch, "--cleanup", "--config", write_config()) == 0
    assert sorted(utils.extract_uid(e) for e in server.stored) == ["F1-2", "mine"]


def test_cleanup_with_prefix_list(monkeypatch, server, write_config):
    server.add("ICS-1", "F1-2", "MUELL-3", "mine")
    assert main(monkeypatch, "--cleanup", "F1-, MUELL-", "--config", write_config()) == 0
    assert sorted(utils.extract_uid(e) for e in server.stored) == ["ICS-1", "mine"]
