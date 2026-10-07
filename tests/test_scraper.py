"""Offline tests for scraper.py, feeds.json and the dashboard script.

Run:  python -m unittest discover -s tests -v
Nothing touches the network: feeds are local fixtures and the PS2 title index is the
built-in fallback list. The dashboard tests need Node.js and are skipped without it."""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ebay_prices  # noqa: E402
import scraper  # noqa: E402

CONFIG_TEXT = (ROOT / "feeds.json").read_text(encoding="utf-8")
CONFIG = json.loads(CONFIG_TEXT)
DASHBOARD_CHECK = ROOT / "tests" / "dashboard_check.mjs"

# The sources that existed before feeds.json. They may be switched off, but removing one
# must be a deliberate decision: update these lists in the same commit.
ORIGINAL_NEWS_FEEDS = [
    "https://www.gematsu.com/feed",
    "https://www.eurogamer.net/feed",
    "https://www.timeextension.com/feed",
    "https://www.pushsquare.com/feeds/latest",
    "https://www.gamespot.com/feeds/mashup/",
    "https://www.pcgamer.com/rss/",
    "https://nintendoeverything.com/feed",
    "https://kotaku.com/rss",
    "https://www.polygon.com/rss/index.xml",
    "https://www.vg247.com/feed",
    "https://www.rockpapershotgun.com/feed/",
    "https://www.destructoid.com/feed/",
    "https://www.nintendolife.com/feeds/latest",
    "https://blog.playstation.com/feed/",
    "https://news.xbox.com/en-us/feed/",
    "https://latam.ign.com/feed.xml",
    "https://www.eurogamer.pt/feed",
    "https://vandal.elespanol.com/xml.cgi",
]
ORIGINAL_SUBREDDIT_GROUPS = [
    ["ps2", "ps2homebrew", "PCSX2", "playstation2"],
    ["gamecollecting", "LimitedPrintGames", "NSCollectors", "Steelbook", "gameverifying",
     "retrogaming", "classicgaming", "emulation", "psx"],
    ["gaming", "Games", "pcgaming", "truegaming", "ShouldIbuythisgame", "gamingsuggestions",
     "pcmasterrace", "NintendoSwitch", "PlayStation", "xboxone", "SteamDeck", "jrpg",
     "patientgamers"],
]

CH1, CH2, CH3, CH4 = ("UC" + c * 22 for c in "abcd")
# Links a browser would "repair" but that aren't valid as written; the scraper and the dashboard
# must both reject them (found in the independent review).
BAD_URLS = {
    "one slash": "https:/example.com/feed",
    "three slashes": "https:///example.com/feed",
    "no slashes": "http:example.com/feed",
    "backslashes": "https:\\\\example.com\\pod.rss",
    "CJK full stop": "https://example。com/feed",
    "percent-encoded dot": "https://example%2Ecom/feed",
    "numeric host": "https://2130706433/feed",
    "space in path": "https://example.com/my feed",
}
NOW = datetime.now(timezone.utc).replace(microsecond=0)


# --- small builders ------------------------------------------------------------

def news(url, name="News", role="press", enabled=True):
    return {"type": "news", "name": name, "url": url, "group": "News", "role": role, "enabled": enabled}


def subreddit(name, group="General", role="community", enabled=True):
    return {"type": "reddit", "name": f"r/{name}", "subreddit": name, "group": group, "role": role, "enabled": enabled}


def youtube(channel_id, name="Channel", role="press", enabled=True):
    return {"type": "youtube", "name": name, "channel_id": channel_id, "group": "YouTube", "role": role, "enabled": enabled}


def youtube_link(channel_url, name="Linked Channel", role="press", enabled=True):
    return {"type": "youtube", "name": name, "channel_url": channel_url, "group": "YouTube", "role": role, "enabled": enabled}


def podcast(url, name="Show", role="press", enabled=True):
    return {"type": "podcast", "name": name, "url": url, "group": "Podcasts", "role": role, "enabled": enabled}


def make_config(*sources, **extra):
    roles = {name: {"label": name, "weight": weight} for name, weight in
             [("official", 1), ("press", 1), ("community", 1), ("ps2", 1.5), ("retro", 1), ("collector", 0.5), ("creator", 0.5)]}
    return {"version": 1, "roles": roles, "sources": list(sources), **extra}


def rss(title, items):
    """items: (title, link or None, enclosure URL or None, datetime)"""
    parts = []
    for item_title, link, enclosure, when in items:
        parts.append("<item><title>" + item_title + "</title>"
                     + (f"<link>{link}</link>" if link else "")
                     + (f"<enclosure url=\"{enclosure}\" type=\"audio/mpeg\" length=\"1\"/>" if enclosure else "")
                     + f"<pubDate>{format_datetime(when)}</pubDate></item>")
    return f"<?xml version=\"1.0\"?><rss version=\"2.0\"><channel><title>{title}</title>{''.join(parts)}</channel></rss>"


