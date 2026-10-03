"""Scrapes gaming news, Reddit, YouTube and podcast feeds, matches headlines against
the PS2 library and writes a sentiment snapshot to data/sentiment_feed.json.

Sources live in feeds.json (edit it by hand or from the dashboard's Sources panel).
Each run merges new headlines into the previous snapshot (kept for RETENTION_DAYS),
leaves the file untouched when nothing changed, and exits non-zero when too many
news/Reddit feeds fail so a bad run never overwrites good data. Per-feed health is
written to data/feed_status.json."""

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
from rapidfuzz import fuzz, process, utils

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "ps2_database.json"
OUTPUT_PATH = DATA_DIR / "sentiment_feed.json"
STATUS_PATH = DATA_DIR / "feed_status.json"
YOUTUBE_IDS_PATH = DATA_DIR / "youtube_channels.json"  # channel link -> channel ID, filled by the scraper
POLL_STATE_PATH = DATA_DIR / "poll_state.json"  # when each source type with poll_every_hours > 1 was last fetched
FEEDS_PATH = ROOT / "feeds.json"

# Regional PS2 title indexes (serial -> title). Titles from every source that
# loads are merged, and the merged set is cached in DB_PATH.
DB_SOURCES = [
    ("EU", "https://raw.githubusercontent.com/garbled1/ps_ripper/master/db_playstation2_official_eu.json"),
    ("US", "https://raw.githubusercontent.com/workhorsylegacy/identify_playstation2_games/master/db_playstation2_official_us.json"),
    # Romanised Japanese names; enable if you want them (adds a lot of noise):
    # ("JP", "https://raw.githubusercontent.com/workhorsylegacy/identify_playstation2_games/master/db_playstation2_official_jp.json"),
]

# Reddit asks for "<platform>:<app-id>:<version> (by /u/<name>)" and throttles
# generic agents harder. Put your own Reddit username here.
USER_AGENT = "python:ps2-sentiment-tracker:1.1 (by /u/SirNovaTofuBlaster)"
REQUEST_TIMEOUT = 15
MAX_ENTRIES_PER_FEED = 50
MATCH_THRESHOLD = 88
BODY_MATCH_THRESHOLD = 93  # body text is noisier than a headline, so it has to match harder
MAX_RATE_LIMIT_WAIT = 90  # seconds
MIN_INDEX_TITLES = 500
SHORT_TITLE_MAX_LEN = 8  # normalised titles shorter than this are matched exactly, not fuzzily
MAX_GRAM_WORDS = 6  # longest run of headline words compared against a title
MIN_GRAM_CHARS = 8  # shorter runs of words match too many titles by accident
MAX_BODY_TOKENS = 120  # only the start of a summary/description is searched
COMMON_TOKEN_SHARE = 0.01  # tokens in more than this share of titles don't narrow the search
RETENTION_DAYS = 14
MAX_ITEMS = 5000
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M UTC"
FETCH_TIME_BUDGET = 600  # seconds; YouTube/podcast feeds not reached by then are skipped this run
HOST_FAILURE_LIMIT = 3  # consecutive YouTube/podcast host-level failures skip the rest of that host
POLL_TOLERANCE = timedelta(minutes=20)  # hourly runs drift a little; don't miss a slot by minutes

# Sources are configured in feeds.json. News and Reddit are the core feeds: when
# too many of them fail the run aborts. YouTube and podcast feeds are extras whose
# failures are only reported, so an outage on either platform can't block updates.
SOURCE_TYPES = ("news", "reddit", "youtube", "podcast")
CORE_TYPES = {"news", "reddit"}
YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
# Reddit allows roughly one unauthenticated request per minute, so subreddits that
# share a group are fetched as one combined multireddit feed instead of one feed each.
REDDIT_FEED_URL = "https://www.reddit.com/r/{}/.rss?limit={}"
SOURCE_PREFIX = {"youtube": "YouTube: ", "podcast": "Podcast: "}
CHANNEL_ID_PATTERN = re.compile(r"UC[0-9A-Za-z_-]{22}")
# The dashboard uses this exact pattern too, so a feed link it accepts always loads here:
# http(s), an ASCII host name with at least one dot, an optional port, printable ASCII after.
FEED_URL_PATTERN = re.compile(r"https?://(?:[A-Za-z0-9-]+\.)+[A-Za-z0-9-]+(?::[0-9]{1,5})?(?:[/?#][!-~]*)?")
# YouTube sources can also be added by channel link (the dashboard normalises pasted
# links to this form); the scraper looks the channel ID up once and remembers it.
YOUTUBE_CHANNEL_URL_PATTERN = re.compile(r"https://www\.youtube\.com/(?:@|c/|user/)[^/?#\s]+")
CANONICAL_CHANNEL_PATTERN = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})"')
SUBREDDIT_PATTERN = re.compile(r"[A-Za-z0-9_]{2,21}")

