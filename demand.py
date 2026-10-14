"""Builds a demand index for the PS2 games currently being discussed.

Runs separately from scraper.py and never touches it: reads the items out of
data/sentiment_feed.json and the figures out of data/prices/latest.json, looks
each game up on Wikipedia, and writes data/demand.json for the dashboard, and
data/wiki_checks.json (is the article really a PS2 game, and does it call the
game a rare collectible).

Version 2 (2026-10-14) scores a game from five signals, each 0-100, and blends
the ones it has: how fast mentions are rising (momentum), how many different
sources name it (breadth), views of YouTube videos that name it, how its eBay
median moved over a week, and Wikipedia's reader trend. See SIGNAL_WEIGHTS.

Every network step fails soft. A title that cannot be resolved confidently is
left out rather than given a wrong number, and a run that collects nothing
leaves the previous file untouched."""

import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from rapidfuzz import fuzz

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "sentiment_feed.json"
DEMAND_PATH = DATA_DIR / "demand.json"
PRICES_PATH = DATA_DIR / "prices" / "latest.json"   # read only: numbers from eBay
WIKI_CHECKS_PATH = DATA_DIR / "wiki_checks.json"    # title -> what its Wikipedia article says
WIKI_MAP_PATH = DATA_DIR / "wiki_titles.json"       # PS2 title -> resolved Wikipedia article
WIKI_OVERRIDES_PATH = ROOT / "wiki_overrides.json"  # hand-curated fixes, committed

USER_AGENT = "python:ps2-sentiment-tracker-demand:1.0 (+https://github.com/SirNovaTofuBlaster/ps2-sentiment-tracker)"
REQUEST_TIMEOUT = 20
WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
                 "/en.wikipedia/all-access/user/{article}/daily/{start}/{end}")

MAX_TITLES = 60          # most-mentioned games to rank; keeps the run short
WINDOW_DAYS = 28         # pageview history fetched per article
TREND_DAYS = 7           # last N days compared against the N before them
RESOLVE_THRESHOLD = 82   # fuzzy score an article title must reach to be trusted
REQUEST_PAUSE = 0.2      # seconds between API calls; well inside both services' limits
TIME_BUDGET = 480        # seconds; whatever is unresolved by then waits for the next run

# How much each signal moves the blended score. A game's score is the weighted
# average of the signals it HAS (a game with no YouTube data is scored on the
# other four, not marked down). The weights are a judgement call, not a
# measurement. Raw Wikipedia pageviews are no longer in it: they measure how
# famous a game already is, on every console and remake.
SIGNAL_WEIGHTS = {"momentum": 0.30, "breadth": 0.15, "youtube": 0.20, "ebay": 0.20, "wikipedia": 0.15}
RECENT_DAYS = 3          # momentum: mentions in the last N days ...
BASELINE_DAYS = 11       # ... against the N days before those (the snapshot keeps 14)
EBAY_MIN_COPIES = 3      # a week's change in a median of fewer copies than this says nothing
CHECKS_PER_RUN = 150     # Wikipedia articles checked per run (resolved + read in full)
RULES_VERSION = 3        # raise when the collectible rules change: every article is read again
CHECK_MAX_AGE_DAYS = 30  # a checked article is read again after this long

# Articles that are never the game, whatever the search says.
BAD_ARTICLE_HINTS = ("disambiguation", "list of", "(franchise)", "(series)", "(company)")


