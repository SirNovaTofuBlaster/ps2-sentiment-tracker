"""Offline tests for archive.py: which mentions count as the same mention."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import archive  # noqa: E402


def item(**extra):
    base = {"headline": "Ico is twenty-five", "source": "Example News", "source_type": "news",
            "link": "https://example.com/ico", "matched_game": "Ico", "matched_games": ["Ico"],
            "match_method": "exact", "is_remaster_rumor": False, "sentiment": 70,
            "timestamp": "2026-10-05 09:00 UTC"}
    return {**base, **extra}


def thread(number, started, games=("Ico",), board="vr"):
    """A row as scraper.analyze_thread() writes it: the headline is made from the board and
    the games, so every thread about one game on one board reads the same."""
    names = " and ".join(games)
    return item(headline=f"Thread on /{board}/ naming {names}", source=f"4chan /{board}/", source_type="4chan",
                link=f"https://boards.4chan.org/{board}/thread/{number}", matched_game=games[0],
                matched_games=list(games), sentiment=None, timestamp=started)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="archive-test-"))
        self.snapshot = self.folder / "sentiment_feed.json"
        patches = [mock.patch.object(archive, "SNAPSHOT_PATH", self.snapshot),
                   mock.patch.object(archive, "ARCHIVE_DIR", self.folder / "archive"),
                   mock.patch.object(archive, "INDEX_PATH", self.folder / "archive" / "index.json"),
                   mock.patch.object(archive, "DIGITAL_DIR", self.folder / "archive" / "digital"),
                   mock.patch.object(archive, "DIGITAL_INDEX_PATH", self.folder / "archive" / "digital" / "index.json"),
                   mock.patch("builtins.print")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_with(self, items):
        self.snapshot.write_text(json.dumps({"items": items}), encoding="utf-8")
        archive.archive()
        return json.loads((self.folder / "archive" / "2026-10.json").read_text(encoding="utf-8"))

    def test_a_story_seen_again_is_archived_once(self):
        """The same headline from the same source is one mention, even when a later run sees
        it under another link or time (the reason the link is not part of the key)."""
        self.run_with([item()])
        rows = self.run_with([item(), item(link="https://example.com/ico?utm=1", timestamp="2026-10-06 10:00 UTC")])
        self.assertEqual([(r["g"], r["s"], r["h"], r["d"]) for r in rows],
                         [("Ico", "Example News", "Ico is twenty-five", "2026-10-05 09:00 UTC")])

    def test_two_threads_about_one_game_are_two_mentions(self):
        """Every thread on a board that names a game carries the same generated headline, so
        the headline alone would fold a month of threads into one row."""
        first, second = thread(101, "2026-10-05 09:00 UTC"), thread(202, "2026-10-06 21:30 UTC")
        rows = self.run_with([first, second])
        self.assertEqual([(r["g"], r["h"], r["d"], r["t"]) for r in rows],
                         [("Ico", "Thread on /vr/ naming Ico", "2026-10-05 09:00 UTC", "4chan"),
                          ("Ico", "Thread on /vr/ naming Ico", "2026-10-06 21:30 UTC", "4chan")])
        # Running again adds nothing: a thread's start time never changes.
        self.assertEqual(self.run_with([second, first]), rows)
        # A third thread joins them, and a thread naming two games gives a row for each.
        rows = self.run_with([first, second, thread(303, "2026-10-07 08:15 UTC", games=("Ico", "Okami"))])
        self.assertEqual([(r["g"], r["d"]) for r in rows],
                         [("Ico", "2026-10-05 09:00 UTC"), ("Ico", "2026-10-06 21:30 UTC"),
                          ("Ico", "2026-10-07 08:15 UTC"), ("Okami", "2026-10-07 08:15 UTC")])

    def test_only_what_the_scraper_wrote_is_archived_for_a_thread(self):
        """The archive is permanent, so it must hold nothing a poster wrote: a thread's row is
        the generated headline, the board, the game and how it was matched. It has no mood
        score ("n"): a thread is not scored, and a made-up 50 would be kept for good."""
        rows = self.run_with([thread(101, "2026-10-05 09:00 UTC")])
        self.assertEqual(rows, [{"g": "Ico", "d": "2026-10-05 09:00 UTC", "h": "Thread on /vr/ naming Ico",
                                 "s": "4chan /vr/", "t": "4chan", "r": False, "m": "exact"}])
        # Every other row keeps its score, and a row without one still gets the neutral 50.
        rows = self.run_with([item(), item(headline="Ico again", sentiment=None)])
        self.assertEqual([row["n"] for row in rows if row["t"] == "news"], [70, 50])


class DigitalArchiveTests(unittest.TestCase):
    """Digital-only news, any game, kept for good next to the PS2 mentions."""

    setUp = ArchiveTests.setUp
    run_with = ArchiveTests.run_with

    def digital(self, headline, source="Kotaku", when="2026-10-05 09:00 UTC", **extra):
        return item(headline=headline, source=source, link=f"https://k.example/{len(headline)}", matched_game=None,
                    matched_games=[], is_digital_only=True, timestamp=when, **extra)

    def stored(self, month="2026-10"):
        path = self.folder / "archive" / "digital" / f"{month}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def test_digital_only_stories_are_kept_once_with_their_link_and_counted(self):
        stories = [self.digital("Sony To Ditch Discs"), self.digital("Phantom Blade Zero Confirmed Digital-Only", source="r/playstation",
                                                                      when="2026-10-08 20:00 UTC"),
                   self.digital("Old one", when="2026-09-30 10:00 UTC"), item(headline="Ico news", is_digital_only=False)]
        self.snapshot.write_text(json.dumps({"items": stories}), encoding="utf-8")
        archive.archive()
        archive.archive()   # run again: nothing doubles
        self.assertEqual(self.stored(), [
            {"d": "2026-10-05 09:00 UTC", "h": "Sony To Ditch Discs", "s": "Kotaku", "t": "news", "l": "https://k.example/19"},
            {"d": "2026-10-08 20:00 UTC", "h": "Phantom Blade Zero Confirmed Digital-Only", "s": "r/playstation", "t": "news",
             "l": "https://k.example/41"}])
        self.assertEqual(len(self.stored("2026-09")), 1)
        index = json.loads((self.folder / "archive" / "digital" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual((index["total_stories"], index["months"]), (3, [{"month": "2026-09", "stories": 1}, {"month": "2026-10", "stories": 2}]))
        self.assertEqual(index["days"], {"2026-09-30": 1, "2026-10-05": 1, "2026-10-08": 1})
        self.assertEqual([p.name for p in sorted((self.folder / "archive").glob("*.json"))], ["2026-10.json", "index.json"],
                         "the PS2 archive holds only the PS2 mention, and its index does not see the digital folder")

    def test_stories_stay_after_they_leave_the_snapshot_and_unflagged_or_undated_ones_are_not_kept(self):
        self.snapshot.write_text(json.dumps({"items": [self.digital("Sony To Ditch Discs")]}), encoding="utf-8")
        archive.archive()
        self.snapshot.write_text(json.dumps({"items": [self.digital("Next one", when="not a date"),
                                                       item(headline="Flag missing", matched_game=None, matched_games=[])]}),
                                 encoding="utf-8")
        archive.archive()
        self.assertEqual([row["h"] for row in self.stored()], ["Sony To Ditch Discs"])

    def test_a_story_the_rules_no_longer_flag_leaves_the_archive_once_the_scraper_has_unflagged_it(self):
        self.snapshot.write_text(json.dumps({"items": [self.digital("Physical media show and tell!"), self.digital("Sony To Ditch Discs")]}),
                                 encoding="utf-8")
        archive.archive()
        unflagged = {**self.digital("Physical media show and tell!"), "is_digital_only": False}
        self.snapshot.write_text(json.dumps({"items": [unflagged, self.digital("Sony To Ditch Discs")]}), encoding="utf-8")
        archive.archive()
        self.assertEqual([row["h"] for row in self.stored()], ["Sony To Ditch Discs"])
        index = json.loads((self.folder / "archive" / "digital" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["total_stories"], 1)
        # A story merely gone from the snapshot (older than two weeks) is never removed: tested above.

    def test_a_real_sentiment_of_zero_is_kept_as_zero(self):
        rows = self.run_with([item(sentiment=0), item(headline="No score", sentiment=None)])
        self.assertEqual({row["h"]: row["n"] for row in rows}, {"Ico is twenty-five": 0, "No score": 50})

if __name__ == "__main__":
    unittest.main()
