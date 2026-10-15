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

Set EBAY_CHECK_GAME="Kuon" (the workflow's "check_game" box) to see how many listings eBay reports for that game
when one part of the search is relaxed at a time (counts only; nothing is looked up or written).

Set EBAY_DIAGNOSE=true to also print how many listings eBay reports for a few
variations of the search (counts only), which shows whether the filters work.
"""

import argparse
import base64
import http.client
import json
import math
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
UNDERRATED_PATH = ROOT / "underrated.json"      # the Underrated page's games (read only)
RARE_PATH = ROOT / "rare_games.json"            # the Rarest page's two lists (read only)
EDITIONS_PATH = ROOT / "editions.json"          # limited and collector's editions, each priced on its own (read only)
CONSOLES_PATH = ROOT / "rare_consoles.json"     # the Rarest page's consoles (read only)
DEFAULT_OUT = Path(tempfile.gettempdir()) / "ebay_prices.json"   # outside the repository on purpose
DATA_DIR = ROOT / "data"
FEED_PATH = DATA_DIR / "sentiment_feed.json"      # the scraper's 14-day snapshot (read only)
ARCHIVE_DIR = DATA_DIR / "archive"                # every mention ever recorded (read only)
LIBRARY_PATH = DATA_DIR / "ps2_database.json"     # the PS2 library (read only)
PRICES_DIR = DATA_DIR / "prices"                  # written here: numbers only
LATEST_NAME = "latest.json"
INDEX_NAME = "index.json"                         # the PS2 price index, worked out from the history
SERIES_NAME = "series.json"                       # each game's daily median, for its chart on the dashboard
SERIES_DAYS = 90
SERIES_EPOCH = "2026-10-01"                      # series.json counts days from here, so old points never change

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"   # public data only; cannot act on an eBay account
USER_AGENT = "python:ps2-sentiment-tracker-ebay:1.0 (+https://github.com/SirNovaTofuBlaster/ps2-sentiment-tracker)"

CATEGORY_ID = "139973"                     # eBay's "Video Games" category, same number on both sites
CONSOLE_CATEGORY_ID = "139971"             # eBay's "Video Game Consoles", same number on both sites
# Every condition but "for parts or not working": a rare console is often sold new or refurbished.
CONSOLE_CONDITION_IDS = "1000|1500|2000|2010|2020|2030|2500|2750|3000|4000|5000|6000"
PLATFORM_ASPECT = "Sony PlayStation 2"     # the "Platform" item specific sellers pick
USED_CONDITION_IDS = "2750|3000|4000|5000"   # like new, used, very good, good; "acceptable" (6000) is left out (2026-10-15)
NEW_CONDITION_IDS = "1000|1500|1750"   # new, new other, new with defects: sealed copies are listed as these
CONDITION_FILTERS = {
    "new": f"conditionIds:{{{NEW_CONDITION_IDS}}}",   # the Rarest page's second look, at unused copies
    "ids": f"conditionIds:{{{USED_CONDITION_IDS}}}",   # what this script uses; leaves out "for parts"
    "used": "conditions:{USED}",                       # diagnosis only
    "any": "",                                         # diagnosis only
}
MARKETS = {
    # "foreign" words mark a copy made for another region, which is a different product.
    # They include the first part of the code printed on the spine: SLES/SCES is Europe, SLUS/SCUS America.
    # Optional, for a site added later (see "Other eBay sites" in AGENTS.md): "extra": True keeps the
    # Rarest page's consoles off it unless they name it; "min_every_hours" is the least time between
    # two checks of one game there (its own clock, so a new site cannot crowd out the first two);
    # "junk" is words in the site's own language that mark a listing as not a copy, "incomplete" those
    # that mark one as less than a complete copy; "names_like" borrows another site's regional_names;
    # "keyword_only" searches by the words "ps2" and never by the PS2 item specific.
    # "zip" is where postage is quoted to. In the US most sellers let eBay work postage out
    # from the buyer's address, and without one eBay gives no figure; New York stands in.
    "EBAY_US": {"label": "US", "site": "www.ebay.com", "country": "US", "currency": "USD", "zip": "10001",
                "foreign": ("pal", "european", "sles", "sces")},
    "EBAY_GB": {"label": "UK", "site": "www.ebay.co.uk", "country": "GB", "currency": "GBP",
                "foreign": ("ntsc", "usa", "us version", "slus", "scus")},
    # Germany (switched on 2026-10-14). Sold there are PAL copies, as in Britain, and the game names are
    # mostly the English ones, so it borrows the UK's renames ("names_like"). The words are as
    # words() writes them (no accents: "Hülle" is "hulle"; no ß, which it would split). Written from
    # knowledge of how German sellers list games, not yet checked against live listings: the first
    # run's listings file on the ebay-data branch shows what each rule left out.
    "EBAY_DE": {"label": "DE", "site": "www.ebay.de", "country": "DE", "currency": "EUR",
                "extra": True, "min_every_hours": 24, "names_like": "UK",
                # Keyword search only: the probe counted listings by the words "ps2" and the category, which
                # works; the "Platform" item specific is named and valued in German there, and a wrong
                # guess would fail every lookup. The title must say PS2 or PlayStation 2 (PLATFORM_WORDS).
                "keyword_only": True,
                "foreign": ("ntsc", "usa", "us version", "us import", "slus", "scus"),
                "junk": ("nur hulle", "nur cover", "nur anleitung", "nur booklet", "nur das cover", "nur die hulle",
                         "leerhulle", "leere hulle", "leerverpackung", "ohne spiel", "ohne disc", "ohne cd", "ohne dvd",
                         "ersatzhulle", "ersatzcover", "defekt", "kaputt", "bastler", "nicht funktionsfahig",
                         "konvolut", "sammlung", "spielesammlung", "spielepaket", "restposten", "paket",
                         "losungsbuch", "spieleberater", "kopie", "raubkopie", "nachdruck", "fanartikel", "figur",
                         "plusch", "nachbau"),
                "incomplete": ("ohne anleitung", "ohne ovp", "ohne hulle", "ohne cover", "ohne handbuch",
                               "nur disc", "nur cd", "nur dvd", "nur spiel", "lose", "ohne box")},
    # France (switched on 2026-10-14): as Germany, with French sellers' words, written the same way
    # (no accents) and equally not yet checked against live listings.
    "EBAY_FR": {"label": "FR", "site": "www.ebay.fr", "country": "FR", "currency": "EUR",
                "extra": True, "min_every_hours": 48, "names_like": "UK", "keyword_only": True,
                "foreign": ("ntsc", "usa", "us version", "us import", "slus", "scus"),
                "junk": ("boite seule", "boitier seul", "notice seule", "livret seul", "jaquette seule", "coque seule",
                         "sans jeu", "sans disque", "boitier vide", "boite vide", "defectueux", "en panne",
                         "ne fonctionne pas", "hors service", "pour pieces", "collection", "guide officiel",
                         "guide strategique", "solution complete", "copie", "figurine", "peluche"),
                "incomplete": ("sans notice", "sans boite", "sans boitier", "sans jaquette", "sans livret",
                               "disque seul", "jeu seul", "cd seul", "dvd seul", "loose")},
    # Italy (switched on 2026-10-14): as Germany and France, with Italian sellers' words.
    "EBAY_IT": {"label": "IT", "site": "www.ebay.it", "country": "IT", "currency": "EUR",
                "extra": True, "min_every_hours": 24, "names_like": "UK", "keyword_only": True,
                "foreign": ("ntsc", "usa", "us version", "us import", "slus", "scus"),
                "junk": ("solo scatola", "solo custodia", "solo manuale", "solo libretto", "solo copertina",
                         "senza gioco", "senza disco", "custodia vuota", "scatola vuota", "difettoso",
                         "non funzionante", "non funziona", "per ricambi", "per parti", "lotto", "stock",
                         "collezione", "guida ufficiale", "guida strategica", "figura", "peluche"),
                "incomplete": ("senza manuale", "senza libretto", "senza custodia", "senza scatola",
                               "senza copertina", "solo disco", "solo gioco", "solo cd", "sfuso")},
    # Spain (switched on 2026-10-14): as the others, with Spanish sellers' words.
    "EBAY_ES": {"label": "ES", "site": "www.ebay.es", "country": "ES", "currency": "EUR",
                "extra": True, "min_every_hours": 72, "names_like": "UK", "keyword_only": True,
                "foreign": ("ntsc", "usa", "us version", "us import", "slus", "scus"),
                "junk": ("solo caja", "solo carcasa", "solo manual", "solo funda", "solo portada", "sin juego",
                         "sin disco", "caja vacia", "estuche vacio", "defectuoso", "roto", "no funciona",
                         "para piezas", "para repuestos", "lote", "coleccion", "guia oficial", "guia estrategica",
                         "replica", "figura", "peluche"),
                "incomplete": ("sin manual", "sin caja", "sin estuche", "sin portada", "solo disco", "solo juego",
                               "solo cd", "suelto")},
}

# ---- How often each game is checked -------------------------------------------------
WINDOW_DAYS = 14             # "recently" means this long; it is also how far back the feed goes
STAPLE_DAYS = 5              # named on this many of those days: a staple, where a mention is no news
SURGE_HOURS = 24             # a surge is judged over this long...
SURGE_SOURCES = 2            # ...and needs this many different sources, each with its own headline,
SURGE_QUIET_MENTIONS = 1     # ...for a game named at most this often in the rest of the window
SURGE_HOLD_HOURS = 48        # once surging, a game stays surging this long after its last mention
CHECK_EVERY_HOURS = {"surging": 0, "normal": 6, "staple": 6, "dormant": 24, "underrated": 24, "rare": 12}   # 0 = every run
RARE_SLOW_KINDS = ("console", "edition")   # level "rare" but still daily: only the Rarest page's games are checked every 12 hours
# The Rarest page's lists in rare_games.json, and the one site each is priced on: a rare PAL game
# is a PAL copy, sold in Britain; a rare US game is an American copy.
RARE_SITES = {"PAL": "EBAY_GB", "US": "EBAY_US"}
# A steady game on one site (normal or staple only): at least STEADY_MIN_COPIES listed every time it was
# checked in the last STEADY_LOOK_DAYS days, the median within STEADY_PRICE_RANGE of its middle value, the
# number of copies within STEADY_COPIES_RANGE of its middle value, and checks spanning STEADY_SPAN_DAYS.
# Such a pair is looked up every STEADY_EVERY_HOURS, until a check breaks the pattern. Chosen by replaying
# the first nine days of history (docs/VERIFICATION.md): 0.4% of flagged moments saw a move over 10% within
# the next two days.
STEADY_EVERY_HOURS = 48
STEADY_MIN_COPIES = 50
STEADY_PRICE_RANGE = 0.10
STEADY_COPIES_RANGE = 0.30
STEADY_LOOK_DAYS = 6
STEADY_SPAN_DAYS = 4
STEADY_MIN_ROWS = 3
EARLY_MINUTES = 30           # a check may come this much early, so "every 6 hours" does not drift to 7
CHANGE_DAYS = 7              # beside each median, how it compares with the median this long before...
CHANGE_SLACK_DAYS = 2        # ...as recorded at most this much longer before (a quiet game is checked daily)
CONFIRMED_MIN = 3           # the "confirmed complete" figure needs this many listings that say so
CHANGE_MIN_DAYS = 3          # until a game has a week of history, it is compared with its oldest check at least this old
WATCH_RECHECK_MINUTES = 60   # a watched game named in the feed since its last check waits at most this long
QUIET_EVERY_HOURS = 48       # a game that had no copies (or whose words found none) at its last check waits this long

# ---- How much of eBay's allowance (5,000 searches a day) a run may use ---------------
DAILY_SEARCHES = 4900        # stop for the day here, leaving room for runs started by hand
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
    suffering syberia tengai timesplitters trapt vexx xiii yakuza zathura zoocube
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
# A console listing with one of these is not a working console of that model.
CONSOLE_JUNK = (
    "for parts", "spares", "spares or repair", "spares or repairs", "for repair", "needs repair", "faulty",
    "not working", "broken",
    "untested", "modded", "modchip", "mod chip", "free mcboot", "fmcb", "skin", "sticker", "decal",
    "shell", "housing", "faceplate", "case only", "box only", "empty box", "manual only", "replica",
    "custom", "painted", "reproduction", "repro", "controller only", "no console", "job lot", "joblot",
    "stand only",
)
# A listing that names one of these is that part, unless it says the console comes with it
# ("with controller", "+ remote") or says it is a console.
CONSOLE_PARTS = (
    "controller", "controllers", "dualshock", "joypad", "gamepad", "remote", "remote control", "power cord",
    "power cable", "power supply", "ac adapter", "adapter", "cable", "cables", "hdd", "hard drive", "pcb",
    "motherboard", "memory card",
)
CONSOLE_WORDS = ("console", "consoles", "system", "scph")
OTHER_CONSOLES = ("ps3", "ps4", "ps5", "psp", "ps vita", "xbox", "wii", "gamecube", "dreamcast", "nintendo switch")
CONSOLE_CATEGORIES = {"consoles": CONSOLE_CATEGORY_ID, "any": ""}
MAX_CONSOLE_QUERIES = 3

# A graded or factory-sealed copy is another product, priced several times a used one; listed
# among used copies by mistake it would pull a rare game's median far up.
# "vga" alone is also a cable, and "new sealed" a replacement case, so neither is on the list.
GRADED_OR_SEALED = (
    "graded", "wata", "vga graded", "cgc", "ukg", "factory sealed", "sealed new", "still sealed",
    "brand new sealed", "sealed brand new", "mint sealed", "sealed mint",
)
NOT_GRADED = ("not graded", "never graded")

# Left out of the figures (reason "incomplete", 2026-10-15): the price is for less than a complete copy.
INCOMPLETE_PHRASES = (
    "disc only", "disk only", "game only", "loose", "no manual", "no case", "no box",
    "no cover", "no inlay", "missing manual", "without manual",
)

# Titles that say the copy is complete: the "confirmed complete" figure is made from these alone.
COMPLETE_PHRASES = (
    "complete", "cib", "boxed", "with manual", "manual included", "includes manual", "inc manual",
    "with case", "with box", "case and manual", "box and manual",
)

# Game lookups ask eBay for the cheapest listings first (`sort=price`), so the 200 a search returns are
# the 200 cheapest. If eBay ever refuses the parameter the run drops it for the rest of the run.
SORT_BY_PRICE = {"on": True, "worked": False}   # "worked": a sorted search has been answered this run


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


def the_less(text):
    """A name with every "the" removed, for comparing: sellers write "Prince of Persia: The Sands of Time"
    where the library has "Prince of Persia: Sands of Time". Used only when a listing's words are
    checked against a game's name (never for the search words or the keys, which stay as they are)."""
    return " ".join(word for word in text.split() if word != "the")


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


def load_regional_names(path=None):
    """The names a game goes by on one site when it was released there under another one, from
    "regional_names" in ebay_watchlist.json: {"UK": [{"from": "Fatal Frame", "to": "Project
    Zero"}, ...]}. A rule renames the start of a game's name: Fatal Frame 2: Crimson Butterfly
    is searched on eBay UK as Project Zero 2: Crimson Butterfly. Returns {market id: [(from
    words, to words), ...]} in the spelling search_terms() gives."""
    path = path or WATCHLIST_PATH
    name = Path(path).name
    raw = read_json(path, {})
    given = raw.get("regional_names", {})
    labels = {market["label"]: market_id for market_id, market in MARKETS.items()}
    if not isinstance(given, dict) or set(given) - set(labels):
        raise EbayError(f'{name}: "regional_names" must map {", ".join(labels)} to lists of renames.')
    rules = {}
    for label, renames in given.items():
        if not isinstance(renames, list):
            raise EbayError(f'{name}: "regional_names" for {label} must be a list.')
        for position, rename in enumerate(renames, 1):
            if not isinstance(rename, dict) or not all(isinstance(rename.get(side), str) and words(rename[side])
                                                       for side in ("from", "to")):
                raise EbayError(f'{name}: rename {position} for {label} needs "from" and "to" names.')
            (old, old_queries), (new, new_queries) = search_terms(rename["from"]), search_terms(rename["to"])
            if not old_queries or not new_queries or len(new_queries[0]) + len(" ps2") > MAX_QUERY_CHARS \
                    or (" " not in new and new_queries[0] not in ONE_WORD_TITLES):
                raise EbayError(f'{name}: rename {position} for {label} ("{rename["to"]}") does not work as eBay '
                                'search words: use the full name, of two words or more.')
            rules.setdefault(labels[label], []).append((old, old_queries[0], new, new_queries[0]))
    for market_id, market in MARKETS.items():          # a site that goes by another site's names
        if market.get("names_like") and market_id not in rules:
            rules[market_id] = list(rules.get(labels[market["names_like"]], ()))
    return rules


def renamed(phrase, rules):
    """The phrase with the first rule whose words it starts with applied, or None."""
    for old, old_plain, new, new_plain in rules:
        for start, replacement in ((old, new), (old_plain, new_plain)):
            if phrase == start or phrase.startswith(start + " "):
                return replacement + phrase[len(start):]
    return None


def apply_regional_names(games, rules, catalogue=()):
    """Give each game that goes by another name on a site its search words for that site
    (game["markets"][market id]). Its other games are those of the name it has there, from the
    library ("forbidden siren 2" for Forbidden Siren), and its usual ones renamed the same way;
    never its own name there."""
    for game in games:
        for market_id, market_rules in rules.items():
            phrase = renamed(game["search"], market_rules)
            if phrase is None:
                continue
            queries = [renamed(query, market_rules) or query for query in game["queries"]]
            siblings = {renamed(other, market_rules) or other for other in game.get("siblings") or ()}
            siblings |= set(other_games(game["title"], phrase, catalogue))
            siblings.discard(phrase)
            game.setdefault("markets", {})[market_id] = {"search": phrase, "queries": queries,
                                                         "siblings": sorted(siblings)}
    return games


def for_market(game, market_id):
    """The game as it is looked for on one site: its regional name there, if it has one."""
    return {**game, **(game.get("markets") or {}).get(market_id, {})}


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
        game["latest_mention"] = max((m["when"] for m in by_key.get(game["key"], [])), default=None)
    return sorted(games.values(), key=lambda game: game["title"].lower()), left_out


def load_underrated(path=None):
    """The titles on the Underrated page, from underrated.json. A missing or damaged file gives none:
    the page's games are an extra and must never stop the pricing of the others."""
    raw = read_json(Path(path or UNDERRATED_PATH), {})
    rows = raw.get("games") if isinstance(raw, dict) else None
    return [row["title"] for row in rows or [] if isinstance(row, dict) and isinstance(row.get("title"), str)
            and key_of(row["title"])]


def add_underrated_games(games, titles, library, catalogue):
    """Price the Underrated page's games on the first two sites (US and UK) once a day, so that a
    gem has a figure the day it is shown. A game the feed tracks already keeps its own level and
    sites; a title that is not in the PS2 library, or whose one word is an ordinary word, is left
    out (the page could not find its figure either). Returns the titles left out."""
    keys = {game["key"] for game in games}
    names = {game["search"] for game in games}
    sites = [market_id for market_id, market in MARKETS.items() if not market.get("extra")]
    left_out = []
    for title in titles:
        key = key_of(title)
        if key in keys:
            continue
        if key not in library:
            left_out.append(title)
            continue
        name, queries = search_terms(library[key])
        if name in names:
            continue
        if not queries or any(len(query) + len(" ps2") > MAX_QUERY_CHARS for query in queries) \
                or (" " not in name and queries[0] not in ONE_WORD_TITLES):
            left_out.append(title)
            continue
        games.append({"title": library[key], "key": key, "search": name, "queries": queries, "exclude": [],
                      "pinned": False, "siblings": other_games(library[key], name, catalogue),
                      "level": "underrated", "mentions": 0, "surging_until": None, "sites": list(sites)})
        keys.add(key)
        names.add(name)
    games.sort(key=lambda game: game["title"].lower())
    return left_out


def mark_watched(games, titles):
    """Flag the games of the Rarest and Underrated pages: a new mention of one in the feed has it looked up
    again at the next run, whatever its clock (`due_lookups()`)."""
    keys = {key_of(title) for title in titles}
    names = {search_terms(title)[0] for title in titles}
    for game in games:
        game["watch"] = game.get("kind") not in RARE_SLOW_KINDS and (game["key"] in keys or game["search"] in names)


def load_rare(path=None, kind=None):
    """(entries, problems) from rare_games.json: every game on the Rarest page's two lists, with
    the words to look for. A missing file gives none. A file or an entry that cannot be used is
    left out and named in the problems, so that it never stops the pricing of every other game.
    With kind="edition" the file is editions.json: the same shape, but every entry must carry
    "require" words (an edition is told from the plain game by them), and the games made from it
    stay off the PS2 index and the eBay prices page."""
    path = Path(path or RARE_PATH)
    if not path.exists():
        return [], []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return [], [f"{path.name} cannot be read ({type(exc).__name__})"]
    lists = raw.get("lists") if isinstance(raw, dict) else None
    if not isinstance(lists, dict) or not lists or set(lists) - set(RARE_SITES) \
            or not all(isinstance(rows, list) for rows in lists.values()):
        return [], [f'{path.name} needs "lists" of games for {" and ".join(RARE_SITES)}']

    def phrases(value):
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(text, str) and words(text) for text in value):
            return None
        return [" ".join(name_words(text)) for text in value]

    entries, problems = [], []
    for list_name, rows in lists.items():
        for position, row in enumerate(rows, 1):
            title = row.get("title") if isinstance(row, dict) else None
            if not isinstance(title, str) or not key_of(title):
                problems.append(f"{list_name} entry {position} has no title")
                continue
            search = row.get("search", title)
            phrase, queries = search_terms(search) if isinstance(search, str) else ("", [])
            require, exclude = phrases(row.get("require")), phrases(row.get("exclude"))
            allow = row.get("allow") or []
            if require is None or exclude is None or not isinstance(allow, list) \
                    or not all(isinstance(phrase, str) and phrase in JUNK_PHRASES for phrase in allow):
                problems.append(f'{list_name} "{title}": "require" and "exclude" must be lists of words, '
                                '"allow" a list of the junk phrases an edition comes with')
                continue
            if kind == "edition" and not require:
                problems.append(f'{list_name} "{title}": an edition needs "require" words to be told from the plain game')
                continue
            # One word that is also an ordinary word would count every listing that uses it
            # ("rare obscure horror game"), as for the games the feed names.
            if " " not in phrase and phrase not in ONE_WORD_TITLES and not require:
                problems.append(f'{list_name} "{title}": not priced, "{phrase}" is an ordinary word')
                continue
            # The words a listing must also contain go into the search, so that eBay finds them.
            queries = [" ".join([query, *[word for word in " ".join(require).split() if word not in query.split()]])
                       for query in queries]
            if not queries or any(len(query) + len(" ps2") > MAX_QUERY_CHARS for query in queries):
                problems.append(f'{list_name} "{title}": the search words do not work for eBay')
                continue
            other = row.get("other_title")
            entries.append({"list": list_name, "title": title.strip(), "search": phrase, "queries": queries,
                            "require": require, "exclude": exclude, "allow": sorted(allow), "kind": kind,
                            "other_title": other.strip() if isinstance(other, str) and key_of(other) else None})
    return entries, problems


