"""rare_games.json notes: every note_sources entry is an https link and belongs to a note."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class RareNotesTests(unittest.TestCase):
    def test_note_sources_are_https_links_on_entries_with_a_note(self):
        data = json.loads((ROOT / "rare_games.json").read_text(encoding="utf-8"))
        seen = 0
        for region, entries in data["lists"].items():
            for entry in entries:
                links = entry.get("note_sources")
                if links is None:
                    continue
                seen += 1
                where = f"{region} {entry['title']}"
                self.assertTrue(entry.get("note"), f"{where}: sources without a note")
                self.assertTrue(links, f"{where}: empty note_sources")
                for url in links:
                    self.assertTrue(url.startswith("https://"), f"{where}: {url}")
        self.assertGreater(seen, 0)


if __name__ == "__main__":
    unittest.main()
