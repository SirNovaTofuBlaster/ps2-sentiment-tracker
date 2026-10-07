"""Offline tests for scraper.py, feeds.json and the dashboard script.

Run:  python -m unittest discover -s tests -v
Nothing touches the network: feeds are local fixtures and the PS2 title index is the
built-in fallback list. The dashboard tests need Node.js and are skipped without it."""

import contextlib
import copy
import importlib.util
import io
import json
import os
import re
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


def forum(url, name="Board", role="community", enabled=True):
    return {"type": "forum", "name": name, "url": url, "group": "Forums", "role": role, "enabled": enabled}


def board(code, role="anonymous", enabled=True):
    return {"type": "4chan", "name": f"/{code}/", "board": code, "group": "Boards", "role": role, "enabled": enabled}


# Everything else a poster can put into a thread, as 4chan's catalog carries it. None of it is
# ever read, and none of these words may turn up in a file or in the log.
POSTER_FIELDS = {"name": "NAMEWORD", "trip": "!TRIPWORD", "id": "IDWORD", "capcode": "CAPCODEWORD",
                 "country": "XX", "country_name": "COUNTRYWORD", "board_flag": "FLAGWORD", "flag_name": "FLAGNAMEWORD",
                 "filename": "FILENAMEWORD", "ext": ".jpg", "md5": "MDFIVEWORD==", "tag": "TAGWORD",
                 "semantic_url": "slugword-made-from-the-subject", "now": "10/07/26(Wed)12:00:00"}
POSTER_WORDS = ("NAMEWORD", "TRIPWORD", "IDWORD", "CAPCODEWORD", "COUNTRYWORD", "FLAGWORD", "FLAGNAMEWORD", "FILENAMEWORD",
                "MDFIVEWORD", "TAGWORD", "slugword", "REPLYWORD", "REPLYNAME")
REAL_FETCH_BOARD, REAL_BOARD_GAP = scraper.fetch_board, scraper.BOARD_REQUEST_GAP


def thread(number, when, subject=None, comment=None, **extra):
    """One thread of a board's catalog, the way 4chan's API gives it (text is HTML-escaped)."""
    post = {"no": number, "resto": 0, "time": int(when.timestamp()), "replies": 3, "images": 1, **POSTER_FIELDS,
            "last_replies": [{"no": number + 1, "resto": number, "time": int(when.timestamp()) + 60,
                              "name": "REPLYNAME", "com": "REPLYWORD about Okami and Silent Hill 2"}]}
    if subject is not None:
        post["sub"] = subject
    if comment is not None:
        post["com"] = comment
    return {**post, **extra}


class FakeSession:
    """Stands in for requests.Session: answers each address with what the test set up."""

    def __init__(self, replies):
        self.replies, self.headers, self.calls = replies, {}, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, timeout=None, headers=None, **kwargs):
        self.calls.append((url, headers))
        reply = self.replies[url]
        status = reply.get("status", 200)
        response = mock.Mock(status_code=status, headers=reply.get("headers", {}))
        if "error" in reply:
            response.json.side_effect = reply["error"]
        else:
            response.json.return_value = reply.get("body")
        response.raise_for_status.side_effect = None if status < 400 else http_error(status)
        return response