def load_json(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def save_json_if_changed(path, value, previous):
    if value != previous:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        return True
    return False


def resolve_article(session, title):
    """Best Wikipedia article for a PS2 title, or None when nothing matches well
    enough. A wrong article would publish a wrong number, so the gate is strict."""
    params = {
        "action": "query", "list": "search", "srsearch": f'{title} video game',
        "srlimit": 5, "srnamespace": 0, "format": "json", "formatversion": 2,
    }
    response = session.get(WIKI_API, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    results = response.json().get("query", {}).get("search", [])
    best, best_score = None, 0
    for result in results:
        article = result.get("title", "")
        lowered = article.lower()
        if any(hint in lowered for hint in BAD_ARTICLE_HINTS):
            continue
        # Compare against the article name with any "(video game)" qualifier removed.
        bare = article.split(" (")[0]
        score = fuzz.WRatio(title, bare)
        if score > best_score:
            best, best_score = article, score
    return best if best_score >= RESOLVE_THRESHOLD else None


def fetch_pageviews(session, article, start, end):
    """Daily view counts for an article, oldest first. [] when Wikipedia has none."""
    url = PAGEVIEWS_API.format(
        article=quote(article.replace(" ", "_"), safe=""),
        start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"),
    )
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    items = response.json().get("items", [])
    return [int(i.get("views", 0)) for i in items]


def split_trend(views):
    """(recent total, previous total, percent change) over the trend window."""
    if len(views) < TREND_DAYS * 2:
        return sum(views), 0, None
    recent = sum(views[-TREND_DAYS:])
    previous = sum(views[-TREND_DAYS * 2:-TREND_DAYS])
    if previous <= 0:
        return recent, previous, None
    return recent, previous, round((recent - previous) / previous * 100, 1)


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


# ---------------------------------------------------------------------------------------
# What the feed says about each game (no network)
# ---------------------------------------------------------------------------------------

def parse_stamp(value):
    """"2026-10-14 13:00 UTC" -> an aware datetime, or None."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def feed_stats(items, now):
    """{title: raw figures} from the snapshot's items: mentions in the last RECENT_DAYS and in the
    BASELINE_DAYS before, the sources that named it, and the YouTube views of videos naming it.
    Also returns whether any item carries a view count at all (before the scraper keeps them,
    none does, and YouTube is then no signal rather than a zero)."""
    recent_from = now - timedelta(days=RECENT_DAYS)
    base_from = now - timedelta(days=RECENT_DAYS + BASELINE_DAYS)
    stats, any_views = {}, False
    for item in items:
        if not isinstance(item, dict):
            continue
        titles = item.get("matched_games") or ([item["matched_game"]] if item.get("matched_game") else [])
        when = parse_stamp(item.get("timestamp"))
        if when is None or when < base_from or when > now + timedelta(hours=1):
            continue
        views = item.get("views")
        has_views = item.get("source_type") == "youtube" and isinstance(views, int) and views >= 0
        any_views = any_views or has_views
        for title in titles:
            if not isinstance(title, str) or not title:
                continue
            row = stats.setdefault(title, {"mentions": 0, "recent": 0, "prior": 0, "last_day": 0,
                                           "sources": set(), "youtube_views": 0, "youtube_videos": 0})
            row["mentions"] += 1
            row["recent" if when >= recent_from else "prior"] += 1
            if when >= now - timedelta(days=1):
                row["last_day"] += 1
            row["sources"].add(item.get("feed") or item.get("source") or "?")
            if has_views:
                row["youtube_views"] += views
                row["youtube_videos"] += 1
    return stats, any_views


def ebay_change(entry):
    """(percent change of the median over a week, averaged over the eBay sites that have one) for
    an entry of latest.json, or None. Needs a week-old figure and enough copies to mean something."""
    changes = []
    for site in ("UK", "US"):
        figures = entry.get(site) if isinstance(entry, dict) else None
        if not isinstance(figures, dict) or figures.get("unmatched"):
            continue
        week = figures.get("week") if isinstance(figures.get("week"), dict) else {}
        median, before, copies = figures.get("median"), week.get("median"), figures.get("copies")
        if isinstance(median, (int, float)) and isinstance(before, (int, float)) and before > 0 \
                and isinstance(copies, int) and copies >= EBAY_MIN_COPIES:
            changes.append((median - before) / before * 100)
    return round(sum(changes) / len(changes), 1) if changes else None


def momentum_score(recent, prior):
    """50 when mentions come at the usual pace, 100 at four times it, 0 at a quarter of it.
    The pseudo-counts stop one stray mention from looking like a surge."""
    ratio = ((recent + 2) / RECENT_DAYS) / ((prior + 6) / BASELINE_DAYS)
    return clamp(50 + 33 * math.log2(ratio))


def signal_scores(row, most_sources, most_views, have_youtube):
    """The five 0-100 scores of one row; None where there is nothing to score."""
    trend = row.get("trend_pct")
    return {
        "momentum": round(momentum_score(row["recent"], row["prior"]), 1),
        "breadth": round(len(row["sources"]) / most_sources * 100, 1) if most_sources else None,
        # Logarithmic: one viral video must not hide everything else.
        "youtube": (round(math.log1p(row["youtube_views"]) / math.log1p(most_views) * 100, 1)
                    if have_youtube and most_views > 0 else (0.0 if have_youtube else None)),
        # +20% in a week is full marks, -20% nothing.
        "ebay": None if row.get("ebay_change_pct") is None else round(clamp(50 + 2.5 * row["ebay_change_pct"]), 1),
        "wikipedia": None if trend is None else round(clamp((trend + 50) / 1.5), 1),
    }


def blend(rows, have_youtube):
    """Adds "signals" and a 0-100 "demand" to each row, then sorts best first."""
    most_sources = max((len(r["sources"]) for r in rows), default=0)
    most_views = max((r["youtube_views"] for r in rows), default=0)
    for row in rows:
        scores = signal_scores(row, most_sources, most_views, have_youtube)
        have = {name: value for name, value in scores.items() if value is not None}
        total = sum(SIGNAL_WEIGHTS[name] for name in have)
        row["signals"] = scores
        row["demand"] = round(sum(SIGNAL_WEIGHTS[name] * value for name, value in have.items()) / total, 1) if total else 0.0
        row["sources"] = len(row["sources"])      # a number in the file, not the list
    rows.sort(key=lambda r: (-r["demand"], -r["mentions"], r["title"]))
    return rows


# ---------------------------------------------------------------------------------------
# What Wikipedia says about a game's article
# ---------------------------------------------------------------------------------------

# A sentence is evidence that a game is a rare collectible when it uses a value word AND talks
# about copies or the market, and is not about the game's own contents.
VALUE_WORDS = re.compile(r"\b(rare|rarity|scarce|scarcity|collector'?s?|collectible|collectable|sought[- ]after|"
                         r"valuable|expensive|out of print|limited (?:print|run|release|production)|"
                         r"high prices?|sells? for|sold for|fetch(?:es|ed)?)\b", re.I)
MARKET_WORDS = re.compile(r"\b(copies|copy|resale|market|prices?|priced|second-?hand|ebay|auctions?|"
                          r"collectors?|print run|retail(?:er|ers)?|[$£€]\d)", re.I)
IN_GAME_WORDS = re.compile(r"\b(in-game|player|players|character|characters|weapon|weapons|enemy|enemies|"
                           r"boss|loot|quest)\b", re.I)


# What counts as "the article calls the game a rare collectible" (rules v3, 2026-10-14, written
# from reading the flagged articles): the rarity must be of the game's copies, versions, releases
# or of the game itself becoming sought after, or a price must be given for second-hand copies.
# Not counted: rare items or enemies inside the game, "collector's edition" boxes, a development
# budget ("most expensive game"), sales figures ("sold for" / "sold 1 million"), review quotes
# ("a rarity in the comic book world").
_RARITY = r"(?:rare|rarer|scarce|sought[- ]after|out of print|highly valued)"
_COPY = r"(?:copies|copy|versions?|releases?|editions?|pressings?|print(?:ing)?s?|discs?)"
COLLECTIBLE_PATTERNS = [
    ("rare", re.compile(r"\b(?:become|became|becoming|becomes)\s+(?:an?\s+)?(?:somewhat\s+|very\s+|extremely\s+|highly\s+|quite\s+)?" + _RARITY + r"\b", re.I)),
    ("rare", re.compile(r"\b" + _RARITY + r"\s+(?:collect[ai]ble|collector'?s?\s+items?|" + _COPY + r")\b", re.I)),
    ("rare", re.compile(r"\b" + _COPY + r"\b[^.;]{0,40}\b(?:are|is|have become|has become|became)\s+(?:now\s+)?(?:very\s+|extremely\s+|highly\s+)?" + _RARITY + r"\b", re.I)),
    ("out of print", re.compile(r"\bout of print\b", re.I)),
    ("low quantities", re.compile(r"\b(?:low quantities|limited number of copies|limited print run|small print run)\b", re.I)),
    ("second-hand price", re.compile(r"\b(?:pre-owned|second-?hand|used|resale|loose|complete)\s+(?:copies|market|prices?)[^.;]{0,60}[$£€]\s?\d", re.I)),
    ("expensive second-hand", re.compile(r"\bexpensive\b[^.;]{0,40}\b(?:second-?hand|to buy|to collect|on the (?:resale|used) market)\b", re.I)),
]


def collectible_terms(text):
    """Short labels (at most three) for why the article calls the game a rare or valuable
    collectible; [] when it does not. Only the labels are kept, never the sentences."""
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+", str(text or "")):
        if IN_GAME_WORDS.search(sentence):
            continue
        for label, pattern in COLLECTIBLE_PATTERNS:
            if label not in found and pattern.search(sentence):
                found.append(label)
    return found[:3]


def check_article_text(text):
    """What the full text of an article says: is it a video game, does it mention the PS2, and
    which collectible words does it use."""
    text = str(text or "")
    lead = text[:700].lower()
    return {
        "game": "video game" in lead or "game" in lead[:300],
        "ps2": bool(re.search(r"PlayStation 2|\bPS2\b", text)),
        "collectible": collectible_terms(text),
    }


def fetch_extract(session, article):
    """The whole plain text of an article ("" when there is none)."""
    params = {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
              "titles": article, "format": "json", "formatversion": 2}
    response = session.get(WIKI_API, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", [])
    return pages[0].get("extract", "") if pages and isinstance(pages[0], dict) else ""


def due_for_check(title, checks, today):
    entry = checks.get(title)
    if not isinstance(entry, dict) or entry.get("rules") != RULES_VERSION:
        return True
    try:
        age = (today - datetime.strptime(entry.get("checked", ""), "%Y-%m-%d").date()).days
    except ValueError:
        return True
    return age >= CHECK_MAX_AGE_DAYS


def update_checks(session, titles, resolved, overrides, checks, started):
    """Reads the Wikipedia article of up to CHECKS_PER_RUN of the titles that are due, in order,
    and records what it says. Returns True when something was recorded."""
    today = datetime.now(timezone.utc).date()
    done = changed = 0
    for title in titles:
        if done >= CHECKS_PER_RUN or time.monotonic() - started > TIME_BUDGET:
            break
        if not due_for_check(title, checks, today):
            continue
        done += 1
        try:
            article = overrides[title] if title in overrides else resolved.get(title)
            if article is None and title not in overrides and title not in resolved:
                article = resolve_article(session, title)
                resolved[title] = article
                time.sleep(REQUEST_PAUSE)
            entry = {"article": article, "checked": today.strftime("%Y-%m-%d"), "rules": RULES_VERSION}
            if article:
                entry.update(check_article_text(fetch_extract(session, article)))
                time.sleep(REQUEST_PAUSE)
        except (requests.RequestException, ValueError) as e:
            print(f"  could not check {title}: {e}")
            continue
        checks[title] = entry
        changed += 1
    return changed > 0


def usable_article(title, checks, resolved, overrides):
    """The Wikipedia article to trust for a title: an override wins; otherwise the resolved one, but
    only once it has been read and is a video game that mentions the PS2. None otherwise."""
    if title in overrides:
        return overrides[title] or None
    entry = checks.get(title)
    if isinstance(entry, dict):
        return entry["article"] if entry.get("article") and entry.get("game") and entry.get("ps2") else None
    return resolved.get(title)       # not read yet: the old, strict-match behaviour


# ---------------------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------------------

def build_demand():
    DATA_DIR.mkdir(exist_ok=True)
    snapshot = load_json(SNAPSHOT_PATH, {})
    now = datetime.now(timezone.utc)
    stats, have_youtube = feed_stats(snapshot.get("items", []), now)
    if not stats:
        print("No matched games in the snapshot; nothing to rank.")
        return
    prices = load_json(PRICES_PATH, {}).get("games", {})
    ranked = sorted(stats, key=lambda t: (-stats[t]["mentions"], t))
    wanted = ranked[:MAX_TITLES]
    # Articles are read for the games named in the last day first (the dashboard's "rare" list needs
    # those), then for the ranked games, then for any other game with a mention.
    last_day = sorted((t for t in stats if stats[t]["last_day"]), key=lambda t: (-stats[t]["last_day"], t))
    check_order = list(dict.fromkeys(last_day + wanted + ranked))

    remembered = load_json(WIKI_MAP_PATH, {})
    overrides = load_json(WIKI_OVERRIDES_PATH, {})
    checks_before = load_json(WIKI_CHECKS_PATH, {})
    checks = {title: dict(entry) for title, entry in checks_before.items() if isinstance(entry, dict)}
    resolved = dict(remembered)
    rows, started = [], time.monotonic()
    used_articles = {}

    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        update_checks(session, check_order, resolved, overrides, checks, started)

        end = now.date() - timedelta(days=1)  # yesterday: today is incomplete
        start = end - timedelta(days=WINDOW_DAYS - 1)
        for title in wanted:
            row = {"title": title, "mentions": stats[title]["mentions"], "recent": stats[title]["recent"],
                   "prior": stats[title]["prior"], "sources": set(stats[title]["sources"]),
                   "youtube_views": stats[title]["youtube_views"], "youtube_videos": stats[title]["youtube_videos"],
                   "ebay_change_pct": ebay_change(prices.get(title)), "article": None, "url": None,
                   "views_30d": None, "trend_pct": None}
            article = usable_article(title, checks, resolved, overrides)
            if article and article in used_articles:
                # Two titles on one article would count its readers twice (a series page, say).
                print(f"  {title}: {article} already ranks as {used_articles[article]}; no Wikipedia signal")
                article = None
            if article and time.monotonic() - started <= TIME_BUDGET:
                try:
                    views = fetch_pageviews(session, article, start, end)
                    time.sleep(REQUEST_PAUSE)
                except (requests.RequestException, ValueError) as e:
                    print(f"  no pageviews for {article}: {e}")
                else:
                    used_articles[article] = title
                    recent, previous, change = split_trend(views)
                    row.update({"article": article, "url": f"https://en.wikipedia.org/wiki/{quote(article.replace(' ', '_'))}",
                                "views_30d": sum(views), "views_recent": recent, "views_previous": previous,
                                "trend_pct": change})
            rows.append(row)
            print(f"  {row['mentions']:>4} mentions  {row['youtube_views']:>9,} yt views  {title}")

    save_json_if_changed(WIKI_MAP_PATH, resolved, remembered)
    save_json_if_changed(WIKI_CHECKS_PATH, dict(sorted(checks.items())), checks_before)
    output = {
        "version": 2,
        "generated": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "window_days": WINDOW_DAYS,
        "trend_days": TREND_DAYS,
        "recent_days": RECENT_DAYS,
        "baseline_days": BASELINE_DAYS,
        "weights": SIGNAL_WEIGHTS,
        "youtube_views_seen": have_youtube,
        "games": blend(rows, have_youtube),
    }
    previous_file = load_json(DEMAND_PATH, {})
    # Only the timestamp changing isn't worth a commit.
    if previous_file.get("games") == output["games"] and previous_file.get("version") == 2:
        print("Demand unchanged; leaving demand.json untouched.")
        return
    DEMAND_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Ranked {len(rows)} games to {DEMAND_PATH}")


if __name__ == "__main__":
    build_demand()
