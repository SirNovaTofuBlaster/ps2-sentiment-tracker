"""Scrapes gaming news and Reddit RSS feeds, matches headlines against the PS2
library and writes a sentiment snapshot to data/sentiment_feed.json.

Each run merges new headlines into the previous snapshot (kept for
RETENTION_DAYS), leaves the file untouched when nothing changed, and exits
non-zero when too many feeds fail so a bad run never overwrites good data."""

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from rapidfuzz import fuzz, process, utils

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "ps2_database.json"
OUTPUT_PATH = DATA_DIR / "sentiment_feed.json"

# Regional PS2 title indexes (serial -> title). Titles from every source that
# loads are merged, and the merged set is cached in DB_PATH.
DB_SOURCES = [
    ("EU", "https://raw.githubusercontent.com/garbled1/ps_ripper/master/db_playstation2_official_eu.json"),
    ("US", "https://raw.githubusercontent.com/workhorsylegacy/identify_playstation2_games/master/db_playstation2_official_us.json"),
    # Romanised Japanese names; enable if you want them (adds a lot of noise):
    # ("JP", "https://raw.githubusercontent.com/workhorsylegacy/identify_playstation2_games/master/db_playstation2_official_jp.json"),
]

USER_AGENT = "ps2-sentiment-tracker/1.0 (+https://github.com/beskay/ps2-sentiment-tracker)"
REQUEST_TIMEOUT = 15
MAX_ENTRIES_PER_FEED = 50
MATCH_THRESHOLD = 88
MAX_RATE_LIMIT_WAIT = 90  # seconds
MIN_INDEX_TITLES = 500
SHORT_TITLE_MAX_LEN = 8  # normalised titles shorter than this are matched exactly, not fuzzily
RETENTION_DAYS = 14
MAX_ITEMS = 5000
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M UTC"

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

# Posts from these subreddits count as PS2 context on their own.
PS2_SUBREDDITS = {name.lower() for name in SUBREDDIT_GROUPS[0]}
PS2_CONTEXT_PATTERN = re.compile(r"\b(?:ps2|ps 2|playstation ?2|pcsx2)\b", re.IGNORECASE)

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

# --- Title cleaning -------------------------------------------------------
# Index entries that are discs/tools rather than games.
JUNK_TITLE_PATTERN = re.compile(
    r"zzz_|demo disc|magazine demo|hits demo|network access disc|swap magic"
    r"|action replay|greatest hits vol|\bsampler\b",
    re.IGNORECASE,
)
BRACKET_PATTERN = re.compile(r"\s*\[[^\]]*\]")  # "[Platinum]", "[Demo]", "[Der Herr der Ringe]"
INVERTED_ARTICLE_PATTERN = re.compile(r"^(.+),\s*(The|A|An)$")  # "Thing, The" -> "The Thing"
NUMERAL_TOKEN = re.compile(r"(?:\d+|[ivx]+)")  # digits and roman numerals

# Short one-word titles that are common English words / names need PS2 context
# in the headline to count as a match. These distinctive ones do not.
DISTINCTIVE_SHORT = {"ico", "okami", "vexx", "genji", "kessen"}

# Abbreviations and alternate names that fuzzy matching can't bridge.
# Keys are matched against runs of up to 4 words in the headline.
TITLE_ALIASES = {
    "gta 3": "Grand Theft Auto III",
    "gta iii": "Grand Theft Auto III",
    "gta vice city": "Grand Theft Auto: Vice City",
    "gta vc": "Grand Theft Auto: Vice City",
    "gta san andreas": "Grand Theft Auto: San Andreas",
    "gta sa": "Grand Theft Auto: San Andreas",
    "gta lcs": "Grand Theft Auto: Liberty City Stories",
    "gta vcs": "Grand Theft Auto: Vice City Stories",
    "re4": "Resident Evil 4",
    "code veronica": "Resident Evil Code: Veronica X",
    "mgs2": "Metal Gear Solid 2: Sons of Liberty",
    "mgs3": "Metal Gear Solid 3: Snake Eater",
    "snake eater": "Metal Gear Solid 3: Snake Eater",
    "ffx": "Final Fantasy X",
    "ff10": "Final Fantasy X",
    "ffx 2": "Final Fantasy X-2",
    "ff12": "Final Fantasy XII",
    "ffxii": "Final Fantasy XII",
    "kh2": "Kingdom Hearts II",
    "dmc3": "Devil May Cry 3: Dante's Awakening",
    "sh2": "Silent Hill 2",
    "sh3": "Silent Hill 3",
    "sh4": "Silent Hill 4: The Room",
    "sotc": "Shadow of the Colossus",
    "p3fes": "Persona 3 FES",
    "smt nocturne": "Shin Megami Tensei: Nocturne",
    "dq8": "Dragon Quest VIII: Journey of the Cursed King",
    "dragon quest 8": "Dragon Quest VIII: Journey of the Cursed King",
    "gow2": "God of War II",
    "god of war 2": "God of War II",
    "jak 2": "Jak II",
    "jak and daxter": "Jak and Daxter: The Precursor Legacy",
    "rockstar bully": "Bully",
    "canis canem edit": "Bully",
}

