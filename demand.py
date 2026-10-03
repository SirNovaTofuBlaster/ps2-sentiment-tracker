"""Builds a demand index for the PS2 games currently being discussed.

Runs separately from scraper.py and never touches it: reads the titles out of
data/sentiment_feed.json, looks each one up on Wikipedia (pageviews) and
optionally archive.org, and writes data/demand.json for the dashboard.

Every network step fails soft. A title that cannot be resolved confidently is
left out rather than given a wrong number, and a run that collects nothing
leaves the previous file untouched."""

import json
import os
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
WIKI_MAP_PATH = DATA_DIR / "wiki_titles.json"       # PS2 title -> resolved Wikipedia article
WIKI_OVERRIDES_PATH = ROOT / "wiki_overrides.json"  # hand-curated fixes, committed

USER_AGENT = "python:ps2-sentiment-tracker-demand:1.0 (+https://github.com/SirNovaTofuBlaster/ps2-sentiment-tracker)"
REQUEST_TIMEOUT = 20
WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
                 "/en.wikipedia/all-access/user/{article}/daily/{start}/{end}")
ARCHIVE_API = "https://archive.org/advancedsearch.php"

MAX_TITLES = 60          # most-mentioned games to rank; keeps the run short
WINDOW_DAYS = 28         # pageview history fetched per article
TREND_DAYS = 7           # last N days compared against the N before them
RESOLVE_THRESHOLD = 82   # fuzzy score an article title must reach to be trusted
REQUEST_PAUSE = 0.2      # seconds between API calls; well inside both services' limits
TIME_BUDGET = 480        # seconds; whatever is unresolved by then waits for the next run
ARCHIVE_ENABLED = False  # set True once you have looked at what archive.org returns

# How much each signal moves the blended score. Trend leads because raw
# pageviews only measure how famous a game already is.
WEIGHTS = {"trend": 0.45, "views": 0.25, "mentions": 0.25, "archive": 0.05}

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


def mention_counts():
    """{title: mentions} from the current snapshot, most mentioned first."""
    snapshot = load_json(SNAPSHOT_PATH, {})
    counts = {}
    for item in snapshot.get("items", []):
        if not isinstance(item, dict):
            continue
        # match_all() records every game an item mentions; fall back to the single field.
        titles = item.get("matched_games") or ([item["matched_game"]] if item.get("matched_game") else [])
        for title in titles:
            if isinstance(title, str) and title:
                counts[title] = counts.get(title, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


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


def fetch_archive_downloads(session, title):
    """Total downloads of archive.org items whose title matches. 0 on anything unexpected."""
    params = {
        "q": f'title:("{title}") AND mediatype:(texts OR software OR audio)',
        "fl[]": "downloads", "rows": 10, "page": 1, "output": "json",
    }
    response = session.get(ARCHIVE_API, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    docs = response.json().get("response", {}).get("docs", [])
    return sum(int(d.get("downloads", 0) or 0) for d in docs)


def split_trend(views):
    """(recent total, previous total, percent change) over the trend window."""
    if len(views) < TREND_DAYS * 2:
        return sum(views), 0, None
    recent = sum(views[-TREND_DAYS:])
    previous = sum(views[-TREND_DAYS * 2:-TREND_DAYS])
    if previous <= 0:
        return recent, previous, None
    return recent, previous, round((recent - previous) / previous * 100, 1)


def normalise(values):
    """Scales a {key: number} map onto 0-100 by its own maximum."""
    highest = max(values.values(), default=0)
    if highest <= 0:
        return {k: 0.0 for k in values}
    return {k: v / highest * 100 for k, v in values.items()}


def blend(rows):
    """Adds a 0-100 'demand' figure to each row. The weights are a judgement call,
    not a measurement: they are in WEIGHTS so they can be argued with."""
    views = normalise({r["title"]: r.get("views_30d") or 0 for r in rows})
    mentions = normalise({r["title"]: r.get("mentions") or 0 for r in rows})
    archive = normalise({r["title"]: r.get("archive_downloads") or 0 for r in rows})
    # A trend of +100% or more scores full marks; -50% or worse scores nothing.
    trend = {}
    for row in rows:
        change = row.get("trend_pct")
        trend[row["title"]] = 50.0 if change is None else max(0.0, min(100.0, (change + 50) / 1.5))
    for row in rows:
        title = row["title"]
        row["demand"] = round(
            WEIGHTS["trend"] * trend[title]
            + WEIGHTS["views"] * views[title]
            + WEIGHTS["mentions"] * mentions[title]
            + WEIGHTS["archive"] * archive[title], 1)
    rows.sort(key=lambda r: -r["demand"])
    return rows


def build_demand():
    DATA_DIR.mkdir(exist_ok=True)
    counts = mention_counts()
    if not counts:
        print("No matched games in the snapshot; nothing to rank.")
        return

    wanted = list(counts)[:MAX_TITLES]
    remembered = load_json(WIKI_MAP_PATH, {})
    overrides = load_json(WIKI_OVERRIDES_PATH, {})
    resolved = dict(remembered)
    rows, started = [], time.monotonic()

    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        end = datetime.now(timezone.utc).date() - timedelta(days=1)  # yesterday: today is incomplete
        start = end - timedelta(days=WINDOW_DAYS - 1)

        for title in wanted:
            if time.monotonic() - started > TIME_BUDGET:
                print(f"  time budget used up; {len(wanted) - len(rows)} titles left for next run")
                break

            article = overrides.get(title, resolved.get(title))
            if article is None and title not in resolved:
                try:
                    article = resolve_article(session, title)
                    resolved[title] = article  # remember misses too, so they aren't retried hourly
                    time.sleep(REQUEST_PAUSE)
                except (requests.RequestException, ValueError) as e:
                    print(f"  could not resolve {title}: {e}")
                    continue
            if not article:
                continue

            try:
                views = fetch_pageviews(session, article, start, end)
                time.sleep(REQUEST_PAUSE)
            except (requests.RequestException, ValueError) as e:
                print(f"  no pageviews for {article}: {e}")
                continue

            recent, previous, change = split_trend(views)
            row = {
                "title": title,
                "article": article,
                "url": f"https://en.wikipedia.org/wiki/{quote(article.replace(' ', '_'))}",
                "mentions": counts[title],
                "views_30d": sum(views),
                "views_recent": recent,
                "views_previous": previous,
                "trend_pct": change,
            }

            if ARCHIVE_ENABLED:
                try:
                    row["archive_downloads"] = fetch_archive_downloads(session, title)
                    time.sleep(REQUEST_PAUSE)
                except (requests.RequestException, ValueError) as e:
                    print(f"  archive.org lookup failed for {title}: {e}")

            rows.append(row)
            print(f"  {row['views_30d']:>8,} views  {change if change is not None else '--':>7}%  {title}")

    save_json_if_changed(WIKI_MAP_PATH, resolved, remembered)
    if not rows:
        print("Nothing collected; leaving demand.json untouched.")
        return

    output = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "window_days": WINDOW_DAYS,
        "trend_days": TREND_DAYS,
        "weights": WEIGHTS,
        "games": blend(rows),
    }
    previous_file = load_json(DEMAND_PATH, {})
    # Only the timestamp changing isn't worth a commit.
    if previous_file.get("games") == output["games"]:
        print("Demand unchanged; leaving demand.json untouched.")
        return
    DEMAND_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Ranked {len(rows)} games to {DEMAND_PATH}")


if __name__ == "__main__":
    build_demand()