# Posts from sources with this role count as PS2 context on their own.
PS2_ROLE = "ps2"
PS2_CONTEXT_PATTERN = re.compile(r"\b(?:ps2|ps 2|playstation ?2|pcsx2)\b", re.IGNORECASE)

# Remaster wording splits in two. Strong terms flag on their own; weak ones are
# ordinary English ("my PS2 collection", "he returns to the series") and only
# flag when the item also matched a PS2 game.
REMASTER_STRONG_PATTERN = re.compile(
    r"\b(remaster|remake|reboot|reviv|hd version|director['’]s cut|re-?release)",
    re.IGNORECASE,
)
REMASTER_WEAK_PATTERN = re.compile(
    r"\b(collections?\b|ports?\b|ported\b|returns?\b|enhanced)",
    re.IGNORECASE,
)
# Kept so anything matching either half still matches this name.
REMASTER_PATTERN = re.compile(
    REMASTER_STRONG_PATTERN.pattern + "|" + REMASTER_WEAK_PATTERN.pattern, re.IGNORECASE
)

# Sentiment is about tone, not subject. Words that describe what a story is
# about (remaster, announce, revival) used to count as positive, which scored
# every remaster announcement as good news; they are tracked separately now.
POSITIVE_STEMS = ("masterpiece", "amazing", "love", "best", "classic", "brilliant",
                  "great", "favourite", "favorite", "underrated", "gorgeous", "perfect")
NEGATIVE_STEMS = ("bug", "worst", "broken", "terrible", "flop", "disaster",
                  "disappoint", "overrated", "awful", "unplayable", "janky")
HYPE_STEMS = ("hype", "announce", "revival", "remaster", "remake", "confirmed", "leak")
NEGATORS = {"not", "no", "never", "isn", "aren", "wasn", "doesn", "didn", "won", "hardly", "barely"}
NEGATION_WINDOW = 3  # tokens before a sentiment word that can flip it

# --- Title cleaning -------------------------------------------------------
# Index entries that are discs/tools rather than games.
JUNK_TITLE_PATTERN = re.compile(
    r"zzz_|demo disc|magazine demo|hits demo|network access disc|swap magic"
    r"|action replay|greatest hits vol|\bsampler\b",
    re.IGNORECASE,
)
BRACKET_PATTERN = re.compile(r"\s*\[[^\]]*\]")  # "[Platinum]", "[Demo]", "[Der Herr der Ringe]"
INVERTED_ARTICLE_PATTERN = re.compile(r"^(.+),\s*(The|A|An)$")  # "Thing, The" -> "The Thing"
NUMERAL_TOKEN = re.compile(r"\d+")  # after normalisation every numeral is a digit run
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

# Roman numerals are written both ways ("Jak II" vs "Jak 2", "Final Fantasy X"
# vs "FF10"), so both sides are normalised to digits before anything is compared.
ROMAN_TO_ARABIC = {
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7",
    "viii": "8", "ix": "9", "x": "10", "xi": "11", "xii": "12", "xiii": "13",
    "xiv": "14", "xv": "15", "xvi": "16", "xvii": "17", "xviii": "18",
    "xix": "19", "xx": "20",
}

# Words too common to narrow a search by, on top of the ones measured from the index.
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for", "with",
    "is", "it", "its", "this", "that", "from", "by", "as", "be", "was", "are",
    "game", "games", "ps2", "playstation", "new", "now", "my", "i", "you",
}

# Short one-word titles that are common English words / names need PS2 context
# in the headline to count as a match. These distinctive ones do not.
DISTINCTIVE_SHORT = {"ico", "okami", "vexx", "genji", "kessen"}

