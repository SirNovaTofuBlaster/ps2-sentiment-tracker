"""Compares rare_reference_prices.json with the values in rare_games.json (offline, writes nothing).

Prints, for each reference point that names a US-scoped condition we also hold (loose or complete),
how far it is from the list's PriceCharting figure. Large gaps are leads for a human to look at,
not corrections: the articles are older, rounded and mostly copy PriceCharting themselves."""
import json
import sys

BASIS = {"loose": "loose", "complete": "cib"}


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def compare(reference, games, region="US"):
    held = {entry["title"]: entry for entry in games["lists"][region]}
    rows = []
    for item in reference["prices"]:
        entry = held.get(item["title"])
        key = BASIS.get(item["condition"])
        if not entry or not key or item["currency"] != "USD" or item["region"] not in (region, "?"):
            continue
        ours = (entry.get("value_usd") or {}).get(key)
        if ours:
            rows.append((item["title"], item["condition"], item["price"], ours, item["price"] / ours - 1, item["source"]))
    return sorted(rows, key=lambda row: -abs(row[4]))


if __name__ == "__main__":
    for title, condition, theirs, ours, gap, source in compare(load("rare_reference_prices.json"), load("rare_games.json")):
        print(f"{gap:+6.0%}  {title[:40]:40} {condition:9} article ${theirs:,.0f} vs ours ${ours:,.0f}  ({source})")