def add_rare_games(games, rare, catalogue):
    """Put the Rarest page's games among the games to price. One that is tracked already (the feed
    has named it) is priced as before, and its figures serve the list too. Any other one is added
    with the level "rare": looked up once a day, and only on its own list's site. Returns
    {list: {title on the list: title in latest.json}}, so the page can find each game's figures."""
    known = {}
    for game in games:
        known.setdefault(("name", search_terms(game["title"])[0]), game)
        for market_id in MARKETS:
            known.setdefault((market_id, for_market(game, market_id)["search"]), game)
    keys = {game["key"] for game in games}
    owners = {game["key"]: game for game in games}
    placed, added = {list_name: {} for list_name in RARE_SITES}, {}
    for entry in rare:
        market_id = RARE_SITES[entry["list"]]
        game = None
        if not entry["require"]:   # an edition is never the same thing as the game the feed tracks
            # Not by its name in the other region: the tracked game is looked for under that name
            # here ("Tokyo Xtreme Racer: Drift 2" on eBay UK, where it was sold as Kaido Racer 2).
            name = search_terms(entry["title"])[0]
            game = known.get((market_id, entry["search"])) or known.get((market_id, name)) or known.get(("name", name))
        if game is None:
            # The same game on both lists is one game, looked up on both sites, leaving out what
            # either list leaves out.
            identity = (entry["search"], tuple(entry["require"]), tuple(entry["allow"]), entry.get("kind"))
            game = added.get(identity)
            if game is None:
                key = key_of(entry["title"])
                if key in keys:
                    # Its title belongs to another game here and would take that one's figures. An edition
                    # whose own name is already priced (the feed tracks it, or the Rarest page lists it, by the
                    # same strict title) points at that game, when it is priced on this site.
                    owner = owners.get(key)
                    if entry.get("kind") == "edition" and owner is not None and owner.get("kind") != "console" \
                            and (not owner.get("sites") or market_id in owner["sites"]):
                        placed[entry["list"]][entry["title"]] = owner["title"]
                    continue
                # Library names for this very game are not other games: "Project Zero 3 Tormented",
                # "R.A.D. Robot Alchemic Drive" (single letters are an abbreviation's).
                own = set(name_words(readable(entry["title"])))
                siblings = [] if entry["require"] else [
                    other for other in other_games(entry["title"], entry["search"], catalogue)
                    if {word for word in other.split() if len(word) > 1} - own]
                game = {"title": entry["title"], "key": key, "search": entry["search"], "queries": entry["queries"],
                        "exclude": entry["exclude"], "require": entry["require"], "allow": entry["allow"], "pinned": False,
                        "siblings": siblings, "level": "rare", "mentions": 0, "surging_until": None, "sites": []}
                if entry.get("kind"):
                    game["kind"] = entry["kind"]
                added[identity] = game
                keys.add(key)
                owners[key] = game
            if market_id not in game["sites"]:
                game["sites"].append(market_id)
            game["exclude"] = sorted(set(game["exclude"]) | set(entry["exclude"]))
        # Its new and sealed copies are counted too, on this list's site: a rare game's copies are often that. This
        # includes a game the feed already tracks (Kuon): its used lookup is reused, and it was left without the
        # second look until 2026-10-15.
        game["new_tier"] = sorted(set(game.get("new_tier") or ()) | {market_id})
        placed[entry["list"]][entry["title"]] = game["title"]
    games.extend(added.values())
    games.sort(key=lambda game: game["title"].lower())
    return placed


