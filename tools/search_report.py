"""Prints where eBay searches went, from data/prices/searches.json (written by ebay_prices.py).

    python tools/search_report.py            # the latest day
    python tools/search_report.py 2026-10-20 # a given UTC day
    python tools/search_report.py --games 40 # more games
    python tools/search_report.py --level normal   # the most searched games of one level (days from 2026-10-26)

Reads one file, asks nobody, writes nothing."""
import json
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "prices" / "searches.json"


def main(argv):
    top, day = 25, None
    args = list(argv)
    if "--games" in args:
        at = args.index("--games")
        top = int(args[at + 1])
        del args[at:at + 2]
    want = None
    if "--level" in args:
        at = args.index("--level")
        want = args[at + 1]
        del args[at:at + 2]
    if args:
        day = args[0]
    try:
        days = json.loads(PATH.read_text(encoding="utf-8"))["days"]
    except (OSError, ValueError, KeyError):
        print("No search log yet (data/prices/searches.json).")
        return 1
    day = day or max(days)
    entry = days.get(day)
    if not entry:
        print(f"No log for {day}. Days kept: {', '.join(sorted(days))}")
        return 1
    print(f"{day}: {entry['total']} searches ({entry.get('other', 0)} not tied to a game)")
    print("\nBy level and site:")
    for level, sites in sorted(entry["levels"].items(), key=lambda pair: -sum(pair[1].values())):
        print(f"  {level:<11}{sum(sites.values()):>6}   " + "  ".join(f"{site} {n}" for site, n in sorted(sites.items())))
    if want:
        titles = (entry.get("level_games") or {}).get(want)
        if titles is None:
            print(f"\nNo per-level games for '{want}' on {day} (kept from 2026-10-26 on; levels: {', '.join(sorted(entry.get('level_games') or {})) or 'none yet'}).")
            return 1
        print(f"\nMost searched {want} games (top {top}):")
        for title, n in list(titles.items())[:top]:
            print(f"  {n:>5}  {title}")
        return 0
    print(f"\nMost searched games (top {top}):")
    for title, n in list(entry["games"].items())[:top]:
        print(f"  {n:>5}  {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
