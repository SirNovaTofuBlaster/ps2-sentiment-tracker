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

# Regression floors, set from the first real measurement (2026-10-05):
# precision 0.562, recall 0.900 over 41 labelled headlines.
#
# They sit below that, not at it, because the corpus is still small: those 41
# headlines carry only ~10 real game mentions and 16 claims, so one row
# changing its mind moves recall by a tenth. These floors catch a change that
# makes the matcher clearly worse; they are not a precision instrument yet.
# Raise them as the corpus grows and as the known false positives get fixed.
MIN_PRECISION = 0.50   # of the games the matcher claimed, how many were right
MIN_RECALL = 0.80      # of the games actually discussed, how many it found
MIN_REVIEWED = 40      # below this the numbers are too noisy to gate on


# --------------------------------------------------------------------------
# Adapter. scraper.py's matcher API is the only thing this file assumes, and
# it is all assumed here. If an error below tells you the entry point could
# not be found, fix these two functions -- nothing else needs to change.
# --------------------------------------------------------------------------

import functools
import inspect
import re

# scraper.py builds its matcher as TitleMatcher(titles) inside run_scraper, from
# a module-level function that returns the title list. Rather than hard-code that
# function's name -- renaming it would silently break this file -- we read
# scraper.py and follow whatever run_scraper actually passes.
# scraper.py builds its library in load_ps2_titles(session): the online regional
# indexes, merged with the local cache, merged with FALLBACK_TITLES. We rebuild
# that from the cache and the fallback list and skip the network entirely -- the
# cache is what the fetched indexes are written to, so the only thing a fetch
# adds is titles published since the last scraper run.
#
# This is deliberately exact rather than clever. An earlier version searched the
# module for anything that looked like a title list and picked FALLBACK_TITLES,
# which scored every game outside that hand-written list as a missed match.
TITLE_SOURCES = ("read_cached_titles", "FALLBACK_TITLES")


def _library(scraper):
    cached = scraper.read_cached_titles()
    fallback = set(scraper.FALLBACK_TITLES)
    if not cached:
        raise RuntimeError(
            "data/ps2_database.json is empty or missing, so the only titles "
            "available are the fallback list. Run the scraper once to build "
            "the cache, or the numbers here mean nothing."
        )
    return sorted(cached | fallback), len(cached), len(fallback)


@functools.lru_cache(maxsize=1)
def build_matcher():
    """A TitleMatcher holding the same library the scraper matches against."""
    import scraper

    titles, cached, fallback = _library(scraper)
    build_matcher.source = (f"read_cached_titles() + FALLBACK_TITLES "
                            f"({cached} cached, {fallback} fallback, {len(titles)} merged)")
    return scraper.TitleMatcher(titles)


# Sources whose items the scraper treats as PS2 context, which lets ambiguous
# short titles ("Bully", "Black") match. A row may set "ps2_source" itself to
# override this; otherwise it is read from the source name, the same way the
# scraper's ps2 role does.
_PS2_SOURCE = re.compile(r"\bps2\b|\bpcsx2\b|playstation\s*2", re.I)


def is_ps2_source(row: dict) -> bool:
    if isinstance(row.get("ps2_source"), bool):
        return row["ps2_source"]
    return bool(_PS2_SOURCE.search(str(row.get("source", ""))))


def match_games(matcher, headline: str, ps2_source: bool = False) -> set[str]:
    """Every title the matcher finds, as the scraper would see them.

    match_all() is the right entry point: match() returns a single
    (title, score) pair and would be misread as two separate games.
    """
    method = getattr(matcher, "match_all", None)
    if not callable(method):
        raise RuntimeError("TitleMatcher has no match_all(); edit match_games() in this file.")
    return _as_titles(method(headline, ps2_source=ps2_source))


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
        found = match_games(matcher, headline, is_ps2_source(row))

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
        # Printed whether the tests pass or fail: a green run that tells you
        # nothing is how a matcher regression goes unnoticed.
        r = cls.result
        # Which title list was loaded, and every one that was considered. A
        # library far smaller than the scraper's turns every obscure game into
        # a fake missed match, so this line is checked before the scores are.
        print(f"\n  library: {getattr(build_matcher, 'source', '?')}")
        summary = getattr(build_matcher(), "summary", None)
        if callable(summary):
            print(f"  matcher: {summary()}")
        print(f"\n  matcher on {r['items']} labelled headlines:"
              f"  precision {r['precision']:.3f}  recall {r['recall']:.3f}"
              f"  ({r['hits']} right, {r['spurious']} wrong, {r['misses']} missed,"
              f" {r['exact']}/{r['items']} headlines exact)")
        for headline, games in r["false_positives"][:10]:
            print(f"    wrong:  {sorted(games)} <- {headline[:80]}")
        for headline, games in r["false_negatives"][:10]:
            print(f"    missed: {sorted(games)} <- {headline[:80]}")
        print(f"  floors: precision {MIN_PRECISION}, recall {MIN_RECALL}\n")

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
        for attr in ("fuzzy_titles", "titles"):
            known |= {t for t in getattr(matcher, attr, []) or [] if isinstance(t, str)}
        # short/variants map a normalised name to (title, needs_context);
        # aliases maps it straight to the title.
        for attr in ("short", "variants", "aliases"):
            for value in (getattr(matcher, attr, {}) or {}).values():
                title = value[0] if isinstance(value, (tuple, list)) and value else value
                if isinstance(title, str):
                    known.add(title)
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
