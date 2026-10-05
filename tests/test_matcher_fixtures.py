#!/usr/bin/env python3
"""Precision and recall for the title matcher, against hand-labelled headlines.

The corpus lives in tests/fixtures/headlines.json; build a draft of it with
tools/sample_fixtures.py and correct the labels by hand. Only rows marked
"reviewed": true are scored, so a half-labelled file still runs.

Each row carries:

    headline     the text handed to TitleMatcher.match_all()
    ps2_source   whether the scraper would treat its source as PS2 context
    expect       the PS2 games the headline is really about ([] for none)
    accept       optional: other database names for those same games; claiming
                 one is neither a hit nor a mistake

Three rules decide a label, and they have to be applied the same way every time:
the headline only (never the body), a named non-PS2 platform wins ("... for
GameCube" is []), and a remake or re-release of a PS2 game counts as that game.

Scoring is per game mention, not per headline: a headline labelled
["God of War II", "Shadow of the Colossus"] where the matcher found only the
first is one hit and one miss. Titles are compared after scraper.normalise(), so
"Need for Speed Most Wanted" and "Need for Speed: Most Wanted" are one game.

    python -m unittest tests.test_matcher_fixtures -v     # pass/fail
    python tests/test_matcher_fixtures.py                 # the same report, standalone
"""

from __future__ import annotations

import functools
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scraper  # noqa: E402  (needs ROOT on the path first)

FIXTURES = ROOT / "tests" / "fixtures" / "headlines.json"

# Regression floors. They sit just under the measured numbers, so a matcher
# change that makes things clearly worse fails the build and one that makes
# them better is a reason to raise them. Measured 2026-10-05 on 268 reviewed
# headlines: precision 0.635, recall 0.948.
MIN_PRECISION = 0.60   # of the games the matcher claimed, how many were right
MIN_RECALL = 0.93      # of the games actually discussed, how many it found
MIN_REVIEWED = 40      # below this the numbers are too noisy to gate on
SHOWN = 80             # wrong / missed rows printed in the report


# --------------------------------------------------------------------------
# The same library and the same PS2 context the scraper uses
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def build_matcher():
    """A TitleMatcher holding the library run_scraper() matches against.

    load_ps2_titles() merges the online indexes, the local cache and
    FALLBACK_TITLES. The cache is what the fetched indexes are written to, so
    cache + fallback is the same library without touching the network.
    """
    cached = scraper.read_cached_titles()
    if not cached:
        raise RuntimeError(
            "data/ps2_database.json is empty or missing, so only the fallback "
            "list is available and every other game would score as a miss. "
            "Run the scraper once to build the cache."
        )
    titles = sorted(cached | set(scraper.FALLBACK_TITLES))
    build_matcher.source = f"{len(cached)} cached + {len(scraper.FALLBACK_TITLES)} fallback = {len(titles)} titles"
    return scraper.TitleMatcher(titles)


@functools.lru_cache(maxsize=1)
def ps2_source_names() -> frozenset[str]:
    """Display names of the sources run_scraper() counts as PS2 context: enabled
    sources with the ps2 role, named the way entry_source() names their items."""
    config = json.loads(scraper.FEEDS_PATH.read_text(encoding="utf-8-sig"))
    names = set()
    for src in config["sources"]:
        if not (src["enabled"] and src["role"] == scraper.PS2_ROLE):
            continue
        if src["type"] == "reddit":
            names.add(f"r/{src['subreddit']}".lower())
        elif src["type"] in scraper.SOURCE_PREFIX:
            names.add((scraper.SOURCE_PREFIX[src["type"]] + src["name"]).strip().lower())
    return frozenset(names)


def is_ps2_source(row: dict) -> bool:
    """The row's own recorded answer; rows sampled before it was recorded fall
    back to today's feeds.json roles."""
    if isinstance(row.get("ps2_source"), bool):
        return row["ps2_source"]
    return str(row.get("source", "")).strip().lower() in ps2_source_names()


def titles_of(row: dict, field: str) -> dict[str, str]:
    """{normalised title: title as written} for a row's expect or accept list."""
    return {scraper.normalise(t): t for t in row.get(field) or [] if str(t or "").strip()}