# Abbreviations and alternate names that fuzzy matching can't bridge. Roman/Arabic
# pairs are handled by normalisation now, so only true abbreviations belong here.
# Keys are matched against runs of up to 4 words in the headline.
TITLE_ALIASES = {
    "gta 3": "Grand Theft Auto III",
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
    "gow2": "God of War II",
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


def normalise(text):
    """Lower-cases, strips punctuation (rapidfuzz) and turns roman numerals into digits,
    so "Jak II" and "Jak 2" compare equal on both sides of every match."""
    base = utils.default_process(text or "")
    if not base:
        return ""
    return " ".join(ROMAN_TO_ARABIC.get(tok, tok) for tok in base.split())


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
    """Matches text to PS2 titles: aliases, exact short titles, name variants, then fuzzy.

    The fuzzy pass compares runs of words from the text against candidate titles.
    It scores with token_sort_ratio rather than WRatio on purpose: WRatio rewards
    a good *substring* match, so a generic run of words like "collector s edition"
    scored 90 against "The Godfather: Collector's Edition" simply by appearing
    inside it. token_sort_ratio counts what the title has and the text doesn't,
    so a gram has to account for most of a title to match it.

    Candidates are narrowed through a token index first, so most text costs a few
    set lookups instead of thousands of string comparisons."""

    def __init__(self, titles):
        self.fuzzy_titles, self.fuzzy_norms, self.fuzzy_required = [], [], []
        self.short = {}  # normalised title -> (title, needs_ps2_context)
        self.variants = {}  # normalised main title / subtitle -> (title, needs_ps2_context)
        seen = set()
        for title in titles:
            norm = normalise(title)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            if len(norm) >= SHORT_TITLE_MAX_LEN:
                self.fuzzy_titles.append(title)
                self.fuzzy_norms.append(norm)
                self.fuzzy_required.append({t for t in norm.split() if NUMERAL_TOKEN.fullmatch(t)})
            else:
                ambiguous = " " not in norm and not any(c.isdigit() for c in norm) \
                    and norm not in DISTINCTIVE_SHORT
                self.short[norm] = (title, ambiguous)
        self.aliases = {normalise(k): v for k, v in TITLE_ALIASES.items()}
        self._build_token_index()
        self._build_variants(titles, seen)

    def _build_token_index(self):
        """token -> indices of fuzzy titles containing it, skipping tokens so common
        they wouldn't narrow anything down. The distinctive tokens double as the test
        for whether a run of words is worth comparing at all."""
        frequency = Counter()
        for norm in self.fuzzy_norms:
            frequency.update(set(norm.split()))
                # 1% of ~3,100 titles is about 31, which excludes words like "silent" or
        # "hill" that appear across a franchise but still identify it. The cap is
        # on genuinely generic words ("the", "2", "world"), not on series names.
        ceiling = max(30, int(len(self.fuzzy_norms) * COMMON_TOKEN_SHARE))
        self.distinctive_tokens = {t for t, n in frequency.items() if n <= ceiling and t not in STOPWORDS}
        self.token_index = defaultdict(set)
        for index, norm in enumerate(self.fuzzy_norms):
            tokens = set(norm.split()) - STOPWORDS
            distinctive = tokens & self.distinctive_tokens
            # Every title needs at least one way in; a title made only of common
            # words is indexed under its rarest one.
            if not distinctive and tokens:
                distinctive = {min(tokens, key=lambda t: frequency[t])}
            for token in distinctive:
                self.token_index[token].add(index)

    def _build_variants(self, titles, taken):
        """Indexes both halves of a title with a colon as names for it: "Metal Gear
        Solid 3" and "Snake Eater" both mean Metal Gear Solid 3: Snake Eater. A half
        that two different games share ("Prince of Persia", "Silent Hill") is dropped
        as ambiguous; a short one only counts when the text also mentions the PS2."""
        claims = {}
        for title in titles:
            if ":" not in title:
                continue
            head, tail = title.split(":", 1)
            for part in (head, tail):
                name = normalise(part)
                tokens = name.split()
                if len(name) < SHORT_TITLE_MAX_LEN or name in taken or name in self.aliases:
                    continue
                if all(t in STOPWORDS for t in tokens):
                    continue
                if not (set(tokens) & self.distinctive_tokens):
                    continue  # nothing here identifies a particular game
                claims.setdefault(name, set()).add(title)
        for name, owners in claims.items():
            if len(owners) != 1:
                continue  # two games share it: not a usable name
            self.variants[name] = (next(iter(owners)), len(name.split()) < 3)

    def summary(self):
        return (f"{len(self.fuzzy_titles)} fuzzy, {len(self.short)} short, "
                f"{len(self.variants)} variants, {len(self.aliases)} aliases, "
                f"{len(self.token_index)} index tokens")

    @staticmethod
    def _has_ps2_context(text, ps2_source):
        return bool(PS2_CONTEXT_PATTERN.search(text)) or ps2_source

    def _grams(self, tokens):
        """Runs of 2..MAX_GRAM_WORDS words that are long enough and specific enough to
        identify a game, longest first. Single words are left to the alias and short-title
        passes; on their own they match franchises too loosely."""
        grams = {" ".join(tokens[i:i + n])
                 for n in range(2, MAX_GRAM_WORDS + 1)
                 for i in range(len(tokens) - n + 1)}
                # Length alone, plus at least one word that isn't a stopword: a run like
        # "back in the day" or "collector s edition" has nothing to anchor on, while
        # "silent hill 2" does even though "silent" and "hill" recur across a series.
        usable = [g for g in grams
                  if len(g) >= MIN_GRAM_CHARS and (set(g.split()) - STOPWORDS)]
        return sorted(usable, key=lambda g: (-len(g), g))

    def _fuzzy_matches(self, norm, threshold):
        tokens = norm.split()
        if len(tokens) < 2:
            return []
        token_set = set(tokens)
        candidates = set()
        for token in token_set - STOPWORDS:
            candidates |= self.token_index.get(token, frozenset())
        if not candidates:
            return []
        candidates = sorted(candidates)
        candidate_norms = [self.fuzzy_norms[i] for i in candidates]
        found = {}
        for gram in self._grams(tokens):
            hit = process.extractOne(gram, candidate_norms,
                                     scorer=fuzz.token_sort_ratio, score_cutoff=threshold)
            if not hit:
                continue
            index = candidates[hit[2]]
            # A title's numbers must appear in the text, so "Final Fantasy X"
            # doesn't match "Final Fantasy XVI" and "FIFA 25" doesn't match "FIFA 2005".
            if not self.fuzzy_required[index] <= token_set:
                continue
            title = self.fuzzy_titles[index]
            found[title] = max(found.get(title, 0), round(hit[1]))
        return sorted(found.items(), key=lambda pair: -pair[1])

    def match_all(self, text, ps2_source=False, threshold=MATCH_THRESHOLD):
        """Every PS2 title the text mentions, best first, as (title, score, method)."""
        norm = normalise(text)
        if not norm:
            return []
        tokens = norm.split()
        grams = {" ".join(tokens[i:i + n]) for n in range(1, 5) for i in range(len(tokens) - n + 1)}
        ordered = sorted(grams, key=lambda g: (-len(g), g))
        has_context = self._has_ps2_context(text, ps2_source)

        results, seen = [], set()

        def add(title, score, method):
            if title not in seen:
                seen.add(title)
                results.append((title, score, method))

        for gram in ordered:
            if gram in self.aliases:
                add(self.aliases[gram], 100, "alias")
        for gram in ordered:
            if gram in self.short:
                title, ambiguous = self.short[gram]
                if ambiguous and not has_context:
                    continue
                add(title, 100, "exact")
        for gram in ordered:
            if gram in self.variants:
                title, needs_context = self.variants[gram]
                if needs_context and not has_context:
                    continue
                add(title, 92, "variant")
        for title, score in self._fuzzy_matches(norm, threshold):
            add(title, score, "fuzzy")
        return results

    def match(self, text, ps2_source=False):
        """Returns (title, score) or (None, 0) — the best single match, as before."""
        found = self.match_all(text, ps2_source)
        return (found[0][0], found[0][1]) if found else (None, 0)


def _retry_delay(response):
    header = response.headers.get("x-ratelimit-reset") or response.headers.get("retry-after") or 60
    try:
        seconds = int(float(header))
    except ValueError:
        seconds = 60
    return min(seconds + 1, MAX_RATE_LIMIT_WAIT)


def fetch_feed(session, url, retry_rate_limit=True):
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code == 429 and retry_rate_limit:
        wait = _retry_delay(response)
        print(f"  rate limited, retrying in {wait}s")
        time.sleep(wait)
        response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return feedparser.parse(response.content)


def _stem_hit(token, stems):
    return any(token.startswith(stem) for stem in stems)


def analyze_sentiment(text):
    """Tone only. A negator within NEGATION_WINDOW tokens flips a word's sign, so
    "not a masterpiece" no longer reads as praise."""
    tokens = re.findall(r"[a-z]+", (text or "").lower())
    score = 50
    for i, token in enumerate(tokens):
        negated = any(w in NEGATORS for w in tokens[max(0, i - NEGATION_WINDOW):i])
        if _stem_hit(token, POSITIVE_STEMS):
            score += -10 if negated else 10
        elif _stem_hit(token, NEGATIVE_STEMS):
            score += 15 if negated else -15
    return max(10, min(100, score))


def hype_score(text):
    """How much announcement/rumour language an item carries, kept out of sentiment
    so a remaster announcement isn't automatically 'positive'."""
    tokens = re.findall(r"[a-z]+", (text or "").lower())
    return sum(1 for token in tokens if _stem_hit(token, HYPE_STEMS))


def is_remaster(text, matched):
    """Strong wording flags on its own; everyday words like "collection" or "returns"
    only flag alongside a matched PS2 game."""
    if REMASTER_STRONG_PATTERN.search(text):
        return True
    return bool(matched) and bool(REMASTER_WEAK_PATTERN.search(text))


def entry_source(entry, feed, job):
    if job["type"] in SOURCE_PREFIX:  # labelled with the configured name, e.g. "YouTube: IGN"
        return SOURCE_PREFIX[job["type"]] + job["sources"][0]["name"]
    tags = entry.get("tags")
    if "reddit.com" in entry.get("link", "") and tags:
        return f"r/{tags[0]['term']}"
    return feed.feed.get("title", "Unknown source").split(" | ")[0]


def entry_feed_key(entry, job):
    """source_key() of the configured source an entry came from (None if unknown)."""
    if job["type"] == "reddit":
        tags = entry.get("tags")
        term = tags[0].get("term") if tags else None
        return f"reddit:{term.lower()}" if term else None
    return source_key(job["sources"][0])


def entry_body(entry):
    """The start of an entry's summary / description / self-post text, stripped of markup.
    Reddit self-posts, YouTube descriptions and most RSS feeds all carry one, and it
    names games the title doesn't."""
    raw = entry.get("summary") or ""
    if not raw:
        content = entry.get("content") or []
        raw = content[0].get("value", "") if content else ""
    text = HTML_TAG_PATTERN.sub(" ", raw)
    return " ".join(text.split()[:MAX_BODY_TOKENS])


def entry_link(entry, kind, shared_links=frozenset()):
    if kind != "podcast":
        return entry.get("link", "#")
    # Many podcast episodes have no page of their own: no link, a link every episode shares
    # (the show's homepage), or a bare guid instead of a URL. Those use the audio file, so each
    # episode keeps a distinct, working link (the link is also what tells items apart).
    link = entry.get("link") or ""
    if link.startswith(("http://", "https://")) and link not in shared_links:
        return link
    enclosure = next((e.get("href") for e in entry.get("enclosures", []) if e.get("href")), None)
    return enclosure or link or "#"


def shared_links(feed, kind):
    """Episode links that several entries of a podcast feed have in common."""
    if kind != "podcast":
        return frozenset()
    counts = Counter(e.get("link") for e in feed.entries if e.get("link"))
    return frozenset(link for link, count in counts.items() if count > 1)


def entry_timestamp(entry):
    """Returns (timestamp string, whether the entry carried a real date)."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    dt = datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else datetime.now(timezone.utc)
    return dt.strftime(TIMESTAMP_FORMAT), bool(parsed)


def item_key(item):
    link = item.get("link", "#")
    return link if link != "#" else f"{item.get('source', '')}|{item.get('headline', '')}"


def analyze_entry(entry, feed, job, matcher, first_seen, ps2_keys, repeated_links=frozenset()):
    headline = entry.title.strip()
    source = entry_source(entry, feed, job)
    key = entry_feed_key(entry, job)
    ps2_source = key in ps2_keys
    found = matcher.match_all(headline, ps2_source=ps2_source)
    matched_in = "title" if found else None
    if not found:
        # Nothing in the title: try the body, which is noisier, so it has to match
        # harder and the item has to be about the PS2 one way or another.
        body = entry_body(entry)
        if body and (ps2_source or PS2_CONTEXT_PATTERN.search(f"{headline} {body}")):
            found = matcher.match_all(body, ps2_source=ps2_source, threshold=BODY_MATCH_THRESHOLD)
            matched_in = "body" if found else None
    game, score, method = found[0] if found else (None, 0, None)
    timestamp, dated = entry_timestamp(entry)
    item = {
        "headline": headline,
        "source": source,
        "source_type": job["type"],
        "feed": key,
        "link": entry_link(entry, job["type"], repeated_links),
        "matched_game": game,
        "matched_games": [t for t, _, _ in found],
        "match_score": score,
        "match_method": method,
        "matched_in": matched_in,
        "is_remaster_rumor": is_remaster(headline, game),
        "sentiment": analyze_sentiment(headline),
        "hype": hype_score(headline),
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


# --- Source configuration (feeds.json) ------------------------------------

def source_key(src):
    """Stable id linking a source to its items and status; the dashboard derives it the same way."""
    if src["type"] == "youtube":
        return f"youtube:{src.get('channel_id') or src['channel_url'].lower()}"
    if src["type"] == "reddit":
        return f"reddit:{src['subreddit'].lower()}"
    return src["url"]


def _is_weight(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 10


def _is_hours(value):
    # Whole numbers only; 6.0 is accepted because the dashboard's JavaScript can't tell it from 6.
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return value.is_integer() and 1 <= value <= 24
    return isinstance(value, int) and 1 <= value <= 24


def _is_http_url(value):
    return isinstance(value, str) and bool(FEED_URL_PATTERN.fullmatch(value))


def validate_config(config):
    """Returns a list of problems with a feeds.json document (empty when it is usable)."""
    if not isinstance(config, dict):
        return ["the top level must be an object"]
    roles, sources = config.get("roles"), config.get("sources")
    if not isinstance(roles, dict) or not roles:
        return ["'roles' must be a non-empty object"]
    if not isinstance(sources, list):
        return ["'sources' must be a list"]
    problems = [f"role {name!r} needs a 'weight' between 0 and 10"
                for name, role in roles.items() if not isinstance(role, dict) or not _is_weight(role.get("weight"))]
    intervals = config.get("poll_every_hours", {})
    if not isinstance(intervals, dict) or any(kind not in SOURCE_TYPES or not _is_hours(hours)
                                              for kind, hours in intervals.items()):
        problems.append("'poll_every_hours' must map source types to whole hours between 1 and 24")
    seen = set()
    for i, src in enumerate(sources):
        where = f"sources[{i}]"
        if not isinstance(src, dict) or src.get("type") not in SOURCE_TYPES:
            problems.append(f"{where}: 'type' must be one of {', '.join(SOURCE_TYPES)}")
            continue
        kind = src["type"]
        if not isinstance(src.get("name"), str) or not src["name"].strip():
            problems.append(f"{where}: missing 'name'")
        if not isinstance(src.get("enabled"), bool):
            problems.append(f"{where}: 'enabled' must be true or false")
        if not isinstance(src.get("role"), str) or src["role"] not in roles:
            problems.append(f"{where}: unknown role {src.get('role')!r}")
        if "weight" in src and not _is_weight(src["weight"]):
            problems.append(f"{where}: 'weight' must be between 0 and 10")
        if kind == "youtube" and "channel_id" in src:
            field, valid = "channel_id", isinstance(src["channel_id"], str) and CHANNEL_ID_PATTERN.fullmatch(src["channel_id"])
        elif kind == "youtube":
            field, valid = "channel_id/channel_url", (isinstance(src.get("channel_url"), str)
                                                      and YOUTUBE_CHANNEL_URL_PATTERN.fullmatch(src["channel_url"]))
        elif kind == "reddit":
            field, valid = "subreddit/group", (isinstance(src.get("subreddit"), str)
                                               and SUBREDDIT_PATTERN.fullmatch(src["subreddit"])
                                               and isinstance(src.get("group"), str) and src["group"].strip())
        else:
            field, valid = "url", _is_http_url(src.get("url"))
        if not valid:
            problems.append(f"{where}: invalid {field}")
            continue
        key = source_key(src)
        if key in seen:
            problems.append(f"{where}: duplicate source {key}")
        seen.add(key)
    return problems


def load_config():
    """Reads feeds.json; exits with a clear message when it is missing or invalid."""
    try:
        config = json.loads(FEEDS_PATH.read_text(encoding="utf-8-sig"))  # tolerate a BOM from hand edits
    except (OSError, ValueError) as e:
        raise SystemExit(f"Cannot read {FEEDS_PATH.name}: {e}")
    problems = validate_config(config)
    if problems:
        raise SystemExit(f"{FEEDS_PATH.name} is invalid:\n  " + "\n  ".join(problems))
    return config


def build_jobs(config, youtube_ids=None):
    """Turns enabled sources into feeds to fetch, core types first. Subreddits that
    share a group become one multireddit feed (in the order they are listed).
    youtube_ids maps channel links to IDs (see resolve_youtube_links); a YouTube
    source added by link is skipped until its ID is known."""
    jobs, reddit_groups = [], {}
    for src in config["sources"]:
        if not src["enabled"]:
            continue
        if src["type"] == "reddit":
            job = reddit_groups.get(src["group"])
            if job is None:
                job = reddit_groups[src["group"]] = {"type": "reddit", "sources": []}
                jobs.append(job)
            job["sources"].append(src)
        elif src["type"] == "youtube":
            channel_id = src.get("channel_id") or (youtube_ids or {}).get(src["channel_url"].lower())
            if channel_id:
                jobs.append({"type": "youtube", "sources": [src], "url": YOUTUBE_FEED_URL.format(channel_id)})
        else:
            jobs.append({"type": src["type"], "sources": [src], "url": src["url"]})
    for job in reddit_groups.values():
        job["url"] = REDDIT_FEED_URL.format("+".join(s["subreddit"] for s in job["sources"]), MAX_ENTRIES_PER_FEED)
    jobs.sort(key=lambda job: SOURCE_TYPES.index(job["type"]))  # stable: keeps file order within a type
    return jobs


def parse_timestamp(text):
    try:
        return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def due_types(config, now, last_polled=None):
    """Source types to fetch this run. A type with poll_every_hours N is due once about N hours
    have passed since it was last fetched (data/poll_state.json). GitHub often delays or skips
    scheduled runs, so fixed UTC hours could be missed for days. FULL_RUN=1 fetches everything."""
    if os.environ.get("FULL_RUN") == "1":
        return set(SOURCE_TYPES)
    intervals = config.get("poll_every_hours", {})
    due = set()
    for kind in SOURCE_TYPES:
        hours = int(intervals.get(kind, 1))
        last = parse_timestamp((last_polled or {}).get(kind))
        if hours <= 1 or last is None or now - last >= timedelta(hours=hours) - POLL_TOLERANCE:
            due.add(kind)
    return due


def load_json_dict(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def save_json_if_changed(path, value, previous):
    if value != previous:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def select_entries(feed, kind):
    if kind in CORE_TYPES:
        return [e for e in feed.entries[:MAX_ENTRIES_PER_FEED] if e.get("title")]
    # YouTube/podcast feeds aren't guaranteed newest-first (some podcasts list oldest episodes first).
    entries = [e for e in feed.entries if e.get("title")]
    entries.sort(key=lambda e: tuple(e.get("published_parsed") or e.get("updated_parsed") or ()), reverse=True)
    return entries[:MAX_ENTRIES_PER_FEED]


# --- Per-feed health (data/feed_status.json) -------------------------------
# Only fields that change when something actually happens are stored, so the file
# (and the hourly commit) stays unchanged on quiet runs.

def feed_error(e):
    response = getattr(e, "response", None)
    if response is not None:
        return f"HTTP {response.status_code}"
    return type(e).__name__ if isinstance(e, requests.RequestException) else str(e) or type(e).__name__


def host_is_down(e):
    """Connection problems, timeouts, 5xx and 429 mean the host is struggling. Other HTTP errors
    (404, 410...) concern one feed, so they don't count towards skipping the whole host."""
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return True
    response = getattr(e, "response", None)
    return response is not None and (response.status_code >= 500 or response.status_code == 429)


def newest_by_key(feed, job):
    """Newest dated entry per source key in a fetched feed."""
    newest = {}
    for entry in feed.entries:
        timestamp, dated = entry_timestamp(entry)
        key = entry_feed_key(entry, job)
        if dated and key and timestamp > newest.get(key, ""):
            newest[key] = timestamp
    return newest


def record_success(status, key, latest):
    previous_latest = status.get(key, {}).get("latest")
    status[key] = {"ok": True, "latest": max(filter(None, [previous_latest, latest]), default=None)}


def record_failure(status, key, error, now):
    previous = status.get(key, {})
    failing_since = previous.get("failing_since") if previous.get("ok") is False else None
    status[key] = {"ok": False, "error": error, "failing_since": failing_since or now,
                   "latest": previous.get("latest")}


# --- YouTube sources added by channel link ----------------------------------

def fetch_channel_id(session, url):
    """Reads the channel ID from a channel page such as https://www.youtube.com/@IGN."""
    # SOCS=CAI skips the cookie-consent page YouTube shows in some regions.
    response = session.get(url, timeout=REQUEST_TIMEOUT, cookies={"SOCS": "CAI"})
    response.raise_for_status()
    match = CANONICAL_CHANNEL_PATTERN.search(response.text)
    if not match:
        raise ValueError("no channel ID on the page")
    return match.group(1)


def resolve_youtube_links(config, session, status, now):
    """Returns {channel link: channel ID} for enabled YouTube sources added by link.
    IDs are looked up once and remembered in data/youtube_channels.json. A link that
    can't be resolved, or points at a channel that is already listed, is reported in
    the feed status and left out of this run."""
    remembered = load_json_dict(YOUTUBE_IDS_PATH)
    known = dict(remembered)
    listed = {s["channel_id"]: s["name"] for s in config["sources"]
              if s["type"] == "youtube" and s["enabled"] and "channel_id" in s}
    resolved = {}
    for src in config["sources"]:
        if src["type"] != "youtube" or not src["enabled"] or "channel_id" in src:
            continue
        link = src["channel_url"].lower()
        if link not in known:
            try:
                known[link] = fetch_channel_id(session, src["channel_url"])
            except (requests.RequestException, ValueError) as e:
                print(f"  FAILED to resolve {src['channel_url']}: {e}")
                record_failure(status, source_key(src), f"channel link: {feed_error(e)}", now)
                continue
        channel_id = known[link]
        if channel_id in listed:
            record_failure(status, source_key(src), f"already listed as {listed[channel_id]}", now)
            continue
        listed[channel_id] = src["name"]
        resolved[link] = channel_id
    save_json_if_changed(YOUTUBE_IDS_PATH, known, remembered)
    return resolved


def run_scraper():
    DATA_DIR.mkdir(exist_ok=True)
    config = load_config()
    now = datetime.now(timezone.utc)
    now_text = now.strftime(TIMESTAMP_FORMAT)
    previous_polls = load_json_dict(POLL_STATE_PATH)
    due = due_types(config, now, previous_polls)
    ps2_keys = {source_key(s) for s in config["sources"] if s["enabled"] and s["role"] == PS2_ROLE}
    previous = load_previous_items()
    first_seen = {item_key(i): i["timestamp"] for i in previous if i.get("timestamp")}
    previous_status = load_json_dict(STATUS_PATH)
    known_keys = {source_key(s) for s in config["sources"]}
    status = {k: v for k, v in previous_status.items() if k in known_keys}

    items = []
    core_failures = extra_failures = skipped = 0
    host_failures = defaultdict(int)
    fetched_types = set()
    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        matcher = TitleMatcher(load_ps2_titles(session))
        youtube_ids = resolve_youtube_links(config, session, status, now_text) if "youtube" in due else {}
        jobs = build_jobs(config, youtube_ids)
        core_jobs = [job for job in jobs if job["type"] in CORE_TYPES and job["type"] in due]

        due_jobs = [job for job in jobs if job["type"] in due]
        print(f"Scanning {len(due_jobs)} of {len(jobs)} feeds (due now: {', '.join(t for t in SOURCE_TYPES if t in due)}) "
              f"against PS2 titles ({matcher.summary()})...")
        started = time.monotonic()
        for job in due_jobs:
            url, core = job["url"], job["type"] in CORE_TYPES
            host = urlparse(url).hostname
            if not core and time.monotonic() - started > FETCH_TIME_BUDGET:
                skipped += 1
                print(f"  SKIPPED {url}: fetch time budget used up")
                continue
            if not core and host_failures[host] >= HOST_FAILURE_LIMIT:
                skipped += 1
                print(f"  SKIPPED {url}: {host} keeps failing")
                continue
            fetched_types.add(job["type"])
            try:
                feed = fetch_feed(session, url, retry_rate_limit=core)
                if feed.get("bozo") and not feed.entries:
                    raise ValueError("unreadable feed")
            except (requests.RequestException, ValueError) as e:
                if core:
                    core_failures += 1
                else:
                    extra_failures += 1
                    host_failures[host] = host_failures[host] + 1 if host_is_down(e) else 0
                print(f"  FAILED {url}: {e}")
                for src in job["sources"]:
                    record_failure(status, source_key(src), feed_error(e), now_text)
                continue
            host_failures[host] = 0
            entries = select_entries(feed, job["type"])
            repeated = shared_links(feed, job["type"])
            items.extend(analyze_entry(e, feed, job, matcher, first_seen, ps2_keys, repeated) for e in entries)
            newest = newest_by_key(feed, job)
            for src in job["sources"]:
                record_success(status, source_key(src), newest.get(source_key(src)))
            print(f"  {len(entries):3d} items  {url}")

    # Never replace a good snapshot with the result of a mostly-failed run.
    if core_jobs and (not items or core_failures > len(core_jobs) // 2):
        raise SystemExit(
            f"Aborting: {core_failures}/{len(core_jobs)} news/Reddit feeds failed and {len(items)} items were "
            "collected; keeping the previous snapshot."
        )
    save_json_if_changed(STATUS_PATH, status, previous_status)
    # Remember when the slower source types (poll_every_hours > 1) were last fetched.
    intervals = config.get("poll_every_hours", {})
    polls = {kind: when for kind, when in previous_polls.items() if int(intervals.get(kind, 1)) > 1}
    polls.update({kind: now_text for kind in fetched_types if int(intervals.get(kind, 1)) > 1})
    save_json_if_changed(POLL_STATE_PATH, polls, previous_polls)
    if not items:
        print("No items collected; leaving snapshot untouched.")
        return

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

    matched = sum(1 for i in items if i.get("matched_game"))
    from_body = sum(1 for i in items if i.get("matched_in") == "body")
    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_tracked_feeds": sum(1 for s in config["sources"] if s["enabled"]),
        "items": merged_items,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(merged_items)} items ({len(items)} fetched this run, {matched} matched a PS2 game "
          f"({from_body} from body text), {core_failures} news/Reddit and {extra_failures} YouTube/podcast "
          f"feed failures, {skipped} skipped) to {OUTPUT_PATH}")


if __name__ == "__main__":
    run_scraper()
