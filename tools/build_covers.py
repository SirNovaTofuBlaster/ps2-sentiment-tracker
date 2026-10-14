#!/usr/bin/env python3
"""Builds covers.json: which box-art picture the Libretro thumbnail collection has for each game.

The pictures are not copied here. The collection (github.com/libretro-thumbnails/Sony_-_PlayStation_2,
the box art RetroArch shows, served at thumbnails.libretro.com) is asked for by the visitor's own
browser; this file only says which file name belongs to which game, so the page can build the address.

Usage (reads nothing from the network):
    git clone --depth 1 --filter=blob:none --no-checkout https://github.com/libretro-thumbnails/Sony_-_PlayStation_2 /tmp/lt
    git -C /tmp/lt ls-tree -r --name-only HEAD Named_Boxarts | sed 's#^Named_Boxarts/##' | python tools/build_covers.py

Each game's key is the name ebay_prices.search_terms() gives its title, the same key the page's
priceKey() makes, so "Ratchet & Clank" (the collection writes "Ratchet _ Clank") and
"Getaway, The" find their files. A key holds [file name without its region, NTSC-U suffix, PAL suffix].
"""
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ebay_prices import search_terms  # noqa: E402  (standard library only)

BASE = "https://thumbnails.libretro.com/Sony%20-%20PlayStation%202/Named_Boxarts/"
BAD = re.compile(r"\b(Beta|Demo|Proto|Prototype|Sample|Unl|Pirate|Promo|Kiosk|Bonus|Disc [2-9])\b", re.I)
US_TAGS = ("USA", "Canada", "USA, Canada")
PAL_TAGS = ("Europe", "UK", "Australia", "World")


def split(name):
    """'Okami (USA)' -> ('Okami', ' (USA)'): the title is what comes before the first bracket."""
    match = re.match(r"^(.*?)((?:\s*\([^)]*\))+)$", name)
    return (match.group(1).strip(), match.group(2)) if match else (name, "")


def rank(suffix, wanted):
    """Lower is better: not a beta or demo, then the wanted region, then the shortest suffix."""
    first = (re.match(r"\s*\(([^)]*)\)", suffix) or [None, ""])[1]
    region = next((i for i, tag in enumerate(wanted) if first.split(",")[0].strip() == tag), len(wanted))
    return (bool(BAD.search(suffix)), region, len(suffix))


def build(names):
    games = {}
    for line in names:
        line = line.strip()
        if not line.endswith(".png"):
            continue
        title, suffix = split(line[:-4])
        key = search_terms(title.replace(" _ ", " and ").replace("_", " "))[0]
        if key:
            games.setdefault(key, {}).setdefault(title, []).append(suffix)
    out = {}
    for key, titles in games.items():
        # one spelling per key: the one with the most files (a game's many regional releases)
        title, suffixes = max(titles.items(), key=lambda item: (len(item[1]), -len(item[0])))
        us = min(suffixes, key=lambda s: rank(s, US_TAGS))
        pal = min(suffixes, key=lambda s: rank(s, PAL_TAGS))
        # any region will do as a last resort (India, Asia, Germany...): a cover in the wrong language beats none
        usable = lambda s: not BAD.search(s) and s.strip().startswith("(")
        if not usable(us) and not usable(pal):
            continue
        out[key] = [title, us if usable(us) else "", pal if usable(pal) else ""]
    return out


# Titles the collection files under another name (a Japanese or European title).
MANUAL = {
    "okami": "ookami",
    # The library's name for a game the collection files under its full or publisher's title (2026-10-14: the same game, found
    # from the 24-hour shelf, where "Metal Gear Solid 2" had a tile without a picture).
    "metal gear solid 2": "metal gear solid 2 sons of liberty",
    "splinter cell": "tom clancys splinter cell",
    "tomb raider anniversary": "lara croft tomb raider anniversary",
    "cars race o rama": "disney pixar cars race o rama",
    "disney pixars cars mater national": "disney pixar cars mater national championship",
    "spyro the eternal night": "legend of spyro the eternal night",
    "james bond 007 everything or nothing": "007 everything or nothing",
    "james bond 007 from russia with love": "007 from russia with love",
    "kings field 4 the ancient city": "kings field the ancient city",
    "over the hedge": "dreamworks over the hedge",
    "donald duck goin quackers": "disneys donald duck goin quackers",
    "eyetoy": "eyetoy play",
    "pimp my ride": "mtv pimp my ride",
    "dead or alive 2 hardcore": "dead or alive 2",
    "arena football ea sports": "arena football",
    "shin megami tensei devil summoner": "shin megami tensei devil summoner raidou kuzunoha vs the soulless army",
    "shin megami tensei devil summoner 2": "shin megami tensei devil summoner 2 raidou kuzunoha vs king abaddon",
}


def typo_of(key, spellings, unpadded):
    """A near-identical spelling (a typo in the library, "Vol." / "Volume", an added "The") with the same
    numbers. A difference of a one or two letter token ("max" / "x", "x2") is a different game, not a typo."""
    close = difflib.get_close_matches(key, spellings, n=1, cutoff=0.88)
    if not close or re.findall(r"\d+", close[0]) != re.findall(r"\d+", key):
        return None
    differing = set(key.split()) ^ set(close[0].split())
    if any(len(word) <= 2 and word not in ("a", "o", "de", "of", "in", "s") for word in differing):
        return None
    return unpadded[close[0]]


def add_aliases(covers):
    """Library and search names the collection spells a little differently get the same files:
    the same letters without spaces ("off road" / "offroad"), or the collection's longer title
    ("18 wheeler" / "18 wheeler american pro trucker") when exactly one of them starts with it."""
    names = []
    for path, field in (("data/ps2_database.json", None), ("search_extra_titles.json", "titles")):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        names += [t for t in (data.get(field, []) if field else data) if isinstance(t, str)]
    compact = {key.replace(" ", ""): key for key in covers}
    unpadded = {}
    for key in covers:
        unpadded.setdefault(re.sub(r"\b0+(\d)", r"\1", key), key)    # "ace combat 04" -> "ace combat 4"
    spellings = list(unpadded)
    for title in names:
        key = search_terms(title)[0]
        if not key or key in covers:
            continue
        target = MANUAL.get(key) or compact.get(key.replace(" ", "")) or unpadded.get(key)
        if not target:
            starts = [other for other in covers if other.startswith(key + " ")]
            target = starts[0] if len(starts) == 1 else None
        if not target:
            target = typo_of(key, spellings, unpadded)
        if target in covers:
            covers[key] = covers[target]
    return covers


def main():
    covers = add_aliases(build(sys.stdin))
    doc = {"what": "Which Libretro box-art file belongs to which game (key = priceKey()); the pictures are not stored here.",
           "source": "https://github.com/libretro-thumbnails/Sony_-_PlayStation_2", "base": BASE,
           "checked": date.today().isoformat(), "covers": dict(sorted(covers.items()))}
    Path("covers.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(covers)} games with covers")


if __name__ == "__main__":
    main()