def atom(title, entries):
    """entries: (title, link, datetime, category or None)"""
    parts = []
    for entry_title, link, when, category in entries:
        parts.append("<entry><title>" + entry_title + "</title>"
                     + f"<link rel=\"alternate\" href=\"{link}\"/>"
                     + (f"<category term=\"{category}\" label=\"r/{category}\"/>" if category else "")
                     + f"<published>{when.isoformat()}</published><updated>{when.isoformat()}</updated></entry>")
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><feed xmlns=\"http://www.w3.org/2005/Atom\">"
            f"<title>{title}</title>{''.join(parts)}</feed>")


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} Client Error", response=response)


# --- feeds.json ------------------------------------------------------------------

class FeedsFileTests(unittest.TestCase):
    def test_feeds_json_is_valid(self):
        self.assertEqual(scraper.validate_config(CONFIG), [])

    def test_original_news_feeds_are_kept(self):
        urls = {s["url"] for s in CONFIG["sources"] if s["type"] == "news"}
        self.assertEqual([url for url in ORIGINAL_NEWS_FEEDS if url not in urls], [])

    def test_original_subreddits_are_kept(self):
        names = {s["subreddit"] for s in CONFIG["sources"] if s["type"] == "reddit"}
        missing = [name for group in ORIGINAL_SUBREDDIT_GROUPS for name in group if name not in names]
        self.assertEqual(missing, [])

    def test_source_keys_are_unique(self):
        keys = [scraper.source_key(s) for s in CONFIG["sources"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_file_is_canonically_formatted(self):
        # The dashboard writes the file back with JSON.stringify(config, null, 2); keeping
        # this exact format means a save from the page only shows the real changes.
        self.assertEqual(CONFIG_TEXT, json.dumps(CONFIG, indent=2, ensure_ascii=False) + "\n")

    def test_measured_stats_are_dated(self):
        # Sources added later from the dashboard may have no stats; any stats present must say when.
        for src in CONFIG["sources"]:
            if "stats" in src:
                self.assertRegex(src["stats"].get("checked", ""), r"^\d{4}-\d{2}-\d{2}$", src["name"])


# --- validation ------------------------------------------------------------------

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config(news("https://example.com/feed"), subreddit("ps2"), youtube(CH1),
                                  podcast("https://example.com/pod.rss"), poll_every_hours={"podcast": 6})

    def problems_after(self, change):
        config = copy.deepcopy(self.config)
        change(config)
        return scraper.validate_config(config)

    def test_valid_config_has_no_problems(self):
        self.assertEqual(scraper.validate_config(self.config), [])

    def test_rejects_bad_values(self):
        cases = {
            "url": lambda c: c["sources"][0].update(url="not a url"),
            "ftp url": lambda c: c["sources"][3].update(url="ftp://example.com/pod.rss"),
            **{f"url {name}": (lambda url: lambda c: c["sources"][0].update(url=url))(url) for name, url in BAD_URLS.items()},
            "role as a list": lambda c: c["sources"][0].update(role=["press"]),
            "huge interval": lambda c: c["poll_every_hours"].update(podcast=10 ** 400),
            "null intervals": lambda c: c.update(poll_every_hours=None),
            "channel id": lambda c: c["sources"][2].update(channel_id="UCshort"),
            "subreddit": lambda c: c["sources"][1].update(subreddit="bad name"),
            "missing group": lambda c: c["sources"][1].update(group=" "),
            "unknown role": lambda c: c["sources"][0].update(role="nope"),
            "weight too big": lambda c: c["sources"][0].update(weight=11),
            "weight as text": lambda c: c["sources"][0].update(weight="1"),
            "weight as bool": lambda c: c["sources"][0].update(weight=True),
            "role weight": lambda c: c["roles"]["press"].update(weight="heavy"),
            "enabled as text": lambda c: c["sources"][0].update(enabled="yes"),
            "empty name": lambda c: c["sources"][0].update(name=""),
            "unknown type": lambda c: c["sources"][0].update(type="tiktok"),
            "duplicate": lambda c: c["sources"].append(copy.deepcopy(c["sources"][0])),
            "interval 0": lambda c: c["poll_every_hours"].update(podcast=0),
            "interval 1.5": lambda c: c["poll_every_hours"].update(podcast=1.5),
            "interval type": lambda c: c["poll_every_hours"].update(tiktok=1),
            "youtube without id or link": lambda c: c["sources"][2].pop("channel_id"),
            "youtube video link": lambda c: c["sources"].append(youtube_link("https://www.youtube.com/watch?v=abc")),
            "youtube link not normalised": lambda c: c["sources"].append(youtube_link("youtube.com/@IGN")),
            "youtube link with a path": lambda c: c["sources"].append(youtube_link("https://www.youtube.com/@IGN/videos")),
            "bad id next to a good link": lambda c: c["sources"][2].update(channel_id="nope", channel_url="https://www.youtube.com/@IGN"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assertTrue(self.problems_after(change))

    def test_youtube_channel_links_are_accepted(self):
        for link in ("https://www.youtube.com/@IGN", "https://www.youtube.com/c/IGN", "https://www.youtube.com/user/IGNentertainment"):
            with self.subTest(link):
                self.assertEqual(self.problems_after(lambda c: c["sources"].append(youtube_link(link))), [])
        self.assertEqual(scraper.source_key(youtube_link("https://www.youtube.com/@IGN")), "youtube:https://www.youtube.com/@ign")

    def test_load_config_exits_with_a_message_on_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feeds.json"
            path.write_text(json.dumps(make_config(news("nope"))), encoding="utf-8")
            with mock.patch.object(scraper, "FEEDS_PATH", path), self.assertRaises(SystemExit) as raised:
                scraper.load_config()
        self.assertIn("invalid url", str(raised.exception))


# --- building the fetch plan -----------------------------------------------------------

class BuildJobsTests(unittest.TestCase):
    def test_original_reddit_groups_become_the_original_multireddit_urls(self):
        sources = [subreddit(name, group=f"group {i}") for i, group in enumerate(ORIGINAL_SUBREDDIT_GROUPS) for name in group]
        urls = [job["url"] for job in scraper.build_jobs(make_config(*sources))]
        self.assertEqual(urls, [f"https://www.reddit.com/r/{'+'.join(group)}/.rss?limit=50" for group in ORIGINAL_SUBREDDIT_GROUPS])

    def test_disabled_sources_are_not_fetched(self):
        config = make_config(news("https://a.example/feed"), news("https://b.example/feed", enabled=False),
                             subreddit("ps2", enabled=False), youtube(CH1, enabled=False))
        self.assertEqual([job["url"] for job in scraper.build_jobs(config)], ["https://a.example/feed"])

    def test_core_feeds_come_first_and_groups_keep_their_order(self):
        config = make_config(podcast("https://p.example/rss"), youtube(CH1), subreddit("a", group="G1"),
                             news("https://n.example/feed"), subreddit("b", group="G2"), subreddit("c", group="G1"))
        jobs = scraper.build_jobs(config)
        self.assertEqual([job["type"] for job in jobs], ["news", "reddit", "reddit", "youtube", "podcast"])
        self.assertEqual(jobs[1]["url"], "https://www.reddit.com/r/a+c/.rss?limit=50")
        self.assertEqual(jobs[2]["url"], "https://www.reddit.com/r/b/.rss?limit=50")
        self.assertEqual(jobs[3]["url"], f"https://www.youtube.com/feeds/videos.xml?channel_id={CH1}")

    def test_youtube_links_wait_for_their_channel_id(self):
        config = make_config(youtube_link("https://www.youtube.com/@Some"))
        self.assertEqual(scraper.build_jobs(config), [])
        jobs = scraper.build_jobs(config, {"https://www.youtube.com/@some": CH2})
        self.assertEqual([job["url"] for job in jobs], [f"https://www.youtube.com/feeds/videos.xml?channel_id={CH2}"])


class ScheduleTests(unittest.TestCase):
    config = make_config(poll_every_hours={"news": 1, "reddit": 1, "youtube": 1, "podcast": 6})
    now = datetime(2026, 1, 1, 13, 17, tzinfo=timezone.utc)

    def due_after(self, **elapsed):
        last = (self.now - timedelta(**elapsed)).strftime(scraper.TIMESTAMP_FORMAT)
        with mock.patch.dict(os.environ, {"FULL_RUN": ""}):
            return scraper.due_types(self.config, self.now, {"podcast": last})

    def test_podcasts_wait_for_their_interval(self):
        self.assertEqual(self.due_after(hours=2), {"news", "reddit", "youtube"})
        self.assertEqual(self.due_after(hours=5, minutes=30), {"news", "reddit", "youtube"})
        self.assertEqual(self.due_after(hours=5, minutes=45), set(scraper.SOURCE_TYPES))  # within the tolerance
        self.assertEqual(self.due_after(days=3), set(scraper.SOURCE_TYPES))  # GitHub skipped many runs

    def test_never_fetched_or_unreadable_state_means_due(self):
        with mock.patch.dict(os.environ, {"FULL_RUN": ""}):
            self.assertEqual(scraper.due_types(self.config, self.now, {}), set(scraper.SOURCE_TYPES))
            self.assertEqual(scraper.due_types(self.config, self.now, {"podcast": "garbage"}), set(scraper.SOURCE_TYPES))

    def test_full_run_fetches_everything(self):
        last = self.now.strftime(scraper.TIMESTAMP_FORMAT)
        with mock.patch.dict(os.environ, {"FULL_RUN": "1"}):
            self.assertEqual(scraper.due_types(self.config, self.now, {"podcast": last}), set(scraper.SOURCE_TYPES))

    def test_missing_interval_means_every_hour(self):
        with mock.patch.dict(os.environ, {"FULL_RUN": ""}):
            self.assertEqual(scraper.due_types(make_config(), NOW), set(scraper.SOURCE_TYPES))


# --- entry helpers ---------------------------------------------------------------

class EntryHelperTests(unittest.TestCase):
    def test_podcast_without_episode_link_uses_the_audio_file(self):
        feed = feedparser.parse(rss("Show", [("Ep", None, "https://cdn.example/ep.mp3", NOW)]))
        self.assertEqual(scraper.entry_link(feed.entries[0], "podcast"), "https://cdn.example/ep.mp3")
        self.assertEqual(scraper.entry_link(feed.entries[0], "news"), "#")

    def test_extra_feeds_are_sorted_newest_first_but_news_order_is_kept(self):
        oldest_first = rss("Show", [("old", None, None, NOW - timedelta(days=2)), ("new", None, None, NOW)])
        feed = feedparser.parse(oldest_first)
        self.assertEqual([e.title for e in scraper.select_entries(feed, "podcast")], ["new", "old"])
        self.assertEqual([e.title for e in scraper.select_entries(feed, "news")], ["old", "new"])

    def test_labels_and_keys(self):
        feed = feedparser.parse(atom("posts", [("Hi", "https://www.reddit.com/r/PCSX2/comments/1/hi/", NOW, "PCSX2")]))
        reddit_job = {"type": "reddit", "sources": [subreddit("PCSX2")]}
        self.assertEqual(scraper.entry_source(feed.entries[0], feed, reddit_job), "r/PCSX2")
        self.assertEqual(scraper.entry_feed_key(feed.entries[0], reddit_job), "reddit:pcsx2")
        yt_job = {"type": "youtube", "sources": [youtube(CH1, name="Some Channel")]}
        self.assertEqual(scraper.entry_source(feed.entries[0], feed, yt_job), "YouTube: Some Channel")
        self.assertEqual(scraper.entry_feed_key(feed.entries[0], yt_job), f"youtube:{CH1}")

    def test_ps2_sources_give_ps2_context_to_ambiguous_titles(self):
        matcher = scraper.TitleMatcher(scraper.FALLBACK_TITLES)
        self.assertIsNone(matcher.match("Black is still great")[0])
        self.assertEqual(matcher.match("Black is still great", ps2_source=True)[0], "Black")
        self.assertEqual(matcher.match("Black on PS2 is still great")[0], "Black")


class StatusTests(unittest.TestCase):
    def test_latest_only_moves_forward(self):
        status = {}
        scraper.record_success(status, "k", "2026-09-01 10:00 UTC")
        scraper.record_success(status, "k", None)
        scraper.record_success(status, "k", "2026-08-01 10:00 UTC")
        self.assertEqual(status["k"], {"ok": True, "latest": "2026-09-01 10:00 UTC"})

    def test_failing_since_survives_repeated_failures_and_resets_after_success(self):
        status = {}
        scraper.record_success(status, "k", "2026-09-01 10:00 UTC")
        scraper.record_failure(status, "k", "HTTP 404", "2026-09-02 10:00 UTC")
        scraper.record_failure(status, "k", "HTTP 500", "2026-09-03 10:00 UTC")
        self.assertEqual(status["k"], {"ok": False, "error": "HTTP 500", "failing_since": "2026-09-02 10:00 UTC",
                                       "latest": "2026-09-01 10:00 UTC"})
        scraper.record_success(status, "k", None)
        scraper.record_failure(status, "k", "HTTP 404", "2026-09-04 10:00 UTC")
        self.assertEqual(status["k"]["failing_since"], "2026-09-04 10:00 UTC")

    def test_error_labels_are_short_and_stable(self):
        self.assertEqual(scraper.feed_error(http_error(404)), "HTTP 404")
        self.assertEqual(scraper.feed_error(requests.ConnectionError("boom")), "ConnectionError")
        self.assertEqual(scraper.feed_error(ValueError("unreadable feed")), "unreadable feed")


# --- whole runs against fixture feeds -------------------------------------------------

class RunScraperTests(unittest.TestCase):
    NEWS_URL = "https://news.example/feed"
    POD_URL = "https://pod.example/rss"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.fetched, self.failures = [], {}
        self.config = make_config(
            news(self.NEWS_URL),
            subreddit("ps2", group="PS2", role="ps2"), subreddit("PCSX2", group="PS2", role="ps2"),
            subreddit("gaming", group="General"),
            youtube(CH1, name="PS2 Channel", role="ps2"), youtube(CH2, name="Disabled Channel", enabled=False),
            podcast(self.POD_URL, name="Retro Show", role="retro"),
        )
        hour = timedelta(hours=1)
        self.fixtures = {
            self.NEWS_URL: rss("Example News", [("Silent Hill 2 remake announced", "https://news.example/sh2", None, NOW - hour),
                                                ("Unrelated news", "https://news.example/other", None, NOW - 2 * hour)]),
            "https://www.reddit.com/r/ps2+PCSX2/.rss?limit=50": atom("posts", [
                ("Black is still great", "https://www.reddit.com/r/ps2/comments/1/black/", NOW - hour, "ps2"),
                ("PCSX2 settings help", "https://www.reddit.com/r/PCSX2/comments/2/help/", NOW - 3 * hour, "PCSX2")]),
            "https://www.reddit.com/r/gaming/.rss?limit=50": atom("posts", [
                ("Black is still great", "https://www.reddit.com/r/gaming/comments/3/black/", NOW - hour, "gaming")]),
            f"https://www.youtube.com/feeds/videos.xml?channel_id={CH1}": atom("PS2 Channel", [
                ("Black - full playthrough", "https://www.youtube.com/watch?v=abc123", NOW - hour, None)]),
            self.POD_URL: rss("Retro Show", [  # oldest first, no episode links
                ("Episode 1", None, "https://cdn.example/ep1.mp3", NOW - timedelta(days=3)),
                ("Episode 2: Okami", None, "https://cdn.example/ep2.mp3", NOW - timedelta(days=1))]),
        }
        data_dir = self.tmp / "data"
        paths = {"DATA_DIR": data_dir, "DB_PATH": data_dir / "ps2_database.json",
                 "OUTPUT_PATH": data_dir / "sentiment_feed.json", "STATUS_PATH": data_dir / "feed_status.json",
                 "YOUTUBE_IDS_PATH": data_dir / "youtube_channels.json", "POLL_STATE_PATH": data_dir / "poll_state.json",
                 "FEEDS_PATH": self.tmp / "feeds.json"}
        for name, value in paths.items():
            patcher = mock.patch.object(scraper, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (mock.patch.object(scraper, "fetch_feed", side_effect=self.fake_fetch),
                        mock.patch.object(scraper, "load_ps2_titles", return_value=scraper.FALLBACK_TITLES),
                        mock.patch.dict(os.environ, {"FULL_RUN": "1"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_fetch(self, session, url, retry_rate_limit=True):
        self.fetched.append((url, retry_rate_limit))
        if url in self.failures:
            raise self.failures[url]
        return feedparser.parse(self.fixtures[url])

    def run_scraper(self):
        scraper.FEEDS_PATH.write_text(json.dumps(self.config), encoding="utf-8")
        with mock.patch("builtins.print"):
            scraper.run_scraper()
        output = json.loads(scraper.OUTPUT_PATH.read_text(encoding="utf-8"))
        status = json.loads(scraper.STATUS_PATH.read_text(encoding="utf-8"))
        return output, status

    def item(self, output, headline, source):
        return next(i for i in output["items"] if i["headline"] == headline and i["source"] == source)

    def test_all_source_types_end_up_in_the_snapshot(self):
        output, status = self.run_scraper()
        self.assertEqual(output["total_tracked_feeds"], 6)  # enabled sources; each subreddit counts once
        news_item = self.item(output, "Silent Hill 2 remake announced", "Example News")
        self.assertEqual((news_item["source_type"], news_item["feed"]), ("news", self.NEWS_URL))
        self.assertEqual(news_item["matched_game"], "Silent Hill 2")
        self.assertTrue(news_item["is_remaster_rumor"])
        video = self.item(output, "Black - full playthrough", "YouTube: PS2 Channel")
        self.assertEqual((video["source_type"], video["feed"], video["link"]),
                         ("youtube", f"youtube:{CH1}", "https://www.youtube.com/watch?v=abc123"))
        episode = self.item(output, "Episode 2: Okami", "Podcast: Retro Show")
        self.assertEqual((episode["source_type"], episode["feed"], episode["link"], episode["matched_game"]),
                         ("podcast", self.POD_URL, "https://cdn.example/ep2.mp3", "Okami"))
        self.assertEqual(self.item(output, "PCSX2 settings help", "r/PCSX2")["feed"], "reddit:pcsx2")
        self.assertEqual(set(status), {self.NEWS_URL, "reddit:ps2", "reddit:pcsx2", "reddit:gaming",
                                       f"youtube:{CH1}", self.POD_URL})
        self.assertTrue(all(entry["ok"] for entry in status.values()))
        self.assertEqual(status["reddit:ps2"]["latest"], (NOW - timedelta(hours=1)).strftime(scraper.TIMESTAMP_FORMAT))

    def test_ps2_role_decides_ambiguous_matches(self):
        output, _ = self.run_scraper()
        self.assertEqual(self.item(output, "Black is still great", "r/ps2")["matched_game"], "Black")
        self.assertIsNone(self.item(output, "Black is still great", "r/gaming")["matched_game"])
        self.assertEqual(self.item(output, "Black - full playthrough", "YouTube: PS2 Channel")["matched_game"], "Black")

    def test_disabled_sources_are_never_fetched_and_extras_skip_rate_limit_waits(self):
        self.run_scraper()
        urls = [url for url, _ in self.fetched]
        self.assertNotIn(f"https://www.youtube.com/feeds/videos.xml?channel_id={CH2}", urls)
        retries = {url: retry for url, retry in self.fetched}
        self.assertTrue(retries[self.NEWS_URL])
        self.assertFalse(retries[self.POD_URL])

    def test_youtube_failure_is_reported_but_does_not_abort(self):
        self.failures[f"https://www.youtube.com/feeds/videos.xml?channel_id={CH1}"] = http_error(404)
        output, status = self.run_scraper()
        self.assertEqual(status[f"youtube:{CH1}"]["error"], "HTTP 404")
        self.assertFalse(status[f"youtube:{CH1}"]["ok"])
        self.item(output, "Silent Hill 2 remake announced", "Example News")  # the rest was still saved

    def test_mostly_failed_core_run_aborts_and_keeps_the_previous_snapshot(self):
        for url in list(self.fixtures)[:3]:  # the news feed and both Reddit groups
            self.failures[url] = requests.ConnectionError("down")
        scraper.FEEDS_PATH.write_text(json.dumps(self.config), encoding="utf-8")
        with mock.patch("builtins.print"), self.assertRaises(SystemExit):
            scraper.run_scraper()
        self.assertFalse(scraper.OUTPUT_PATH.exists())
        self.assertFalse(scraper.STATUS_PATH.exists())

    def test_a_host_that_keeps_failing_is_skipped(self):
        channels = [youtube(channel_id, name=f"Channel {i}") for i, channel_id in enumerate((CH1, CH2, CH3, CH4))]
        self.config["sources"] = [s for s in self.config["sources"] if s["type"] != "youtube"] + channels
        for channel in channels:
            self.failures[f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"] = requests.ConnectionError("down")
        _, status = self.run_scraper()
        youtube_calls = [url for url, _ in self.fetched if "youtube.com" in url]
        self.assertEqual(len(youtube_calls), scraper.HOST_FAILURE_LIMIT)
        self.assertNotIn(f"youtube:{CH4}", status)  # skipped, not marked as failing

    def test_quiet_rerun_leaves_both_files_untouched(self):
        self.run_scraper()
        before = (scraper.OUTPUT_PATH.stat().st_mtime_ns, scraper.STATUS_PATH.stat().st_mtime_ns)
        self.run_scraper()
        self.assertEqual((scraper.OUTPUT_PATH.stat().st_mtime_ns, scraper.STATUS_PATH.stat().st_mtime_ns), before)

    def test_youtube_link_is_resolved_once_and_remembered(self):
        link = "https://www.youtube.com/@RetroLink"
        self.config["sources"].append(youtube_link(link, name="Retro Link", role="retro"))
        self.fixtures[f"https://www.youtube.com/feeds/videos.xml?channel_id={CH3}"] = atom("Retro Link", [
            ("Okami retrospective", "https://www.youtube.com/watch?v=okami1", NOW - timedelta(hours=2), None)])
        with mock.patch.object(scraper, "fetch_channel_id", return_value=CH3) as lookup:
            output, status = self.run_scraper()
            self.assertEqual(json.loads(scraper.YOUTUBE_IDS_PATH.read_text(encoding="utf-8")), {link.lower(): CH3})
            self.fixtures[self.NEWS_URL] = rss("Example News", [("Another story", "https://news.example/2", None, NOW)])
            self.run_scraper()
        self.assertEqual(lookup.call_count, 1)  # the second run used the remembered ID
        video = self.item(output, "Okami retrospective", "YouTube: Retro Link")
        self.assertEqual((video["feed"], video["matched_game"]), (f"youtube:{link.lower()}", "Okami"))
        self.assertTrue(status[f"youtube:{link.lower()}"]["ok"])

    def test_unresolvable_youtube_link_is_reported_and_skipped(self):
        link = "https://www.youtube.com/@NoSuchChannel"
        self.config["sources"].append(youtube_link(link))
        with mock.patch.object(scraper, "fetch_channel_id", side_effect=http_error(404)):
            _, status = self.run_scraper()
        self.assertEqual(status[f"youtube:{link.lower()}"]["error"], "channel link: HTTP 404")
        self.assertFalse(scraper.YOUTUBE_IDS_PATH.exists())  # failures aren't remembered

    def test_youtube_link_to_an_already_listed_channel_is_not_fetched_twice(self):
        link = "https://www.youtube.com/@SameAsCh1"
        self.config["sources"].append(youtube_link(link))
        with mock.patch.object(scraper, "fetch_channel_id", return_value=CH1):
            _, status = self.run_scraper()
        self.assertEqual(status[f"youtube:{link.lower()}"]["error"], "already listed as PS2 Channel")
        youtube_calls = [url for url, _ in self.fetched if CH1 in url]
        self.assertEqual(len(youtube_calls), 1)

    def test_podcast_episodes_sharing_one_link_stay_separate(self):
        # e.g. The Besties: every episode links to the show's homepage.
        episodes = [(f"Episode {n}", "https://show.example/", f"https://cdn.example/ep{n}.mp3", NOW - timedelta(days=n))
                    for n in range(1, 4)]
        self.fixtures[self.POD_URL] = rss("Retro Show", episodes)
        output, _ = self.run_scraper()
        links = sorted(i["link"] for i in output["items"] if i["source"] == "Podcast: Retro Show")
        self.assertEqual(links, [f"https://cdn.example/ep{n}.mp3" for n in range(1, 4)])

    def test_dead_feeds_do_not_make_a_host_look_down(self):
        channels = [youtube(channel_id, name=f"Channel {i}") for i, channel_id in enumerate((CH1, CH2, CH3, CH4))]
        self.config["sources"] = [s for s in self.config["sources"] if s["type"] != "youtube"] + channels
        for channel_id in (CH1, CH2, CH3):
            self.failures[f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"] = http_error(404)
        self.fixtures[f"https://www.youtube.com/feeds/videos.xml?channel_id={CH4}"] = atom("Channel 3", [
            ("A live channel", "https://www.youtube.com/watch?v=live1", NOW - timedelta(hours=1), None)])
        output, status = self.run_scraper()
        self.assertTrue(status[f"youtube:{CH4}"]["ok"])
        self.item(output, "A live channel", "YouTube: Channel 3")

    def test_slow_source_types_wait_for_their_interval_between_runs(self):
        self.config["poll_every_hours"] = {"podcast": 6}
        with mock.patch.dict(os.environ, {"FULL_RUN": ""}):
            self.run_scraper()
            first = [url for url, _ in self.fetched]
            self.assertIn(self.POD_URL, first)
            self.assertIn("podcast", json.loads(scraper.POLL_STATE_PATH.read_text(encoding="utf-8")))
            self.fetched.clear()
            self.run_scraper()
        second = [url for url, _ in self.fetched]
        self.assertNotIn(self.POD_URL, second)  # polled minutes ago
        self.assertIn(self.NEWS_URL, second)

    def test_feeds_json_saved_with_a_bom_still_loads(self):
        scraper.FEEDS_PATH.write_text(json.dumps(self.config), encoding="utf-8-sig")
        with mock.patch("builtins.print"):
            scraper.run_scraper()
        self.assertTrue(scraper.OUTPUT_PATH.exists())

    def test_the_snapshot_holds_two_weeks_and_its_ceiling_drops_the_oldest_first(self):
        def earlier(days):
            return {"headline": f"Story from {days} days ago", "source": "Example News", "source_type": "news",
                    "link": f"https://news.example/old-{days}", "matched_game": None, "is_remaster_rumor": False,
                    "sentiment": 50, "timestamp": (NOW - timedelta(days=days)).strftime(scraper.TIMESTAMP_FORMAT)}

        def ages(output):
            return [item["headline"] for item in output["items"] if item["headline"].startswith("Story from")]

        scraper.DATA_DIR.mkdir(parents=True, exist_ok=True)
        scraper.OUTPUT_PATH.write_text(json.dumps({"items": [earlier(days) for days in (20, 1, 13.9, 14.1, 5)]}), encoding="utf-8")
        output, _ = self.run_scraper()
        self.assertEqual(ages(output), ["Story from 1 days ago", "Story from 5 days ago", "Story from 13.9 days ago"],
                         "two weeks are kept, newest first; anything older is dropped")
        fetched = len(output["items"]) - 3
        self.assertGreater(fetched, 0)
        stamps = [item["timestamp"] for item in output["items"]]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

        # Past the ceiling it is the oldest items that go, never the ones just collected.
        self.fixtures[self.NEWS_URL] = rss("Example News", [("Brand new story", "https://news.example/new", None, NOW)])
        with mock.patch.object(scraper, "MAX_ITEMS", fetched + 2):
            output, _ = self.run_scraper()
        self.assertEqual(len(output["items"]), fetched + 2)
        self.assertEqual(output["items"][0]["headline"], "Brand new story")
        self.assertEqual(ages(output), ["Story from 1 days ago"])

        # The ceiling is a safety net: two weeks of a busy day (about 750 items) must fit under it.
        self.assertGreaterEqual(scraper.MAX_ITEMS, scraper.RETENTION_DAYS * 750)

    def test_status_of_removed_sources_is_dropped(self):
        self.run_scraper()
        self.config["sources"] = [s for s in self.config["sources"] if s["type"] != "podcast"]
        self.fixtures[self.NEWS_URL] = rss("Example News", [("Brand new story", "https://news.example/new", None, NOW)])
        _, status = self.run_scraper()
        self.assertNotIn(self.POD_URL, status)


# --- dashboard (index.html) ----------------------------------------------------------

@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
class DashboardTests(unittest.TestCase):
    def node(self, *args):
        result = subprocess.run(["node", str(DASHBOARD_CHECK), *args], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_dashboard_checks(self):
        self.assertIn("dashboard checks passed", self.node())

    def test_dashboard_and_scraper_validators_agree(self):
        base = make_config(news("https://example.com/feed"), subreddit("ps2"), youtube(CH1),
                           podcast("https://example.com/pod.rss"), poll_every_hours={"podcast": 6})
        changes = [
            lambda c: None,
            lambda c: c["sources"][0].update(url="not a url"),
            lambda c: c["sources"][0].update(url="https://example.com:99999/feed"),
            lambda c: c["sources"][0].update(url="https://localhost/feed"),
            lambda c: c["sources"][0].update(url="https://user.name@localhost/feed"),
            lambda c: c["sources"][2].update(channel_id="UCshort"),
            lambda c: c["sources"][1].update(subreddit="bad name"),
            lambda c: c["sources"][1].pop("group"),
            lambda c: c["sources"][0].update(role="nope"),
            lambda c: c["sources"][0].update(weight=0),
            lambda c: c["sources"][0].update(weight=10.5),
            lambda c: c["sources"][0].update(weight=True),
            lambda c: c["sources"][0].update(enabled="yes"),
            lambda c: c["sources"].append(copy.deepcopy(c["sources"][0])),
            lambda c: c["poll_every_hours"].update(podcast=6.0),
            lambda c: c["poll_every_hours"].update(podcast=6.5),
            lambda c: c["poll_every_hours"].update(podcast="6"),
            lambda c: c.update(roles={}),
            lambda c: c.update(sources={}),
            lambda c: c["sources"].append(youtube_link("https://www.youtube.com/@IGN")),
            lambda c: c["sources"].append(youtube_link("https://www.youtube.com/c/Some.Name")),
            lambda c: c["sources"].append(youtube_link("https://www.youtube.com/@IGN/videos")),
            lambda c: c["sources"].append(youtube_link("https://youtube.com/@IGN")),
            lambda c: c["sources"].append(youtube_link("https://www.youtube.com/watch?v=abc")),
            lambda c: c["sources"][2].pop("channel_id"),
            lambda c: c["sources"][2].update(channel_id="nope", channel_url="https://www.youtube.com/@IGN"),
            *[(lambda url: lambda c: c["sources"][0].update(url=url))(url) for url in BAD_URLS.values()],
            lambda c: c["sources"][0].update(url="https://example.com:8080/feed?x=1#top"),
            lambda c: c["sources"][0].update(role=["press"]),
            lambda c: c.update(poll_every_hours=None),
        ]
        cases = [CONFIG]
        for change in changes:
            config = copy.deepcopy(base)
            change(config)
            cases.append(config)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(cases), encoding="utf-8")
            verdicts = json.loads(self.node("--validate", str(path)))
        self.assertEqual(verdicts, [not scraper.validate_config(c) for c in cases])

    def test_dashboard_and_price_script_agree_on_which_titles_are_one_game(self):
        """The dashboard puts eBay's figures beside a game's name by evening the name out with
        priceKey(); ebay_prices.py decides two titles are one game with search_terms(). If the two
        drift apart, prices go missing from rows, or land on the wrong game."""
        titles = {
            "Kingdom Hearts II", "Kingdom Hearts 2", "Jak & Daxter: The Precursor Legacy", "Jak and Daxter",
            "Godfather, The: Collector's Edition", "The Getaway", "Getaway, The", "Getaway, The: Black Monday",
            "The", "A", "An", "and", "The and", "A and B", "A.I. Wars", "the  thing", "An Tóstal",
            "Thing, A", "Thing, An: Part VI", "Final Fantasy VI", "Final Fantasy VII", "Final Fantasy VIII",
            "Final Fantasy IX", "Final Fantasy XI", "Resident Evil IV", "Shadow Hearts III",
            " The Getaway", "Getaway, The ", "The\tThing", "A\u00a0Thing", "An Thing", "the getaway", "Thing,The",
            "Ōkami™ (PS2)", "Pokémon", "Director’s Cut", "Director's Cut", "Rock`n Roll", "Final Fantasy X-2",
            "Final Fantasy XII", "Final Fantasy XIII", "Mega Man X8", "Shin Megami Tensei: Persona 4",
            "  Kingdom   Hearts  II ", "ICO", "Ico", "007: Nightfire", "constructor toString II", "", "   ", "İstanbul",
            "Okami⭐Complete", "50 Cent: Bulletproof", ".hack//Infection", "Ratchet & Clank: Up Your Arsenal",
        }
        library = ROOT / "data" / "ps2_database.json"
        if library.exists():
            titles.update(title for title in json.loads(library.read_text(encoding="utf-8")) if isinstance(title, str))
        watchlist = json.loads((ROOT / "ebay_watchlist.json").read_text(encoding="utf-8"))
        for game in watchlist["games"]:
            titles.update(value for value in (game.get("title"), game.get("search")) if isinstance(value, str))
        titles = sorted(titles)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "titles.json"
            path.write_text(json.dumps(titles), encoding="utf-8")
            keys = json.loads(self.node("--price-keys", str(path)))
        expected = [ebay_prices.search_terms(title)[0] for title in titles]
        different = [(title, key, want) for title, key, want in zip(titles, keys, expected) if key != want]
        self.assertEqual(different, [], "index.html priceKey() and ebay_prices.search_terms() disagree")
        self.assertGreater(len(titles), 30)


if __name__ == "__main__":
    unittest.main()
