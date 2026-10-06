"""Tracks what PS2 games are listed for on eBay, and how that changes.

Runs separately from scraper.py and never touches it. It prices every game the
feed has ever mentioned (as long as the game is in the PS2 library), plus the
games pinned in ebay_watchlist.json, on eBay US and eBay UK.

HOW OFTEN a game is checked depends on how it is being talked about:

  surging   a game the feed rarely names is suddenly named by several sources
            within a day: checked on every run for the next two days
  normal    named in the feed in the last two weeks: every 6 hours
  staple    named on so many days that a mention is no news: every 6 hours,
            and never treated as surging
  dormant   named some time ago and quiet since: once a day

WHAT it asks eBay's official Browse API for: used, Buy It Now listings located
in that country. Listings that are not a copy of the game are dropped (other
games in the series, empty cases, soundtracks, cheat discs, job lots, imports).

WHAT it keeps:

  data/prices/latest.json   per game and site: copies listed, lowest and median
                            asking price, typical postage, when it was checked
  data/prices/YYYY-MM.json  the same three numbers over time, one row whenever
                            they change (and at least one a day)
  the --out file            this run's listings with their links, for checking
                            the rules; the workflow keeps only the latest one,
                            on its own branch

Nothing under data/ holds a listing title, a link or anything about a seller:
numbers only.

Read the numbers for what they are:

- They are ASKING prices of copies still for sale, not sold prices. Sellers
  ask for more than buyers pay, and a bargain that sold in an hour never
  shows up here.
- US and UK are never mixed. A US copy (NTSC) and a UK copy (PAL) are
  different products in different currencies.
- Loose discs and complete copies are counted together.
- eBay returns at most 200 listings for a search. When a game has more,
  "truncated" is set and the figures describe those 200 only.
- The search words for a game come from its title. That works for most games
  and badly for some; give those a "search" in ebay_watchlist.json.

The eBay key comes from two environment variables, EBAY_CLIENT_ID and
EBAY_CLIENT_SECRET (GitHub Actions secrets). It is never written to a file
and never printed. This script uses only Python's standard library, so the
job that holds the key installs nothing.

    python ebay_prices.py --plan              # what would be checked now; needs no key
    python ebay_prices.py --out some/file.json

Set EBAY_DIAGNOSE=true to also print how many listings eBay reports for a few
variations of the search (counts only), which shows whether the filters work.
"""

import argparse
import base64
import http.client
import json
import os
import re
import statistics
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import quote, urlencode

ROOT = Path(__file__).parent
WATCHLIST_PATH = ROOT / "ebay_watchlist.json"
DEFAULT_OUT = Path(tempfile.gettempdir()) / "ebay_prices.json"   # outside the repository on purpose
DATA_DIR = ROOT / "data"
FEED_PATH = DATA_DIR / "sentiment_feed.json"      # the scraper's 14-day snapshot (read only)
ARCHIVE_DIR = DATA_DIR / "archive"                # every mention ever recorded (read only)
LIBRARY_PATH = DATA_DIR / "ps2_database.json"     # the PS2 library (read only)
PRICES_DIR = DATA_DIR / "prices"                  # written here: numbers only
LATEST_NAME = "latest.json"

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"   # public data only; cannot act on an eBay account
USER_AGENT = "python:ps2-sentiment-tracker-ebay:1.0 (+https://github.com/SirNovaTofuBlaster/ps2-sentiment-tracker)"

CATEGORY_ID = "139973"                     # eBay's "Video Games" category, same number on both sites
PLATFORM_ASPECT = "Sony PlayStation 2"     # the "Platform" item specific sellers pick
USED_CONDITION_IDS = "2750|3000|4000|5000|6000"   # like new, used, very good, good, acceptable
CONDITION_FILTERS = {
    "ids": f"conditionIds:{{{USED_CONDITION_IDS}}}",   # what this script uses; leaves out "for parts"
    "used": "conditions:{USED}",                       # diagnosis only
    "any": "",                                         # diagnosis only
}
MARKETS = {
    # "foreign" words mark a copy made for another region, which is a different product.
    # They include the first part of the code printed on the spine: SLES/SCES is Europe, SLUS/SCUS America.
    # "zip" is where postage is quoted to. In the US most sellers let eBay work postage out
    # from the buyer's address, and without one eBay gives no figure; New York stands in.
    "EBAY_US": {"label": "US", "site": "www.ebay.com", "country": "US", "currency": "USD", "zip": "10001",
                "foreign": ("pal", "european", "sles", "sces")},
    "EBAY_GB": {"label": "UK", "site": "www.ebay.co.uk", "country": "GB", "currency": "GBP",
                "foreign": ("ntsc", "usa", "us version", "slus", "scus")},
}

# ---- How often each game is checked -------------------------------------------------
WINDOW_DAYS = 14             # "recently" means this long; it is also how far back the feed goes
STAPLE_DAYS = 5              # named on this many of those days: a staple, where a mention is no news
SURGE_HOURS = 24             # a surge is judged over this long...
SURGE_SOURCES = 2            # ...and needs this many different sources, each with its own headline,
SURGE_QUIET_MENTIONS = 1     # ...for a game named at most this often in the rest of the window
SURGE_HOLD_HOURS = 48        # once surging, a game stays surging this long after its last mention
CHECK_EVERY_HOURS = {"surging": 0, "normal": 6, "staple": 6, "dormant": 24}   # 0 = every run
EARLY_MINUTES = 30           # a check may come this much early, so "every 6 hours" does not drift to 7

# ---- How much of eBay's allowance (5,000 searches a day) a run may use ---------------
DAILY_SEARCHES = 4500        # stop for the day here, leaving room for runs started by hand
MAX_SEARCHES_PER_RUN = 500   # and never more than this in one run
TIME_BUDGET = 420            # seconds; whatever is still due then waits for the next run

PAGE_LIMIT = 200         # the most eBay returns for one search
LISTINGS_KEPT = 10       # cheapest listings saved per game per site in the --out file
MAX_PINNED = 100         # games that may be pinned in ebay_watchlist.json
MAX_QUERY_CHARS = 100    # eBay's limit for the search words
REQUEST_TIMEOUT = 15
REQUEST_PAUSE = 0.25     # seconds between searches
RETRY_PAUSES = (2, 8)    # seconds before the second and third try of a failed search
MAX_SILENT_LOOKUPS = 3   # give up when eBay has not answered this many lookups in a row
MIN_LOOKUPS_TO_JUDGE = 10   # with fewer, "eBay returned nothing at all" proves little
MIN_KNOWN_TO_JUDGE = 5      # games that had copies last time and return nothing at all now