def load_consoles(path=None):
    """(consoles, problems) from rare_consoles.json, each ready to price. A missing file gives
    none; a file or an entry that cannot be used is named in the problems and left out. An
    entry with "price": false is left out without a word: the page says why."""
    path = Path(path or CONSOLES_PATH)
    if not path.exists():
        return [], []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return [], [f"{path.name} cannot be read ({type(exc).__name__})"]
    rows = raw.get("consoles") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return [], [f'{path.name} needs a "consoles" list']
    labels = {market["label"]: market_id for market_id, market in MARKETS.items()}

    def phrases(value):
        if not isinstance(value, list) or not all(isinstance(text, str) and words(text) for text in value):
            return None
        return [" ".join(words(text)) for text in value]

    consoles, problems = [], []
    for position, row in enumerate(rows, 1):
        name = row.get("name") if isinstance(row, dict) else None
        if not isinstance(name, str) or not key_of(name):
            problems.append(f"console {position} has no name")
            continue
        if row.get("price", True) is False:
            continue
        spec = row.get("search") if isinstance(row.get("search"), dict) else {}
        queries = spec.get("queries")
        require, require_any, exclude = (phrases(spec.get(field, [])) for field in ("require", "require_any", "exclude"))
        sites = row.get("sites", [market["label"] for market in MARKETS.values() if not market.get("extra")])
        if not isinstance(queries, list) or not 1 <= len(queries) <= MAX_CONSOLE_QUERIES \
                or not all(isinstance(query, str) and words(query) and len(query) <= MAX_QUERY_CHARS for query in queries) \
                or None in (require, require_any, exclude) or not (require or require_any) \
                or spec.get("category", "consoles") not in CONSOLE_CATEGORIES \
                or not isinstance(sites, list) or not sites or not all(site in labels for site in sites):
            problems.append(f'console "{name}": its "search" or "sites" cannot be used')
            continue
        consoles.append({
            "title": name.strip(), "key": key_of(name), "kind": "console",
            "search": " ".join(words(queries[0])), "queries": [" ".join(query.lower().split()) for query in queries],
            "require": require, "require_any": require_any, "exclude": exclude,
            "category": CONSOLE_CATEGORIES[spec.get("category", "consoles")],
            "sites": [market_id for market_id in MARKETS if MARKETS[market_id]["label"] in sites],
            "siblings": [], "pinned": False, "level": "rare", "mentions": 0, "surging_until": None})
    return consoles, problems


def add_consoles(games, consoles):
    """Put the consoles among the things to price; one whose name a game has is left out."""
    keys = {game["key"] for game in games}
    added = [console for console in consoles if console["key"] not in keys and not keys.add(console["key"])]
    games.extend(added)
    games.sort(key=lambda game: game["title"].lower())
    return len(added)


def steady_index(rows):
    """{(key, site): [(time, copies, median), ...]} from history rows, for is_steady()."""
    index = {}
    for row in rows:
        if not (isinstance(row, list) and len(row) == 6 and isinstance(row[1], str) and isinstance(row[2], str)):
            continue
        when = parse_stamp(row[0])
        if when is not None:
            index.setdefault((key_of(row[1]), row[2]), []).append((when, row[3], row[5]))
    return index


def is_steady(rows, now):
    """True when a game on one site has priced the same for days: see STEADY_* above. `rows` are
    (time, copies, median) for that pair. Any missing number, or a single check outside the limits,
    makes it False, so a game is looked at again as soon as it moves."""
    recent = sorted(row for row in rows if now - timedelta(days=STEADY_LOOK_DAYS) <= row[0] <= now)
    if len(recent) < STEADY_MIN_ROWS or (recent[-1][0] - recent[0][0]) < timedelta(days=STEADY_SPAN_DAYS):
        return False
    copies, medians = [row[1] for row in recent], [row[2] for row in recent]
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in copies + medians):
        return False
    if min(copies) < STEADY_MIN_COPIES or min(medians) <= 0:
        return False
    middle_copies, middle_median = statistics.median(copies), statistics.median(medians)
    return ((max(copies) - min(copies)) / middle_copies <= STEADY_COPIES_RANGE
            and (max(medians) - min(medians)) / middle_median <= STEADY_PRICE_RANGE)