def make_config(*sources, **extra):
    roles = {name: {"label": name, "weight": weight} for name, weight in
             [("official", 1), ("press", 1), ("community", 1), ("ps2", 1.5), ("retro", 1), ("collector", 0.5), ("creator", 0.5),
              ("anonymous", 0)]}
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
                                  podcast("https://example.com/pod.rss"), forum("https://forum.example.com/index.rss"),
                                  board("vr"), poll_every_hours={"podcast": 6})

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
            "forum url": lambda c: c["sources"][4].update(url="forum.example.com/index.rss"),
            "forum without a url": lambda c: c["sources"][4].pop("url"),
            "duplicate forum": lambda c: c["sources"].append(forum("https://forum.example.com/index.rss", name="Again")),
            **{f"board {code!r}": (lambda code: lambda c: c["sources"][5].update(board=code))(code)
               for code in ("VR", "/vr/", "v r", "", "toolong", "vr\n", "v-r", 4, None, ["vr"])},
            "board missing": lambda c: c["sources"][5].pop("board"),
            "duplicate board": lambda c: c["sources"].append(board("vr")),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assertTrue(self.problems_after(change))

    def test_forums_and_boards_are_accepted(self):
        for code in ("v", "vg", "vmg", "vrpg", "3", "s4s"):
            with self.subTest(code):
                self.assertEqual(self.problems_after(lambda c: c["sources"].append(board(code))), [])
        self.assertEqual(self.problems_after(lambda c: c["poll_every_hours"].update({"forum": 2, "4chan": 3})), [])
        self.assertEqual(scraper.source_key(board("vr")), "4chan:vr")
        self.assertEqual(scraper.source_key(forum("https://forum.example.com/index.rss")), "https://forum.example.com/index.rss")
        self.assertEqual(self.problems_after(lambda c: c["roles"]["anonymous"].update(weight=0)), [], "a weight of 0 leaves a role out")

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
        config = make_config(podcast("https://p.example/rss"), youtube(CH1), board("vr"), subreddit("a", group="G1"),
                             forum("https://f.example/index.rss"), news("https://n.example/feed"), subreddit("b", group="G2"),
                             board("v"), board("vst", enabled=False), subreddit("c", group="G1"))
        jobs = scraper.build_jobs(config)
        # Forums and boards are a few quick requests: they go before the hundreds of YouTube and
        # podcast feeds, which can use up the run's time.
        self.assertEqual([job["type"] for job in jobs], ["news", "reddit", "reddit", "forum", "4chan", "4chan", "youtube", "podcast"])
        self.assertEqual(jobs[1]["url"], "https://www.reddit.com/r/a+c/.rss?limit=50")
        self.assertEqual(jobs[2]["url"], "https://www.reddit.com/r/b/.rss?limit=50")
        self.assertEqual([job["url"] for job in jobs[3:6]], ["https://f.example/index.rss", "https://a.4cdn.org/vr/catalog.json",
                                                             "https://a.4cdn.org/v/catalog.json"])
        self.assertEqual(jobs[6]["url"], f"https://www.youtube.com/feeds/videos.xml?channel_id={CH1}")

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
        self.assertEqual(self.due_after(hours=2), set(scraper.SOURCE_TYPES) - {"podcast"})
        self.assertEqual(self.due_after(hours=5, minutes=30), set(scraper.SOURCE_TYPES) - {"podcast"})
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
    FORUM_URL = "https://forum.example/forums/gaming.2/index.rss"
    VR_URL = "https://a.4cdn.org/vr/catalog.json"
    V_URL = "https://a.4cdn.org/v/catalog.json"

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
            forum(self.FORUM_URL, name="Example Forum"),
            board("vr"), board("v"), board("vst", enabled=False),
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
            self.FORUM_URL: rss("Gaming", [
                ("Ico appreciation thread", "https://forum.example/threads/ico.1/", None, NOW - hour),
                ("What are you playing this weekend?", "https://forum.example/threads/weekend.2/", None, NOW - 2 * hour)]),
        }
        # What 4chan's catalog gives for each board: the opening post of every live thread.
        # The words in capitals stand for what posters write; none of them may be kept.
        self.boards = {
            self.VR_URL: [
                thread(100, NOW - 6 * hour, subject="Board rules", comment="RULESTEXT about Okami", sticky=1, closed=1),
                thread(101, NOW - 3 * hour, subject="Silent Hill 2 thread", comment="RUDEWORD you all, the remake is a masterpiece"),
                thread(102, NOW - 2 * hour, comment="Is Shadow of the Colossus<br><span class=\"quote\">&gt;still worth it</span> SECRETWORD"),
                thread(103, NOW - hour, subject="comfy thread", comment="OTHERWORD what are you playing"),
            ],
            self.V_URL: [
                thread(900, NOW - 2 * hour, comment="Ico, Okami &amp; Gran Turismo 4. PRIVATEWORD Also Final Fantasy X and Persona 4"),
                thread(901, NOW - hour, comment="NOTAGAME thread"),
            ],
        }
        self.board_calls = []
        self.board_changed = {self.VR_URL: "Wed, 07 Oct 2026 13:31:02 GMT", self.V_URL: "Wed, 07 Oct 2026 13:47:59 GMT"}
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
                        mock.patch.object(scraper, "fetch_board", side_effect=self.fake_board),
                        mock.patch.object(scraper, "BOARD_REQUEST_GAP", 0),
                        mock.patch.object(scraper, "load_ps2_titles", return_value=scraper.FALLBACK_TITLES),
                        mock.patch.dict(os.environ, {"FULL_RUN": "1"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_fetch(self, session, url, retry_rate_limit=True):
        self.fetched.append((url, retry_rate_limit))
        if url in self.failures:
            raise self.failures[url]
        return feedparser.parse(self.fixtures[url])

    def fake_board(self, session, url, modified=None):
        """Stands in for fetch_board(): (threads, when the board last changed). A board set to
        None has had no post since it was last read and answers "not modified"."""
        self.board_calls.append((url, modified))
        if url in self.failures:
            raise self.failures[url]
        threads = self.boards[url]
        return (None, modified) if threads is None else (threads, self.board_changed.get(url))

    def run_scraper(self):
        scraper.FEEDS_PATH.write_text(json.dumps(self.config), encoding="utf-8")
        with mock.patch("builtins.print") as printed:
            scraper.run_scraper()
        self.log = "\n".join(" ".join(str(arg) for arg in call.args) for call in printed.call_args_list)
        output = json.loads(scraper.OUTPUT_PATH.read_text(encoding="utf-8"))
        status = json.loads(scraper.STATUS_PATH.read_text(encoding="utf-8"))
        return output, status

    def item(self, output, headline, source):
        return next(i for i in output["items"] if i["headline"] == headline and i["source"] == source)

    def test_all_source_types_end_up_in_the_snapshot(self):
        output, status = self.run_scraper()
        self.assertEqual(output["total_tracked_feeds"], 9)  # enabled sources; each subreddit counts once
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
                                       f"youtube:{CH1}", self.POD_URL, self.FORUM_URL, "4chan:vr", "4chan:v"})
        self.assertTrue(all(entry["ok"] for entry in status.values()))
        self.assertEqual(status["reddit:ps2"]["latest"], (NOW - timedelta(hours=1)).strftime(scraper.TIMESTAMP_FORMAT))

    def test_forum_threads_are_items_like_any_other_feed(self):
        output, status = self.run_scraper()
        ico = self.item(output, "Ico appreciation thread", "Forum: Example Forum")
        self.assertEqual((ico["source_type"], ico["feed"], ico["link"], ico["matched_game"]),
                         ("forum", self.FORUM_URL, "https://forum.example/threads/ico.1/", "Ico"))
        self.assertIsNone(self.item(output, "What are you playing this weekend?", "Forum: Example Forum")["matched_game"])
        self.assertEqual(status[self.FORUM_URL], {"ok": True, "latest": (NOW - timedelta(hours=1)).strftime(scraper.TIMESTAMP_FORMAT)})
        # A forum is an extra: when it is down the run goes on.
        self.failures[self.FORUM_URL] = http_error(403)
        output, status = self.run_scraper()
        self.assertEqual((status[self.FORUM_URL]["ok"], status[self.FORUM_URL]["error"]), (False, "HTTP 403"))
        self.item(output, "Ico appreciation thread", "Forum: Example Forum")  # what was collected before is kept

    def test_a_board_thread_keeps_the_games_it_names_and_nothing_a_poster_wrote(self):
        output, status = self.run_scraper()
        threads = {item["link"]: item for item in output["items"] if item["source_type"] == "4chan"}
        stamp = lambda hours: (NOW - timedelta(hours=hours)).strftime(scraper.TIMESTAMP_FORMAT)  # noqa: E731
        self.assertEqual(threads, {
            "https://boards.4chan.org/vr/thread/101": {
                "headline": "Thread on /vr/ naming Silent Hill 2", "source": "4chan /vr/", "source_type": "4chan", "feed": "4chan:vr",
                "link": "https://boards.4chan.org/vr/thread/101", "matched_game": "Silent Hill 2", "matched_games": ["Silent Hill 2"],
                "match_score": 100, "match_method": threads["https://boards.4chan.org/vr/thread/101"]["match_method"],
                "matched_in": "title", "is_remaster_rumor": False, "sentiment": None, "hype": 0, "timestamp": stamp(3)},
            "https://boards.4chan.org/vr/thread/102": {
                "headline": "Thread on /vr/ naming Shadow of the Colossus", "source": "4chan /vr/", "source_type": "4chan", "feed": "4chan:vr",
                "link": "https://boards.4chan.org/vr/thread/102", "matched_game": "Shadow of the Colossus",
                "matched_games": ["Shadow of the Colossus"], "match_score": 100,
                "match_method": threads["https://boards.4chan.org/vr/thread/102"]["match_method"],
                "matched_in": "body", "is_remaster_rumor": False, "sentiment": None, "hype": 0, "timestamp": stamp(2)},
            "https://boards.4chan.org/v/thread/900": threads.get("https://boards.4chan.org/v/thread/900"),
        }, "one row per thread that names a game; the rules thread and the threads naming none are not kept")
        many = threads["https://boards.4chan.org/v/thread/900"]
        self.assertEqual(sorted(many["matched_games"]), ["Final Fantasy X", "Gran Turismo 4", "Ico", "Okami", "Persona 4"])
        self.assertEqual(many["headline"], f"Thread on /v/ naming {', '.join(many['matched_games'][:3])} and 2 more")
        self.assertEqual((many["matched_in"], many["sentiment"], many["is_remaster_rumor"]), ("body", None, False),
                         "a thread is not scored: no mood, never a remaster flag, whatever its text says")

        # Nothing a poster wrote reaches either file or the log: not the rude word, not an ordinary
        # one, not the name, the file name, the flag, the link's slug or a reply.
        saved = scraper.OUTPUT_PATH.read_text(encoding="utf-8") + scraper.STATUS_PATH.read_text(encoding="utf-8")
        for word in ("RULESTEXT", "RUDEWORD", "SECRETWORD", "OTHERWORD", "PRIVATEWORD", "NOTAGAME",
                     "masterpiece", "comfy", "worth", "quote", *POSTER_WORDS):
            self.assertNotIn(word.lower(), saved.lower(), word)
            self.assertNotIn(word.lower(), self.log.lower(), word)
        self.assertIn("2 threads naming a game  https://a.4cdn.org/vr/catalog.json", self.log, "the log has counts, and only counts")
        self.assertEqual(status["4chan:vr"], {"ok": True, "latest": stamp(1), "modified": "Wed, 07 Oct 2026 13:31:02 GMT"},
                         "the newest thread, whether or not it named a game, and when the board itself last changed")
        self.assertEqual(status["4chan:v"], {"ok": True, "latest": stamp(1), "modified": "Wed, 07 Oct 2026 13:47:59 GMT"})

    def test_a_board_that_answers_nonsense_leaks_nothing_and_stops_nothing(self):
        """The real reader against answers of every wrong shape, each carrying a poster's words
        where a careless reader would pick them up. The run goes on, the board is reported
        (or simply has nothing to say), and none of those words is stored or printed."""
        secret = "LEAKWORD"
        wrong_shapes = [
            [{"page": 1, "threads": 5}], [{"page": 1, "threads": True}], [{"page": 1, "threads": 1.5}],
            [{"page": 1, "threads": {"no": 1, "sub": secret}}], [{"page": 1, "threads": secret}], [{"page": secret}], [secret, 7, None],
            [{"page": 1, "threads": [secret, 5, None, [secret], {"no": secret, "time": secret, "sub": f"Okami {secret}"},
                                     {"no": 5, "time": int(NOW.timestamp()), "sub": {"x": secret}, "com": [secret]},
                                     {"no": 6, "time": int(NOW.timestamp()), "sub": f"okami {secret}", "semantic_url": secret}]}],
        ]
        failures = [{"body": {"error": secret}}, {"body": secret}, {"body": None}, {"status": 403, "body": secret},
                    {"error": ValueError(f"Expecting value: line 1 column 1 (char 0)")},
                    {"error": requests.exceptions.JSONDecodeError("Expecting value", secret, 0)}]
        for number, reply in enumerate([{"body": shape} for shape in wrong_shapes] + failures):
            with self.subTest(reply=number):
                session = FakeSession({self.VR_URL: reply, self.V_URL: {"body": [{"page": 1, "threads": self.boards[self.V_URL]}],
                                                                        "headers": {"Last-Modified": "Wed, 07 Oct 2026 13:47:59 GMT"}}})
                with mock.patch.object(scraper, "fetch_board", REAL_FETCH_BOARD), \
                        mock.patch.object(scraper.requests, "Session", return_value=session):
                    output, status = self.run_scraper()
                self.assertEqual([call[0] for call in session.calls], [self.VR_URL, self.V_URL])
                self.item(output, "Silent Hill 2 remake announced", "Example News")
                self.assertIn("https://boards.4chan.org/v/thread/900", [item["link"] for item in output["items"]], "the next board is still read")
                self.assertEqual(status["4chan:vr"]["ok"], number < len(wrong_shapes), "a wrong shape inside a catalog is nothing to read; no catalog is a failure")
                saved = scraper.OUTPUT_PATH.read_text(encoding="utf-8") + scraper.STATUS_PATH.read_text(encoding="utf-8")
                for word in (secret, *POSTER_WORDS):
                    self.assertNotIn(word.lower(), (saved + self.log).lower(), word)
                scraper.OUTPUT_PATH.unlink()
                scraper.STATUS_PATH.unlink()

    def test_a_forum_thread_never_takes_a_row_from_another_source(self):
        """Rows are told apart by their link. A link aggregator's feed gives the article a post
        shares as the post's link; the discussion page is used instead (it is the item here),
        and a thread that has nothing but another row's link is left out rather than replace it."""
        when = format_datetime(NOW - timedelta(minutes=30))
        self.fixtures[self.FORUM_URL] = (
            '<?xml version="1.0"?><rss version="2.0"><channel><title>Lemmy - games</title>'
            # Lemmy: <link> is the article, <comments> and <guid> are the post.
            '<item><title>this remake is broken garbage</title><link>https://news.example/sh2</link>'
            '<comments>https://forum.example/post/1</comments><guid>https://forum.example/post/1</guid>'
            f'<pubDate>{when}</pubDate></item>'
            # A feed with nothing but the article's address...
            '<item><title>terrible, awful, the worst</title><link>https://news.example/sh2</link>'
            f'<guid isPermaLink="false">4242</guid><pubDate>{when}</pubDate></item>'
            # ...and an ordinary thread, whose link is its own page.
            f'<item><title>Okami thread</title><link>https://forum.example/threads/okami.3/</link><pubDate>{when}</pubDate></item>'
            '</channel></rss>')
        output, _ = self.run_scraper()
        article = [item for item in output["items"] if item["link"] == "https://news.example/sh2"]
        self.assertEqual([(item["source"], item["headline"], item["sentiment"] > 50) for item in article],
                         [("Example News", "Silent Hill 2 remake announced", False)], "the article keeps its own row")
        forum_rows = {item["link"]: item["headline"] for item in output["items"] if item["source_type"] == "forum"}
        self.assertEqual(forum_rows, {"https://forum.example/post/1": "this remake is broken garbage",
                                      "https://forum.example/threads/okami.3/": "Okami thread"})
        # The same on a later run, when the article has dropped out of its own feed but is still in the snapshot.
        self.fixtures[self.NEWS_URL] = rss("Example News", [("Brand new story", "https://news.example/new", None, NOW)])
        output, _ = self.run_scraper()
        self.assertEqual([item["source"] for item in output["items"] if item["link"] == "https://news.example/sh2"], ["Example News"])
        # A thread seen again updates its own row as before.
        self.assertEqual(sum(1 for item in output["items"] if item["source_type"] == "forum"), 2)

    def test_a_forum_is_an_extra_like_a_channel_or_a_show(self):
        """Its failure is reported and never counts towards calling the run off, and it is not
        waited on when it says "too many requests"."""
        forums = [forum(f"https://forum{n}.example/index.rss", name=f"Forum {n}") for n in range(3)]
        self.config["sources"] = [s for s in self.config["sources"] if s["type"] == "news"] + forums
        for source in forums:
            self.failures[source["url"]] = http_error(403)
        output, status = self.run_scraper()  # one news feed that works, three forums that do not
        self.item(output, "Silent Hill 2 remake announced", "Example News")
        self.assertEqual([status[source["url"]]["error"] for source in forums], ["HTTP 403"] * 3)
        self.assertEqual({url: retry for url, retry in self.fetched}, {self.NEWS_URL: True, **{source["url"]: False for source in forums}})
    def test_boards_are_read_one_at_a_time_and_only_when_something_changed(self):
        self.assertGreater(REAL_BOARD_GAP, 1.0, "4chan's API allows at most one request a second")
        third = next(source for source in self.config["sources"] if source.get("board") == "vst")
        third["enabled"] = True
        self.boards["https://a.4cdn.org/vst/catalog.json"] = []
        clock = [1000.0]  # a clock that only moves when the scraper sleeps

        def sleep(seconds):
            clock[0] += seconds

        with mock.patch.object(scraper, "BOARD_REQUEST_GAP", REAL_BOARD_GAP), \
                mock.patch.object(scraper.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(scraper.time, "sleep", side_effect=sleep) as slept:
            self.run_scraper()
        self.assertEqual(self.board_calls, [(self.VR_URL, None), (self.V_URL, None), ("https://a.4cdn.org/vst/catalog.json", None)],
                         "in the order listed, each asked for everything the first time")
        self.assertEqual([call.args[0] for call in slept.call_args_list], [REAL_BOARD_GAP, REAL_BOARD_GAP],
                         "a full pause before every board but the first, counted from the request before it")
        third["enabled"] = False

        # The next run hands each board the date its server gave last time, word for word, and
        # a board nobody has posted on since answers "not modified".
        self.board_calls.clear()
        self.boards[self.VR_URL] = None
        self.board_changed[self.V_URL] = "Wed, 07 Oct 2026 14:05:10 GMT"
        before = scraper.STATUS_PATH.read_text(encoding="utf-8")
        output, status = self.run_scraper()
        newest = (NOW - timedelta(hours=1)).strftime(scraper.TIMESTAMP_FORMAT)
        self.assertEqual(self.board_calls, [(self.VR_URL, "Wed, 07 Oct 2026 13:31:02 GMT"), (self.V_URL, "Wed, 07 Oct 2026 13:47:59 GMT")])
        self.assertEqual(status["4chan:vr"], json.loads(before)["4chan:vr"], "an unchanged board changes nothing in the status file")
        self.assertEqual(status["4chan:v"], {"ok": True, "latest": newest, "modified": "Wed, 07 Oct 2026 14:05:10 GMT"})
        self.assertIn("https://boards.4chan.org/vr/thread/101", [item["link"] for item in output["items"]],
                      "threads already collected stay until they age out")

        # A board that failed is read in full the next time: there is no date to hand back.
        self.failures[self.VR_URL] = requests.ConnectionError("blocked")
        _, status = self.run_scraper()
        self.assertEqual(status["4chan:vr"], {"ok": False, "error": "ConnectionError", "latest": newest,
                                              "failing_since": status["4chan:vr"]["failing_since"]})
        self.failures.clear()
        self.board_calls.clear()
        self.boards[self.VR_URL] = [thread(104, NOW - timedelta(minutes=30), subject="Okami thread")]
        output, status = self.run_scraper()
        self.assertEqual(self.board_calls[0], (self.VR_URL, None))
        self.assertEqual(status["4chan:vr"], {"ok": True, "latest": (NOW - timedelta(minutes=30)).strftime(scraper.TIMESTAMP_FORMAT),
                                              "modified": "Wed, 07 Oct 2026 13:31:02 GMT"})
        self.assertIn("https://boards.4chan.org/vr/thread/104", [item["link"] for item in output["items"]])
    def test_a_board_that_cannot_be_read_never_stops_a_run(self):
        codes = ("vr", "v", "vg", "vm", "vmg")
        self.config["sources"] = [s for s in self.config["sources"] if s["type"] != "4chan"] + [board(code) for code in codes]
        for code in codes:
            self.failures[f"https://a.4cdn.org/{code}/catalog.json"] = requests.ConnectionError("blocked")
        output, status = self.run_scraper()
        self.item(output, "Silent Hill 2 remake announced", "Example News")
        self.assertEqual(len(self.board_calls), scraper.HOST_FAILURE_LIMIT, "after three failures the rest are left for the next run")
        self.assertEqual((status["4chan:vr"]["ok"], status["4chan:vr"]["error"]), (False, "ConnectionError"))
        self.assertNotIn("4chan:vmg", status)
        self.failures.clear()
        self.failures[self.VR_URL] = ValueError("unreadable catalog")
        self.boards.update({f"https://a.4cdn.org/{code}/catalog.json": [] for code in codes[2:]})
        output, status = self.run_scraper()
        self.assertEqual((status["4chan:vr"]["ok"], status["4chan:vr"]["error"]), (False, "unreadable catalog"))
        self.assertTrue(status["4chan:v"]["ok"])
        self.assertIn("https://boards.4chan.org/v/thread/900", [item["link"] for item in output["items"]])

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


class BoardTests(unittest.TestCase):
    """Reading a 4chan board: the request, and turning what it returns into plain words."""

    class Session:
        def __init__(self, status=200, body=None, changed="Wed, 07 Oct 2026 13:31:02 GMT"):
            self.status, self.body, self.changed, self.calls = status, body, changed, []

        def get(self, url, timeout=None, headers=None):
            self.calls.append((url, timeout, headers))
            response = mock.Mock(status_code=self.status, headers={} if self.changed is None else {"Last-Modified": self.changed})
            response.json.return_value = self.body
            response.raise_for_status.side_effect = None if self.status < 400 else http_error(self.status)
            return response

    def test_the_catalog_is_flattened_into_threads(self):
        pages = [{"page": 1, "threads": [{"no": 1}, {"no": 2}]}, {"page": 2, "threads": [{"no": 3}, "junk"]}, "junk", {"page": 3}]
        session = self.Session(body=pages)
        self.assertEqual(scraper.fetch_board(session, "https://a.4cdn.org/vr/catalog.json"),
                         ([{"no": 1}, {"no": 2}, {"no": 3}], "Wed, 07 Oct 2026 13:31:02 GMT"))
        self.assertEqual(session.calls, [("https://a.4cdn.org/vr/catalog.json", scraper.REQUEST_TIMEOUT, {})])

    def test_it_asks_only_for_what_changed(self):
        """4chan's API rules ask for If-Modified-Since. It only works with the date the server
        itself gave: a date of our own making (the newest thread seen, say) is always older than
        the board's last change, so the board would be sent in full every time."""
        url, date = "https://a.4cdn.org/vr/catalog.json", "Wed, 07 Oct 2026 12:30:00 GMT"
        session = self.Session(status=304)
        self.assertEqual(scraper.fetch_board(session, url, date), (None, date), "not modified: no threads, the same date")
        self.assertEqual(session.calls[0][2], {"If-Modified-Since": date})
        # Anything that is not a date as servers write it is neither sent nor kept: it would
        # end up in a request header and in a data file.
        for bad in ("yesterday", "Wed, 07 Oct 2026 12:30:00 GMT\r\nX-Injected: 1", "2026-10-07 12:30 UTC", "", 5, None,
                    ["Wed, 07 Oct 2026 12:30:00 GMT"], "wed, 07 oct 2026 12:30:00 gmt", "Wed, 07 Oct 2026 12:30:00 +0000"):
            with self.subTest(bad=bad):
                session = self.Session(body=[], changed=bad if isinstance(bad, str) else None)
                self.assertEqual(scraper.fetch_board(session, url, bad), ([], None))
                self.assertEqual(session.calls[0][2], {})
        self.assertEqual(scraper.fetch_board(self.Session(body=[], changed=None), url, date), ([], None), "no date given: none kept")

    def test_wrong_shapes_inside_a_catalog_are_passed_over(self):
        """Only the two errors a feed is expected to raise are caught by the run; anything else
        (a TypeError from iterating a number, say) would stop it, news included."""
        for threads in (5, True, 1.5, None, "text", {"no": 1}):
            with self.subTest(threads=threads):
                session = self.Session(body=[{"page": 1, "threads": threads}, {"page": 2, "threads": [{"no": 2}]}])
                self.assertEqual(scraper.fetch_board(session, "https://a.4cdn.org/vr/catalog.json")[0], [{"no": 2}])

    def test_an_answer_that_is_not_a_catalog_is_a_failure(self):
        for body in ({"error": "nope"}, None, "text"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                scraper.fetch_board(self.Session(body=body), "https://a.4cdn.org/vr/catalog.json")
        with self.assertRaises(requests.HTTPError):
            scraper.fetch_board(self.Session(status=403), "https://a.4cdn.org/vr/catalog.json")

    def test_markup_and_entities_become_plain_words(self):
        self.assertEqual(scraper.board_text('Ico &amp; Okami<br><span class="quote">&gt;implying</span> long<wbr>word &#039;s'),
                         "Ico & Okami\n>implying longword 's", "a line of the post stays a line: that is where a sentence starts")
        self.assertEqual(scraper.board_text("one<br>two<BR/>three<br />  four &#10; five<br><br><br>six"), "one\ntwo\nthree\nfour\nfive\nsix")
        self.assertEqual([scraper.board_text(value) for value in (None, "", 5, "<br>", " \n ")], ["", "", "5", "", ""])
        self.assertEqual(scraper.first_words("one two\nthree  four", 3), "one two\nthree")
        self.assertEqual([scraper.first_words("one two", limit) for limit in (2, 5)], ["one two", "one two"])

    def test_the_line_for_a_thread_names_up_to_three_games(self):
        names = ["Ico", "Okami", "Kuon", "God Hand", "Black"]
        self.assertEqual([scraper.games_named(names[:count]) for count in (1, 2, 3, 4, 5)],
                         ["Ico", "Ico and Okami", "Ico, Okami and Kuon", "Ico, Okami, Kuon and 1 more", "Ico, Okami, Kuon and 2 more"])

    def test_a_post_names_a_game_only_when_it_is_spelt_right_and_written_as_a_name(self):
        library = scraper.FALLBACK_TITLES + [
            "The Thing", "Top Gun", "Dragon Rage", "Legend of Herkules", "XIII", "Retro", "Obscure", "Cars", "Yakuza 2",
            "I-Ninja", "Tekken 5", "WWE SmackDown! vs. RAW", "Ar tonelico", "kill.switch", "Half-Life", "Monster Hunter",
            "Silent Hill 4: The Room", "Metal Gear Solid 2: Substance", "Devil May Cry", "Persona 3", "Area 51"]
        matcher = scraper.TitleMatcher(library)
        named = lambda text: [title for title, _, _ in scraper.games_in_post(text, matcher)]  # noqa: E731
        loose = lambda text: [title for title, _, _ in matcher.match_all(text)]  # noqa: E731

        def check(expected, *texts):
            for text in texts:
                with self.subTest(text=text):
                    self.assertEqual(sorted(named(text)), sorted(expected))

        # --- the whole name, spelt as the library spells it ---
        # A near miss is usually another game. A headline is given the benefit of the doubt; a post is not.
        for text, wrong in (("Dragon Age general", "Dragon Rage"), ("Legend of Heroes thread", "Legend of Herkules")):
            self.assertEqual((loose(text), named(text)), ([wrong], []), text)
        self.assertEqual((loose("Silent Hil 2 is great"), named("Silent Hil 2 is great")), (["Silent Hill 2"], []), "a number does not excuse a misspelling")
        # Half a title is not its name, even where the text mentions the console (a headline's rule).
        self.assertEqual(loose("my ps2 is in the room next to the tv"), ["Silent Hill 4: The Room"])
        check([], "my ps2 is in the room next to the tv", "ps2 games had substance", "Snake Eater on PS2")
        # A title too long for the matcher's runs is found whole, and the shorter titles inside it are not counted beside it.
        check(["Prince of Persia: The Sands of Time"], "Prince of Persia: The Sands of Time still holds up")
        check(["Zone of the Enders: The 2nd Runner"], "Zone of the Enders: The 2nd Runner is great")
        check(["Shin Megami Tensei: Digital Devil Saga 2"], "Shin Megami Tensei: Digital Devil Saga 2")
        check(["Max Payne 2: The Fall of Max Payne"], "Max Payne 2: The Fall of Max Payne")
        check(["Zone of the Enders", "Zone of the Enders: The 2nd Runner"], "Zone of the Enders, then Zone of the Enders: The 2nd Runner")

        # --- written as a name: capitals where the library has them, each in its place ---
        check(["The Thing"], "The Thing is the best horror game", "I love the Thing game")
        check([], "the thing is, I never liked it", "What's the thing you hate", "The thing is", "top gun pilots",
              "Top tier. Gun to my head, the top gun here", "shadow of the colossus was overrated", "Shadow of the colossus was overrated")
        check(["Shadow of the Colossus"], "Was Shadow of the Colossus overrated?")
        check(["Ico", "Okami"], "Ico and Okami", ">Okami\n>Ico")
        check([], "ico and okami", "half life", "Half-life")
        check(["Half-Life"], "Half-Life on PS2", "Half Life was fine")
        check(["Kingdom Hearts", "God of War"], "I love Kingdom Hearts and God of War")
        # The library's own spelling always counts, lower-case words and all.
        check(["WWE SmackDown! vs. RAW"], "WWE SmackDown! vs. RAW is the best wrestling game", "WWE Smackdown VS RAW")
        check([".hack//Infection"], ".hack//Infection is underrated")
        check(["Ar tonelico"], "Ar tonelico is kino", "Ar Tonelico")
        check(["kill.switch"], "kill.switch was ahead of its time", "Kill.Switch")
        check([], "kill switch", "I flipped the kill switch")
        # A post written all in capitals marks nothing with them.
        check([], "MY PS2 SHOWS A BLACK SCREEN", "THE THING IS BROKEN", "OKAMI THREAD")
        check(["Silent Hill 2"], "SILENT HILL 2 THREAD")
        # One everyday word that is also a title: the capital that starts a sentence says nothing.
        check([], "Black screen on my PS2", "Obscure PS2 games thread", "Retro PS2 thread", "Cars in this PS2 game look great",
              "what do\nBlack screen on PS2", "It broke. Black screen on PS2", "Bully on PS2 is great")
        check(["Black"], "I think Black is the best PS2 shooter", "Why is Black so good on PS2?\nBlack is great")
        check(["Bully"], "I played Bully on PS2")
        check(["Okami"], "Okami is great", "Okami")  # a name nothing else uses

        # --- a number written as a number settles it, capitals or not ---
        check(["Silent Hill 2"], "silent hill 2 is kino", "Silent Hill 2, 3 and 4 are great")
        check(["Kingdom Hearts II"], "kingdom hearts ii", "kingdom hearts 2 was peak")
        check(["Final Fantasy X"], "final fantasy 10", "Final Fantasy X", "Final Fantasy x")
        check(["Area 51"], "area 51 was a fun shooter")
        # A lone I, V or X is also a pronoun and a letter: there the capitals decide.
        check([], "final fantasy x", "can i ninja edit my post", "Can I ninja edit", "i-ninja was fun", "jak x is underrated")
        check(["I-Ninja"], "I-Ninja was fun")
        check(["Jak X: Combat Racing"], "Jak X: Combat Racing")
        # A title that is only a number names the game only as the library writes it.
        self.assertEqual(loose("I was 13 when I got my PS2"), ["XIII"])
        check([], "I was 13 when I got my PS2", "My PS2 died after 13 years")
        check(["XIII"], "XIII on PS2 was underrated", "xiii is a good ps2 shooter")
        # A number that is counting something is not part of a name.
        check([], "bought Yakuza 2 days ago", "i beat persona 3 times", "Tekken 5 years ago", "Jak 3 times")
        check(["Tekken 5"], "tekken 5 is the best", "Tekken 5 10/10")

        # --- not another entry of the series ---
        check([], "Max Payne 2 is better", "Kingdom Hearts 3 was a mistake", "God of War 3", "Devil May Cry 5", "Monster Hunter 4 Ultimate",
              "Okami 2 never ever", "God of War III")
        check(["Max Payne"], "Max Payne is great", "Max Payne, 2001", "Max Payne 2001", "Max Payne\n2 hours long")
        check(["Okami"], "Okami 10/10", "Okami 1")
        check(["God of War II"], "God of War II", "god of war 2")
        check(["Monster Hunter"], "/mhg/ - Monster Hunter General")  # a series under its PS2 entry's name: the matcher's known limit

        # --- names the matcher knows by heart count however they are written ---
        check(["Metal Gear Solid 3: Snake Eater"], "mgs3 was good")
        check(["Grand Theft Auto: San Andreas"], "gta sa is the best", "GTA: San Andreas", "Grand Theft Auto: San Andreas")
        check([], "grand theft auto san andreas", "")

    def test_words_are_lined_up_with_the_matcher_or_not_trusted(self):
        """The rules above look at how each word was written, so the words as written must line
        up one to one with the words the matcher read. Where they cannot, nothing is taken on
        trust: only the names the matcher knows by heart count."""
        matcher = scraper.TitleMatcher(scraper.FALLBACK_TITLES)
        words = scraper.post_words("Jak II &amp; Half-Life, 2 of_them")
        self.assertEqual([(token, raw) for token, raw, _, _ in words[:6]],
                         [("jak", "Jak"), ("2", "II"), ("amp", "amp"), ("half", "Half"), ("life", "Life"), ("2", "2")])
        self.assertEqual(" ".join(token for token, *_ in words), scraper.normalise("Jak II &amp; Half-Life, 2 of_them"))
        text = "Jak II is great"
        self.assertEqual([text[start:end] for _, _, start, end in scraper.post_words(text)], ["Jak", "II", "is", "great"])
        with mock.patch.object(scraper, "POST_WORD_PATTERNS", (re.compile(r"[a-z]+"),)):  # a splitter that disagrees with the matcher
            self.assertIsNone(scraper.post_words("Okami and Jak II"))
            self.assertEqual([title for title, _, _ in scraper.games_in_post("Okami and Jak II and MGS3", matcher)],
                             ["Metal Gear Solid 3: Snake Eater"])
        # Both ways rapidfuzz may split words are covered (it treats "_" differently when compiled).
        for pattern in scraper.POST_WORD_PATTERNS:
            self.assertEqual(pattern.findall("Silent Hill 2"), ["Silent", "Hill", "2"])
        self.assertEqual({tuple(pattern.findall("a_b")) for pattern in scraper.POST_WORD_PATTERNS}, {("a", "b"), ("a_b",)})

    def test_threads_without_a_usable_number_or_time_are_left_alone(self):
        matcher = scraper.TitleMatcher(scraper.FALLBACK_TITLES)
        job = {"type": "4chan", "sources": [board("vr")], "url": "https://a.4cdn.org/vr/catalog.json"}
        good = thread(7, NOW, subject="Okami")
        self.assertEqual(scraper.analyze_thread(good, job, matcher, set())["matched_game"], "Okami")
        # Times are compared as text, so a date that is not a plausible one would never age out:
        # year 322 and year 2300 both sort above everything written this century.
        for change in ({"no": None}, {"no": "7"}, {"no": True}, {"time": None}, {"time": "now"}, {"time": True},
                       {"time": 10 ** 20}, {"time": -52_000_000_000}, {"time": 10_413_792_000}, {"time": 0},
                       {"time": int((NOW + timedelta(days=3)).timestamp())}, {"time": int((NOW - timedelta(days=366 * 21)).timestamp())},
                       {"sticky": 1}):
            with self.subTest(change=change):
                self.assertIsNone(scraper.analyze_thread({**good, **change}, job, matcher, set()))
                self.assertIsNone(scraper.thread_timestamp({**good, **change}) if "no" not in change else None)
        for age in (timedelta(0), timedelta(days=365 * 4), -timedelta(hours=2)):  # /vmg/ had a thread over three years old
            self.assertIsNotNone(scraper.thread_timestamp(thread(7, NOW - age)), age)
        self.assertIsNone(scraper.analyze_thread(thread(8, NOW), job, matcher, set()), "a thread with no text at all")
        # An over-long comment is read only at its start, like any other body text.
        late = thread(9, NOW, comment=" ".join(["word"] * scraper.MAX_BODY_TOKENS) + " Okami")
        self.assertIsNone(scraper.analyze_thread(late, job, matcher, set()))
        early = thread(9, NOW, comment=" ".join(["word"] * (scraper.MAX_BODY_TOKENS - 1)) + " Okami")
        self.assertEqual(scraper.analyze_thread(early, job, matcher, set())["matched_game"], "Okami")

    def test_a_thread_counts_on_the_day_it_was_started(self):
        """Slow boards keep threads live for months. One started before the feed's two weeks
        is not a new mention, though it still tells how recently the board was active."""
        matcher = scraper.TitleMatcher(scraper.FALLBACK_TITLES)
        job = {"type": "4chan", "sources": [board("vst")], "url": "https://a.4cdn.org/vst/catalog.json"}
        window = timedelta(days=scraper.RETENTION_DAYS)
        threads = [thread(1, NOW - timedelta(days=400), subject="Okami general"),
                   thread(2, NOW - window - timedelta(hours=1), subject="Ico"),
                   thread(3, NOW - window + timedelta(hours=1), subject="Gran Turismo 4"),
                   thread(4, NOW - timedelta(hours=2), subject="Persona 4"),
                   thread(5, NOW - timedelta(minutes=5), subject="no game here")]
        status = {}
        with mock.patch.object(scraper, "fetch_board", return_value=(threads, None)) as fetch:
            items = scraper.scan_board(object(), job, matcher, status, set())
        self.assertEqual([(item["link"].rsplit("/", 1)[1], item["matched_game"]) for item in items],
                         [("3", "Gran Turismo 4"), ("4", "Persona 4")])
        self.assertEqual(fetch.call_args.args[2], None, "a board never read before is asked for everything")
        self.assertEqual(status, {"4chan:vst": {"ok": True, "latest": (NOW - timedelta(minutes=5)).strftime(scraper.TIMESTAMP_FORMAT)}})


class TrySourcesTests(unittest.TestCase):
    """tools/try_sources.py prints what the live sources give. On a pull request its output
    is the public log of the Live checks run, its notices and its summary page."""

    def run_tool(self, boards, feed, github=True):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        summary = self.tmp / "summary.md"
        env = {"GITHUB_ACTIONS": "true" if github else "", "GITHUB_STEP_SUMMARY": str(summary) if github else ""}
        config = make_config(forum("https://forum.example/index.rss", name="Example Forum"), board("vr"), board("v"))
        session = FakeSession({f"https://a.4cdn.org/{code}/catalog.json": reply for code, reply in boards.items()})
        out, error = io.StringIO(), None
        with mock.patch.dict(os.environ, env), mock.patch.object(sys, "argv", ["try_sources.py", "forum", "4chan"]), \
                mock.patch.object(scraper, "load_config", return_value=config), \
                mock.patch.object(scraper, "load_ps2_titles", return_value=scraper.FALLBACK_TITLES), \
                mock.patch.object(scraper, "fetch_feed", return_value=feedparser.parse(feed)), \
                mock.patch.object(scraper, "BOARD_REQUEST_GAP", 0), \
                mock.patch.object(scraper.requests, "Session", return_value=session), contextlib.redirect_stdout(out):
            spec = importlib.util.spec_from_file_location("try_sources", ROOT / "tools" / "try_sources.py")
            tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tool)
            try:
                tool.main()
            except SystemExit as stopped:
                error = str(stopped)
        return out.getvalue(), summary.read_text(encoding="utf-8") if summary.exists() else "", error

    def test_for_boards_it_prints_counts_and_game_names_and_nothing_a_poster_wrote(self):
        hour = timedelta(hours=1)
        catalog = lambda threads: {"body": [{"page": 1, "threads": threads}]}  # noqa: E731
        boards = {
            "vr": catalog([thread(101, NOW - hour, subject="Silent Hill 2 thread SUBJECTWORD", comment="COMMENTWORD it is a masterpiece"),
                           thread(102, NOW - 2 * hour, comment="Is Shadow of the Colossus PRIVATEWORD worth it"),
                           thread(103, NOW - 3 * hour, subject="dragon age general LOOSEWORD", comment="nothing here"),
                           thread(104, NOW - timedelta(days=400), subject="Okami general OLDWORD")]),
            "v": catalog([thread(900, NOW - hour, comment="NOTAGAME thread")]),
        }
        # A forum's headline is somebody else's text too: it must not be able to start a line of
        # its own, where GitHub would read "::error ..." as a command.
        feed = rss("Gaming", [("Okami&#10;::error file=scraper.py,line=1::INJECTED&#13;::stop-commands::x thread",
                               "https://forum.example/threads/1/", None, NOW - hour)])
        out, summary, error = self.run_tool(boards, feed)
        self.assertIsNone(error)
        for word in ("SUBJECTWORD", "COMMENTWORD", "PRIVATEWORD", "LOOSEWORD", "OLDWORD", "NOTAGAME", "masterpiece", *POSTER_WORDS):
            self.assertNotIn(word.lower(), (out + summary).lower(), word)
        for text in (out, summary):
            self.assertIn("4 live threads (3 with a subject)", text)
            self.assertIn("3 name a PS2 game: 2 in the subject, 1 in the comment", text)
            self.assertIn("2 of those were started in the last 14 days and would enter the feed: ", text)
            for game in ("Silent Hill 2", "Shadow of the Colossus", "Okami"):
                self.assertIn(game, text)
        commands = [line for line in out.splitlines() if line.lstrip().startswith("::")]
        self.assertTrue(commands and all(line.startswith("::notice title=") for line in commands), commands)
        self.assertIn("INJECTED", out, "the forum headline is still shown, on its own line's tail")
        self.assertIn("All 3 sources answered.", out)

        # Away from GitHub it only prints; and a board that cannot be read fails the check by name.
        boards["v"] = {"status": 403, "body": "REFUSEDWORD"}
        out, summary, error = self.run_tool(boards, feed, github=False)
        self.assertEqual(summary, "")
        self.assertNotIn("::notice", out)
        self.assertIn("FAILED: HTTP 403", out)
        self.assertNotIn("REFUSEDWORD", out)
        self.assertEqual(error.strip(), "1 of 3 sources could not be read: /v/")


class FixtureSamplerTests(unittest.TestCase):
    """tools/sample_fixtures.py draws real headlines for the matcher's test corpus."""

    def test_lines_the_scraper_wrote_itself_are_never_drawn(self):
        """A 4chan row's headline is made from the games it matched, so as a test of the
        matcher it would always pass, and it would crowd real headlines out of the sample."""
        spec = importlib.util.spec_from_file_location("sample_fixtures", ROOT / "tools" / "sample_fixtures.py")
        sampler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sampler)
        with tempfile.TemporaryDirectory() as tmp:
            feed, archive = Path(tmp) / "sentiment_feed.json", Path(tmp) / "archive"
            archive.mkdir()
            feed.write_text(json.dumps({"items": [
                {"headline": "Okami HD review roundup", "source": "Example News", "source_type": "news", "matched_game": "Okami"},
                {"headline": "Thread on /vr/ naming Okami", "source": "4chan /vr/", "source_type": "4chan", "matched_game": "Okami"},
                {"headline": "A story from before items said where they came from", "source": "Old News"}]}), encoding="utf-8")
            (archive / "2026-10.json").write_text(json.dumps([
                {"d": "2026-10-01 10:00 UTC", "g": "Ico", "h": "Ico turns 25", "s": "Example News", "t": "news"},
                {"d": "2026-10-01 11:00 UTC", "g": "Ico", "h": "Thread on /v/ naming Ico", "s": "4chan /v/", "t": "4chan"}]), encoding="utf-8")
            with mock.patch.object(sampler, "FEED", feed), mock.patch.object(sampler, "ARCHIVE_DIR", archive), mock.patch("builtins.print"):
                headlines = sorted(item["headline"] for item in sampler.load_items())
        self.assertEqual(headlines, ["A story from before items said where they came from", "Ico turns 25", "Okami HD review roundup"])
        self.assertEqual(sampler.GENERATED_TYPES, {scraper.BOARD_TYPE})