FEED_TIME_FORMAT = "%Y-%m-%d %H:%M UTC"
STAMP_FORMAT = "%Y-%m-%dT%H:%MZ"

# How a title says "PS2". A keyword search only counts titles that do.
PLATFORM_WORDS = re.compile(r"\b(?:sony )?(?:playstation ?2|play station 2|ps ?2)\b")
# "Godfather, The: Collector's Edition" is how the library files "The Godfather: ...".
INVERTED_ARTICLE = re.compile(r"^([^:]+?),\s*(The|A|An)(:.*)?$")
ARTICLES = {"the", "a", "an"}
# Sellers write "Kingdom Hearts II" and "Kingdom Hearts 2" for the same game.
ROMAN_NUMERALS = {"ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8", "ix": "9",
                  "xi": "11", "xii": "12", "xiii": "13"}
DISC_WORDS = {"disc", "discs", "disk", "disks", "dvd", "cd", "player", "players"}
# One-word titles that can be searched for safely: nothing else on a PS2 listing is called this.
# A one-word title that is also an ordinary word ("Black", "Cars", "Gift", "Gun") is not here,
# because a search for it returns every listing that happens to use the word. Pin such a game
# in ebay_watchlist.json, with its own search words, to track it anyway.
ONE_WORD_TITLES = frozenset("""
    airblade amplitude astroboy baroque beatmania bionicle bloodrayne bully burnout castleween
    catwoman chessmaster choroq chulip constantine coraline culdcept darkwatch drakengard
    equestriad eragon everblue evergrace fantavision fightbox flatout flipnic freekstyle
    frequency fruitfall futurama garfield genji getaway ghosthunter ghostmaster gladius
    godfather grimgrimoire gungrave headhunter heatseeker hobbit homura ico incredibles juiced
    jumanji kessen killzone kinetica kuon lemmings madagascar mafia manhunt maximo mercenaries
    metropolismania monopoly mummy nanobreaker okami psychonauts psyvariar punisher ratatouille
    rez robocop rocky scaler scarface shinobi siren skygunner splashdown spyhunter ssx stuntman
    suffering syberia timesplitters trapt vexx xiii yakuza zathura zoocube
""".split())
# Words that turn a game into an edition of the same game, not into another game.
EDITION_WORDS = {
    "directors", "cut", "special", "limited", "collectors", "edition", "greatest", "hits",
    "platinum", "the", "best", "premium", "pack", "bonus", "disc", "complete", "gold", "ultimate",
    "game", "of", "year", "classics", "essentials", "version",
}

# Words in front of a name that do not make it another game: "Disney's Tarzan" is Tarzan.
BRAND_WORDS = {"the", "a", "an", "disney", "disneys", "pixar", "pixars", "marvel", "marvels", "nickelodeon",
               "ea", "sports", "sega", "capcom", "namco", "konami", "taito", "midway", "atari", "snk"}
# Words after "Title:" that make it an expansion or a different release, not the title's full name.
EXPANSION_WORDS = {"xtreme", "legends", "empires", "prologue", "expansion", "remix", "substance",
                   "international", "episode", "volume", "vol", "part"}

# A listing whose title contains one of these (as whole words) is not a copy of the game.
JUNK_PHRASES = (
    "case only", "box only", "manual only", "cover only", "inlay only", "artwork only",
    "sleeve only", "booklet only", "no game", "no disc", "no disk", "empty case", "empty box",
    "replacement case", "replacement cover", "art only", "case inlay", "manual booklet",
    "reproduction", "repro", "bundle", "lot", "joblot",
    "strategy guide", "official guide", "guide book", "guidebook", "demo disc", "demo",
    "jampack", "jam pack", "press kit", "promo dvd", "famitsu", "magazine",
    "action replay", "gameshark", "game shark", "codebreaker", "code breaker", "cheats", "cheat disc",
    "hat", "shirt", "figure", "statue", "plush", "keychain", "artbook", "art book",
    "faulty", "not working", "for parts", "spares or repairs", "spares repairs",
)
# Words that may sit between a game's name and "soundtrack" when the listing IS the soundtrack.
SOUNDTRACK_LEAD_INS = {"original", "official", "music", "game", "video", "promo"}
SOUNDTRACK_WORDS = {"soundtrack", "soundtracks", "ost"}
# "+ soundtrack", "& OST", "+ original soundtrack": the copy comes with it.
SOUNDTRACK_INCLUDED = re.compile(
    r"[+&]\s*(?:(?:the|a|an|bonus|original|official|music|game|video|promo|mini)\s+)*(?:soundtracks?|ost)\b",
    re.IGNORECASE)
# The seller picked PS2 as the platform, but the title says it is for something else.
OTHER_PLATFORMS = (
    "xbox", "gamecube", "dreamcast", "wii", "psp", "vita", "ps1", "psx", "ps3", "ps4", "ps5",
    "nintendo switch", "pc dvd", "pc cd", "pc game",
)
# A copy made for Japan, wherever the seller is. SLPM/SLPS/SCPS start a Japanese spine code.
IMPORT_PHRASES = ("japan", "japanese", "ntsc j", "jpn", "jp", "jap", "slpm", "slps", "scps")
SKIPPED_EXAMPLES = 5     # titles saved per reason, so the rules can be checked against real listings
# Counted, but worth knowing about: the price is for less than a complete copy.
INCOMPLETE_PHRASES = (
    "disc only", "disk only", "game only", "loose", "no manual", "no case", "no box",
    "no cover", "no inlay", "missing manual", "without manual",
)


class EbayError(Exception):
    """Something a person has to fix: bad key, bad watchlist, eBay not answering."""


class NetworkProblem(Exception):
    """The request never got an answer. Carries the kind of failure, never the request."""


class LimitReached(Exception):
    """eBay keeps answering 429: the allowance of searches is used up."""


def say(text):
    """Print straight away, so the Actions log shows lines in the order they happened."""
    print(text, flush=True)


def utc_now():
    return datetime.now(timezone.utc)


# ======================================================================================
# The network
# ======================================================================================

class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):   # the key must never follow a redirect elsewhere
        return None


class Http:
    """The only door to the network: one request in, (status, text) out."""

    def __init__(self, timeout=REQUEST_TIMEOUT):
        self.timeout = timeout
        self.opener = urllib.request.build_opener(_NoRedirects)

    def send(self, url, headers, body=None):
        request = urllib.request.Request(
            url, data=body, headers={**headers, "User-Agent": USER_AGENT},
            method="GET" if body is None else "POST")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.read().decode("utf-8", "replace")
            except (OSError, http.client.HTTPException):
                return exc.code, ""
        except (OSError, http.client.HTTPException) as exc:
            raise NetworkProblem(type(exc).__name__) from None


