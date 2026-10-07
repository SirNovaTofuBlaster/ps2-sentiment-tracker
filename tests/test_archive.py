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


if __name__ == "__main__":
    unittest.main()