def due_lookups(games, state, now, history=()):
    """(game, market) pairs whose turn has come, most urgent first. A game the library also
    files under the name it has on a site ("Project Zero" beside "Fatal Frame") is looked up
    there once, for the game the feed knows by the other name; the second is skipped there."""
    previous = prior_games(state)
    steady_rows = steady_index(history)
    due = []
    renamed_to = {(market_id, words_there["search"]) for game in games
                  for market_id, words_there in (game.get("markets") or {}).items()}
    for game in games:
        every = CHECK_EVERY_HOURS[game["level"]] * 60
        if game["level"] == "rare" and game.get("kind") in RARE_SLOW_KINDS:
            every = CHECK_EVERY_HOURS["dormant"] * 60     # consoles and editions: once a day, as before
        game["steady_on"] = []          # the sites on which it waits 48 hours, so the dashboard knows
        for market_id, market in MARKETS.items():
            if game.get("sites"):                  # a game only on the Rarest page: its own list's site
                if market_id not in game["sites"]:
                    continue
            elif market_id not in (game.get("markets") or {}) and (market_id, game["search"]) in renamed_to:
                continue
            entry = (previous.get(game["key"]) or {}).get(market["label"])
            checked = parse_stamp(entry.get("checked")) if isinstance(entry, dict) else None
            waited = (now - checked).total_seconds() / 60 if checked else None
            wait = every
            if (game["level"] in ("normal", "staple") and not game["pinned"] and checked
                    and is_steady(steady_rows.get((game["key"], market["label"]), ()), now)):
                wait = STEADY_EVERY_HOURS * 60
                game["steady_on"].append(market["label"])
            if (market.get("extra") and game["level"] != "surging" and not game["pinned"] and checked
                    and game["level"] != "rare"
                    and isinstance(entry, dict) and (entry.get("unmatched") or entry.get("copies") == 0)):
                # Nothing was for sale (or the words find nothing) at the last check on a euro site: the answer rarely
                # changes, so it is asked every 48 hours (US and UK are never slowed this way); the dashboard gives it the steady figures' longer allowance.
                wait = max(wait, QUIET_EVERY_HOURS * 60)
                game["steady_on"].append(market["label"])
            wait = max(wait, market.get("min_every_hours", 0) * 60)
            mentioned = game.get("latest_mention")
            if (game.get("watch") and not market.get("extra") and mentioned is not None and checked is not None
                    and mentioned > checked):
                # A game of the Rarest or Underrated page was named after its last check: look again now (a
                # mention can be the start of a rush), whatever its clock. The euro sites keep their own.
                wait = min(wait, WATCH_RECHECK_MINUTES)
            if waited is None or waited >= wait - EARLY_MINUTES:
                overdue = float("inf") if waited is None else waited / max(every, 60)
                due.append((bool(market.get("extra")), game["level"] != "surging", not game["pinned"],
                            {"underrated": 1, "rare": 2}.get(game["level"], 0), -overdue, game["title"].lower(), market_id, game))
    due.sort(key=lambda row: row[:7])        # an extra site comes after the first two, whatever a game's level
    return [(row[7], row[6]) for row in due]


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


def search_url(market_id, query, by_aspect=True, condition="ids", console=None, relax=()):
    """The search request for one game on one site, encoded the way eBay's examples are. For a
    console (`console` is its category, or "" for every category): any condition but for parts,
    from sellers anywhere (most rare consoles are sold from Japan), and the words as given."""
    market = MARKETS[market_id]
    if console is not None:
        params = {"q": query, "filter": f"conditionIds:{{{CONSOLE_CONDITION_IDS}}},buyingOptions:{{FIXED_PRICE}}",
                  "limit": str(PAGE_LIMIT)}
        if console:
            params["category_ids"] = console
        return SEARCH_URL + "?" + urlencode(params, quote_via=quote)
    # `relax` is for the search check only: "format" also asks for auctions, "anywhere" for listings in
    # any country, "category" for every category. Lookups never use it.
    filters = [CONDITION_FILTERS[condition], "" if "format" in relax else "buyingOptions:{FIXED_PRICE}",
               "" if "anywhere" in relax else f"itemLocationCountry:{market['country']}"]
    params = {
        "q": query if by_aspect else f"{query} ps2",
        "filter": ",".join(part for part in filters if part),
        "limit": str(PAGE_LIMIT),
    }
    if "category" not in relax:
        params["category_ids"] = CATEGORY_ID
    if SORT_BY_PRICE["on"] and "sort" not in relax:
        params["sort"] = "price"
    if not params["filter"]:
        del params["filter"]
    if by_aspect:
        params["aspect_filter"] = f"categoryId:{CATEGORY_ID},Platform:{{{PLATFORM_ASPECT}}}"
    return SEARCH_URL + "?" + urlencode(params, quote_via=quote)   # spaces as %20, never "+"


def buyer_location(market):
    """Where eBay should quote postage to: the site's own country, plus a postcode if one is set."""
    return f"country={market['country']}" + (f",zip={market['zip']}" if market.get("zip") else "")


def search(http_client, token, market_id, query, counter, by_aspect=True, condition="ids", console=None, relax=()):
    """One search, tried up to three times. Returns (HTTP status or 0 for no answer, JSON)."""
    market = MARKETS[market_id]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": market_id,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + quote(buyer_location(market), safe=""),
    }
    url = search_url(market_id, query, by_aspect, condition, console, relax)
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
        if status == 200 and "sort=price" in url:
            SORT_BY_PRICE["worked"] = True
        if status == 400 and "sort=price" in url and not SORT_BY_PRICE["worked"]:
            # Not one sorted search has been answered yet, so eBay may not take the sort: ask again without
            # it, and without it for the rest of the run. (After one has worked, a 400 is something else.)
            SORT_BY_PRICE["on"] = False
            say("eBay refused sort=price (HTTP 400): asking without it from now on.")
            url = search_url(market_id, query, by_aspect, condition, console, relax)
            continue
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


def comes_with(title, phrase):
    """True when the title says the copy comes with the thing: "w/ Plush", "+ Art Book",
    "with the art book", "includes artbook"."""
    pattern = r"\s+".join(re.escape(word) for word in phrase.split())
    return re.search(rf"(?:\bwith|\bw/|\+|&|\band|\bplus|\bincl\w*)\s*(?:[\w'’-]+\s+){{0,3}}{pattern}\b",
                     str(title or "").lower()) is not None


def console_reject_reason(item, console, market):
    """Why a listing is left out of a console's figures, or None to count it. The title must
    have every "require" phrase and one of "require_any" (the model, the colour's name)."""
    text = " ".join(words(item.get("title")))
    if not all(has_phrase(text, [phrase]) for phrase in console["require"]) \
            or (console["require_any"] and not has_phrase(text, console["require_any"])):
        return "other_game"
    if has_phrase(text, OTHER_CONSOLES):
        return "other_platform"
    if has_phrase(text, CONSOLE_JUNK) or has_phrase(text, console["exclude"]):
        return "not_a_copy"
    parts = [part for part in CONSOLE_PARTS if has_phrase(text, [part])]
    if parts and not has_phrase(text, CONSOLE_WORDS) and not all(comes_with(item.get("title"), part) for part in parts):
        return "not_a_copy"
    if amount(item.get("price"), market["currency"]) is None:
        return "no_price"
    if listing_url(item, market) is None:
        return "no_link"
    return None


def reject_reason(item, game, market, keyword_search, sealed_ok=False):
    """Why a listing is left out, or None to count it."""
    if game.get("kind") == "console":
        return console_reject_reason(item, game, market)
    text = " ".join(words(item.get("title")))             # for junk words, as the seller wrote them
    name_text = " ".join(name_words(item.get("title")))   # for the game's name, spellings evened out
    if keyword_search and not PLATFORM_WORDS.search(text):
        return "other_game"
    # Both sides lose any "the", so a listing that adds or drops one is still the game.
    bare, search = the_less(name_text), the_less(game["search"])
    if not names_this_game(bare, search) or names_another_entry(bare, search) \
            or has_phrase(bare, [the_less(sibling) for sibling in game.get("siblings") or ()]) \
            or not all(has_phrase(bare, [the_less(words_needed)]) for words_needed in game.get("require") or ()):
        return "other_game"
    if has_phrase(text, OTHER_PLATFORMS):
        return "other_platform"
    # An edition's extras count only as part of the copy ("Limited Edition with Art Book"), never
    # sold on their own ("Limited Edition Art Book").
    junk = [phrase for phrase in JUNK_PHRASES
            if phrase not in (game.get("allow") or ()) or not comes_with(item.get("title"), phrase)]
    if has_phrase(text, junk) or has_phrase(text, market.get("junk", ())) or has_phrase(text, game["exclude"]) \
            or is_the_soundtrack(item.get("title"), name_text, game["search"]):
        return "not_a_copy"
    if not sealed_ok and has_phrase(text, GRADED_OR_SEALED) and not has_phrase(text, NOT_GRADED):
        return "graded_or_sealed"
    if has_phrase(text, IMPORT_PHRASES) or has_phrase(text, market["foreign"]):
        return "import"
    if has_phrase(text, INCOMPLETE_PHRASES + tuple(market.get("incomplete", ()))):
        return "incomplete"
    if amount(item.get("price"), market["currency"]) is None:
        return "no_price"
    if listing_url(item, market) is None:
        return "no_link"
    return None


def summarise(payload, game, market, keyword_search, sealed_ok=False):
    """Turn one search result into the numbers and links for this run's file."""
    items = [item for item in payload.get("itemSummaries") or [] if isinstance(item, dict)]
    skipped, examples, kept = {}, {}, []
    for item in items:
        reason = reject_reason(item, game, market, keyword_search, sealed_ok)
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
            "confirmed": has_phrase(" ".join(words(item.get("title"))), COMPLETE_PHRASES),
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
            # The copies whose titles say they are complete (CIB, with manual...): the figure to set beside
            # a collector's value for a complete copy. The others are not wrong, they just do not say.
            "confirmed_counted": sum(1 for row in kept if row["confirmed"]),
            "confirmed_median": middle([row["price"] for row in kept if row["confirmed"]])
                                if any(row["confirmed"] for row in kept) else None,
            "listings": [{k: v for k, v in row.items() if k != "confirmed"} for row in kept[:LISTINGS_KEPT]],
        })
    return result