def parse(text):
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def redact(text, secrets):
    """Remove the key from anything about to be printed or saved. Belt and braces."""
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


# ======================================================================================
# Words and names
# ======================================================================================

def words(text):
    """Lower-case words with accents and punctuation removed: "Ōkami™ (PS2)" -> ["okami", "ps2"].

    Accents are folded into their letter and apostrophes vanish ("Director's" is
    "directors"); every other symbol, emoji included, separates words, so
    "Okami⭐Complete" is two words and not one."""
    plain = "".join(char for char in unicodedata.normalize("NFD", str(text or ""))
                    if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", re.sub(r"['’`]", "", plain.lower()))


def name_words(text):
    """words(), further evened out so that two spellings of one name compare equal.

    "and" is dropped ("Jak & Daxter" and "Jak and Daxter" agree) and a Roman
    numeral becomes a number ("Kingdom Hearts II" and "Kingdom Hearts 2" agree)."""
    return [ROMAN_NUMERALS.get(word, word) for word in words(text) if word != "and"]


def has_phrase(text, phrases):
    """True when one of the phrases appears in the text as whole words."""
    padded = f" {text} "
    return any(f" {phrase} " in padded for phrase in phrases if phrase)


def readable(title):
    """ "Godfather, The: Collector's Edition" -> "The Godfather: Collector's Edition"."""
    match = INVERTED_ARTICLE.match(str(title or "").strip())
    return f"{match.group(2)} {match.group(1)}{match.group(3) or ''}" if match else str(title or "").strip()


def key_of(title):
    """One key per game however it is spelt: "ICO" and "Ico" are the same game, and so are
    "Getaway, The: Black Monday" and "The Getaway: Black Monday"."""
    return " ".join(words(readable(title)))


def search_terms(text):
    """(the name a listing must contain, the searches to send eBay) for a title or a hand-written search.

    A leading article is dropped ("The Godfather" is looked for as "godfather").
    A title with a Roman numeral is searched both ways, "kingdom hearts ii" and
    "kingdom hearts 2", because sellers write both; the name check then treats
    the two spellings as one."""
    title = readable(text)
    plain = [word for word in words(title) if word != "and"]
    if len(plain) > 1 and re.match(r"(?i)(?:the|a|an)\s", title):
        plain = plain[1:]
    name = [ROMAN_NUMERALS.get(word, word) for word in plain]
    queries = [" ".join(plain)]
    if name != plain and len(plain) > 1:
        queries.append(" ".join(name))
    return " ".join(name), [query for query in queries if query]


# ======================================================================================
# Files this script reads
# ======================================================================================

def read_json(path, default):
    """A file's JSON, or the default when the file is missing, unreadable or the wrong shape.
    Only for files this script reads but does not own."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def read_own(path, default):
    """A file this script writes: the default when it does not exist yet, an error when it
    exists but cannot be read. Carrying on would overwrite it with less than it held."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise EbayError(f"data/prices/{path.name} cannot be read ({type(exc).__name__}). Nothing was "
                        "changed. Put back the last good version of that file from its history "
                        "on GitHub.") from None
    if not isinstance(value, type(default)):
        raise EbayError(f"data/prices/{path.name} is not in the shape this script writes. Nothing was "
                        "changed. Put back the last good version of that file from its history on GitHub.")
    return value


def load_state(path):
    """latest.json from the previous run, checked."""
    state = read_own(path, {})
    games, searches = state.get("games", {}), state.get("searches", {})
    sound = (isinstance(games, dict) and all(isinstance(entry, dict) for entry in games.values())
             and isinstance(searches, dict) and isinstance(searches.get("used", 0), int))
    if not sound:
        raise EbayError(f"data/prices/{Path(path).name} is not in the shape this script writes. Nothing "
                        "was changed. Put back the last good version of that file from its history on GitHub.")
    return state


def prior_games(state):
    """{key: entry} for the games in latest.json, whatever spelling each was saved under."""
    return {key_of(title): entry for title, entry in state.get("games", {}).items()}


def load_watchlist(path=None):
    """(pinned games, titles never to price), checked so that a typo fails with a readable message."""
    path = path or WATCHLIST_PATH
    name = Path(path).name
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise EbayError(f"Cannot read {name}: {type(exc).__name__}") from None
    except ValueError as exc:
        raise EbayError(f"{name} is not valid JSON: {exc}") from None

    games = raw.get("games") if isinstance(raw, dict) else None
    if not isinstance(games, list):
        raise EbayError(f'{name} needs a "games" list (it may be empty: []).')
    if len(games) > MAX_PINNED:
        raise EbayError(f"{name} pins {len(games)} games; the most allowed is {MAX_PINNED}.")
    never = raw.get("never", [])
    if not isinstance(never, list) or not all(isinstance(title, str) for title in never):
        raise EbayError(f'{name}: "never" must be a list of game titles.')

    pinned, seen = [], set()
    for position, game in enumerate(games, 1):
        if not isinstance(game, dict) or not isinstance(game.get("title"), str) or not game["title"].strip():
            raise EbayError(f'Game {position} in {name} needs a "title".')
        title = game["title"].strip()
        search = game.get("search", title)
        if not isinstance(search, str) or not words(search):
            raise EbayError(f'"{title}": "search" must be the words to look for on eBay.')
        phrase, queries = search_terms(search)
        if not queries or any(len(query) + len(" ps2") > MAX_QUERY_CHARS for query in queries):
            raise EbayError(f'"{title}": the search words do not work for eBay; write a shorter "search".')
        exclude = game.get("exclude", [])
        if not isinstance(exclude, list) or not all(isinstance(word, str) for word in exclude):
            raise EbayError(f'"{title}": "exclude" must be a list of words.')
        if key_of(title) in seen:
            raise EbayError(f'"{title}" is listed twice in {name}.')
        seen.add(key_of(title))
        pinned.append({"title": title, "key": key_of(title), "search": phrase, "queries": queries,
                       "search_as_written": search,
                       "exclude": [" ".join(words(word)) for word in exclude if words(word)],
                       "pinned": True})
    return pinned, {key_of(title) for title in never if key_of(title)}


def parse_feed_time(text):
    try:
        return datetime.strptime(text, FEED_TIME_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_stamp(text):
    try:
        return datetime.strptime(text, STAMP_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def load_mentions():
    """(mentions in the feed's window, {key: title} of every game ever mentioned).

    A mention is one game named by one item: when, by which source, under
    which headline, and whether the name was in the headline itself or only in
    the text underneath."""
    mentions, ever = [], {}
    for item in read_json(FEED_PATH, {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        games = item.get("matched_games")
        if not isinstance(games, list) or not games:
            games = [item.get("matched_game")]
        when = parse_feed_time(item.get("timestamp"))
        for title in games:
            if not isinstance(title, str) or not key_of(title):
                continue
            ever.setdefault(key_of(title), title)
            if when is not None:
                mentions.append({"key": key_of(title), "when": when,
                                 "source": str(item.get("source") or ""),
                                 "headline": " ".join(words(item.get("headline")))[:80],
                                 "in_headline": item.get("matched_in") != "body"})
    for path in sorted(Path(ARCHIVE_DIR).glob("20*.json")):
        for row in read_json(path, []):
            if isinstance(row, dict) and isinstance(row.get("g"), str) and key_of(row["g"]):
                ever.setdefault(key_of(row["g"]), row["g"])
    return mentions, ever


def load_library():
    """({key: title} for the PS2 library, a catalogue of every title's name for telling games apart)."""
    titles = [title for title in read_json(LIBRARY_PATH, []) if isinstance(title, str) and key_of(title)]
    by_key, catalogue, seen = {}, [], set()
    for title in titles:
        by_key.setdefault(key_of(title), title)
        name = search_terms(title)[0]
        if name and name not in seen:
            seen.add(name)
            owners = {" ".join(words(owner + "s")) for owner in re.findall(r"([A-Za-z]+)['\u2019]s\b", title)}
            catalogue.append({"name": name, "title": readable(title), "possessive": owners})
    return by_key, catalogue


# ======================================================================================
# Which games, and which of them are due
# ======================================================================================

def other_games(title, name, catalogue):
    """Library names that contain this game's name and are a different game.

    A listing naming one of them is not a copy of this game:
      "kingdom hearts"  ->  "kingdom hearts 2", "kingdom hearts re chain of memories"
      "spider man"      ->  "ultimate spider man", "spider man friend or foe"
    Not different games:
      an edition                         "silent hill 2 directors cut"
      a brand or an owner in front       "tom clancys splinter cell" for "splinter cell"
      the game's own full name, when the library files one title as "Jak X" and
      as "Jak X: Combat Racing" and nothing else starts "Jak X:"."""
    padded_name, own_title = f" {name} ", readable(title).lower()
    different, full_names = [], []
    for entry in catalogue:
        other = entry["name"]
        at = f" {other} ".find(padded_name)
        if other == name or at < 0:
            continue
        before = f" {other} "[:at].split()
        after = f" {other} "[at + len(padded_name):].split()
        if set(after) - EDITION_WORDS:
            different.append(other)
            if not before and entry["title"].lower().startswith(own_title + ":") \
                    and not set(after) & EXPANSION_WORDS and not after[0].isdigit():
                full_names.append(other)
        elif before and before[-1] not in entry["possessive"] and not set(before) <= BRAND_WORDS:
            different.append(other)
    if len(full_names) == 1:
        different.remove(full_names[0])
    return sorted(set(different))


def level_of(mentions, now, held_until, pinned=False):
    """(level, headline mentions in the window, surging-until time or None) for one game."""
    window = [m for m in mentions if now - timedelta(days=WINDOW_DAYS) < m["when"] <= now]
    named = [m for m in window if m["in_headline"]]
    recent = [m for m in named if m["when"] > now - timedelta(hours=SURGE_HOURS)]
    before = len(named) - len(recent)

    if len({m["when"].date() for m in named}) >= STAPLE_DAYS:
        return "staple", len(named), None
    if (before <= SURGE_QUIET_MENTIONS
            and len({m["source"] for m in recent}) >= SURGE_SOURCES
            and len({m["headline"] for m in recent}) >= SURGE_SOURCES):
        until = max(m["when"] for m in recent) + timedelta(hours=SURGE_HOLD_HOURS)
        held_until = max(held_until, until) if held_until else until
    if held_until and now < held_until:
        return "surging", len(named), held_until
    return ("normal" if window or pinned else "dormant"), len(named), None


def plan_games(now, pinned, never, mentions, ever, library, catalogue, state):
    """Every game to track, each with its level. Also returns what was left out, and why."""
    games = {game["key"]: dict(game, siblings=[]) for game in pinned}
    # The feed may call a pinned game by its short name ("Persona 4" for "Shin Megami Tensei:
    # Persona 4"); a pinned game's search words count as another name for it. Two library
    # titles that come to the same name ("Getaway" and "The Getaway") are one game here.
    also = {" ".join(words(game["search_as_written"])): game["key"] for game in pinned}
    by_name = {game["search"]: game["key"] for game in pinned}
    left_out = {"one_word": [], "not_in_library": [], "never": []}
    for key in sorted(ever):
        if key in games or key in also:
            continue
        if key in never:
            left_out["never"].append(ever[key])
        elif key not in library:
            left_out["not_in_library"].append(ever[key])
        else:
            name, queries = search_terms(library[key])
            if name in by_name:
                also[key] = by_name[name]
            elif not queries or any(len(query) + len(" ps2") > MAX_QUERY_CHARS for query in queries) \
                    or (" " not in name and queries[0] not in ONE_WORD_TITLES):
                left_out["one_word"].append(library[key])
            else:
                by_name[name] = key
                games[key] = {"title": library[key], "key": key, "search": name, "queries": queries,
                              "exclude": [], "pinned": False,
                              "siblings": other_games(library[key], name, catalogue)}

    by_key = {}
    for mention in mentions:
        by_key.setdefault(also.get(mention["key"], mention["key"]), []).append(mention)
    previous = prior_games(state)
    for game in games.values():
        held = parse_stamp((previous.get(game["key"]) or {}).get("surging_until"))
        game["level"], game["mentions"], game["surging_until"] = level_of(
            by_key.get(game["key"], []), now, held, game["pinned"])
    return sorted(games.values(), key=lambda game: game["title"].lower()), left_out


def due_lookups(games, state, now):
    """(game, market) pairs whose turn has come, most urgent first."""
    previous = prior_games(state)
    due = []
    for game in games:
        every = CHECK_EVERY_HOURS[game["level"]] * 60
        for market_id, market in MARKETS.items():
            entry = (previous.get(game["key"]) or {}).get(market["label"])
            checked = parse_stamp(entry.get("checked")) if isinstance(entry, dict) else None
            waited = (now - checked).total_seconds() / 60 if checked else None
            if waited is None or waited >= every - EARLY_MINUTES:
                overdue = float("inf") if waited is None else waited / max(every, 60)
                due.append((game["level"] != "surging", not game["pinned"], -overdue,
                            game["title"].lower(), market_id, game))
    due.sort(key=lambda row: row[:5])
    return [(row[5], row[4]) for row in due]


# ======================================================================================
# Asking eBay
# ======================================================================================

def get_token(http_client, client_id, client_secret):
    """Swap the key for a short-lived token that can only read public listings."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode("ascii")
    try:
        status, text = http_client.send(
            TOKEN_URL,
            {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            body)
    except NetworkProblem as exc:
        raise EbayError(f"Could not reach eBay to sign in ({exc}).") from None

    payload = parse(text)
    token = payload.get("access_token")
    if status != 200 or not isinstance(token, str) or not token:
        reason = redact(str(payload.get("error_description") or payload.get("error") or "")[:200],
                        (client_id, client_secret, basic))
        raise EbayError(
            f"eBay refused the key (HTTP {status}{': ' + reason if reason else ''}). "
            "Check that EBAY_CLIENT_ID is the Production App ID, that EBAY_CLIENT_SECRET is the "
            "Production Cert ID, and that the keyset is not shown as disabled in eBay's developer portal."
        )
    return token, basic


def search_url(market_id, query, by_aspect=True, condition="ids"):
    """The search request for one game on one site, encoded the way eBay's examples are."""
    market = MARKETS[market_id]
    filters = [CONDITION_FILTERS[condition], "buyingOptions:{FIXED_PRICE}",
               f"itemLocationCountry:{market['country']}"]
    params = {
        "q": query if by_aspect else f"{query} ps2",
        "category_ids": CATEGORY_ID,
        "filter": ",".join(part for part in filters if part),
        "limit": str(PAGE_LIMIT),
    }
    if by_aspect:
        params["aspect_filter"] = f"categoryId:{CATEGORY_ID},Platform:{{{PLATFORM_ASPECT}}}"
    return SEARCH_URL + "?" + urlencode(params, quote_via=quote)   # spaces as %20, never "+"


def buyer_location(market):
    """Where eBay should quote postage to: the site's own country, plus a postcode if one is set."""
    return f"country={market['country']}" + (f",zip={market['zip']}" if market.get("zip") else "")


def search(http_client, token, market_id, query, counter, by_aspect=True, condition="ids"):
    """One search, tried up to three times. Returns (HTTP status or 0 for no answer, JSON)."""
    market = MARKETS[market_id]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": market_id,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + quote(buyer_location(market), safe=""),
    }
    url = search_url(market_id, query, by_aspect, condition)
    status, payload = 0, {}
    for pause in (0,) + RETRY_PAUSES:
        if pause:
            time.sleep(pause)
        counter["searches"] += 1
        try:
            status, text = http_client.send(url, headers)
            payload = parse(text)
        except NetworkProblem as exc:
            status, payload = 0, {"errors": [{"message": f"network problem ({exc})"}]}
        if status not in (0, 429) and status < 500:
            break
    if status == 429:
        raise LimitReached(error_text(status, payload))
    return status, payload


def first_message(entries):
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        return str(entries[0].get("longMessage") or entries[0].get("message") or "")[:200]
    return ""


def error_text(status, payload):
    message = first_message(payload.get("errors"))
    label = f"HTTP {status}" if status else "no answer"
    return f"{label}: {message}" if message else label


# ======================================================================================
# Sorting listings
# ======================================================================================

def amount(value, currency):
    """A price as a number, or None if it is missing, zero or in another currency."""
    if not isinstance(value, dict) or value.get("currency") != currency:
        return None
    try:
        number = float(value.get("value"))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def middle(values):
    """The median, worked out in exact pennies so that 28.245 becomes 28.25 and not 28.24."""
    exact = statistics.median(Decimal(str(value)) for value in values)
    return float(exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def postage_of(item, currency):
    """Cheapest postage eBay quotes for the listing, or None when it gives no figure."""
    costs = []
    for option in item.get("shippingOptions") or []:
        cost = option.get("shippingCost") if isinstance(option, dict) else None
        if isinstance(cost, dict) and cost.get("currency") == currency:
            try:
                costs.append(float(cost.get("value")))
            except (TypeError, ValueError):
                pass
    return min(costs) if costs else None


def listing_url(item, market):
    """A plain link to the listing on the right eBay site, or None if eBay gave nothing usable."""
    legacy = str(item.get("legacyItemId") or "")
    if legacy.isdigit():
        return f"https://{market['site']}/itm/{legacy}"
    url = str(item.get("itemWebUrl") or "")
    return url if url.startswith(f"https://{market['site']}/") else None


def names_this_game(text, phrase):
    """True when the title names this game and not a sequel or several games.

    The game's words must appear together and in order, so the "2" in
    "Silent Hill 3 (PlayStation 2)" is never taken for the "2" in "Silent Hill
    2". They must not run straight on into another single number either:
    "silent hill 2 3 4" is a set and "kingdom hearts 2" is the sequel. A
    number that counts discs ("2 disc"), a score ("9 10") or an age rating
    ("18") is fine. Both arguments are in the evened-out form of name_words()."""
    padded = f" {text} "
    at = padded.find(f" {phrase} ")
    if at < 0:
        return False
    rest = padded[at + len(phrase) + 2:].split()
    if rest[:1] == ["plus"]:
        rest = rest[1:]
    if not rest:
        return True
    if re.fullmatch(r"[1-9]", rest[0]) and not (rest[1:2] and (rest[1] in DISC_WORDS or rest[1] == "10")):
        return False
    return True


def names_another_entry(text, phrase):
    """True when a numbered game's title also names another number in the series.

    "silent hill 2 case with silent hill 3 manual" and "silent hill 2, silent
    hill 3, silent hill 4 promo set" are not one copy of Silent Hill 2."""
    *stem, number = phrase.split()
    if not stem or not number.isdigit():
        return False
    found = re.findall(rf"(?<![a-z0-9]){re.escape(' '.join(stem))} (\d{{1,2}})(?![a-z0-9])", text)
    return any(other != number for other in found)


def is_the_soundtrack(title, name_text, phrase):
    """True when the listing is the game's soundtrack: "Rule of Rose Original Soundtrack CD".

    A copy that comes with, or is missing, its bonus soundtrack says so some
    other way ("Silent Hill 3 + soundtrack", "Silent Hill 3 PS2 disc w/
    soundtrack", "no soundtrack"), and is still a copy."""
    if SOUNDTRACK_INCLUDED.search(str(title or "")):
        return False
    padded = f" {name_text} "
    at = padded.find(f" {phrase} ")
    rest = padded[at + len(phrase) + 2:].split() if at >= 0 else []
    while rest and rest[0] in SOUNDTRACK_LEAD_INS:
        rest = rest[1:]
    return bool(rest) and rest[0] in SOUNDTRACK_WORDS


def reject_reason(item, game, market, keyword_search):
    """Why a listing is left out, or None to count it."""
    text = " ".join(words(item.get("title")))             # for junk words, as the seller wrote them
    name_text = " ".join(name_words(item.get("title")))   # for the game's name, spellings evened out
    if keyword_search and not PLATFORM_WORDS.search(text):
        return "other_game"
    if not names_this_game(name_text, game["search"]) or names_another_entry(name_text, game["search"]) \
            or has_phrase(name_text, game.get("siblings") or ()):
        return "other_game"
    if has_phrase(text, OTHER_PLATFORMS):
        return "other_platform"
    if has_phrase(text, JUNK_PHRASES) or has_phrase(text, game["exclude"]) \
            or is_the_soundtrack(item.get("title"), name_text, game["search"]):
        return "not_a_copy"
    if has_phrase(text, IMPORT_PHRASES) or has_phrase(text, market["foreign"]):
        return "import"
    if amount(item.get("price"), market["currency"]) is None:
        return "no_price"
    if listing_url(item, market) is None:
        return "no_link"
    return None


def summarise(payload, game, market, keyword_search):
    """Turn one search result into the numbers and links for this run's file."""
    items = [item for item in payload.get("itemSummaries") or [] if isinstance(item, dict)]
    skipped, examples, kept = {}, {}, []
    for item in items:
        reason = reject_reason(item, game, market, keyword_search)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            if len(examples.setdefault(reason, [])) < SKIPPED_EXAMPLES:
                examples[reason].append(" ".join(str(item.get("title") or "").split())[:120])
            continue
        postage = postage_of(item, market["currency"])
        kept.append({
            "title": " ".join(str(item.get("title") or "").split())[:160],
            "price": round(amount(item.get("price"), market["currency"]), 2),
            "postage": None if postage is None else round(postage, 2),
            "condition": str(item.get("condition") or "")[:40],
            "listed": str(item.get("itemCreationDate") or "")[:25],
            "url": listing_url(item, market),
            "incomplete": has_phrase(" ".join(words(item.get("title"))), INCOMPLETE_PHRASES),
        })

    total = payload.get("total")
    on_ebay = total if isinstance(total, int) and total >= len(items) else len(items)
    # eBay returned listings and not one of them names this game: that is not "no copies for
    # sale", it is "these search words do not find the game". The two are kept apart.
    unmatched = bool(items) and not kept and skipped.get("other_game") == len(items)
    result = {
        "status": "ok" if kept else "unmatched" if unmatched else "none",
        "currency": market["currency"],
        "platform_filter": "keyword" if keyword_search else "item_specific",
        "on_ebay": on_ebay,                   # eBay's own count for the search
        "fetched": len(items),
        "truncated": bool(payload.get("truncated", on_ebay > len(items))),   # true: eBay had more than it returned
        "counted": len(kept),
        "skipped": dict(sorted(skipped.items())),
        "skipped_examples": dict(sorted(examples.items())),   # a few left-out titles per reason
    }
    warning = first_message(payload.get("warnings"))
    if warning:
        result["warning"] = warning
    if kept:
        prices = [row["price"] for row in kept]
        postages = [row["postage"] for row in kept if row["postage"] is not None]
        kept.sort(key=lambda row: (row["price"], row["url"]))
        result.update({
            "lowest": round(min(prices), 2),
            "median": middle(prices),                                 # item price, postage not included
            "postage_known": len(postages),
            "median_postage": middle(postages) if postages else None,
            "incomplete_hint": sum(1 for row in kept if row["incomplete"]),
            "listings": [{k: v for k, v in row.items() if k != "incomplete"} for row in kept[:LISTINGS_KEPT]],
        })
    return result


def human_search_url(game, market):
    """The same search on eBay's own site, so every number links back to its source."""
    return (f"https://{market['site']}/sch/i.html?_nkw={quote(game['queries'][-1] + ' ps2')}"
            f"&_sacat={CATEGORY_ID}&LH_ItemCondition={quote(USED_CONDITION_IDS)}&LH_BIN=1&LH_PrefLoc=1")


def fetch(http_client, token, game, market_id, counter, by_aspect):
    """Run the game's searches on one site and merge them, each listing once.
    Returns (status, payload): the first failure as it came, or 200 and the merged listings."""
    merged, total, truncated, warning = {}, 0, False, ""
    for position, query in enumerate(game["queries"]):
        if position:
            time.sleep(REQUEST_PAUSE)
        status, payload = search(http_client, token, market_id, query, counter, by_aspect=by_aspect)
        if status != 200:
            return status, payload
        items = [item for item in payload.get("itemSummaries") or [] if isinstance(item, dict)]
        reported = payload.get("total") if isinstance(payload.get("total"), int) else len(items)
        truncated = truncated or reported > len(items)
        fresh = 0
        for item in items:
            identity = str(item.get("itemId") or item.get("legacyItemId") or len(merged))
            fresh += identity not in merged
            merged.setdefault(identity, item)
        total += max(reported, len(items)) - (len(items) - fresh)
        warning = warning or first_message(payload.get("warnings"))
    return 200, {"itemSummaries": list(merged.values()), "total": total, "truncated": truncated,
                 "warnings": [{"message": warning}] if warning else []}


def check_market(http_client, token, game, market_id, counter):
    """Look one game up on one eBay site."""
    market = MARKETS[market_id]
    base = {"search_url": human_search_url(game, market), "currency": market["currency"]}

    status, payload = fetch(http_client, token, game, market_id, counter, by_aspect=True)
    keyword_search = False
    if status == 200 and not payload["itemSummaries"]:
        # Nothing carries the PS2 item specific: ask again by keyword instead.
        time.sleep(REQUEST_PAUSE)
        status, payload = fetch(http_client, token, game, market_id, counter, by_aspect=False)
        keyword_search = True

    if status != 200:
        return {**base, "status": "error", "answered": status != 0, "error": error_text(status, payload)}
    return {**base, **summarise(payload, game, market, keyword_search)}


def describe(game, market, result):
    """One log line per lookup. Counts only: prices stay out of the public log."""
    label = f"  {game['title']} [{market['label']}]"
    if result["status"] == "error":
        return f"{label}: FAILED {result.get('error', '')}"
    notes = []
    if game.get("level") == "surging":
        notes.append("surging")
    if result["platform_filter"] == "keyword":
        notes.append("keyword search")
    if result["truncated"]:
        notes.append(f"first {result['fetched']} of {result['on_ebay']} on eBay")
    if result.get("warning"):
        notes.append(f"eBay warning: {result['warning']}")
    tail = f" ({'; '.join(notes)})" if notes else ""
    if result["status"] == "unmatched":
        return (f"{label}: none of the {result['fetched']} listings eBay returned names this game; "
                f"it needs its own search words{tail}")
    if result["status"] == "none":
        return f"{label}: no copies counted, {result['fetched']} returned{tail}"
    return f"{label}: {result['counted']} of {result['fetched']} listings counted{tail}"


def diagnose(http_client, token, game, counter, secrets):
    """How many listings eBay reports when one part of the search is changed. Counts only."""
    variants = (
        ("the search this script uses", True, "ids"),
        ("platform by keyword, not item specific", False, "ids"),
        ("condition asked for as USED", True, "used"),
        ("any condition", True, "any"),
    )
    say(f'Search check for "{game["title"]}" (listings eBay reports):')
    for market_id, market in MARKETS.items():
        for label, by_aspect, condition in variants:
            try:
                status, payload = search(http_client, token, market_id, game["queries"][0], counter,
                                         by_aspect=by_aspect, condition=condition)
            except LimitReached as exc:
                say(redact(f"  [{market['label']}] {label}: {exc}", secrets))
                return
            total = payload.get("total")
            answer = f"{total}" if status == 200 and isinstance(total, int) else error_text(status, payload)
            warning = first_message(payload.get("warnings"))
            say(redact(f"  [{market['label']}] {label}: {answer}"
                       + (f" (eBay warning: {warning})" if warning else ""), secrets))
            time.sleep(REQUEST_PAUSE)


def check_all(http_client, client_id, client_secret, lookups, allowance, known_good=True,
              with_diagnosis=False):
    """Work through the due lookups until they, the allowance or the time run out.

    Returns {"results": [(game, market id, result)], "searches": n, "stopped": why or ""}.
    `known_good` says whether earlier runs found listings; without that, a start in which
    every lookup comes back empty means the search itself is broken, and the run ends early."""
    token, basic = get_token(http_client, client_id, client_secret)
    secrets = (client_id, client_secret, token, basic)
    counter = {"searches": 0}
    if with_diagnosis and lookups:
        diagnose(http_client, token, lookups[0][0], counter, secrets)

    started, results, stopped, silent = time.monotonic(), [], "", 0
    for game, market_id in lookups:
        if counter["searches"] + 2 > allowance:
            stopped = "this run's allowance of searches is used"
            break
        if time.monotonic() - started > TIME_BUDGET:
            stopped = "this run's time is up"
            break
        try:
            result = check_market(http_client, token, game, market_id, counter)
        except LimitReached as exc:
            stopped = f"eBay says the allowance of searches is used up ({redact(exc, secrets)})"
            break
        time.sleep(REQUEST_PAUSE)
        for field in ("error", "warning"):
            if field in result:
                result[field] = redact(result[field], secrets)
        silent = silent + 1 if result.get("answered") is False else 0
        result.pop("answered", None)
        results.append((game, market_id, result))
        say(redact(describe(game, MARKETS[market_id], result), secrets))
        if silent >= MAX_SILENT_LOOKUPS:
            stopped = f"eBay did not answer {silent} lookups in a row"
            break
        if len(results) == MIN_LOOKUPS_TO_JUDGE:
            failed = sum(1 for _, _, earlier in results if earlier["status"] == "error")
            empty = sum(1 for _, _, earlier in results if earlier["status"] != "error" and not earlier["fetched"])
            if failed == len(results) or (not known_good and failed + empty == len(results)):
                stopped = f"the first {len(results)} lookups all failed or came back empty"
                break
    return {"results": results, "searches": counter["searches"], "stopped": stopped}


def verdict(results, state):
    """None when the run is worth keeping, otherwise the reason it is not."""
    answered = [(game, market_id, result) for game, market_id, result in results if result["status"] != "error"]
    errors = len(results) - len(answered)
    if not results:
        return None
    if not answered:
        return "every lookup failed, so nothing was written."
    if errors * 2 > len(results):
        return (f"{errors} of {len(results)} lookups failed, so nothing was written and the "
                "previous figures stay in place.")

    previous = prior_games(state)

    def had_copies(entry):
        return isinstance(entry, dict) and isinstance(entry.get("copies"), int) and entry["copies"] > 0

    known = [result for game, market_id, result in answered
             if had_copies((previous.get(game["key"]) or {}).get(MARKETS[market_id]["label"]))]
    if len(known) >= MIN_KNOWN_TO_JUDGE and all(result["fetched"] == 0 for result in known):
        return (f"{len(known)} games that had copies listed last time now return nothing at all, so nothing "
                "was written. The search is probably broken: send this log to whoever maintains the script.")
    nothing_known = not any(had_copies(entry.get(market["label"])) for entry in previous.values()
                            for market in MARKETS.values())
    if nothing_known and len(answered) >= MIN_LOOKUPS_TO_JUDGE \
            and all(result["fetched"] == 0 for _, _, result in answered):
        return ("eBay answered but returned no listings for any game, so nothing was written. "
                "The search filter is probably wrong: send this log to whoever maintains the script.")
    return None


# ======================================================================================
# What gets written
# ======================================================================================

def numbers_of(result, stamp):
    """The part of a lookup that is kept under data/: numbers only."""
    if result["status"] == "unmatched":
        return {"checked": stamp, "unmatched": True}
    entry = {"checked": stamp, "copies": result["counted"],
             "lowest": result.get("lowest"), "median": result.get("median"),
             "postage": result.get("median_postage")}
    if result["truncated"]:
        entry["truncated"] = True
    return entry


def update_records(state, games, run, now):
    """(new latest.json, rows to add to this month's history) after a run."""
    stamp, today = now.strftime(STAMP_FORMAT), now.strftime("%Y-%m-%d")
    previous = prior_games(state)
    checked = {}
    for game, market_id, result in run["results"]:
        if result["status"] != "error":
            checked[(game["key"], MARKETS[market_id]["label"])] = numbers_of(result, stamp)

    rows, latest_games = [], {}
    for game in games:
        entry = {"level": game["level"], "mentions": game["mentions"]}
        if game["pinned"]:
            entry["pinned"] = True
        if game["surging_until"]:
            entry["surging_until"] = game["surging_until"].strftime(STAMP_FORMAT)
        old_entry = previous.get(game["key"]) or {}
        for market in MARKETS.values():
            label = market["label"]
            old = old_entry.get(label) if isinstance(old_entry.get(label), dict) else None
            new = checked.get((game["key"], label))
            if new is None:
                if old:
                    entry[label] = old          # not checked this run (or it failed): keep what we had
                continue
            if "copies" in new:                 # a real answer; "unmatched" has no figures to record
                figures = (new["copies"], new["lowest"], new["median"])
                unchanged = old and figures == (old.get("copies"), old.get("lowest"), old.get("median"))
                if not (unchanged and old.get("recorded") == today):
                    rows.append([stamp, game["title"], label, *figures])   # changed, or the day's first check
                new["recorded"] = today                                     # the day of its latest history row
            entry[label] = new
        latest_games[game["title"]] = entry

    used = state.get("searches") if isinstance(state.get("searches"), dict) else {}
    used_today = used.get("used", 0) if used.get("day") == today else 0
    latest = {
        "what": ("Asking prices of used Buy It Now copies of PS2 games on eBay, by site. Numbers only: "
                 "copies listed, lowest and median price before postage, typical postage. Not sold prices."),
        "currencies": {market["label"]: market["currency"] for market in MARKETS.values()},
        "searches": {"day": today, "used": used_today + run["searches"]},
        "games": latest_games,
    }
    return latest, rows


def write_latest(path, latest):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(latest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def append_history(path, rows):
    """Add rows to a month's history. One row per line: the file stays readable and its diffs small."""
    if not rows:
        return
    history = read_own(path, []) + rows
    lines = ",\n  ".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in history)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(f"[\n  {lines}\n]\n", encoding="utf-8")


def snapshot_of(run, now):
    """This run's listings, for the --out file."""
    rows = {}
    for game, market_id, result in run["results"]:
        row = rows.setdefault(game["title"], {"title": game["title"], "level": game["level"],
                                              "search": game["search"], "queries": game["queries"],
                                              "left_out_if_named": game["siblings"][:20], "markets": {}})
        row["markets"][market_id] = result
    return {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "what": "Asking prices of used Buy It Now listings still for sale on eBay. Not sold prices.",
        "source": "eBay Browse API",
        "markets": {market_id: {k: market[k] for k in ("label", "site", "currency")}
                    for market_id, market in MARKETS.items()},
        "searches_used": run["searches"],
        "stopped_early": run["stopped"],
        "games": list(rows.values()),
    }


def describe_plan(games, left_out, lookups, allowance):
    levels = {level: sum(1 for game in games if game["level"] == level) for level in CHECK_EVERY_HOURS}
    pinned = sum(1 for game in games if game["pinned"])
    say(f"Tracking {len(games)} games ({pinned} pinned): " + ", ".join(
        f"{count} {level}" for level, count in levels.items()) + ".")
    for game in games:
        if game["level"] == "surging":
            say(f"  surging: {game['title']}")
    reasons = (("one_word", "one-word name that is also an ordinary word (pin it to track it)"),
               ("not_in_library", "not in the PS2 library"),
               ("never", 'on the "never" list'))
    for reason, text in reasons:
        titles = left_out[reason]
        if titles:
            shown = ", ".join(titles[:12]) + (f" and {len(titles) - 12} more" if len(titles) > 12 else "")
            say(f"Left out, {text}: {len(titles)} ({shown}).")
    say(f"Due now: {len(lookups)} lookups. This run may use {max(allowance, 0)} searches.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="eBay asking prices for the PS2 games the feed mentions.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write this run's listings")
    parser.add_argument("--plan", action="store_true", help="show what would be checked now, then stop")
    args = parser.parse_args(argv)

    client_id = os.environ.get("EBAY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    with_diagnosis = os.environ.get("EBAY_DIAGNOSE", "").strip().lower() == "true"
    now = utc_now()
    latest_path = PRICES_DIR / LATEST_NAME
    try:
        history_path = PRICES_DIR / f"{now.strftime('%Y-%m')}.json"
        pinned, never = load_watchlist()
        state = load_state(latest_path)
        read_own(history_path, [])    # fail now, before asking eBay, if the history cannot be added to
        mentions, ever = load_mentions()
        library, catalogue = load_library()
        games, left_out = plan_games(now, pinned, never, mentions, ever, library, catalogue, state)
        lookups = due_lookups(games, state, now)
        used = state.get("searches") if isinstance(state.get("searches"), dict) else {}
        used_today = used.get("used", 0) if used.get("day") == now.strftime("%Y-%m-%d") else 0
        allowance = min(MAX_SEARCHES_PER_RUN, DAILY_SEARCHES - used_today)
        describe_plan(games, left_out, lookups, allowance)
        if args.plan:
            return 0
        if not lookups:
            say("Nothing is due, so eBay was not asked.")
            return 0
        if allowance < 2:
            say("Today's allowance of eBay searches is used up; the due lookups wait for tomorrow.")
            return 0
        if not client_id or not client_secret:
            raise EbayError(
                "The eBay key is not set. In the repository on GitHub: Settings > Secrets and variables "
                "> Actions > New repository secret. Add EBAY_CLIENT_ID (the Production App ID) and "
                "EBAY_CLIENT_SECRET (the Production Cert ID)."
            )
        known_good = any(isinstance(site, dict) and site.get("copies") for entry in state.get("games", {}).values()
                         for site in entry.values())
        run = check_all(Http(), client_id, client_secret, lookups, allowance, known_good, with_diagnosis)
    except EbayError as exc:
        say(f"STOPPED: {redact(exc, (client_id, client_secret))}")
        return 1

    answered = sum(1 for _, _, result in run["results"] if result["status"] != "error")
    say(f"{run['searches']} searches used; {answered} of {len(run['results'])} lookups answered; "
        f"{len(lookups) - len(run['results'])} left for the next run.")
    if run["stopped"]:
        say(f"Stopped early: {run['stopped']}.")
    problem = verdict(run["results"], state)
    if problem:
        say(f"STOPPED: {problem}")
        return 1

    latest, rows = update_records(state, games, run, now)
    try:
        append_history(history_path, rows)
    except EbayError as exc:
        say(f"STOPPED: {exc}")
        return 1
    write_latest(latest_path, latest)
    say(f"Wrote {LATEST_NAME} and added {len(rows)} rows to this month's price history.")
    if run["results"]:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(snapshot_of(run, now), indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
