"""Scrapes gaming news and Reddit RSS feeds, matches headlines against the PS2
library and writes a sentiment snapshot to data/sentiment_feed.json."""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from rapidfuzz import fuzz, process, utils

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "ps2_database.json"
OUTPUT_PATH = DATA_DIR / "sentiment_feed.json"
DB_URL = "https://raw.githubusercontent.com/garbled1/ps_ripper/master/db_playstation2_official_eu.json"

USER_AGENT = "ps2-sentiment-tracker/1.0 (+https://github.com/beskay/ps2-sentiment-tracker)"
REQUEST_TIMEOUT = 15
MAX_ENTRIES_PER_FEED = 50
MATCH_THRESHOLD = 88
MAX_RATE_LIMIT_WAIT = 90  # seconds

NEWS_FEEDS = [
    # --- Major Global Outlets & Magazines ---
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
    # --- Official Platform Blogs ---
    "https://blog.playstation.com/feed/",
    "https://news.xbox.com/en-us/feed/",
    # --- Spanish & Portuguese Feeds ---
    "https://latam.ign.com/feed.xml",
    "https://www.eurogamer.pt/feed",
    "https://vandal.elespanol.com/xml.cgi",
]

# Reddit allows roughly one unauthenticated request per minute, so subreddits
# are fetched as a few combined multireddit feeds instead of one feed each.
SUBREDDIT_GROUPS = [
    # --- Dedicated PS2 & Emulation Hubs ---
    ["ps2", "ps2homebrew", "PCSX2", "playstation2"],
    # --- Collecting, Retro & Emulation ---
    ["gamecollecting", "LimitedPrintGames", "NSCollectors", "Steelbook", "gameverifying",
     "retrogaming", "classicgaming", "emulation", "psx"],
    # --- High-Traffic General Communities ---
    ["gaming", "Games", "pcgaming", "truegaming", "ShouldIbuythisgame", "gamingsuggestions",
     "pcmasterrace", "NintendoSwitch", "PlayStation", "xboxone", "SteamDeck", "jrpg",
     "patientgamers"],
]

RSS_FEEDS = NEWS_FEEDS + [
    f"https://www.reddit.com/r/{'+'.join(group)}/.rss?limit={MAX_ENTRIES_PER_FEED}"
    for group in SUBREDDIT_GROUPS
]
TOTAL_SOURCES = len(NEWS_FEEDS) + sum(len(group) for group in SUBREDDIT_GROUPS)

REMASTER_PATTERN = re.compile(
    r"\b(remaster|remake|reboot|reviv|hd version|director['’]s cut|enhanced"
    r"|collections?\b|ports?\b|ported\b|returns?\b)",
    re.IGNORECASE,
)


def _word_patterns(words):
    return [re.compile(rf"\b{re.escape(word)}", re.IGNORECASE) for word in words]


POSITIVE_WORDS = _word_patterns([
    "masterpiece", "amazing", "love", "best", "classic", "brilliant", "hype",
    "return", "remaster", "announce", "revival",
])
NEGATIVE_WORDS = _word_patterns(["bug", "worst", "broken", "terrible", "flop", "disaster"])

# Used only when both the online index and the local cache are unavailable.
FALLBACK_TITLES = [
    ".hack//Infection", ".hack//Mutation", ".hack//Outbreak", ".hack//Quarantine",
    ".hack//G.U. Vol. 1//Rebirth", ".hack//G.U. Vol. 2//Reminisce", ".hack//G.U. Vol. 3//Redemption",
    "Silent Hill 2", "Silent Hill 3", "Silent Hill 4: The Room", "Silent Hill: Origins",
    "Silent Hill: Shattered Memories",
    "Metal Gear Solid 2: Sons of Liberty", "Metal Gear Solid 3: Snake Eater", "Metal Gear Solid: Portable Ops",
    "Grand Theft Auto III", "Grand Theft Auto: Vice City", "Grand Theft Auto: San Andreas",
    "Grand Theft Auto: Liberty City Stories", "Grand Theft Auto: Vice City Stories",
    "Shadow of the Colossus", "Ico", "Persona 3", "Persona 3 FES", "Persona 4", "Okami",
    "Final Fantasy X", "Final Fantasy X-2", "Final Fantasy XI", "Final Fantasy XII",
    "God of War", "God of War II",
    "Resident Evil 4", "Resident Evil Code: Veronica X", "Resident Evil Outbreak",
    "Kingdom Hearts", "Kingdom Hearts II", "Bully", "Burnout 3: Takedown", "Burnout Revenge", "Black",
    "SSX Tricky", "SSX 3", "Tony Hawk's Pro Skater 3", "Tony Hawk's Underground", "Tony Hawk's Underground 2",
    "Ratchet & Clank", "Ratchet & Clank: Going Commando", "Ratchet & Clank: Up Your Arsenal",
    "Ratchet: Deadlocked",
    "Jak and Daxter: The Precursor Legacy", "Jak II", "Jak 3", "Jak X: Combat Racing",
    "Sly Cooper and the Thievius Raccoonus", "Sly 2: Band of Thieves", "Sly 3: Honor Among Thieves",
    "Zone of the Enders", "Zone of the Enders: The 2nd Runner",
    "Gran Turismo 3: A-Spec", "Gran Turismo 4", "Tekken 4", "Tekken 5", "Virtua Fighter 4",
    "Soulcalibur II", "Soulcalibur III", "Dragon Ball Z: Budokai 3", "Dragon Ball Z: Budokai Tenkaichi 3",
    "Xenosaga Episode I", "Xenosaga Episode II", "Xenosaga Episode III",
    "Suikoden III", "Suikoden IV", "Suikoden V", "Suikoden Tactics",
    "Star Ocean: Till the End of Time", "Valkyrie Profile 2: Silmeria", "Odin Sphere",
    "Castlevania: Lament of Innocence", "Castlevania: Curse of Darkness",
    "Max Payne", "Max Payne 2: The Fall of Max Payne",
    "Prince of Persia: The Sands of Time", "Prince of Persia: Warrior Within",
    "Prince of Persia: The Two Thrones",
    "Viewtiful Joe", "Viewtiful Joe 2", "Dark Cloud", "Dark Chronicle", "Yakuza", "Yakuza 2",
    "Onimusha: Warlords", "Onimusha 2: Samurai's Destiny", "Onimusha 3: Demon Siege",
    "Onimusha: Dawn of Dreams",
    "Shin Megami Tensei: Nocturne", "Shin Megami Tensei: Digital Devil Saga",
    "Shin Megami Tensei: Digital Devil Saga 2", "Rogue Galaxy",
]