def human_search_url(game, market):
    """The same search on eBay's own site, so every number links back to its source."""
    if game.get("kind") == "console":
        return (f"https://{market['site']}/sch/i.html?_nkw={quote(game['queries'][0])}"
                f"&_sacat={game['category'] or 0}&LH_BIN=1")
    return (f"https://{market['site']}/sch/i.html?_nkw={quote(game['queries'][-1] + ' ps2')}"
            f"&_sacat={CATEGORY_ID}&LH_ItemCondition={quote(USED_CONDITION_IDS)}&LH_BIN=1&LH_PrefLoc=1")


def fetch(http_client, token, game, market_id, counter, by_aspect, console=None, condition="ids"):
    """Run the game's searches on one site and merge them, each listing once.
    Returns (status, payload): the first failure as it came, or 200 and the merged listings."""
    merged, total, truncated, warning = {}, 0, False, ""
    for position, query in enumerate(game["queries"]):
        if position:
            time.sleep(REQUEST_PAUSE)
        status, payload = search(http_client, token, market_id, query, counter, by_aspect=by_aspect, condition=condition,
                                 console=console)
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
    """Look one game up on one eBay site, under the name it goes by there."""
    market = MARKETS[market_id]
    game = for_market(game, market_id)
    base = {"search_url": human_search_url(game, market), "currency": market["currency"]}
    if game.get("kind") == "console":
        status, payload = fetch(http_client, token, game, market_id, counter, by_aspect=False, console=game["category"])
        if status != 200:
            return {**base, "status": "error", "answered": status != 0, "error": error_text(status, payload)}
        return {**base, **summarise(payload, game, market, False)}

    keyword_search = bool(market.get("keyword_only"))
    status, payload = fetch(http_client, token, game, market_id, counter, by_aspect=not keyword_search)
    if status == 200 and not payload["itemSummaries"] and not keyword_search:
        # Nothing carries the PS2 item specific: ask again by keyword instead.
        time.sleep(REQUEST_PAUSE)
        status, payload = fetch(http_client, token, game, market_id, counter, by_aspect=False)
        keyword_search = True

    if status != 200:
        return {**base, "status": "error", "answered": status != 0, "error": error_text(status, payload)}
    result = {**base, **summarise(payload, game, market, keyword_search)}
    if game.get("new_tier") and market_id in game["new_tier"]:
        result["new"] = check_new_copies(http_client, token, game, market_id, counter, keyword_search)
    return result


