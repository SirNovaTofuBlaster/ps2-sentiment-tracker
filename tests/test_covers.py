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

    def test_near_spellings_and_odd_regions_are_found_but_different_games_are_not(self):
        covers = build_covers.build(["Cart Kings (India) (En,Hi).png", "Ace Combat 04 - Shattered Skies (USA).png",
                                     "Alien Hominid (USA).png", "Dance Dance Revolution X (USA).png"])
        self.assertEqual(covers["cart kings"][1], " (India) (En,Hi)", "any region beats no cover")
        self.assertIn("ace combat 04 shattered skies", covers)
        self.assertEqual(build_covers.typo_of("alien homind", ["alien hominid"], {"alien hominid": "alien hominid"}), "alien hominid")
        self.assertIsNone(build_covers.typo_of("dance dance revolution max", ["dance dance revolution x"], {"dance dance revolution x": "x"}))
        self.assertIsNone(build_covers.typo_of("ace combat 5", ["ace combat 4"], {"ace combat 4": "x"}), "other numbers are other games")

    def test_local_pictures_are_listed_small_and_present(self):
        with open(os.path.join(ROOT, "covers.json"), encoding="utf-8") as handle:
            doc = json.load(handle)
        self.assertEqual(doc["local"], build_covers.LOCAL)
        for key, path in doc["local"].items():
            self.assertRegex(path, r"^covers/[\w.-]+\.jpg$")
            full = os.path.join(ROOT, path)
            self.assertTrue(os.path.isfile(full), path)
            self.assertLess(os.path.getsize(full), 60000, "a small picture, not a scan")
            self.assertRegex(key, r"^[a-z0-9]+( [a-z0-9]+)*$")

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
        for title in ("Cart Kings", "Ace Combat 4: Shattered Skies", "Alien Homind", "God Hand", "Okami", "Silent Hill 2", "Kingdom Hearts II", "Getaway, The"):
            self.assertIn(search_terms(title)[0], covers, title)
        with open(os.path.join(ROOT, "data", "ps2_database.json"), encoding="utf-8") as handle:
            library = json.load(handle)
        have = sum(search_terms(title)[0] in covers for title in library)
        self.assertGreater(have / len(library), 0.8, "most library games have a cover")


class OneTilePerGame(unittest.TestCase):
    """covers.json["same"] folds the library's many spellings of one game into the spelling the Library page shows."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "covers.json"), encoding="utf-8") as handle:
            cls.doc = json.load(handle)
        cls.titles = build_covers.library_titles()

    def test_every_folded_spelling_is_a_library_name_and_points_at_one_that_stays(self):
        same = self.doc["same"]
        self.assertGreater(len(same), 300)
        for key, shown in same.items():
            self.assertIn(key, self.titles)
            self.assertIn(shown, self.titles)
            self.assertNotIn(shown, same, f"{key} -> {shown} -> another: the chain would leave a game with two tiles")

    def test_regional_names_publisher_prefixes_and_typos_meet_but_sequels_do_not(self):
        same = self.doc["same"]
        def shown(title):
            key = search_terms(title)[0]
            return same.get(key, key)
        self.assertEqual(shown("Hack: Part 1: Infection"), shown(".hack Infection Part 1"))
        self.assertEqual(shown("Club Football 2005: Arsenal"), shown("Arsenal FC: Club Football 2005"))
        self.assertEqual(shown("Alien Homind"), shown("Alien Hominid"))
        self.assertEqual(shown("FIFA Soccer 07"), shown("FIFA 07"))
        self.assertEqual(shown("PES 2008: Pro Evolution Soccer"), shown("Pro Evolution Soccer 2008"))
        self.assertEqual(shown("Mondiali FIFA 2002"), shown("FIFA World Cup 2002"))
        self.assertEqual(shown("Disney's Finding Nemo"), shown("Disney/Pixar Finding Nemo"))
        for a, b in (("Dark Angel: Vampire Apocalypse", "Dark Angel: James Cameron's"), ("EyeToy: Play", "EyeToy: Play Sports"),
                     ("Ratchet & Clank", "Ratchet & Clank 2: Going Commando"), ("Burnout 2", "Burnout 3"),
                     ("Ty the Tasmanian Tiger", "Ty the Tasmanian Tiger 2: Bush Rescue"), ("Jak and Daxter", "Jak II")):
            if search_terms(a)[0] in self.titles and search_terms(b)[0] in self.titles:
                self.assertNotEqual(shown(a), shown(b), f"{a} and {b} are different games")

    def test_the_hack_games_are_all_in_the_library_with_pictures(self):
        wanted = ["hack part 1 infection", "hack part 2 mutation", "hack part 3 outbreak", "hack part 4 quarantine",
                  "hack g u vol 1 rebirth", "hack g u vol 2 reminisce", "hack g u vol 3 redemption",
                  "hack g u vol 1 rebirth terminal disc", "hack g u terminal disc the end of the world", "hack fragment"]
        for key in wanted:
            self.assertIn(key, self.titles)
            self.assertIn(key, self.doc["covers"], key)


if __name__ == "__main__":
    unittest.main()