def claims_for(matcher, row: dict) -> dict[str, str]:
    """{normalised title: title} for everything the matcher claims in a headline."""
    found = matcher.match_all(str(row.get("headline", "")), ps2_source=is_ps2_source(row))
    return {scraper.normalise(title): title for title, _score, _method in found}


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
    hits = misses = spurious = exact = 0
    wrong, missed = [], []   # (headline, [titles])

    for row in rows:
        expected, accepted, found = titles_of(row, "expect"), titles_of(row, "accept"), claims_for(matcher, row)
        extra = found.keys() - expected.keys() - accepted.keys()
        absent = expected.keys() - found.keys()

        hits += len(expected.keys() & found.keys())
        misses += len(absent)
        spurious += len(extra)
        if not extra and not absent:
            exact += 1
        if extra:
            wrong.append((row["headline"], sorted(found[k] for k in extra)))
        if absent:
            missed.append((row["headline"], sorted(expected[k] for k in absent)))

    return {
        "items": len(rows), "exact": exact,
        "precision": hits / (hits + spurious) if hits + spurious else 1.0,
        "recall": hits / (hits + misses) if hits + misses else 1.0,
        "hits": hits, "misses": misses, "spurious": spurious,
        "wrong": wrong, "missed": missed,
    }


def print_report(result: dict) -> None:
    """Printed whether the tests pass or fail: a green run that says nothing is
    how a matcher regression goes unnoticed."""
    matcher = build_matcher()
    print(f"\n  library: {build_matcher.source}")
    print(f"  matcher: {matcher.summary()}")
    print(f"\n  matcher on {result['items']} labelled headlines:"
          f"  precision {result['precision']:.3f}  recall {result['recall']:.3f}"
          f"  ({result['hits']} right, {result['spurious']} wrong, {result['misses']} missed,"
          f" {result['exact']}/{result['items']} headlines exact)")
    # One title wrongly claimed across many headlines is a rule to fix; a long
    # tail of one-offs is not, and a flat list hides which is which.
    repeats = [(t, n) for t, n in Counter(t for _, ts in result["wrong"] for t in ts).most_common(12) if n > 1]
    if repeats:
        print("    worst offenders: " + ", ".join(f"{t} x{n}" for t, n in repeats))
    for headline, titles in result["wrong"][:SHOWN]:
        print(f"    wrong:  {titles} <- {headline[:80]}")
    if len(result["wrong"]) > SHOWN:
        print(f"    ... and {len(result['wrong']) - SHOWN} more")
    for headline, titles in result["missed"][:SHOWN]:
        print(f"    missed: {titles} <- {headline[:80]}")
    print(f"  floors: precision {MIN_PRECISION}, recall {MIN_RECALL}\n")


class MatcherFixtureTests(unittest.TestCase):
    """Gates matcher changes on labelled real headlines."""

    @classmethod
    def setUpClass(cls):
        if not FIXTURES.exists():
            raise unittest.SkipTest("tests/fixtures/headlines.json missing; build it with tools/sample_fixtures.py")
        cls.rows = load_corpus()
        if len(cls.rows) < MIN_REVIEWED:
            raise unittest.SkipTest(f"only {len(cls.rows)} reviewed headlines; label at least {MIN_REVIEWED}")
        cls.result = score(cls.rows)
        print_report(cls.result)

    def test_precision_has_not_regressed(self):
        examples = "; ".join(f"{h[:60]!r} -> {t}" for h, t in self.result["wrong"][:5])
        self.assertGreaterEqual(
            self.result["precision"], MIN_PRECISION,
            f"precision {self.result['precision']:.3f} < {MIN_PRECISION} "
            f"({self.result['spurious']} wrong matches). Examples: {examples}")

    def test_recall_has_not_regressed(self):
        examples = "; ".join(f"{h[:60]!r} missed {t}" for h, t in self.result["missed"][:5])
        self.assertGreaterEqual(
            self.result["recall"], MIN_RECALL,
            f"recall {self.result['recall']:.3f} < {MIN_RECALL} "
            f"({self.result['misses']} missed matches). Examples: {examples}")

    def test_every_label_names_a_title_in_the_library(self):
        """A label the matcher could never produce is a typo, not a miss."""
        matcher = build_matcher()
        known = set(matcher.fuzzy_norms) | set(matcher.short)
        known |= {scraper.normalise(title) for title, _ in matcher.variants.values()}
        known |= {scraper.normalise(title) for title in matcher.aliases.values()}
        unknown = sorted({
            title for row in self.rows for field in ("expect", "accept")
            for norm, title in titles_of(row, field).items() if norm not in known
        })
        self.assertFalse(unknown, f"labels name titles that are not in the library: {unknown[:10]}")