def check_new_copies(http_client, token, game, market_id, counter, keyword_search):
    """The Rarest page's second look at a game: its new and sealed copies (condition new), which the main
    search leaves out because they sell at many times a used copy. Counted apart, never mixed into the
    used figures. {"counted", "lowest", "median", "listings"}, or {"counted": 0} when there are none or eBay
    could not be asked (the used figures stand either way)."""
    market = MARKETS[market_id]
    time.sleep(REQUEST_PAUSE)
    status, payload = fetch(http_client, token, game, market_id, counter, not keyword_search, condition="new")
    if status != 200:
        return {"counted": 0}
    summary = summarise(payload, game, market, keyword_search, sealed_ok=True)
    if not summary.get("counted"):
        return {"counted": 0}
    return {"counted": summary["counted"], "lowest": summary["lowest"], "median": summary["median"],
            "listings": summary["listings"]}


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
    if isinstance(result.get("new"), dict):
        tail += f"; {result['new']['counted']} new or sealed"
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
                status, payload = search(http_client, token, market_id, for_market(game, market_id)["queries"][0], counter,
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


def describe_conditions(payload, game, market):
    """For the search check: the condition ids of the listings returned and how many of them the Rarest page's new-copy
    count would take (they must name the game; sealed ones are welcome). Counts and eBay's own ids only."""
    items = payload.get("itemSummaries") if isinstance(payload.get("itemSummaries"), list) else []
    ids = {}
    for item in items:
        key = str(item.get("conditionId", "none")) if isinstance(item, dict) else "none"
        ids[key] = ids.get(key, 0) + 1
    counted = summarise(payload, game, market, False, sealed_ok=True).get("counted", 0)
    return f"{len(items)} returned, condition ids {', '.join(f'{k} x{v}' for k, v in sorted(ids.items())) or 'none'}; {counted} name the game"


GAME_CHECK_VARIANTS = (
    # (what is asked, platform by item specific, condition, what is relaxed)
    ("the search this script uses", True, "ids", ()),
    ("the same, not sorted by price", True, "ids", ("sort",)),
    ("platform by keyword", False, "ids", ()),
    ("new condition only (the Rarest page's second look)", True, "new", ()),
    ("any condition (new and sealed included)", True, "any", ()),
    ("listed in any country", True, "ids", ("anywhere",)),
    ("auctions as well as Buy It Now", True, "ids", ("format",)),
    ("any category", False, "ids", ("category",)),
    ("everything relaxed at once", False, "any", ("anywhere", "format", "category")),
)


def describe_order(payload, market):
    """Is a result cheapest first, and which fields does a listing carry? Field names and a yes or no only:
    no price, title or seller is printed."""
    items = [item for item in payload.get("itemSummaries") or [] if isinstance(item, dict)]
    prices = [amount(item.get("price"), market["currency"]) for item in items]
    prices = [price for price in prices if price is not None]
    ascending = all(a <= b for a, b in zip(prices, prices[1:]))
    fields = sorted({key for item in items[:5] for key in item})
    return (f"{len(prices)} priced listings returned, cheapest first: {'yes' if ascending else 'NO'}; "
            f"fields: {', '.join(fields) or 'none'}")


def check_game(http_client, token, game, secrets, markets=("EBAY_GB", "EBAY_US")):
    """How many listings eBay reports for one game when one part of the search is relaxed, for finding out why a
    game shows no copies where a person can see some. Counts only (no price, title or seller), as lines for a notice."""
    counter, lines = {"searches": 0}, []
    for market_id in markets:
        market = MARKETS[market_id]
        for label, by_aspect, condition, relax in GAME_CHECK_VARIANTS:
            try:
                status, payload = search(http_client, token, market_id, for_market(game, market_id)["queries"][0], counter,
                                         by_aspect=by_aspect, condition=condition, relax=relax)
            except LimitReached as exc:
                lines.append(redact(f"[{market['label']}] {label}: {exc}", secrets))
                return lines
            total = payload.get("total")
            answer = f"{total}" if status == 200 and isinstance(total, int) else error_text(status, payload)
            lines.append(redact(f"[{market['label']}] {label}: {answer}", secrets))
            if status == 200 and not relax and condition == "ids" and by_aspect:
                lines.append(redact(f"[{market['label']}]   {describe_order(payload, market)}", secrets))
            if status == 200 and condition in ("new", "any") and not relax and by_aspect:
                lines.append(redact(f"[{market['label']}]   of those: {describe_conditions(payload, for_market(game, market_id), market)}", secrets))
            time.sleep(REQUEST_PAUSE)
    return lines


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
    if not results:
        return None
    # A site added later (extra) that fails must not throw away the first two sites' good answers:
    # the run is judged on the first two sites alone whenever it has lookups on them.
    judged = [row for row in results if not MARKETS[row[1]].get("extra")] or results
    errors = sum(1 for _, _, result in judged if result["status"] == "error")
    if errors == len(judged):
        return "every lookup failed, so nothing was written."
    if errors * 2 > len(judged):
        return (f"{errors} of {len(judged)} lookups failed, so nothing was written and the "
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
             "postage": result.get("median_postage"),
             # eBay's own count for the same search, before the name checks: the dashboard calls a
             # game "scarce" only when the two agree (copies is never more than this).
             "listed": result["on_ebay"]}
    if result["truncated"]:
        entry["truncated"] = True
    new = result.get("new")
    if isinstance(new, dict) and new.get("counted"):
        entry["new"] = {"copies": new["counted"], "lowest": new["lowest"], "median": new["median"]}
    # Only when at least CONFIRMED_MIN copies say they are complete, and not all of them do anyway.
    if result.get("confirmed_median") is not None and CONFIRMED_MIN <= result.get("confirmed_counted", 0) < result["counted"]:
        entry["complete"] = {"copies": result["confirmed_counted"], "median": result["confirmed_median"]}
    return entry


def update_records(state, games, run, now, rare_titles=None, edition_titles=None):
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
        if game.get("sites"):
            entry["sites"] = [MARKETS[market_id]["label"] for market_id in MARKETS if market_id in game["sites"]]
        if game.get("kind") in ("console", "edition"):
            entry["kind"] = game["kind"]
        old_entry = previous.get(game["key"]) or {}
        for market in MARKETS.values():
            label = market["label"]
            old = old_entry.get(label) if isinstance(old_entry.get(label), dict) else None
            new = checked.get((game["key"], label))
            if new is None:
                if old:
                    # Not checked this run (or it failed): keep what we had, with its "steady" mark brought up to date. A figure
                    # written before a game turned steady has no mark, and until it is looked up again (48 hours) the dashboard
                    # would call it overdue after 8 hours.
                    if label in game.get("steady_on", ()) and "copies" in old and old.get("steady") is not True:
                        old = {**old, "steady": True}
                    elif old.get("steady") and label not in game.get("steady_on", ()):
                        old = {key: value for key, value in old.items() if key != "steady"}
                    entry[label] = old
                continue
            if "copies" in new:                 # a real answer; "unmatched" has no figures to record
                figures = (new["copies"], new["lowest"], new["median"])
                unchanged = old and figures == (old.get("copies"), old.get("lowest"), old.get("median"))
                if not (unchanged and old.get("recorded") == today):
                    rows.append([stamp, game["title"], label, *figures])   # changed, or the day's first check
                new["recorded"] = today                                     # the day of its latest history row
                if label in game.get("steady_on", ()):
                    new["steady"] = True        # checked every 48 hours, so the dashboard must not call it overdue
            entry[label] = new
        latest_games[game["title"]] = entry

    used = state.get("searches") if isinstance(state.get("searches"), dict) else {}
    used_today = used.get("used", 0) if used.get("day") == today else 0
    latest = {
        "what": ("Asking prices of used Buy It Now copies of PS2 games on eBay, by site (the Rarest games also count new and sealed copies apart, as `new`). Numbers only: "
                 "copies listed, lowest and median price before postage, typical postage. Not sold prices."),
        "currencies": {market["label"]: market["currency"] for market in MARKETS.values()},
        "searches": {"day": today, "used": used_today + run["searches"]},
        "games": latest_games,
    }
    if rare_titles:
        # Which game in "games" holds the figures of each game on the Rarest page's lists.
        latest["rare"] = {list_name: dict(titles) for list_name, titles in rare_titles.items()}
    if edition_titles and any(edition_titles.values()):
        # Which game in "games" holds the figures of each edition in editions.json.
        latest["editions"] = {list_name: dict(titles) for list_name, titles in edition_titles.items()}
    return latest, rows


def history_index(rows):
    """{(key, site): [(time, median), ...]} from history rows, skipping any row that is not
    in the shape this script writes. Keyed by key_of(title), so that a game whose title is
    spelt another way from one run to the next ("Ico", "ICO") keeps its history."""
    index = {}
    for row in rows:
        if not (isinstance(row, list) and len(row) == 6 and isinstance(row[1], str) and isinstance(row[2], str)):
            continue
        when = parse_stamp(row[0])
        if when is not None:
            index.setdefault((key_of(row[1]), row[2]), []).append((when, row[5]))
    return index


def week_before(index, title, label, checked):
    """The median recorded CHANGE_DAYS before a check, for the change shown beside it: the
    latest history row of that game and site from between CHANGE_DAYS and CHANGE_DAYS +
    CHANGE_SLACK_DAYS before. When there is none yet (the game has less than a week of history), the
    oldest row that is at least CHANGE_MIN_DAYS old, which the dashboard calls "3 days before" and so on.
    None when there is no such row, or when it found no copies."""
    then = parse_stamp(checked)
    if then is None:
        return None
    newest, oldest = then - timedelta(days=CHANGE_DAYS), then - timedelta(days=CHANGE_DAYS + CHANGE_SLACK_DAYS)
    known = list(index.get((key_of(title), label), ()))
    rows = [(when, median) for when, median in known if oldest <= when <= newest]
    if rows:
        when, median = max(rows, key=lambda row: row[0])
    else:
        young = [(when, median) for when, median in known
                 if newest < when <= then - timedelta(days=CHANGE_MIN_DAYS)]
        if not young:
            return None
        when, median = min(young, key=lambda row: row[0])
    if isinstance(median, bool) or not isinstance(median, (int, float)) or not math.isfinite(median) or median <= 0:
        return None
    return {"checked": when.strftime(STAMP_FORMAT), "median": median}


def add_week_before(latest, history):
    """Give every median in latest.json the median of a week before it, where there is one."""
    index = history_index(history)
    for title, entry in latest["games"].items():
        for market in MARKETS.values():
            site = entry.get(market["label"])
            if not isinstance(site, dict):
                continue
            site = {key: value for key, value in site.items() if key != "week"}
            before = week_before(index, title, market["label"], site.get("checked")) if site.get("median") else None
            if before:
                site["week"] = before
            entry[market["label"]] = site
    return latest


# ---- The PS2 price index ------------------------------------------------------------
# One number per site and day that says how asking prices moved, like a stock market index:
# 100 on its first day. Each day it moves by the geometric mean of how each game's median moved
# since that game's previous day (a chained Jevons index, the kind statistics offices use when
# no quantities are known). Only games priced on both days count, so a game joining or leaving
# never moves it. A median from fewer than INDEX_MIN_COPIES copies is too thin to count, and a
# move beyond INDEX_MAX_MOVE either way is taken for a change of search words, not the market.
INDEX_MIN_COPIES = 3
INDEX_MAX_GAP_DAYS = 3        # a game's previous day may be this many days back (a quiet game, a late run)
INDEX_MAX_MOVE = 2.0          # a median that doubled or halved is left out of that day
INDEX_MIN_GAMES = 10          # a day with fewer games compared keeps the day before's value


STAMP_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")


def daily_medians(rows, leave_out=(), before_day=None, min_copies=INDEX_MIN_COPIES, only=None):
    """{(site, day): {game key: median}} from history rows: each game's last good median of the
    day. Only days before `before_day`: a day still under way is not finished. `only`, when
    given, is the set of game keys to keep."""
    days, keys = {}, {}
    rows = [row for row in rows if isinstance(row, list) and len(row) == 6
            and isinstance(row[0], str) and STAMP_SHAPE.match(row[0])]
    for row in sorted(rows, key=lambda row: row[0]):   # the stamps sort as text
        when, title, site, copies, _, median = row
        day = when[:10]
        if (before_day and day >= before_day) or not isinstance(title, str) or not isinstance(site, str):
            continue
        key = keys.get(title)
        if key is None:
            key = keys[title] = key_of(title)
        if key in leave_out or (only is not None and key not in only):
            continue
        if isinstance(copies, bool) or not isinstance(copies, int) or copies < min_copies:
            continue
        if isinstance(median, bool) or not isinstance(median, (int, float)) or not math.isfinite(median) or median <= 0:
            continue
        days.setdefault((site, day), {})[key] = float(median)
    return days


PAL_INDEX = "PAL"


def pal_sites():
    """The labels of the sites that sell PAL copies: every site but the US."""
    return [market["label"] for market in MARKETS.values() if market["country"] != "US"]


def add_pal_days(days):
    """Add the PAL index's days: every game on every PAL site is one item, so a game on three sites
    counts three times, and a game or site joining on a later day never moves it (only items priced
    on both days count, as in each site's own index). Nothing is added with fewer than two sites."""
    sites = pal_sites()
    present = {site for site, _ in days if site in sites}
    if len(present) < 2:
        return days
    for (site, day), medians in list(days.items()):
        if site in present:
            days.setdefault((PAL_INDEX, day), {}).update({f"{key}@{site}": median for key, median in medians.items()})
    return days


def price_index(rows, leave_out=(), before_day=None):
    """{site: [[day, index, games compared], ...]} from history rows, oldest day first. When two or
    more PAL sites have figures, "PAL" is the index of all their games together."""
    days = add_pal_days(daily_medians(rows, leave_out, before_day))
    index = {}
    for site in sorted({site for site, _ in days}):
        dates = sorted(day for each_site, day in days if each_site == site)
        points, value, last_seen = [], 100.0, {}
        for day in dates:
            today = days[(site, day)]
            when = datetime.strptime(day, "%Y-%m-%d")
            logs = []
            for key, median in today.items():
                seen = last_seen.get(key)
                if seen and (when - seen[0]).days <= INDEX_MAX_GAP_DAYS:
                    move = median / seen[1]
                    if 1 / INDEX_MAX_MOVE <= move <= INDEX_MAX_MOVE:
                        logs.append(math.log(move))
            if points and len(logs) >= INDEX_MIN_GAMES:
                value *= math.exp(sum(logs) / len(logs))
            if points or len(today) >= INDEX_MIN_GAMES:   # the index starts on the first day with enough games
                points.append([day, round(value, 2), len(logs) if points else len(today)])
            for key, median in today.items():
                last_seen[key] = (when, median)
        if points:
            index[site] = points
    return index


# ---- The Rarest page's index and market cap -----------------------------------------------
# Each list (PAL on eBay UK, US on eBay US) gets an index of its own games, chained like the PS2
# index, and a market cap: every game's latest median (on that site, within CAP_CARRY_DAYS) times
# the copies rare_games.json estimates exist ("copies" there says how the estimate was made).
# Rare games often have one or two copies for sale, so the index takes medians from two copies.
RARE_INDEX_MIN_COPIES = 2
RARE_INDEX_MIN_GAMES = 10
CAP_CARRY_DAYS = 7
CAP_SURVIVAL = 0.65            # used when rare_games.json gives no share of copies still in existence
CAP_CORE_BELOW = 100000        # "core" leaves out games estimated at this many copies or more
CAP_START_SHARE = 0.8          # both lines start on the first day this share of the list has a price


def rare_members(latest, rare_file):
    """{list: {game key: estimated copies sold}}: each list's games as the price job holds them
    (latest.json's "rare"), with the "mid" estimate of their entry. An entry without one is left out."""
    members = {}
    placed = latest.get("rare") if isinstance(latest.get("rare"), dict) else {}
    lists = rare_file.get("lists") if isinstance(rare_file, dict) and isinstance(rare_file.get("lists"), dict) else {}
    for list_name in RARE_SITES:
        found = {}
        names = placed.get(list_name) if isinstance(placed.get(list_name), dict) else {}
        for entry in lists.get(list_name) or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("title"), str):
                continue
            game = names.get(entry["title"])
            copies = (entry.get("copies") or {}).get("mid") if isinstance(entry.get("copies"), dict) else None
            if not isinstance(game, str) or isinstance(copies, bool) or not isinstance(copies, (int, float)) \
                    or not math.isfinite(copies) or copies <= 0:
                continue
            key = key_of(game)
            found[key] = max(found.get(key, 0), copies)   # two entries for one game count once
        members[list_name] = found
    return members


