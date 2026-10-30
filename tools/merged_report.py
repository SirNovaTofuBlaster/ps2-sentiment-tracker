"""Shows whether merging spellings of one game (ebay_prices.merge_duplicates) costs any copies.

    python tools/merged_report.py            # every merged-away spelling, worst first
    python tools/merged_report.py --all      # also the ones that agree

For each spelling that is no longer searched every cycle, `data/prices/audit.json` holds its own numbers from its
weekly look and the keeper's numbers from the same moment. A spelling is FLAGGED on a site when it listed at least
3 more copies than the keeper and at least half as many again: the keeper's search words are missing copies there.
The fix is to un-merge it (a `regional_names` rule for the keeper, or add the pair to the watchlist's pins).
Reads one file, asks nobody, writes nothing."""
import json
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "prices" / "audit.json"
MORE_COPIES, MORE_RATIO = 3, 1.5


def verdict(row):
    own, keeper = row.get("copies"), row.get("keeper_copies")
    if row.get("unmatched") or own is None or keeper is None:
        return "no figure"
    if own >= keeper + MORE_COPIES and own >= keeper * MORE_RATIO:
        return "FLAGGED"
    return "agrees"


def main(argv):
    if not PATH.exists():
        print("No data/prices/audit.json yet: the first weekly looks have not run.")
        return 0
    spellings = json.loads(PATH.read_text(encoding="utf-8")).get("spellings") or {}
    rows = []
    for title, entry in spellings.items():
        for site in ("US", "UK"):
            row = entry.get(site)
            if isinstance(row, dict):
                rows.append((verdict(row), title, entry.get("keeper"), site, row))
    order = {"FLAGGED": 0, "no figure": 1, "agrees": 2}
    rows.sort(key=lambda r: (order[r[0]], r[1], r[3]))
    counts = {kind: sum(1 for r in rows if r[0] == kind) for kind in order}
    waiting = sum(1 for e in spellings.values() for site in ("US", "UK") if site not in e)
    print(f"{len(spellings)} merged spellings: {counts['FLAGGED']} flagged, {counts['agrees']} agree, {counts['no figure']} without a figure; {waiting} site looks still waiting.")
    for kind, title, keeper, site, row in rows:
        if kind == "agrees" and "--all" not in argv:
            continue
        print(f"  {kind:9} {title} [{site}] {row.get('copies')} copies (median {row.get('median')}) vs {keeper}: {row.get('keeper_copies')} (median {row.get('keeper_median')}), {row.get('checked')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
