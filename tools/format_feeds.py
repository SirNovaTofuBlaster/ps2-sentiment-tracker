"""Rewrites feeds.json in the canonical format the tests expect.

Hand edits drift on indentation and brace placement, and
test_file_is_canonically_formatted compares the file byte for byte against
json.dumps(config, indent=2). Run this after editing feeds.json by hand."""

import json
from pathlib import Path

FEEDS_PATH = Path(__file__).parent.parent / "feeds.json"


def format_feeds():
    config = json.loads(FEEDS_PATH.read_text(encoding="utf-8-sig"))  # tolerate a BOM
    text = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if text == FEEDS_PATH.read_text(encoding="utf-8"):
        print(f"{FEEDS_PATH.name} is already canonical.")
        return
    FEEDS_PATH.write_text(text, encoding="utf-8")
    print(f"Reformatted {FEEDS_PATH.name} ({len(config['sources'])} sources).")


if __name__ == "__main__":
    format_feeds()