def rare_index(rows, latest, rare_file, before_day):
    """{list: {"site", "currency", "games", "points": [[day, index or None, games compared, cap,
    core cap, games in the cap], ...]}} for the Rarest page, finished days only."""
    model = rare_file.get("copies") if isinstance(rare_file, dict) and isinstance(rare_file.get("copies"), dict) else {}
    shares = model.get("survival", {}).get("in_existence") if isinstance(model.get("survival"), dict) else None
    middle = shares[1] if isinstance(shares, list) and len(shares) >= 2 else None
    survival = middle if isinstance(middle, (int, float)) and not isinstance(middle, bool) and 0 < middle <= 1 else CAP_SURVIVAL
    core_below = model.get("core_below") if isinstance(model.get("core_below"), int) and model["core_below"] > 0 else CAP_CORE_BELOW
    out = {}
    for list_name, members in rare_members(latest, rare_file).items():
        market = MARKETS[RARE_SITES[list_name]]
        site = market["label"]
        keys = set(members)
        moves = {day: games for (where, day), games in daily_medians(
            rows, before_day=before_day, min_copies=RARE_INDEX_MIN_COPIES, only=keys).items() if where == site}
        prices = {day: games for (where, day), games in daily_medians(
            rows, before_day=before_day, min_copies=1, only=keys).items() if where == site}
        points, value, last_seen, held, live_before = [], None, {}, {}, {}
        for day in sorted(set(moves) | set(prices)):
            when = datetime.strptime(day, "%Y-%m-%d")
            today = moves.get(day, {})
            logs = []
            for key, median in today.items():
                seen = last_seen.get(key)
                if seen and (when - seen[0]).days <= INDEX_MAX_GAP_DAYS and 1 / INDEX_MAX_MOVE <= median / seen[1] <= INDEX_MAX_MOVE:
                    logs.append(math.log(median / seen[1]))
            if value is None:
                compared = len(today)
                if compared >= RARE_INDEX_MIN_GAMES:
                    value = 100.0      # the index starts on the first day with enough games
            else:
                compared = len(logs)
                if compared >= RARE_INDEX_MIN_GAMES:
                    value *= math.exp(sum(logs) / compared)
            for key, median in today.items():
                last_seen[key] = (when, median)
            for key, median in prices.get(day, {}).items():
                held[key] = (when, median)
            live = {key: median for key, (seen, median) in held.items() if (when - seen).days <= CAP_CARRY_DAYS}
            # [this day's sum, the move of the games priced the day before too] for all, then core
            caps = []
            for keep in (lambda key: True, lambda key: members[key] < core_below):
                total = sum(median * members[key] * survival for key, median in live.items() if keep(key))
                both = [key for key in live if keep(key) and key in live_before
                        and 1 / INDEX_MAX_MOVE <= live[key] / live_before[key] <= INDEX_MAX_MOVE]
                then = sum(live_before[key] * members[key] for key in both)
                caps.append((total, sum(live[key] * members[key] for key in both) / then if then else 1.0))
            live_before = live
            points.append([day, round(value, 2) if value is not None else None, compared, caps[0], caps[1], len(live)])
        # Before half the list had a price (the days before the list was priced on its own), the
        # cap would climb only because games joined: both lines start on the first day after.
        start = next((i for i, point in enumerate(points) if point[5] >= CAP_START_SHARE * len(members) and point[1] is not None),
                     len(points))
        points = points[start:]
        if points:
            base = points[0][1]
            # The cap starts at the first day's sum and then moves like a stock index: by how
            # the games priced on both days moved, so a game joining or leaving never moves it.
            cap, core = points[0][3][0], points[0][4][0]
            for i, point in enumerate(points):
                if i:
                    cap *= point[3][1]
                    core *= point[4][1]
                point[1] = round(point[1] / base * 100, 2)
                point[3], point[4] = round(cap), round(core)
        out[list_name] = {"site": site, "currency": market["currency"], "games": len(members), "points": points}
    return {
        "what": ("The Rarest page's two lists, each on its own eBay site: an index of their asking prices "
                 f"(100 on the first day {CAP_START_SHARE:.0%} of the list had a price, moving on days with {RARE_INDEX_MIN_GAMES}+ games "
                 f"priced from {RARE_INDEX_MIN_COPIES}+ copies on both days, chained like the PS2 index) and a market cap: each game's latest median within "
                 f"{CAP_CARRY_DAYS} days x the copies rare_games.json estimates were sold x {survival:g} still in existence, "
                 "summed on the first day, then moved like a stock index by the games priced on both days (a game "
                 f"joining or leaving does not move it). 'core' leaves out games estimated at {core_below:,} copies or more. "
                 "The copies are estimates, so the cap is a rough size, not a count."),
        "points": "[day, index, games compared, market cap, core market cap, games in the cap]",
        "survival": survival,
        "core_below": core_below,
        "lists": out,
    }


def index_file(rows, latest, now, left_out=()):
    """index.json: the price index of each site, for the dashboard, up to yesterday (UTC): a day
    still under way would move it on whichever games happened to be checked first. Consoles are
    left out: those in latest.json and rare_consoles.json, and every one left out before
    (`left_out`, kept in the file), so that a console renamed or dropped from the list never
    enters it with its whole history."""
    consoles = {key_of(title) for title, entry in latest.get("games", {}).items()
                if isinstance(entry, dict) and entry.get("kind") in ("console", "edition")}
    listed = read_json(CONSOLES_PATH, {}).get("consoles")
    consoles |= {key_of(row["name"]) for row in listed or [] if isinstance(row, dict) and isinstance(row.get("name"), str)}
    consoles |= {key for key in left_out if isinstance(key, str)}
    consoles.discard("")
    return {
        "what": ("The PS2 price index: how eBay asking prices of used PS2 games moved, per site (and \"PAL\", every PAL site "
                 "together), 100 on the "
                 "first day. Each day moves by the geometric mean of each game's change in median since its "
                 "previous day, for games priced on both days from at least "
                 f"{INDEX_MIN_COPIES} copies; a median that doubled or halved is left out. Consoles and editions are not in it."),
        "currencies": latest.get("currencies", {}),
        "points": ("[day, index, games compared with their previous day]; the first day counts the games priced. "
                   "Finished UTC days only."),
        "min_games": INDEX_MIN_GAMES,
        "sites": price_index(rows, consoles, now.strftime("%Y-%m-%d")),
        "left_out": sorted(consoles),
        "rare": rare_lists(rows, latest, now),
    }


def rare_lists(rows, latest, now):
    """rare_index(), or nothing when rare_games.json is not as expected: never the PS2 index's loss."""
    try:
        return rare_index(rows, latest, read_json(RARE_PATH, {}), now.strftime("%Y-%m-%d"))
    except (TypeError, ValueError, KeyError, AttributeError, ZeroDivisionError) as error:
        say(f"The Rarest lists' index was left out: rare_games.json is not as expected ({type(error).__name__}).")
        return {}


def series_file(rows, now, days=SERIES_DAYS):
    """series.json: each game's last median of every day it was priced, per site, over the last
    `days` finished days, for the price chart that opens from a game on the dashboard."""
    today = now.strftime("%Y-%m-%d")
    first = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    last = {}
    for row in sorted((row for row in rows if isinstance(row, list) and len(row) == 6
                       and isinstance(row[0], str) and STAMP_SHAPE.match(row[0])), key=lambda row: row[0]):
        when, title, site, copies, _, median = row
        day = when[:10]
        if not max(first, SERIES_EPOCH) <= day < today or not isinstance(title, str) or not isinstance(site, str):
            continue
        if isinstance(copies, bool) or not isinstance(copies, int) or copies < 1:
            continue
        if isinstance(median, bool) or not isinstance(median, (int, float)) or not math.isfinite(median) or median <= 0:
            continue
        last[(title, site, day)] = (median, copies)
    start = SERIES_EPOCH
    zero = datetime.strptime(start, "%Y-%m-%d")
    games = {}
    for (title, site, day), (median, copies) in sorted(last.items()):
        games.setdefault(title, {}).setdefault(site, []).append(
            [(datetime.strptime(day, "%Y-%m-%d") - zero).days, median, copies])
    return {
        "what": ("Each game's eBay median asking price per day (the last check of the day), per site, over the "
                 f"last {days} finished UTC days. Days with no copies for sale are left out."),
        "start": start,
        "points": "[days after start (which never changes), median, copies]",
        "games": games,
    }


def write_series(path, series):
    """One game per line: small diffs."""
    lines = ",\n  ".join(f"{json.dumps(title, ensure_ascii=False)}: {json.dumps(sites, ensure_ascii=False, separators=(',', ':'))}"
                         for title, sites in series["games"].items())
    head = {key: value for key, value in series.items() if key != "games"}
    text = json.dumps(head, indent=1, ensure_ascii=False)[:-2] + (f',\n "games": {{\n  {lines}\n }}\n}}\n' if lines else ',\n "games": {}\n}\n')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


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
        there = for_market(game, market_id)
        row["markets"][market_id] = ({**result, "search_there": there["search"], "queries_there": there["queries"],
                                      "left_out_if_named_there": there["siblings"][:20]}
                                     if market_id in (game.get("markets") or {}) else result)
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


def describe_plan(games, left_out, lookups, allowance, rare_titles=None, rare_problems=(), consoles=0, edition_titles=None):
    games = [game for game in games if game.get("kind") not in ("console", "edition")]   # counted on lines of their own
    levels = {level: sum(1 for game in games if game["level"] == level) for level in CHECK_EVERY_HOURS}
    for extra_level in ("underrated", "rare"):
        if not levels[extra_level]:
            del levels[extra_level]   # only there when underrated.json or rare_games.json adds games
    pinned = sum(1 for game in games if game["pinned"])
    say(f"Tracking {len(games)} games ({pinned} pinned): " + ", ".join(
        f"{count} {level}" for level, count in levels.items()) + ".")
    for game in games:
        if game["level"] == "surging":
            say(f"  surging: {game['title']}")
    reasons = (("one_word", "one-word name that is also an ordinary word (pin it to track it)"),
               ("not_in_library", "not in the PS2 library"),
               ("never", 'on the "never" list'),
               ("underrated", "on the Underrated page but not priced (not in the PS2 library, or a one-word name that is an ordinary word)"))
    for reason, text in reasons:
        titles = left_out.get(reason) or []
        if titles:
            shown = ", ".join(titles[:12]) + (f" and {len(titles) - 12} more" if len(titles) > 12 else "")
            say(f"Left out, {text}: {len(titles)} ({shown}).")
    for market_id, market in MARKETS.items():
        renamed_here = [f"{game['title']} as {game['markets'][market_id]['search']}" for game in games
                        if market_id in (game.get("markets") or {})]
        if renamed_here:
            shown = "; ".join(renamed_here[:12]) + (f" and {len(renamed_here) - 12} more" if len(renamed_here) > 12 else "")
            say(f"Searched on eBay {market['label']} under the name it has there: {len(renamed_here)} ({shown}).")
    if rare_titles is not None:
        on_lists = sum(len(titles) for titles in rare_titles.values())
        say(f"Rarest page: {on_lists} entries, " + ", ".join(f"{len(titles)} {name}" for name, titles in rare_titles.items())
            + f"; {sum(1 for game in games if game['level'] == 'rare' and game.get('kind') != 'console')} of the games are priced for it alone.")
    if consoles:
        say(f"Rarest page: {consoles} consoles priced.")
    if edition_titles:
        say(f"Editions: {sum(len(titles) for titles in edition_titles.values())} entries, "
            + ", ".join(f"{len(titles)} {name}" for name, titles in edition_titles.items()) + ", each priced on its own.")
    for problem in rare_problems:
        say(f"Rarest page, left out: {problem}.")
    say(f"Due now: {len(lookups)} lookups. This run may use {max(allowance, 0)} searches.")


# ======================================================================================
# The count-only check of other eBay sites (a started-by-hand diagnosis; it writes nothing)
# ======================================================================================

