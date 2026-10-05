#!/usr/bin/env python3
"""Build a labelling draft for the matcher fixture corpus.

Reads the scraped feed (and any monthly archives), picks a spread of real
headlines weighted towards the cases the matcher finds hard, and writes
tests/fixtures/headlines.json pre-filled with whatever the matcher said at
scrape time.

You then correct the "expect" lists by hand and set "reviewed": true. This
script never calls the matcher, so it can't quietly agree with a bad label --
the stored match is a starting point, not an answer.

Re-running is safe: items you have already reviewed keep their labels, and
only new headlines are added.

    python tools/sample_fixtures.py                 # ~150 items
    python tools/sample_fixtures.py --count 200
    python tools/sample_fixtures.py --seed 7        # a different sample
    python tools/sample_fixtures.py --stats         # show what it drew from

Run it from the repository root.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "data" / "sentiment_feed.json"
ARCHIVE_DIR = ROOT / "data" / "archive"
OUT = ROOT / "tests" / "fixtures" / "headlines.json"

# How much of the sample each bucket gets. Deliberately lopsided: the easy
# cases are already right, so most of the budget goes to the ambiguous ones
# and to unmatched headlines that look like they should have matched.
QUOTAS = {
    "sequel": 0.22,     # matched a numbered title: "Hitman 2", "Black 2"
    "generic": 0.22,    # matched a short or common-word title: "Fahrenheit", "The Getaway"
    "near_miss": 0.25,  # no match, but the headline smells like PS2
    "matched": 0.16,    # matched something unremarkable
    "unmatched": 0.15,  # no match, no signal: the baseline
}

MAX_PER_GAME = 3          # stop one popular game eating a whole bucket
MIN_HEADLINE_CHARS = 20   # skip truncated or junk entries

ROMAN = re.compile(r"\b(?:III|VIII|VII|VI|IV|IX|XII|XI|II|X|V)\b")
NUMBERED = re.compile(r"\d")
PS2_HINT = re.compile(
    r"\b(ps2|ps\s?2|playstation\s?2|remaster(?:ed|s)?|remake|emulat\w*|hd\s+collection|"
    r"retro|classic(?:s)?|ps\s?plus|backwards?\s+compat\w*)\b",
    re.IGNORECASE,
)

# Title words that are ordinary English and so invite false positives.
COMMON_WORDS = {
    "the", "a", "an", "and", "of", "in", "on", "to", "for", "with", "black", "white",
    "red", "blue", "green", "gold", "silver", "war", "god", "king", "legend", "legends",
    "hero", "heroes", "fight", "fighter", "fighting", "night", "day", "time", "world",
    "life", "death", "dark", "light", "fire", "ice", "storm", "shadow", "shadows",
    "soul", "souls", "star", "stars", "sky", "land", "city", "state", "force", "forces",
    "club", "party", "max", "pro", "live", "online", "arena", "racing", "race", "rally",
    "run", "rush", "drive", "driver", "driven", "zone", "quest", "story", "stories",
    "destiny", "fate", "rising", "reborn", "origins", "evolution", "revolution",
}


def norm_headline(text: str) -> str:
    """Key for dedup: same story from three sites collapses to one entry."""
    return re.sub(r"[^a-z0-9 ]+", "", str(text or "").lower()).strip()


def read_json(path: Path):
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ! skipping {path.name}: {exc}", file=sys.stderr)
        return None


def games_of(item: dict) -> list[str]:
    """The matcher's stored verdict, from either the new or old field."""
    games = item.get("matched_games")
    if isinstance(games, list):
        found = [str(g).strip() for g in games if str(g or "").strip()]
        if found:
            return sorted(dict.fromkeys(found))
    single = item.get("matched_game")
    return [str(single).strip()] if str(single or "").strip() else []


def load_items() -> list[dict]:
    """Every scraped item we can find, newest file last so recent wins on dedup."""
    items: list[dict] = []

    feed = read_json(FEED)
    if isinstance(feed, dict) and isinstance(feed.get("items"), list):
        items.extend(i for i in feed["items"] if isinstance(i, dict))
        print(f"  {len(items):>5} items from data/sentiment_feed.json")
    elif feed is None:
        print("  ! data/sentiment_feed.json not found -- run the scraper first", file=sys.stderr)

    # Monthly archives use short keys (d/g/h/s/t/n/r/m); map them back.
    for path in sorted(ARCHIVE_DIR.glob("*.json")):
        archived = read_json(path)
        rows = archived.get("items") if isinstance(archived, dict) else archived
        if not isinstance(rows, list):
            continue
        before = len(items)
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append({
                "headline": row.get("h") or row.get("headline"),
                "source": row.get("s") or row.get("source"),
                "matched_game": row.get("g") or row.get("matched_game"),
                "matched_games": row.get("m") or row.get("matched_games"),
                "is_remaster_rumor": row.get("r", row.get("is_remaster_rumor")),
            })
        print(f"  {len(items) - before:>5} items from data/archive/{path.name}")

    return items