def load_ps2_titles(session):
    """Returns PS2 titles from the online index, else the local cache, else the fallback list."""
    try:
        response = session.get(DB_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        titles = sorted({t.strip() for t in response.json().values() if isinstance(t, str) and t.strip()})
        if len(titles) > 500:
            DB_PATH.write_text(json.dumps(titles, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Loaded {len(titles)} titles from online index")
            return titles
    except (requests.RequestException, ValueError, AttributeError) as e:
        print(f"Could not fetch online index ({e})")

    try:
        titles = json.loads(DB_PATH.read_text(encoding="utf-8"))
        if isinstance(titles, list) and len(titles) > 500:
            print(f"Loaded {len(titles)} titles from local cache")
            return titles
    except (OSError, ValueError):
        pass

    print(f"Using built-in fallback list of {len(FALLBACK_TITLES)} titles")
    return FALLBACK_TITLES


def fetch_feed(session, url):
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code == 429:
        wait = min(int(float(response.headers.get("x-ratelimit-reset", 60))) + 1, MAX_RATE_LIMIT_WAIT)
        print(f"  rate limited, retrying in {wait}s")
        time.sleep(wait)
        response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return feedparser.parse(response.content)


def analyze_sentiment(text):
    score = 50
    score += 10 * sum(1 for p in POSITIVE_WORDS if p.search(text))
    score -= 15 * sum(1 for p in NEGATIVE_WORDS if p.search(text))
    return max(10, min(100, score))


def entry_source(entry, feed):
    tags = entry.get("tags")
    if "reddit.com" in entry.get("link", "") and tags:
        return f"r/{tags[0]['term']}"
    return feed.feed.get("title", "Unknown source").split(" | ")[0]


def entry_timestamp(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    dt = datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def analyze_entry(entry, feed, titles):
    headline = entry.title.strip()
    match = process.extractOne(
        headline, titles, scorer=fuzz.WRatio, processor=utils.default_process, score_cutoff=MATCH_THRESHOLD
    )
    return {
        "headline": headline,
        "source": entry_source(entry, feed),
        "link": entry.get("link", "#"),
        "matched_game": match[0] if match else None,
        "match_score": round(match[1]) if match else 0,
        "is_remaster_rumor": bool(REMASTER_PATTERN.search(headline)),
        "sentiment": analyze_sentiment(headline),
        "timestamp": entry_timestamp(entry),
    }


def run_scraper():
    DATA_DIR.mkdir(exist_ok=True)
    items = []
    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        titles = load_ps2_titles(session)

        print(f"Scanning {len(RSS_FEEDS)} feeds against {len(titles)} PS2 titles...")
        for url in RSS_FEEDS:
            try:
                feed = fetch_feed(session, url)
            except requests.RequestException as e:
                print(f"  FAILED {url}: {e}")
                continue
            entries = [e for e in feed.entries[:MAX_ENTRIES_PER_FEED] if e.get("title")]
            items.extend(analyze_entry(e, feed, titles) for e in entries)
            print(f"  {len(entries):3d} items  {url}")

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_tracked_feeds": TOTAL_SOURCES,
        "items": items,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(items)} items to {OUTPUT_PATH}")


if __name__ == "__main__":
    run_scraper()
