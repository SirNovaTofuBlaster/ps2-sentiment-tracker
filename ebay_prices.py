"""Looks up what PS2 games are currently listed for on eBay.

Runs separately from scraper.py and never touches it. For every game in
ebay_watchlist.json, and for each eBay site (US and UK), it asks eBay's
official Browse API for used, Buy It Now listings located in that country,
drops listings that are not a copy of that game (other games, empty cases,
soundtracks, cheat discs, job lots, imports), and writes one JSON file: how many copies are listed, the
lowest and the median asking price, and links to the ten cheapest listings.

Read the numbers for what they are:

- They are ASKING prices of copies still for sale, not sold prices. Sellers
  ask for more than buyers pay, and a bargain that sold in an hour never
  shows up here.
- US and UK are never mixed. A US copy (NTSC) and a UK copy (PAL) are
  different products in different currencies.
- Loose discs and complete copies are counted together; "incomplete_hint"
  says how many listings admit to missing something.
- eBay returns at most 200 listings for a search. When a game has more,
  "truncated" is true and the figures describe those 200 only.

The eBay key comes from two environment variables, EBAY_CLIENT_ID and
EBAY_CLIENT_SECRET (GitHub Actions secrets). It is never written to a file
and never printed. This script uses only Python's standard library, so the
job that holds the key installs nothing.

    python ebay_prices.py --out some/file.json

Without --out the file goes to the system's temporary folder, never into the
repository: eBay listing data must not end up in data/ or on the main branch.
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
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import quote, urlencode

ROOT = Path(__file__).parent
WATCHLIST_PATH = ROOT / "ebay_watchlist.json"
DEFAULT_OUT = Path(tempfile.gettempdir()) / "ebay_prices.json"   # outside the repository on purpose

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

PAGE_LIMIT = 200         # the most eBay returns for one search
LISTINGS_KEPT = 10       # cheapest listings saved per game per site, each with its link
MAX_GAMES = 100          # 100 games x 2 sites x 24 runs = 4,800 searches against eBay's 5,000 a day.
#                          A lookup that needs its keyword retry costs one more; if the allowance
#                          runs out the run stops cleanly and says so.
MAX_QUERY_CHARS = 100    # eBay's limit for the search words
REQUEST_TIMEOUT = 15
REQUEST_PAUSE = 0.25     # seconds between searches
RETRY_PAUSES = (2, 8)    # seconds before the second and third try of a failed search
MAX_SILENT_LOOKUPS = 3   # give up when eBay has not answered this many lookups in a row

# How a title says "PS2". A keyword search only counts titles that do.
PLATFORM_WORDS = re.compile(r"\b(?:sony )?(?:playstation ?2|play station 2|ps ?2)\b")
SEQUEL_WORDS = {"ii", "iii", "iv", "vi", "vii", "viii", "ix"}
DISC_WORDS = {"disc", "discs", "disk", "disks", "dvd", "cd", "player", "players"}

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


def words(text):
    """Lower-case words with accents and punctuation removed: 'Ōkami™ (PS2)' -> ['okami', 'ps2'].

    Accents are folded into their letter; every other symbol, emoji included,
    separates words, so "Okami⭐Complete" is two words and not one."""
    plain = "".join(char for char in unicodedata.normalize("NFD", str(text or ""))
                    if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", plain.lower())


def has_phrase(text, phrases):
    """True when one of the phrases appears in the text as whole words."""
    padded = f" {text} "
    return any(f" {phrase} " in padded for phrase in phrases if phrase)


def redact(text, secrets):
    """Remove the key from anything about to be printed or saved. Belt and braces."""
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def load_watchlist(path=WATCHLIST_PATH):
    """The games to look up, checked so that a typo fails with a readable message."""
    name = Path(path).name
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise EbayError(f"Cannot read {name}: {type(exc).__name__}") from None
    except ValueError as exc:
        raise EbayError(f"{name} is not valid JSON: {exc}") from None

    games = raw.get("games") if isinstance(raw, dict) else None
    if not isinstance(games, list) or not games:
        raise EbayError(f'{name} needs a "games" list with at least one game.')
    if len(games) > MAX_GAMES:
        raise EbayError(f"{name} lists {len(games)} games; the most that fits inside "
                        f"eBay's daily limit is {MAX_GAMES}.")

    checked, seen = [], set()
    for position, game in enumerate(games, 1):
        if not isinstance(game, dict) or not isinstance(game.get("title"), str) or not game["title"].strip():
            raise EbayError(f'Game {position} in {name} needs a "title".')
        title = game["title"].strip()
        search = game.get("search", title)
        if not isinstance(search, str) or not words(search):
            raise EbayError(f'"{title}": "search" must be the words to look for on eBay.')
        phrase = " ".join(words(search))
        if len(phrase) + len(" ps2") > MAX_QUERY_CHARS:
            raise EbayError(f'"{title}": the search words are too long for eBay; add a shorter "search".')
        exclude = game.get("exclude", [])
        if not isinstance(exclude, list) or not all(isinstance(word, str) for word in exclude):
            raise EbayError(f'"{title}": "exclude" must be a list of words.')
        key = " ".join(words(title))
        if key in seen:
            raise EbayError(f'"{title}" is listed twice in {name}.')
        seen.add(key)
        checked.append({"title": title, "search": phrase,
                        "exclude": [" ".join(words(word)) for word in exclude if words(word)]})
    return checked


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


def search_url(market_id, phrase, by_aspect=True, condition="ids"):
    """The search request for one game on one site, encoded the way eBay's examples are."""
    market = MARKETS[market_id]
    filters = [CONDITION_FILTERS[condition], "buyingOptions:{FIXED_PRICE}",
               f"itemLocationCountry:{market['country']}"]
    params = {
        "q": phrase if by_aspect else f"{phrase} ps2",
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


def search(http_client, token, market_id, phrase, counter, by_aspect=True, condition="ids"):
    """One search, tried up to three times. Returns (HTTP status or 0 for no answer, JSON)."""
    market = MARKETS[market_id]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": market_id,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + quote(buyer_location(market), safe=""),
    }
    url = search_url(market_id, phrase, by_aspect, condition)
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
    "silent hill 2 3 4" is a set and "kingdom hearts ii" is the sequel. A
    number that counts discs ("2 disc"), a score ("9 10") or an age rating
    ("18") is fine."""
    padded = f" {text} "
    at = padded.find(f" {phrase} ")
    if at < 0:
        return False
    rest = padded[at + len(phrase) + 2:].split()
    if rest[:1] in (["and"], ["plus"]):
        rest = rest[1:]
    if not rest:
        return True
    if rest[0] in SEQUEL_WORDS:
        return False
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


def is_the_soundtrack(title, phrase):
    """True when the listing is the game's soundtrack: "Rule of Rose Original Soundtrack CD".

    A copy that comes with, or is missing, its bonus soundtrack says so some
    other way ("Silent Hill 3 + soundtrack", "Silent Hill 3 PS2 disc w/
    soundtrack", "no soundtrack"), and is still a copy."""
    padded = f" {' '.join(words(re.sub(r'[+&]', ' and ', str(title or ''))))} "
    at = padded.find(f" {phrase} ")
    rest = padded[at + len(phrase) + 2:].split() if at >= 0 else []
    while rest and rest[0] in SOUNDTRACK_LEAD_INS:
        rest = rest[1:]
    return bool(rest) and rest[0] in SOUNDTRACK_WORDS


def reject_reason(item, game, market, keyword_search):
    """Why a listing is left out, or None to count it."""
    text = " ".join(words(item.get("title")))
    if keyword_search and not PLATFORM_WORDS.search(text):
        return "other_game"
    if not names_this_game(text, game["search"]) or names_another_entry(text, game["search"]):
        return "other_game"
    if has_phrase(text, OTHER_PLATFORMS):
        return "other_platform"
    if has_phrase(text, JUNK_PHRASES) or has_phrase(text, game["exclude"]) \
            or is_the_soundtrack(item.get("title"), game["search"]):
        return "not_a_copy"
    if has_phrase(text, IMPORT_PHRASES) or has_phrase(text, market["foreign"]):
        return "import"
    if amount(item.get("price"), market["currency"]) is None:
        return "no_price"
    if listing_url(item, market) is None:
        return "no_link"
    return None


def summarise(payload, game, market, keyword_search):
    """Turn one search result into the numbers and links that get saved."""
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
    result = {
        "status": "ok" if kept else "none",
        "currency": market["currency"],
        "platform_filter": "keyword" if keyword_search else "item_specific",
        "on_ebay": on_ebay,                   # eBay's own count for the search
        "fetched": len(items),
        "truncated": on_ebay > len(items),    # true: the figures below cover the first 200 only
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
    return (f"https://{market['site']}/sch/i.html?_nkw={quote(game['search'] + ' ps2')}"
            f"&_sacat={CATEGORY_ID}&LH_ItemCondition={quote(USED_CONDITION_IDS)}&LH_BIN=1&LH_PrefLoc=1")


def check_market(http_client, token, game, market_id, counter):
    """Look one game up on one eBay site."""
    market = MARKETS[market_id]
    base = {"search_url": human_search_url(game, market), "currency": market["currency"]}

    status, payload = search(http_client, token, market_id, game["search"], counter)
    keyword_search = False
    if status == 200 and not payload.get("itemSummaries"):
        # Nothing carries the PS2 item specific: ask again by keyword instead.
        time.sleep(REQUEST_PAUSE)
        status, payload = search(http_client, token, market_id, game["search"], counter, by_aspect=False)
        keyword_search = True

    if status != 200:
        return {**base, "status": "error", "answered": status != 0, "error": error_text(status, payload)}
    return {**base, **summarise(payload, game, market, keyword_search)}


def describe(game, market, result):
    """One log line per lookup. Counts only: prices stay out of the public log."""
    label = f"  {game['title']} [{market['label']}]"
    if result["status"] == "not_checked":
        return f"{label}: not checked, eBay's allowance of searches ran out"
    if result["status"] == "error":
        return f"{label}: FAILED {result.get('error', '')}"
    notes = []
    if result["platform_filter"] == "keyword":
        notes.append("keyword search")
    if result["truncated"]:
        notes.append(f"first {result['fetched']} of {result['on_ebay']} on eBay")
    if result.get("warning"):
        notes.append(f"eBay warning: {result['warning']}")
    tail = f" ({'; '.join(notes)})" if notes else ""
    if result["status"] == "none":
        return f"{label}: no listings counted, {result['fetched']} returned{tail}"
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
                status, payload = search(http_client, token, market_id, game["search"], counter,
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


def build(http_client, client_id, client_secret, games, with_diagnosis=False):
    """Every game on every site. Returns the output; raises EbayError if eBay stops answering."""
    token, basic = get_token(http_client, client_id, client_secret)
    secrets = (client_id, client_secret, token, basic)
    counter = {"searches": 0}
    if with_diagnosis:
        diagnose(http_client, token, games[0], counter, secrets)

    say(f"Looking up {len(games)} games on {len(MARKETS)} eBay sites:")
    rows, limit_message, silent = [], "", 0
    for game in games:
        row = {"title": game["title"], "search": game["search"], "markets": {}}
        for market_id, market in MARKETS.items():
            result = {"status": "not_checked", "currency": market["currency"],
                      "search_url": human_search_url(game, market)}
            if not limit_message:
                try:
                    result = check_market(http_client, token, game, market_id, counter)
                except LimitReached as exc:
                    limit_message = redact(exc, secrets) or "HTTP 429"
                time.sleep(REQUEST_PAUSE)
            if "error" in result:
                result["error"] = redact(result["error"], secrets)
            if "warning" in result:
                result["warning"] = redact(result["warning"], secrets)
            silent = silent + 1 if result.get("answered") is False else 0
            result.pop("answered", None)
            row["markets"][market_id] = result
            say(redact(describe(game, market, result), secrets))
            if silent >= MAX_SILENT_LOOKUPS:
                raise EbayError(f"eBay did not answer {silent} lookups in a row, so the run was "
                                "abandoned. Nothing was written. Try again later.")
        rows.append(row)

    output = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "what": "Asking prices of used Buy It Now listings still for sale on eBay. Not sold prices.",
        "source": "eBay Browse API",
        "markets": {market_id: {k: market[k] for k in ("label", "site", "currency")}
                    for market_id, market in MARKETS.items()},
        "searches_used": counter["searches"],
        "limit_reached": bool(limit_message),
        "games": rows,
    }
    if limit_message:
        output["limit_message"] = limit_message
    return output


def verdict(output):
    """None when the snapshot is worth publishing, otherwise the reason it is not."""
    results = [market for row in output["games"] for market in row["markets"].values()]
    answered = [r for r in results if r["status"] in ("ok", "none")]
    errors = sum(1 for r in results if r["status"] == "error")
    if not answered:
        return "every lookup failed, so nothing was written."
    if errors * 2 > len(results):
        return (f"{errors} of {len(results)} lookups failed, so nothing was written and the "
                "previous snapshot stays in place.")
    if all(r["fetched"] == 0 for r in answered):
        return ("eBay answered but returned no listings for any game, so nothing was written. "
                "The search filter is probably wrong: send this log to whoever maintains the script.")
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Current eBay asking prices for the PS2 watchlist.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the JSON file")
    args = parser.parse_args(argv)

    client_id = os.environ.get("EBAY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    with_diagnosis = os.environ.get("EBAY_DIAGNOSE", "").strip().lower() == "true"
    try:
        if not client_id or not client_secret:
            raise EbayError(
                "The eBay key is not set. In the repository on GitHub: Settings > Secrets and variables "
                "> Actions > New repository secret. Add EBAY_CLIENT_ID (the Production App ID) and "
                "EBAY_CLIENT_SECRET (the Production Cert ID)."
            )
        games = load_watchlist()
        output = build(Http(), client_id, client_secret, games, with_diagnosis)
    except EbayError as exc:
        say(f"STOPPED: {redact(exc, (client_id, client_secret))}")
        return 1

    results = [market for row in output["games"] for market in row["markets"].values()]
    answered = sum(1 for r in results if r["status"] in ("ok", "none"))
    say(f"{output['searches_used']} searches used; {answered} of {len(results)} lookups answered.")
    if output["limit_reached"]:
        say(f"eBay's allowance of searches ran out ({output['limit_message']}).")
    problem = verdict(output)
    if problem:
        say(f"STOPPED: {problem}")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say(f"Wrote {args.out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
