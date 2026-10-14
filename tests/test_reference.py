import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import compare_reference  # noqa: E402


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
        return json.load(handle)


class ReferencePriceTests(unittest.TestCase):
    def setUp(self):
        self.reference = load("rare_reference_prices.json")
        self.games = load("rare_games.json")

    def test_every_point_is_complete_and_sourced(self):
        for item in self.reference["prices"]:
            self.assertIn(item["source"], self.reference["sources"], item)
            self.assertIn(item["currency"], ("USD", "GBP"), item)
            self.assertGreater(item["price"], 0, item)
            self.assertIn(item["region"], ("US", "PAL", "?"), item)
            self.assertLessEqual(len(item.get("note", "")), 80, "numbers and short labels only, no article text")
        for source in self.reference["sources"].values():
            self.assertTrue(source["url"].startswith("https://"))

    def test_titles_are_library_games_we_list_or_known_extras(self):
        listed = {e["title"] for lst in self.games["lists"].values() for e in lst}
        extras = {"God of War II (retailer/press kit)", "Star Wars: Bounty Hunter (Limited Edition Action Pack)",
                  "Xenosaga Episode III (Best Buy lenticular cover)", "Kingdom Hearts II"}
        for item in self.reference["prices"]:
            self.assertTrue(item["title"] in listed or item["title"] in extras, item["title"])

    def test_comparison_runs_and_finds_rows(self):
        rows = compare_reference.compare(self.reference, self.games)
        self.assertTrue(rows)
        self.assertTrue(all(len(row) == 6 for row in rows))


if __name__ == "__main__":
    unittest.main()
