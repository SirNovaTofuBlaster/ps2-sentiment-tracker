"""Keeps a permanent record of every PS2 game mention.

scraper.py's snapshot is a rolling 14-day window (RETENTION_DAYS), so anything
older is dropped. This script reads that snapshot, keeps only the items where a
PS2 game was recognised, and appends them to monthly files under data/archive/.
Those files are never pruned.

Digital-only news (any game) is kept the same way under data/archive/digital/, with its link.

Rows are deduplicated on (game, source, headline), and for 4chan threads also on
when the thread was started, so running this often is harmless: a run only ever
adds mentions the archive doesn't already hold.

Keys are short because they repeat on every row:
  d  when the item was published       g  the matched PS2 game
  h  the headline                      s  the source name
  t  source type (news/reddit/...)     n  sentiment 0-100 (absent on 4chan rows: not scored)
  r  looked like remaster news         m  how the game was matched
  p  prices, once a price source exists (absent until then)
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "sentiment_feed.json"
ARCHIVE_DIR = DATA_DIR / "archive"
INDEX_PATH = ARCHIVE_DIR / "index.json"  # what months exist, and how big each one is
# News about digital-only releases and discs going away (the scraper's "is_digital_only"), any
# game, kept for good in a folder of its own so it never mixes with the PS2 mentions. Nothing is
# fetched for it: it is read from the same snapshot, so it costs no request to any site.
DIGITAL_DIR = ARCHIVE_DIR / "digital"
DIGITAL_INDEX_PATH = DIGITAL_DIR / "index.json"

MAX_HEADLINE = 160  # characters; longer headlines are cut at a word boundary
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M UTC"


def load_json(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def write_json(path, value):
    """One row per line: the file stays readable and its diffs stay small."""
    rows = ",\n  ".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in value)
    path.write_text(f"[\n  {rows}\n]\n" if rows else "[]\n", encoding="utf-8")


def shorten(text, limit=MAX_HEADLINE):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def month_of(timestamp):
    """"2026-10-04 11:30 UTC" -> "2026-10". None when the date can't be read."""
    try:
        return datetime.strptime(timestamp, TIMESTAMP_FORMAT).strftime("%Y-%m")
    except (TypeError, ValueError):
        return None


def row_key(row):
    """What makes a mention the same mention across runs. Not the link: podcast
    episodes share links, and the same story carries different links per outlet.

    A 4chan row is the exception. Its headline is written by the scraper from the board and
    the games named ("Thread on /vr/ naming Ico"), so two threads about one game read the
    same; when the thread was started is what tells them apart, and that never changes."""
    if row.get("t") == "4chan":
        return (row["g"], row["s"], row["h"], row.get("d"))
    return (row["g"], row["s"], row["h"])


def rows_from_item(item):
    """One row per game the item mentions, so 'everything about Yakuza' is a filter
    rather than a search through lists."""
    games = item.get("matched_games") or ([item["matched_game"]] if item.get("matched_game") else [])
    games = [g for g in games if isinstance(g, str) and g.strip()]
    if not games:
        return []
    month = month_of(item.get("timestamp"))
    if month is None:
        return []  # undated items can't be filed under a month
    base = {
        "d": item["timestamp"],
        "h": shorten(item.get("headline")),
        "s": str(item.get("source") or "")[:60],
        "t": item.get("source_type") or "news",
        # A real 0 is kept as 0; only a missing score is taken as neutral.
        "n": int(item["sentiment"]) if isinstance(item.get("sentiment"), (int, float)) else 50,
        "r": bool(item.get("is_remaster_rumor")),
    }
    if base["t"] == "4chan":
        del base["n"]  # these rows are not scored, and a made-up 50 would be kept for good
    method = item.get("match_method")
    rows = []
    for game in games:
        row = {"g": game, **base}
        if method:
            row["m"] = method
        rows.append((month, row))
    return rows


def digital_row(item):
    """(month, row) for a digital-only item, or None. Rows keep the link, so the story can be read
    again: d when published, h headline, s source, t source type, l link."""
    if item.get("is_digital_only") is not True:
        return None
    month = month_of(item.get("timestamp"))
    if month is None:
        return None
    row = {"d": item["timestamp"], "h": shorten(item.get("headline")), "s": str(item.get("source") or "")[:60],
           "t": item.get("source_type") or "news"}
    link = str(item.get("link") or "")
    if link.startswith(("https://", "http://")):
        row["l"] = link
    return month, row


