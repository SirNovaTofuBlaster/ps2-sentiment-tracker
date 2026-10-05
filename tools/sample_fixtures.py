#!/usr/bin/env python3
"""Precision and recall for the title matcher, against hand-labelled headlines.

The corpus lives in tests/fixtures/headlines.json; build a draft of it with
tools/sample_fixtures.py and correct the labels by hand. Only entries marked
"reviewed": true are scored, so a half-labelled file still runs.

Scoring is per game mention, not per headline: a headline labelled
["God of War II", "Shadow of the Colossus"] where the matcher found only the
first counts as one hit and one miss. Both numbers matter and they pull in
opposite directions, which is the whole point of having them written down.

    python -m unittest tests.test_matcher_fixtures -v     # pass/fail
    python tests/test_matcher_fixtures.py                 # full report

Raise the floors below once you have a run you are happy with -- they exist
to catch a regression, so they should sit just under the current numbers.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "headlines.json"

# Regression floors. Start permissive, tighten after the first clean run.
MIN_PRECISION = 0.85   # of the games the matcher claimed, how many were right
MIN_RECALL = 0.70      # of the games actually discussed, how many it found
MIN_REVIEWED = 40      # below this the numbers are too noisy to gate on


# --------------------------------------------------------------------------
# Adapter. scraper.py's matcher API is the only thing this file assumes, and
# it is all assumed here. If an error below tells you the entry point could
# not be found, fix these two functions -- nothing else needs to change.
# --------------------------------------------------------------------------

MATCHER_FACTORIES = ("build_matcher", "make_matcher", "get_matcher", "title_matcher")
TITLE_SOURCES = ("load_titles", "load_games", "load_library", "ps2_titles",
                 "GAME_TITLES", "PS2_TITLES", "PS2_GAMES", "TITLES", "GAMES")
MATCH_METHODS = ("match", "find", "matches", "find_matches", "match_title",
                 "match_headline", "games_in", "detect", "__call__")


def build_matcher():
    """Return a ready-to-use TitleMatcher, however scraper.py exposes one."""
    import scraper

    for name in MATCHER_FACTORIES:
        factory = getattr(scraper, name, None)
        if callable(factory):
            return factory()

    Matcher = getattr(scraper, "TitleMatcher", None)
    if Matcher is None:
        raise RuntimeError(
            "scraper.py has no TitleMatcher and no matcher factory. "
            f"Looked for: TitleMatcher, {', '.join(MATCHER_FACTORIES)}."
        )

    try:
        return Matcher()
    except TypeError:
        pass

    for name in TITLE_SOURCES:
        obj = getattr(scraper, name, None)
        if obj is None:
            continue
        try:
            titles = obj() if callable(obj) else obj
            return Matcher(titles)
        except TypeError:
            continue

    raise RuntimeError(
        "Could not construct TitleMatcher. It takes arguments, and none of "
        f"{', '.join(TITLE_SOURCES)} fitted. Edit build_matcher() in this file."
    )


def match_games(matcher, headline: str) -> set[str]:
    """Normalise whatever the matcher returns into a set of title strings."""
    for name in MATCH_METHODS:
        method = getattr(matcher, name, None)
        if not callable(method):
            continue
        return _as_titles(method(headline))
    raise RuntimeError(
        "TitleMatcher exposes none of the expected lookup methods "
        f"({', '.join(MATCH_METHODS)}). Edit match_games() in this file."
    )


def _as_titles(result) -> set[str]:
    """Accept a string, a list, a list of (title, score) pairs, or a dict."""
    if result is None:
        return set()
    if isinstance(result, str):
        return {result.strip()} if result.strip() else set()
    if isinstance(result, dict):
        return {str(k).strip() for k in result if str(k).strip()}
    titles = set()
    for entry in result:
        if isinstance(entry, str):
            title = entry
        elif isinstance(entry, (tuple, list)) and entry:
            title = entry[0]
        elif isinstance(entry, dict):
            title = entry.get("title") or entry.get("game") or entry.get("name")
        else:
            title = entry
        title = str(title or "").strip()
        if title:
            titles.add(title)
    return titles


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def load_corpus() -> list[dict]:
    with FIXTURES.open(encoding="utf-8-sig") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        raise ValueError("headlines.json must be a JSON list")
    return [r for r in rows if isinstance(r, dict) and r.get("reviewed")]


def score(rows: list[dict]) -> dict:
    matcher = build_matcher()
    hits = misses = spurious = 0
    exact = 0
    false_positives: list[tuple[str, set[str]]] = []
    false_negatives: list[tuple[str, set[str]]] = []

    for row in rows:
        headline = str(row.get("headline", ""))
        expected = {str(g).strip() for g in row.get("expect", []) if str(g or "").strip()}
        found = match_games(matcher, headline)

        hits += len(expected & found)
        misses += len(expected - found)
        spurious += len(found - expected)
        if expected == found:
            exact += 1
        else:
            if found - expected:
                false_positives.append((headline, found - expected))
            if expected - found:
                false_negatives.append((headline, expected - found))

    claimed = hits + spurious
    actual = hits + misses
    return {
        "items": len(rows),
        "exact": exact,
        "precision": hits / claimed if claimed else 1.0,
        "recall": hits / actual if actual else 1.0,
        "hits": hits,
        "misses": misses,
        "spurious": spurious,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


class MatcherFixtureTests(unittest.TestCase):
    """Gates matcher changes on labelled real headlines, not on vibes."""

    @classmethod
    def setUpClass(cls):
        if not FIXTURES.exists():
            raise unittest.SkipTest(
                "tests/fixtures/headlines.json missing; build it with "
                "tools/sample_fixtures.py"
            )
        cls.rows = load_corpus()
        if len(cls.rows) < MIN_REVIEWED:
            raise unittest.SkipTest(
                f"only {len(cls.rows)} reviewed headlines; "
                f"label at least {MIN_REVIEWED} before gating on them"
            )
        cls.result = score(cls.rows)

    def test_precision_has_not_regressed(self):
        worst = "; ".join(f"{h[:60]!r} -> {sorted(g)}" for h, g in self.result["false_positives"][:5])
        self.assertGreaterEqual(
            self.result["precision"], MIN_PRECISION,
            f"precision {self.result['precision']:.3f} < {MIN_PRECISION} "
            f"({self.result['spurious']} wrong matches). Examples: {worst}"
        )

    def test_recall_has_not_regressed(self):
        worst = "; ".join(f"{h[:60]!r} missed {sorted(g)}" for h, g in self.result["false_negatives"][:5])
        self.assertGreaterEqual(
            self.result["recall"], MIN_RECALL,
            f"recall {self.result['recall']:.3f} < {MIN_RECALL} "
            f"({self.result['misses']} missed matches). Examples: {worst}"
        )

    def test_every_expected_title_is_in_the_library(self):
        """A label the matcher could never produce is a typo, not a miss."""
        matcher = build_matcher()
        known = set()
        for attr in ("fuzzy_titles", "titles", "aliases", "short", "variants"):
            value = getattr(matcher, attr, None)
            if isinstance(value, dict):
                known |= {str(k) for k in value} | {str(v) for v in value.values() if isinstance(v, str)}
            elif isinstance(value, (list, set, tuple)):
                known |= {str(v) for v in value if isinstance(v, str)}
        if not known:
            self.skipTest("cannot read the matcher's title list to check labels against")

        folded = {t.casefold() for t in known}
        unknown = sorted({
            game for row in self.rows for game in row.get("expect", [])
            if str(game).casefold() not in folded
        })
        self.assertFalse(
            unknown,
            "labels name titles the matcher does not know (typo, or a game "
            f"missing from the library): {unknown[:10]}"
        )


def report() -> int:
    if not FIXTURES.exists():
        print(f"No corpus yet. Build one:\n  python tools/sample_fixtures.py")
        return 1

    all_rows = json.loads(FIXTURES.read_text(encoding="utf-8-sig"))
    rows = load_corpus()
    print(f"Corpus: {len(all_rows)} headlines, {len(rows)} reviewed\n")
    if not rows:
        print('Nothing reviewed yet. Correct the "expect" lists and set "reviewed": true.')
        return 1

    result = score(rows)
    print(f"  precision   {result['precision']:.3f}   (floor {MIN_PRECISION})")
    print(f"  recall      {result['recall']:.3f}   (floor {MIN_RECALL})")
    print(f"  exact       {result['exact']}/{result['items']} headlines fully correct")
    print(f"  {result['hits']} right, {result['spurious']} wrong, {result['misses']} missed\n")

    if result["false_positives"]:
        print(f"False positives ({len(result['false_positives'])}):")
        for headline, games in result["false_positives"][:15]:
            print(f"  + {sorted(games)}  <- {headline[:88]}")
        print()
    if result["false_negatives"]:
        print(f"Missed matches ({len(result['false_negatives'])}):")
        for headline, games in result["false_negatives"][:15]:
            print(f"  - {sorted(games)}  <- {headline[:88]}")
        print()

    ok = result["precision"] >= MIN_PRECISION and result["recall"] >= MIN_RECALL
    print("PASS" if ok else "FAIL (below a floor)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(report())
