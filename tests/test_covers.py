import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import build_covers  # noqa: E402
from ebay_prices import search_terms  # noqa: E402


class BuildCovers(unittest.TestCase):
    def test_keys_follow_the_price_key_and_regions_are_chosen(self):
        names = [
            "God Hand (USA).png", "God Hand (Europe) (En,Fr,De,Es,It).png", "God Hand (Japan).png",
            "Ratchet _ Clank (USA) (En,Fr,De,Es,It).png", "Getaway, The (Europe) (En,Fr,De,Es,It) (v1.03).png",
            "Kingdom Hearts II (USA) (Beta).png", "Kingdom Hearts II (USA).png",
            "Demo Only (USA) (Demo).png", "notes.txt",
        ]
        covers = build_covers.build(names)
        self.assertEqual(covers["god hand"], ["God Hand", " (USA)", " (Europe) (En,Fr,De,Es,It)"])
        self.assertEqual(covers["ratchet clank"][0], "Ratchet _ Clank")
        self.assertEqual(covers["getaway"], ["Getaway, The", " (Europe) (En,Fr,De,Es,It) (v1.03)", " (Europe) (En,Fr,De,Es,It) (v1.03)"])
        self.assertEqual(covers["kingdom hearts 2"][1], " (USA)", "a beta is never chosen over the release")
        self.assertNotIn("demo only", covers)
        self.assertEqual(len(covers), 4)

    def test_the_committed_index_is_well_formed_and_names_real_games(self):
        with open(os.path.join(ROOT, "covers.json"), encoding="utf-8") as handle:
            doc = json.load(handle)
        covers = doc["covers"]
        self.assertTrue(doc["base"].startswith("https://thumbnails.libretro.com/"))
        self.assertGreater(len(covers), 4000)
        for key, value in covers.items():
            self.assertRegex(key, r"^[a-z0-9]+( [a-z0-9]+)*$")
            self.assertEqual(len(value), 3, key)
            self.assertTrue(value[0] and (value[1] or value[2]), key)
        for title in ("God Hand", "Okami", "Silent Hill 2", "Kingdom Hearts II", "Getaway, The"):
            self.assertIn(search_terms(title)[0], covers, title)
        with open(os.path.join(ROOT, "data", "ps2_database.json"), encoding="utf-8") as handle:
            library = json.load(handle)
        have = sum(search_terms(title)[0] in covers for title in library)
        self.assertGreater(have / len(library), 0.7, "most library games have a cover")


if __name__ == "__main__":
    unittest.main()