class LiveChecksWorkflowTests(unittest.TestCase):
    """The one workflow that runs a pull request's own code against the real sites. That is
    only safe while it holds nothing worth stealing and cannot change anything."""

    def setUp(self):
        self.text = (ROOT / ".github" / "workflows" / "live-checks.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.code = "\n".join(line for line in self.text.splitlines() if not line.lstrip().startswith("#"))

    def test_it_holds_no_key_and_can_write_nothing(self):
        self.assertIn("\npermissions:\n  contents: read\n", self.code)
        self.assertEqual(self.code.count("permissions:"), 1, "no job widens what the workflow may do")
        for forbidden in ("secrets.", "EBAY", "pull_request_target", "git push", "git commit", "write"):
            self.assertNotIn(forbidden, self.code, forbidden)

    def test_it_cannot_start_the_job_that_holds_the_ebay_key(self):
        """ebay.yml follows the scraper workflow by name; a second workflow under that name
        would be a pull-request trigger for it."""
        name = lambda path: re.search(r"^name: *(.+)$", path.read_text(encoding="utf-8"), re.M).group(1).strip()  # noqa: E731
        names = [name(path) for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))]
        self.assertEqual(len(names), len(set(names)), names)
        ebay = (ROOT / ".github" / "workflows" / "ebay.yml").read_text(encoding="utf-8")
        self.assertNotIn("Live checks", ebay)
        self.assertNotIn("pull_request", (ROOT / ".github" / "workflows" / "scraper.yml").read_text(encoding="utf-8"))

    def test_it_tries_the_sources_and_compares_the_scraper_with_main(self):
        self.assertIn("python tools/try_sources.py forum 4chan", self.code)
        self.assertIn("python tools/regression_check.py --ref origin/main", self.code)
        self.assertIn("fetch-depth: 0", self.code)
        for path in ("scraper.py", "feeds.json", "tools/**"):
            self.assertIn(f"      - {path}\n", self.code)


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
                           podcast("https://example.com/pod.rss"), forum("https://forum.example.com/index.rss"),
                           board("vr"), poll_every_hours={"podcast": 6})
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
            lambda c: c["sources"][4].update(url="forum.example.com/index.rss"),
            lambda c: c["sources"][4].pop("url"),
            lambda c: c["sources"].append(forum("https://forum.example.com/index.rss", name="Again")),
            lambda c: c["sources"].append(forum("https://other.example.com/index.rss", name="Another")),
            *[(lambda code: lambda c: c["sources"][5].update(board=code))(code)
              for code in ("v", "vrpg", "s4s", "3", "VR", "/vr/", "v r", "", "toolong", "vr\n", "v-r", "ｖｒ", 4, None, ["vr"], {"a": 1}, True)],
            lambda c: c["sources"][5].pop("board"),
            lambda c: c["sources"].append(board("vr")),
            lambda c: c["sources"].append(board("vg")),
            lambda c: c["sources"][5].update(url="https://example.com/feed"),
            lambda c: c["poll_every_hours"].update({"forum": 2, "4chan": 3}),
            lambda c: c["poll_every_hours"].update({"4chan": 0}),
            lambda c: c["roles"]["anonymous"].update(weight=0),
            lambda c: c["sources"][5].update(role="nope"),
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