# Used only to guarantee coverage of well-known titles; always merged into the
# index titles (e.g. names that differ between regions, like Bully).
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


def clean_title(raw):
    """Normalises one index entry; returns None for entries that aren't games."""
    if not isinstance(raw, str) or JUNK_TITLE_PATTERN.search(raw):
        return None
    title = BRACKET_PATTERN.sub("", raw)
    title = re.sub(r"\s+", " ", title).lstrip(". ").rstrip()
    match = INVERTED_ARTICLE_PATTERN.match(title)
    if match:
        title = f"{match.group(2)} {match.group(1)}"
    return title or None


def read_cached_titles():
    try:
        raw = json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {t for t in map(clean_title, raw) if t} if isinstance(raw, list) else set()


def load_ps2_titles(session):
    """Merges the online indexes, the local cache and the fallback list into one sorted title list."""
    fetched = set()
    for label, url in DB_SOURCES:
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            entries = list(response.json().values())
        except (requests.RequestException, ValueError, AttributeError) as e:
            print(f"Could not fetch {label} index ({e})")
            continue
        cleaned = {t for t in map(clean_title, entries) if t}
        print(f"Loaded {len(cleaned)} titles from {label} index")
        fetched |= cleaned

    cached = read_cached_titles()
    indexed = fetched | cached  # a failed source never shrinks the cache
    if len(fetched) >= MIN_INDEX_TITLES and indexed != cached:
        DB_PATH.write_text(json.dumps(sorted(indexed), indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    if not indexed:
        print("No index available; using the built-in fallback list only")
    return sorted(indexed | set(FALLBACK_TITLES))


class TitleMatcher:
    """Matches headlines to PS2 titles: aliases first, then exact short titles, then fuzzy."""

    def __init__(self, titles):
        self.fuzzy_titles, self.fuzzy_norms, self.fuzzy_required = [], [], []
        self.short = {}  # normalised title -> (title, needs_ps2_context)
        seen = set()
        for title in titles:
            norm = utils.default_process(title)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            if len(norm) >= SHORT_TITLE_MAX_LEN:
                self.fuzzy_titles.append(title)
                self.fuzzy_norms.append(norm)
                self.fuzzy_required.append(
                    {t for t in norm.split() if NUMERAL_TOKEN.fullmatch(t)}
                )
            else:
                ambiguous = " " not in norm and not any(c.isdigit() for c in norm) \
                    and norm not in DISTINCTIVE_SHORT
                self.short[norm] = (title, ambiguous)
        self.aliases = {utils.default_process(k): v for k, v in TITLE_ALIASES.items()}

    def summary(self):
        return f"{len(self.fuzzy_titles)} fuzzy, {len(self.short)} short, {len(self.aliases)} aliases"

    @staticmethod
    def _has_ps2_context(headline, source):
        return bool(PS2_CONTEXT_PATTERN.search(headline)) or source.lower().removeprefix("r/") in PS2_SUBREDDITS

    def match(self, headline, source=""):
        """Returns (title, score) or (None, 0)."""
        norm = utils.default_process(headline)
        tokens = norm.split()
        grams = {" ".join(tokens[i:i + n]) for n in range(1, 5) for i in range(len(tokens) - n + 1)}
        ordered = sorted(grams, key=lambda g: (-len(g), g))

        for gram in ordered:
            if gram in self.aliases:
                return self.aliases[gram], 100

        for gram in ordered:
            if gram in self.short:
                title, ambiguous = self.short[gram]
                if ambiguous and not self._has_ps2_context(headline, source):
                    continue
                return title, 100

        token_set = set(tokens)
        candidates = process.extract(
            norm, self.fuzzy_norms, scorer=fuzz.WRatio, score_cutoff=MATCH_THRESHOLD, limit=5
        )
        for _, score, index in candidates:
            # A title's numbers/roman numerals must appear in the headline, so
            # "Final Fantasy X" doesn't match "Final Fantasy XVI" and "FIFA 25"
            # doesn't match "FIFA 2005".
            if self.fuzzy_required[index] <= token_set:
                return self.fuzzy_titles[index], round(score)
        return None, 0


def _retry_delay(response):
    header = response.headers.get("x-ratelimit-reset") or response.headers.get("retry-after") or 60
    try:
        seconds = int(float(header))
    except ValueError:
        seconds = 60
    return min(seconds + 1, MAX_RATE_LIMIT_WAIT)


def fetch_feed(session, url):
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code == 429:
        wait = _retry_delay(response)
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
    """Returns (timestamp string, whether the entry carried a real date)."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    dt = datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else datetime.now(timezone.utc)
    return dt.strftime(TIMESTAMP_FORMAT), bool(parsed)


def item_key(item):
    link = item.get("link", "#")
    return link if link != "#" else f"{item.get('source', '')}|{item.get('headline', '')}"


def analyze_entry(entry, feed, matcher, first_seen):
    headline = entry.title.strip()
    source = entry_source(entry, feed)
    game, score = matcher.match(headline, source)
    timestamp, dated = entry_timestamp(entry)
    item = {
        "headline": headline,
        "source": source,
        "link": entry.get("link", "#"),
        "matched_game": game,
        "match_score": score,
        "is_remaster_rumor": bool(REMASTER_PATTERN.search(headline)),
        "sentiment": analyze_sentiment(headline),
        "timestamp": timestamp,
    }
    if not dated:
        # Undated entries keep the time they were first seen so they don't
        # look "new" (and change the file) on every run.
        item["timestamp"] = first_seen.get(item_key(item), timestamp)
    return item


def load_previous_items():
    try:
        items = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError, AttributeError):
        return []
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def run_scraper():
    DATA_DIR.mkdir(exist_ok=True)
    previous = load_previous_items()
    first_seen = {item_key(i): i["timestamp"] for i in previous if i.get("timestamp")}

    items = []
    failures = 0
    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        matcher = TitleMatcher(load_ps2_titles(session))

        print(f"Scanning {len(RSS_FEEDS)} feeds against PS2 titles ({matcher.summary()})...")
        for url in RSS_FEEDS:
            try:
                feed = fetch_feed(session, url)
            except (requests.RequestException, ValueError) as e:
                failures += 1
                print(f"  FAILED {url}: {e}")
                continue
            if feed.get("bozo") and not feed.entries:
                failures += 1
                print(f"  FAILED {url}: unreadable feed")
                continue
            entries = [e for e in feed.entries[:MAX_ENTRIES_PER_FEED] if e.get("title")]
            items.extend(analyze_entry(e, feed, matcher, first_seen) for e in entries)
            print(f"  {len(entries):3d} items  {url}")

    # Never replace a good snapshot with the result of a mostly-failed run.
    if not items or failures > len(RSS_FEEDS) // 2:
        raise SystemExit(
            f"Aborting: {failures}/{len(RSS_FEEDS)} feeds failed and {len(items)} items were "
            "collected; keeping the previous snapshot."
        )

    # Merge into the previous snapshot: new data wins, old items age out.
    merged = {item_key(i): i for i in previous}
    merged.update({item_key(i): i for i in items})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime(TIMESTAMP_FORMAT)
    merged_items = [i for i in merged.values() if i.get("timestamp", "") >= cutoff]
    merged_items.sort(key=lambda item: item["timestamp"], reverse=True)
    merged_items = merged_items[:MAX_ITEMS]

    if merged_items == previous:
        print("No new or changed items; leaving snapshot untouched.")
        return

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_tracked_feeds": TOTAL_SOURCES,
        "items": merged_items,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(merged_items)} items ({len(items)} fetched this run, {failures} feed failures) to {OUTPUT_PATH}")


if __name__ == "__main__":
    run_scraper()