class MatcherRuleTests(unittest.TestCase):
    """One named case per matching rule, so a failure says which rule broke.

    They run against the real library because the rules are about real
    collisions in it: "Combat Ace" and "XIII" are database rows.
    """

    @classmethod
    def setUpClass(cls):
        try:
            cls.matcher = build_matcher()
        except RuntimeError as error:
            raise unittest.SkipTest(str(error))

    def claims(self, text, ps2_source=False):
        return sorted(title for title, _, _ in self.matcher.match_all(text, ps2_source=ps2_source))

    def test_word_order_is_part_of_a_title(self):
        # token_sort_ratio scored "ace combat" 100 against the title "Combat Ace".
        self.assertEqual(self.claims("Ace Combat 8 is the series' biggest launch on Steam"), [])
        self.assertEqual(self.claims("La voz de Snake anima a Konami a continuar la saga Metal Gear"), [])

    def test_one_game_is_claimed_once(self):
        self.assertEqual(self.claims("GOD OF WAR 2", ps2_source=True), ["God of War II"])
        # Two database spellings of one game: one claim, and the same name with or
        # without PS2 context, so the dashboard counts it as one game.
        with_context = self.claims("Let's Play Need For Speed Most Wanted 2005 (PS2) - Part 1")
        self.assertEqual(len(with_context), 1)
        self.assertEqual(with_context, self.claims("Need for Speed: Most Wanted is twenty years old"))
        self.assertEqual(self.claims("Guitar Hero Metallica PS2 Pickup"), ["Guitar Hero: Metallica"])

    def test_a_shorter_title_survives_when_it_also_stands_alone(self):
        self.assertEqual(self.claims("God of War and God of War II both hold up", ps2_source=True),
                         ["God of War", "God of War II"])

    def test_a_title_that_is_only_a_number_needs_ps2_context(self):
        self.assertEqual(self.claims("Nerial shuts down after 13 years"), [])
        self.assertEqual(self.claims("XIII on PS2 deserves another look"), ["XIII"])

    def test_a_word_with_a_digit_in_it_has_to_be_in_the_text(self):
        self.assertEqual(self.claims("Street Fighter 6 - Character Guide: Arjun | PS5 & PS4 Games"), [])
        self.assertEqual(self.claims("Street Fighter EX3 was a PS2 launch title"), ["Street Fighter EX3"])

    def test_inverted_articles_are_restored_before_a_subtitle_too(self):
        self.assertEqual(scraper.clean_title("Thing, The"), "The Thing")
        self.assertEqual(scraper.clean_title("Getaway, The: Black Monday"), "The Getaway: Black Monday")
        self.assertEqual(scraper.clean_title("Lord of the Rings, The: The Two Towers"),
                         "The Lord of the Rings: The Two Towers")
        self.assertEqual(scraper.clean_title("Shadow of the Colossus"), "Shadow of the Colossus")
        self.assertEqual(self.claims("The Getaway: Black Monday PS2 Gameplay HD"), ["The Getaway: Black Monday"])


def report() -> int:
    if not FIXTURES.exists():
        print("No corpus yet. Build one:\n  python tools/sample_fixtures.py")
        return 1
    total = len(json.loads(FIXTURES.read_text(encoding="utf-8-sig")))
    rows = load_corpus()
    print(f"Corpus: {total} headlines, {len(rows)} reviewed")
    if not rows:
        print('Nothing reviewed yet. Correct the "expect" lists and set "reviewed": true.')
        return 1
    result = score(rows)
    print_report(result)
    ok = result["precision"] >= MIN_PRECISION and result["recall"] >= MIN_RECALL
    print("PASS" if ok else "FAIL (below a floor)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(report())
