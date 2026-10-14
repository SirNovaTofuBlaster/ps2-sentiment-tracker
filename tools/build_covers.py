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
    "lifeline voice action adventure": "life line",
    "midnight club": "midnight club street racing",
    "godfather collectors edition": "godfather",
    "godfather limited edition": "godfather",
    "cars": "disney pixar cars",
    "cowboy bebop": "cowboy bebop tsuioku no serenade",
    "socom": "socom u s navy seals",
    "hustle detroit streets kats story": "hustle the detroit streets",
    "uefa champions league": "uefa champions league 2006 2007",
    "wall e": "disney pixar wall e",
    "winning eleven 6": "world soccer winning eleven 6",
    "ultimate spider man limited edition": "ultimate spider man",
    "kirikou et les betes sauvages": "kirikou the wild beasts",
    "hack quarantine": "dot hack part 4 quarantine",
    "hack outbreak": "dot hack part 3 outbreak",
    "hack infection part 1": "dot hack part 1 infection",
    "hack mutation part 2": "dot hack part 2 mutation",
    "hack outbreak part 3": "dot hack part 3 outbreak",
    "hack quarantine part 4": "dot hack part 4 quarantine",
    "hanuman the boy warrior": "hanuman boy warrior",
    "giga wing generations": "gigawing generations",
    "atv off road": "atv offroad fury",
    "shin megami tensei devil summoner": "shin megami tensei devil summoner raidou kuzunoha vs the soulless army",
    "shin megami tensei devil summoner 2": "shin megami tensei devil summoner 2 raidou kuzunoha vs king abaddon",
}


# Pictures the maintainer supplied for games the collection has no file for (2026-10-14), kept small (240 px wide) in covers/.
# They are served from this site itself, so no third party is asked for them. A key here beats the collection's file.
LOCAL = {
    "final fantasy x": "covers/final-fantasy-x.jpg",
    "pro evolution soccer 2014": "covers/pro-evolution-soccer-2014.jpg",
    "world quiz": "covers/world-quiz.jpg",
    "deutsch rock pop": "covers/singstar-deutsch-rock-pop.jpg",
    "harry potter collection": "covers/harry-potter-collection.jpg",
    "grand theft auto complete collection": "covers/grand-theft-auto-complete-collection.jpg",
    "grand theft auto the trilogy": "covers/grand-theft-auto-the-trilogy.jpg",
    "silent hill collection": "covers/silent-hill-collection.jpg",
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
    # The Rarest page's titles are spelled by PriceCharting, not by the library (".hack//Quarantine", "Kirikou et les Bêtes Sauvages").
    try:
        rare = json.loads(Path("rare_games.json").read_text(encoding="utf-8-sig"))
        names += [g["title"] for games in rare.get("lists", {}).values() for g in games if isinstance(g.get("title"), str)]
    except (OSError, ValueError, AttributeError):
        pass
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
           "checked": date.today().isoformat(), "local": {key: path for key, path in LOCAL.items() if Path(path).is_file()},
           "covers": dict(sorted(covers.items()))}
    Path("covers.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(covers)} games with covers")


if __name__ == "__main__":
    main()