# Sites being considered, with Britain as the known-good control. None of them is priced by the
# normal run: this only asks each site how many listings it reports for some games.
PROBE_MARKETS = {
    "EBAY_GB": {"label": "UK", "country": "GB"},
    "EBAY_DE": {"label": "DE", "country": "DE"},
    "EBAY_FR": {"label": "FR", "country": "FR"},
    "EBAY_IT": {"label": "IT", "country": "IT"},
    "EBAY_ES": {"label": "ES", "country": "ES"},
    "EBAY_PL": {"label": "PL", "country": "PL"},
}
PROBE_FAMOUS = (
    "Grand Theft Auto San Andreas", "Grand Theft Auto Vice City", "Pro Evolution Soccer 6", "Final Fantasy X",
    "Kingdom Hearts", "God of War", "Resident Evil 4", "Metal Gear Solid 3 Snake Eater", "Shadow of the Colossus",
    "Gran Turismo 4", "Tekken 5", "Need for Speed Underground 2", "Jak and Daxter The Precursor Legacy",
    "Ratchet & Clank", "Devil May Cry 3", "Silent Hill 2", "Okami", "Burnout 3 Takedown", "Sonic Heroes",
    "Buzz The Music Quiz",
)
PROBE_RARE_GAMES = 20        # the first plain (not edition, not country-only) PAL entries of rare_games.json
PROBE_BY_CATEGORY_CHECK = 5  # per group: also asked without the video games category, to see it is the right one
PROBE_MANY = 5               # "enough": a site is worth pricing games on if most famous games show this many copies
PROBE_TIME_BUDGET = 600      # seconds


def probe_rare_titles(path=None):
    data = read_json(path or ROOT / "rare_games.json", {})
    entries = (data.get("lists") or {}).get("PAL") if isinstance(data, dict) else None
    titles = []
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("title"), str) and not entry.get("flags"):
            titles.append(entry["title"])
        if len(titles) >= PROBE_RARE_GAMES:
            break
    return titles


def annotation(title, lines):
    """A line the Actions run shows as a notice, so it can be read through the checks API
    when the job log cannot be downloaded. Only counts and our own game names go in."""
    def escape(text):
        return str(text).replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    return f"::notice title={escape(title).replace(',', '%2C').replace(':', '%3A')}::{escape(chr(10).join(lines))}"


def probe_search(http_client, token, market_id, country, query, in_category, counter):
    """How many listings one site reports for the words, asked for one listing only. Returns
    (count or None, reason when there is no count). Prices are never read."""
    filters = f"buyingOptions:{{FIXED_PRICE}},itemLocationCountry:{country}"
    params = {"q": f"{query} ps2", "filter": filters, "limit": "1"}
    if in_category:
        params["category_ids"] = CATEGORY_ID
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": market_id,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + quote(f"country={country}", safe=""),
    }
    counter["searches"] += 1
    try:
        status, text = http_client.send(SEARCH_URL + "?" + urlencode(params, quote_via=quote), headers)
        payload = parse(text)
    except NetworkProblem as exc:
        return None, f"network problem ({exc})"
    if status == 429:
        raise LimitReached(error_text(status, payload))
    total = payload.get("total")
    if status == 200 and isinstance(total, int):
        return total, ""
    return None, error_text(status, payload)


def run_probe(http_client, client_id, client_secret, rare_titles=None, pause=REQUEST_PAUSE, out=say):
    """Ask each site in PROBE_MARKETS how many listings it reports for the famous games and the
    rare PAL ones. Prints counts and our own game names; writes nothing."""
    token, basic = get_token(http_client, client_id, client_secret)
    secrets = (client_id, client_secret, token, basic)
    rare_titles = probe_rare_titles() if rare_titles is None else list(rare_titles)
    groups = (("famous", list(PROBE_FAMOUS)), ("rare PAL", rare_titles))
    counter, started, stopped = {"searches": 0}, time.monotonic(), ""
    for market_id, market in PROBE_MARKETS.items():
        lines, summary = [], []
        for group, titles in groups:
            counts, errors = [], []
            for n, title in enumerate(titles):
                if time.monotonic() - started > PROBE_TIME_BUDGET:
                    stopped = "time is up"
                    break
                try:
                    total, reason = probe_search(http_client, token, market_id, market["country"], title, True, counter)
                    wider = ""
                    if n < PROBE_BY_CATEGORY_CHECK:
                        time.sleep(pause)
                        outside, why = probe_search(http_client, token, market_id, market["country"], title, False, counter)
                        wider = f" (without the category: {outside if outside is not None else why})"
                except LimitReached as exc:
                    stopped = f"eBay says the allowance of searches is used up ({redact(exc, secrets)})"
                    break
                time.sleep(pause)
                if total is None:
                    errors.append(reason)
                    lines.append(redact(f"{title}: no count, {reason}", secrets))
                else:
                    counts.append(total)
                    lines.append(redact(f"{title}: {total}{wider}", secrets))
            if counts or errors:
                summary.append(f"{group}: {sum(1 for c in counts if c >= PROBE_MANY)} of {len(counts)} show {PROBE_MANY}+ copies, "
                               f"{sum(1 for c in counts if c >= 1)} show 1+, {len(errors)} could not be counted")
            if stopped:
                break
        head = f"[{market['label']}] " + "; ".join(summary)
        out(head)
        out(annotation(f"eBay check {market['label']}", [head] + lines))
        if stopped:
            break
    out(f"{counter['searches']} searches used" + (f"; stopped early: {stopped}" if stopped else "") + ". Nothing was written.")
    return counter["searches"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="eBay asking prices for the PS2 games the feed mentions.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write this run's listings")
    parser.add_argument("--plan", action="store_true", help="show what would be checked now, then stop")
    args = parser.parse_args(argv)
    SORT_BY_PRICE.update({"on": True, "worked": False})

    client_id = os.environ.get("EBAY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    with_diagnosis = os.environ.get("EBAY_DIAGNOSE", "").strip().lower() == "true"
    if os.environ.get("EBAY_PROBE", "").strip().lower() == "true":
        # Started by hand to count listings on other eBay sites; nothing is read or written.
        if not client_id or not client_secret:
            say("STOPPED: the eBay key is not set.")
            return 1
        try:
            run_probe(Http(), client_id, client_secret)
        except EbayError as exc:
            say(f"STOPPED: {redact(exc, (client_id, client_secret))}")
            return 1
        return 0
    now = utc_now()
    latest_path = PRICES_DIR / LATEST_NAME
    wanted = os.environ.get("EBAY_CHECK_GAME", "").strip()
    try:
        history_path = PRICES_DIR / f"{now.strftime('%Y-%m')}.json"
        pinned, never = load_watchlist()
        state = load_state(latest_path)
        history = read_own(history_path, [])   # fail now, before asking eBay, if it cannot be added to
        # The month before, for a week's change early in a month. Only read: a damaged one
        # costs those changes, not the run.
        last_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        earlier = read_json(PRICES_DIR / f"{last_month}.json", [])
        mentions, ever = load_mentions()
        library, catalogue = load_library()
        games, left_out = plan_games(now, pinned, never, mentions, ever, library, catalogue, state)
        underrated = load_underrated()
        left_out["underrated"] = add_underrated_games(games, underrated, library, catalogue)
        apply_regional_names(games, load_regional_names(), catalogue)
        rare, rare_problems = load_rare()
        rare_titles = add_rare_games(games, rare, catalogue)
        editions, edition_problems = load_rare(EDITIONS_PATH, kind="edition")
        edition_titles = add_rare_games(games, editions, catalogue)
        consoles, console_problems = load_consoles()
        consoles_priced = add_consoles(games, consoles)
        mark_watched(games, underrated + [entry["title"] for entry in rare])
        rare_problems = rare_problems + console_problems + [f"editions.json: {problem}" for problem in edition_problems]
        if wanted:
            # Started by hand to see why one game shows no copies somewhere: counts for the search with one
            # part relaxed at a time. Nothing is looked up for the dashboard and nothing is written.
            game = next((g for g in games if str(g.get("title", "")).lower() == wanted.lower() and g.get("kind") != "console"), None)
            if game is None:
                say(f'STOPPED: "{wanted}" is not a game this script tracks.')
                return 1
            if not client_id or not client_secret:
                say("STOPPED: the eBay key is not set.")
                return 1
            token, basic = get_token(Http(), client_id, client_secret)
            lines = check_game(Http(), token, game, (client_id, client_secret, token, basic))
            say(f'Search check for "{game["title"]}" (listings eBay reports):')
            for line in lines:
                say("  " + line)
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(annotation(f"Search check: {game['title']}", lines), flush=True)
            return 0
        lookups = due_lookups(games, state, now, earlier + history)
        used = state.get("searches") if isinstance(state.get("searches"), dict) else {}
        used_today = used.get("used", 0) if used.get("day") == now.strftime("%Y-%m-%d") else 0
        allowance = min(MAX_SEARCHES_PER_RUN, DAILY_SEARCHES - used_today)
        describe_plan(games, left_out, lookups, allowance, rare_titles if rare else None, rare_problems, consoles_priced, edition_titles if editions else None)
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

    latest, rows = update_records(state, games, run, now, rare_titles if rare else None, edition_titles if editions else None)
    add_week_before(latest, earlier + history + rows)
    try:
        append_history(history_path, rows)
    except EbayError as exc:
        say(f"STOPPED: {exc}")
        return 1
    write_latest(latest_path, latest)
    # The month before is enough history for most of the index, but every month is read so
    # that it never restarts; a month that cannot be read leaves the index as it was.
    every_month = []
    for month in sorted(PRICES_DIR.glob("20??-??.json")):
        try:
            rows_of_month = json.loads(month.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            rows_of_month = None
        if not isinstance(rows_of_month, list):
            every_month = None
            say(f"The price index was not updated: data/prices/{month.name} cannot be read.")
            break
        every_month += rows_of_month
    if every_month is not None:
        before = read_json(PRICES_DIR / INDEX_NAME, {}).get("left_out")
        write_latest(PRICES_DIR / INDEX_NAME, index_file(every_month, latest, now, before if isinstance(before, list) else ()))
        write_series(PRICES_DIR / SERIES_NAME, series_file(every_month, now))
    say(f"Wrote {LATEST_NAME} and added {len(rows)} rows to this month's price history.")
    if run["results"]:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(snapshot_of(run, now), indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
