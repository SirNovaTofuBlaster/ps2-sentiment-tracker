"""Offline tests for demand.py: the five signals, the blend, and what is read from a Wikipedia article."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import demand  # noqa: E402

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def stamp(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M UTC")


def item(game, days_ago, feed="reddit:ps2", kind="reddit", views=None):
    row = {"matched_games": [game], "matched_game": game, "timestamp": stamp(days_ago), "feed": feed, "source_type": kind}
    if views is not None:
        row["views"] = views
    return row


class FeedStatsTests(unittest.TestCase):
    def test_mentions_split_into_recent_and_prior_with_sources_and_youtube_views(self):
        items = [item("God Hand", 0.5), item("God Hand", 2, feed="news:a"), item("God Hand", 8, feed="news:b"),
                 item("God Hand", 1, feed="youtube:UC1", kind="youtube", views=5000),
                 item("Kuon", 20), item("Kuon", 5, kind="youtube", feed="youtube:UC1", views=100)]
        stats, any_views = demand.feed_stats(items, NOW)
        god = stats["God Hand"]
        self.assertEqual((god["mentions"], god["recent"], god["prior"], god["last_day"]), (4, 3, 1, 2))
        self.assertEqual(god["sources"], {"reddit:ps2", "news:a", "news:b", "youtube:UC1"})
        self.assertEqual((god["youtube_views"], god["youtube_videos"]), (5000, 1))
        self.assertEqual(stats["Kuon"]["mentions"], 1, "an item older than two weeks is not counted")
        self.assertTrue(any_views)

    def test_without_any_view_count_youtube_is_no_signal(self):
        stats, any_views = demand.feed_stats([item("God Hand", 1, kind="youtube", feed="youtube:UC1")], NOW)
        self.assertFalse(any_views)

    def test_odd_items_are_ignored(self):
        stats, _ = demand.feed_stats(["x", {"timestamp": "nonsense", "matched_game": "A"}, {"matched_games": [], "timestamp": stamp(1)},
                                      {"matched_game": "A", "timestamp": stamp(-3)}], NOW)
        self.assertEqual(stats, {})


class SignalTests(unittest.TestCase):
    def test_momentum_is_neutral_at_the_usual_pace_high_when_rising_low_when_fading(self):
        usual = demand.momentum_score(3, 11)
        self.assertAlmostEqual(usual, 55, delta=6)
        self.assertGreater(demand.momentum_score(30, 11), 95)
        self.assertLess(demand.momentum_score(0, 60), 20)
        self.assertLess(demand.momentum_score(1, 0), 85, "one stray mention is not a surge")
        self.assertTrue(all(0 <= demand.momentum_score(r, p) <= 100 for r in (0, 1, 50) for p in (0, 5, 500)))

    def test_ebay_change_needs_a_week_old_median_and_enough_copies(self):
        entry = {"UK": {"median": 120.0, "copies": 10, "week": {"median": 100.0}},
                 "US": {"median": 90.0, "copies": 2, "week": {"median": 10.0}}}
        self.assertEqual(demand.ebay_change(entry), 20.0, "the US figure has too few copies")
        self.assertIsNone(demand.ebay_change({"UK": {"median": 1, "copies": 9}}))
        self.assertIsNone(demand.ebay_change({"UK": {"unmatched": True}}))
        self.assertIsNone(demand.ebay_change(None))

    def row(self, title, **over):
        row = {"title": title, "mentions": 5, "recent": 2, "prior": 3, "sources": {"a", "b"}, "youtube_views": 0,
               "youtube_videos": 0, "ebay_change_pct": None, "trend_pct": None}
        row.update(over)
        return row

    def test_a_signal_a_game_lacks_is_left_out_not_counted_as_zero(self):
        rows = demand.blend([self.row("A"), self.row("B", ebay_change_pct=20.0, trend_pct=100)], have_youtube=False)
        scores = {r["title"]: r for r in rows}
        self.assertIsNone(scores["A"]["signals"]["ebay"])
        self.assertIsNone(scores["A"]["signals"]["youtube"])
        self.assertEqual(scores["B"]["signals"]["ebay"], 100.0)
        self.assertEqual(scores["B"]["signals"]["wikipedia"], 100.0)
        self.assertGreater(scores["B"]["demand"], scores["A"]["demand"])
        self.assertEqual(scores["A"]["sources"], 2, "the file holds a number, not a set")

    def test_youtube_views_count_on_a_log_scale_once_any_are_seen(self):
        rows = demand.blend([self.row("Viral", youtube_views=1_000_000), self.row("Modest", youtube_views=1_000),
                             self.row("None")], have_youtube=True)
        y = {r["title"]: r["signals"]["youtube"] for r in rows}
        self.assertEqual(y["Viral"], 100.0)
        self.assertTrue(40 < y["Modest"] < 60, y)
        self.assertEqual(y["None"], 0.0)

    def test_the_score_stays_between_0_and_100_and_weights_add_to_one(self):
        self.assertAlmostEqual(sum(demand.SIGNAL_WEIGHTS.values()), 1.0)
        rows = demand.blend([self.row("X", recent=100, prior=0, youtube_views=10**9, ebay_change_pct=500, trend_pct=900),
                             self.row("Y", recent=0, prior=90, ebay_change_pct=-90, trend_pct=-99)], have_youtube=True)
        for row in rows:
            self.assertTrue(0 <= row["demand"] <= 100, row)
        self.assertEqual(rows[0]["title"], "X")


class ArticleTests(unittest.TestCase):
    def test_a_rare_collectible_article_is_recognised(self):
        text = ("Kuon is a survival horror video game for the PlayStation 2 developed by FromSoftware. "
                "The game was a commercial failure, and has since become a rare and sought-after collector's item, "
                "with copies selling for hundreds of dollars on the second-hand market.")
        found = demand.check_article_text(text)
        self.assertTrue(found["game"] and found["ps2"])
        self.assertIn("rare", found["collectible"])
        self.assertLessEqual(len(found["collectible"]), 3)

    def test_gameplay_talk_of_rare_things_is_not_collectibility(self):
        text = ("God Hand is a beat 'em up video game for the PlayStation 2. The player can find rare items dropped by "
                "enemies, and the rare weapon in the final quest sells for a high price in the in-game shop.")
        self.assertEqual(demand.check_article_text(text)["collectible"], [])

    def test_a_sentence_about_value_without_the_market_is_not_enough(self):
        self.assertEqual(demand.collectible_terms("It was a rare achievement for a studio of that size."), [])

    def test_an_article_that_is_not_a_ps2_game_is_told_apart(self):
        general = demand.check_article_text("Retro gaming is the playing of older video games, mainly on consoles of the 1980s.")
        self.assertFalse(general["ps2"])
        self.assertFalse(demand.check_article_text("Ace Combat is a series of games on the Xbox.")["ps2"])
        self.assertTrue(demand.check_article_text("Ace Combat is a video game series. It began on the PS2.")["ps2"])
        self.assertEqual(demand.check_article_text(""), {"game": False, "ps2": False, "collectible": []})

    def test_usable_article_trusts_overrides_then_only_checked_ps2_games(self):
        checks = {"Good": {"article": "Good (video game)", "game": True, "ps2": True},
                  "Retro": {"article": "Retro gaming", "game": False, "ps2": False},
                  "NoPage": {"article": None}}
        resolved = {"Unread": "Unread (video game)"}
        overrides = {"God of War": "God of War (2005 video game)", "Top Gun": None}
        use = lambda title: demand.usable_article(title, checks, resolved, overrides)
        self.assertEqual(use("Good"), "Good (video game)")
        self.assertIsNone(use("Retro"))
        self.assertIsNone(use("NoPage"))
        self.assertEqual(use("God of War"), "God of War (2005 video game)")
        self.assertIsNone(use("Top Gun"))
        self.assertEqual(use("Unread"), "Unread (video game)", "not read yet: the earlier behaviour")
        self.assertIsNone(use("Unknown"))

    def test_checks_come_due_after_a_month(self):
        today = datetime(2026, 10, 14).date()
        self.assertTrue(demand.due_for_check("A", {}, today))
        self.assertFalse(demand.due_for_check("A", {"A": {"checked": "2026-10-01"}}, today))
        self.assertTrue(demand.due_for_check("A", {"A": {"checked": "2026-09-01"}}, today))
        self.assertTrue(demand.due_for_check("A", {"A": {"checked": "garbage"}}, today))


class UpdateChecksTests(unittest.TestCase):
    def test_it_reads_the_due_titles_and_stops_at_the_limit(self):
        texts = {"Kuon (video game)": "Kuon is a video game for the PlayStation 2. Its rare copies fetch high prices on the market.",
                 "Other (video game)": "Other is a video game for the Xbox."}
        with mock.patch.object(demand, "fetch_extract", side_effect=lambda session, article: texts[article]), \
                mock.patch.object(demand, "resolve_article", side_effect=lambda session, title: f"{title} (video game)"), \
                mock.patch.object(demand, "REQUEST_PAUSE", 0), mock.patch.object(demand, "CHECKS_PER_RUN", 2):
            resolved, checks = {}, {"Done": {"article": "x", "checked": datetime.now(timezone.utc).strftime("%Y-%m-%d")}}
            changed = demand.update_checks(None, ["Done", "Kuon", "Other", "Third"], resolved, {}, checks, time_start())
        self.assertTrue(changed)
        self.assertTrue(checks["Kuon"]["ps2"] and "rare" in checks["Kuon"]["collectible"])
        self.assertFalse(checks["Other"]["ps2"])
        self.assertNotIn("Third", checks, "the limit was two")
        self.assertEqual(resolved["Kuon"], "Kuon (video game)")

    def test_a_title_with_no_article_is_recorded_so_it_is_not_searched_again_daily(self):
        with mock.patch.object(demand, "resolve_article", return_value=None), mock.patch.object(demand, "REQUEST_PAUSE", 0):
            resolved, checks = {}, {}
            demand.update_checks(None, ["Ghost"], resolved, {}, checks, time_start())
        self.assertEqual(checks["Ghost"]["article"], None)
        self.assertIn("Ghost", resolved)


def time_start():
    import time
    return time.monotonic()


if __name__ == "__main__":
    unittest.main()