def bucket_of(headline: str, games: list[str]) -> str:
    if games:
        if any(NUMBERED.search(g) or ROMAN.search(g) for g in games):
            return "sequel"
        for game in games:
            words = [w for w in re.findall(r"[a-z0-9']+", game.lower())]
            if len(words) <= 2 or sum(w in COMMON_WORDS for w in words) >= max(1, len(words) - 1):
                return "generic"
        return "matched"
    return "near_miss" if PS2_HINT.search(headline) else "unmatched"


def build_pool(items: list[dict]) -> dict[str, list[dict]]:
    """Dedup, bucket, and cap how many entries any one game contributes."""
    seen: set[str] = set()
    pool: dict[str, list[dict]] = defaultdict(list)
    per_game: Counter = Counter()

    for item in items:
        headline = str(item.get("headline") or "").strip()
        if len(headline) < MIN_HEADLINE_CHARS:
            continue
        key = norm_headline(headline)
        if not key or key in seen:
            continue
        seen.add(key)

        games = games_of(item)
        if games and any(per_game[g] >= MAX_PER_GAME for g in games):
            continue
        for game in games:
            per_game[game] += 1

        pool[bucket_of(headline, games)].append({
            "headline": re.sub(r"\s+", " ", headline),
            "source": str(item.get("source") or "").strip(),
            "expect": games,
        })

    return pool


def draw(pool: dict[str, list[dict]], count: int, rng: random.Random) -> list[dict]:
    """Take each bucket's quota, then top up from whatever is left over."""
    picked: list[dict] = []
    leftovers: list[dict] = []

    for bucket, share in QUOTAS.items():
        available = pool.get(bucket, [])
        rng.shuffle(available)
        want = round(count * share)
        picked.extend(dict(row, bucket=bucket) for row in available[:want])
        leftovers.extend(dict(row, bucket=bucket) for row in available[want:])

    if len(picked) < count:
        rng.shuffle(leftovers)
        picked.extend(leftovers[: count - len(picked)])

    picked.sort(key=lambda row: (row["bucket"], row["headline"].lower()))
    return picked[:count]


def merge(existing: list[dict], fresh: list[dict]) -> tuple[list[dict], int]:
    """Keep every label already written; add only genuinely new headlines."""
    kept = {norm_headline(row.get("headline", "")): row for row in existing}
    added = 0
    for row in fresh:
        key = norm_headline(row["headline"])
        if key in kept:
            continue
        kept[key] = row
        added += 1

    merged = list(kept.values())
    merged.sort(key=lambda row: (row.get("bucket", "zz"), row.get("headline", "").lower()))
    for n, row in enumerate(merged, 1):
        row["id"] = f"f{n:03d}"
        row.setdefault("reviewed", False)
        # Field order, so the file reads the same way every time.
        for field in ("id", "headline", "source", "bucket", "expect", "reviewed", "note"):
            if field in row:
                row[field] = row.pop(field)
    return merged, added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=150, help="how many headlines to draw (default 150)")
    parser.add_argument("--seed", type=int, default=20261005, help="sampling seed; change it for a different draw")
    parser.add_argument("--stats", action="store_true", help="show the bucket sizes and exit")
    args = parser.parse_args()

    print("Reading scraped data:")
    items = load_items()
    if not items:
        print("\nNothing to sample. Run the scraper, or check you are in the repository root.", file=sys.stderr)
        return 1

    pool = build_pool(items)
    print(f"\n{sum(len(v) for v in pool.values())} usable headlines after dedup:")
    for bucket in QUOTAS:
        print(f"  {bucket:<10} {len(pool.get(bucket, [])):>5}")

    if args.stats:
        return 0

    thin = [b for b in QUOTAS if len(pool.get(b, [])) < round(args.count * QUOTAS[b])]
    if thin:
        print(f"\nNote: not enough items for {', '.join(thin)}; topping up from other buckets.")

    fresh = draw(pool, args.count, random.Random(args.seed))
    existing = read_json(OUT) or []
    if not isinstance(existing, list):
        print(f"\n{OUT} is not a JSON list; move it aside and re-run.", file=sys.stderr)
        return 1

    merged, added = merge(existing, fresh)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    reviewed = sum(1 for row in merged if row.get("reviewed"))
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print(f"  {len(merged)} headlines, {added} new, {reviewed} already reviewed")
    print(f"\nNext: open the file, fix each \"expect\" list, set \"reviewed\": true.")
    print("  expect: [] means no PS2 game is being discussed.")
    print("  Then: python -m unittest tests.test_matcher_fixtures -v")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