def archive_digital(items):
    """Adds the snapshot's digital-only news to data/archive/digital/YYYY-MM.json. A story is the
    same story by source and headline. A kept story that is still in the snapshot but no longer
    flagged (the scraper flags the whole snapshot again with every change of its rules) is taken
    out again; one that has only left the snapshot stays for good. Returns rows added + removed."""
    by_month, unflagged = {}, set()
    for item in items:
        found = digital_row(item)
        if found:
            by_month.setdefault(found[0], []).append(found[1])
        elif item.get("is_digital_only") is False:
            unflagged.add((str(item.get("source") or "")[:60], shorten(item.get("headline"))))
    months = set(by_month) | {path.stem for path in DIGITAL_DIR.glob("20??-??.json")} if DIGITAL_DIR.exists() else set(by_month)
    changed_total = 0
    for month in sorted(months):
        path = DIGITAL_DIR / f"{month}.json"
        existing = [r for r in load_json(path, []) if isinstance(r, dict)]
        kept = [r for r in existing if (r.get("s"), r.get("h")) not in unflagged]
        known = {(r.get("s"), r.get("h")) for r in kept}
        added = []
        for row in by_month.get(month, []):
            if (row["s"], row["h"]) not in known:
                known.add((row["s"], row["h"]))
                added.append(row)
        removed = len(existing) - len(kept)
        if not added and not removed:
            continue
        DIGITAL_DIR.mkdir(parents=True, exist_ok=True)
        merged = sorted(kept + added, key=lambda r: (r.get("d", ""), r.get("s", ""), r.get("h", "")))
        write_json(path, merged)
        changed_total += len(added) + removed
        print(f"  digital-only {month}: +{len(added)}" + (f", -{removed} no longer flagged" if removed else "")
              + f" ({len(merged)} total)")
    if not changed_total:
        return 0
    # Per month and per day, for the dashboard's count without fetching every month.
    months, days, total = [], Counter(), 0
    for path in sorted(DIGITAL_DIR.glob("20??-??.json")):
        rows = [r for r in load_json(path, []) if isinstance(r, dict)]
        total += len(rows)
        months.append({"month": path.stem, "stories": len(rows)})
        days.update(str(r.get("d", ""))[:10] for r in rows if r.get("d"))
    write_json_object(DIGITAL_INDEX_PATH, {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_stories": total, "months": months, "days": dict(sorted(days.items())),
    })
    print(f"Digital-only news: {total} stories kept in all.")
    return changed_total


def archive():
    snapshot = load_json(SNAPSHOT_PATH, {})
    items = [i for i in snapshot.get("items", []) if isinstance(i, dict)]
    if not items:
        print("No snapshot to archive.")
        return
    digital_changed = archive_digital(items)

    by_month = {}
    for item in items:
        for month, row in rows_from_item(item):
            by_month.setdefault(month, []).append(row)
    if not by_month:
        print("No PS2 game mentions in the snapshot." + (" (Digital-only news was archived.)" if digital_changed else ""))
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    added_total = 0
    for month, new_rows in sorted(by_month.items()):
        path = ARCHIVE_DIR / f"{month}.json"
        existing = load_json(path, [])
        known = {row_key(r) for r in existing if isinstance(r, dict) and {"g", "s", "h"} <= r.keys()}
        added = []
        for row in new_rows:
            key = row_key(row)
            if key in known:
                continue
            known.add(key)
            added.append(row)
        if not added:
            continue
        merged = [r for r in existing if isinstance(r, dict)] + added
        merged.sort(key=lambda r: (r.get("d", ""), r.get("g", "")))
        write_json(path, merged)
        added_total += len(added)
        print(f"  {month}: +{len(added)} ({len(merged)} total)")

    if not added_total:
        print("No new PS2 game mentions." if digital_changed else "Nothing new to archive.")
        return

    # A small index so the dashboard can see what exists without fetching every month.
    months = sorted(p.stem for p in ARCHIVE_DIR.glob("*.json") if p.name != INDEX_PATH.name)
    index = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), "months": []}
    grand_total = 0
    for month in months:
        rows = load_json(ARCHIVE_DIR / f"{month}.json", [])
        games = Counter(r.get("g") for r in rows if isinstance(r, dict) and r.get("g"))
        grand_total += len(rows)
        index["months"].append({
            "month": month,
            "mentions": len(rows),
            "games": len(games),
            "top": [{"game": g, "mentions": n} for g, n in games.most_common(5)],
        })
    index["total_mentions"] = grand_total
    write_json_object(INDEX_PATH, index)
    print(f"Archived {added_total} new mentions; {grand_total} in total across {len(months)} month(s).")


def write_json_object(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    archive()
