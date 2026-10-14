#!/usr/bin/env python3
"""Builds genres.json: a genre for each PS2 game, from the Libretro database's own record of the console.

The Libretro database (github.com/libretro/libretro-database, rdb/Sony - PlayStation 2.rdb) lists every disc image
with, for about a third of them, a genre. It is a binary MessagePack file; this tool reads it with the small decoder
below (no packages) and keeps, for each game, the most common genre among its releases, folded into a dozen buckets
(`BUCKETS`). The result is only used by the dashboard's Library page to group games; a game with no genre is "Other".

Usage (reads nothing from the network):
    git clone --depth 1 --filter=blob:none --no-checkout https://github.com/libretro/libretro-database /tmp/ldb
    git -C /tmp/ldb show "HEAD:rdb/Sony - PlayStation 2.rdb" > /tmp/ps2.rdb
    python tools/build_genres.py /tmp/ps2.rdb

A game's key is the name ebay_prices.search_terms() gives its title, the same key the page's priceKey() makes, and the
same spelling fixes as covers.json (`build_covers.add_aliases`) are applied, so "Metal Gear Solid 2" finds "Sons of Liberty".
"""
import collections
import json
import re
import struct
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ebay_prices import search_terms  # noqa: E402
import build_covers  # noqa: E402

# The database's genre (its first word group, before a " / ") -> the bucket the page shows.
BUCKETS = {
    "Action": "Action", "Platform": "Action", "Beat'em Up": "Fighting", "Fighting": "Fighting", "Wrestling": "Fighting", "Boxing": "Fighting",
    "Adventure": "Adventure", "Interactive Movie": "Adventure", "Visual Novel": "Adventure", "Survival Horror": "Horror",
    "Role-playing (RPG)": "RPG", "Racing": "Racing", "Shooter": "Shooter", "Gun": "Shooter",
    "Simulation": "Simulation", "Flight Simulator": "Simulation", "Strategy": "Strategy",
    "Sports": "Sports", "Tennis": "Sports", "Football": "Sports", "Basketball": "Sports", "Hunting and Fishing": "Sports",
    "Puzzle": "Puzzle & party", "Quiz": "Puzzle & party", "Mini Games": "Puzzle & party", "Board": "Puzzle & party", "Card": "Puzzle & party",
    "Gambling": "Puzzle & party", "Mahjong": "Puzzle & party", "Chess": "Puzzle & party", "Pinball": "Puzzle & party", "Breakout": "Puzzle & party",
    "Educational": "Puzzle & party", "Party": "Puzzle & party",
    "Music": "Music & dance", "Dancing": "Music & dance", "Sing": "Music & dance", "Rhythm": "Music & dance",
}
ORDER = ["Action", "Adventure", "Fighting", "Horror", "Puzzle & party", "Racing", "RPG", "Shooter", "Simulation", "Sports", "Strategy", "Music & dance", "Other"]


def parse_rdb(data):
    """The records of a Libretro .rdb file: a 16-byte header, then MessagePack maps until a nil."""
    pos = [16]

    def take(n):
        chunk = data[pos[0]:pos[0] + n]
        pos[0] += n
        return chunk

    def value():
        b = data[pos[0]]
        pos[0] += 1
        if b <= 0x7F:
            return b
        if 0x80 <= b <= 0x8F:
            return mapping(b & 15)
        if 0x90 <= b <= 0x9F:
            return [value() for _ in range(b & 15)]
        if 0xA0 <= b <= 0xBF:
            return take(b & 31).decode("utf-8", "replace")
        if b == 0xC0:
            return None
        if b in (0xC2, 0xC3):
            return b == 0xC3
        if b in (0xC4, 0xD9):
            raw = take(take(1)[0])
            return raw.decode("utf-8", "replace") if b == 0xD9 else raw
        if b in (0xC5, 0xDA):
            raw = take(struct.unpack(">H", take(2))[0])
            return raw.decode("utf-8", "replace") if b == 0xDA else raw
        if b == 0xCC:
            return take(1)[0]
        if b == 0xCD:
            return struct.unpack(">H", take(2))[0]
        if b == 0xCE:
            return struct.unpack(">I", take(4))[0]
        if b == 0xCF:
            return struct.unpack(">Q", take(8))[0]
        if b == 0xDE:
            return mapping(struct.unpack(">H", take(2))[0])
        raise ValueError(f"unsupported MessagePack byte {b:#x} at {pos[0]}")

    def mapping(n):
        out = {}
        for _ in range(n):
            key = value()
            out[key] = value()
        return out

    records = []
    while pos[0] < len(data) and data[pos[0]] != 0xC0:
        records.append(value())
    return records


# Where the database has no genre (about two games in three do not), the title is read for words that give it away. These are
# rules of thumb, not data: a game they get wrong is fixed by adding its key to FIXES. Checked in this order, first hit wins.
KEYWORDS = [
    ("Horror", r"\b(silent hill|resident evil|biohazard|project zero|fatal frame|forbidden siren|siren|haunting ground|rule of rose|obscure|clock tower|dead rising|cold fear|evil dead|stranger room|call of cthulhu|hellboy)\b"),
    ("Music & dance", r"\b(singstar|sing star|karaoke|dance dance revolution|ddr|dancing|dance|guitar hero|rock band|rock revolution|taiko|drum|beatmania|para para|groove|buzz\b.*music|rhythm|amplitude|frequency|singing|disney sing)\b"),
    ("Sports", r"\b(fifa|pro evolution soccer|winning eleven|pes \d|uefa|football|soccer|nba|nhl|nfl|madden|mlb|baseball|basketball|hockey|golf|tennis|rugby|cricket|snooker|pool|bowling|skate|skateboard|tony hawk|snowboard|ski|surf|wwe|wrestling|smackdown|boxing|fight night|ufc|nascar|olympic|athletics|fishing|bass|hunting|horse|polo|volleyball|tiger woods|world cup|euro 20|nba live|nba street|ncaa|espn|fight club)\b"),
    ("Racing", r"\b(racing|racer|rally|gran turismo|need for speed|burnout|midnight club|ridge racer|wipeout|motogp|moto gp|formula|f1|grand prix|drift|drifting|forza|driver|driving|kart|cars?\b|truck|atv|quad|offroad|off road|wrc|colin mcrae|tokyo xtreme|street racer|toca|dirt|speed|nitro|hot wheels|burnout|crash nitro|stuntman|test drive|gt legends|auto modellista|initial d|wangan|import tuner|juiced|need for)\b"),
    ("Fighting", r"\b(tekken|mortal kombat|street fighter|virtua fighter|soulcalibur|soul calibur|dead or alive|king of fighters|guilty gear|blazblue|fighter|fighting|budokai|battle|bushido blade|bloody roar|capcom vs|marvel vs|samurai showdown|fatal fury|darkstalkers|tournament|arcana heart|melty blood|dragon ball|naruto|bleach|one piece|jump|knockout kings|def jam|rumble|brawl|martial|vs\.?|versus)\b"),
    ("RPG", r"\b(final fantasy|dragon quest|tales of|persona|shin megami|megami tensei|kingdom hearts|xenosaga|star ocean|suikoden|dark cloud|dark chronicle|rogue galaxy|grandia|growlanser|valkyrie profile|wild arms|ar tonelico|atelier|disgaea|phantom brave|okage|ys\b|baldur|neverwinter|champions of norrath|everquest|rpg|odin sphere|legend of dragoon|breath of fire|digital devil|devil summoner|cardinal|fantasy|dungeon|quest|saga|monster hunter|hack\b|dot hack|\.hack|radiata|shadow hearts|lunar|arc the lad|tactics ogre|romancing|bahamut|magna carta|enchanted arms|gungnir|resonance|tenchu)\b"),
    ("Shooter", r"\b(call of duty|medal of honor|socom|timesplitters|time splitters|halo|battlefield|killzone|black|goldeneye|007|james bond|ghost recon|rainbow six|splinter cell|metal gear|syphon filter|spy hunter|shooter|shooting|gun|guns|sniper|commando|soldier|war|army|marine|wolfenstein|doom|quake|half life|unreal|red faction|conflict|delta force|operation|mercenaries|ghost|swat|crime|turok|area 51|bullet|jackie chan|robotech|armored core|ace combat|raiden|r-type|gradius|gunbird|thunder|strikers|dodonpachi|ikaruga|silpheed|1942|sky|zero wing|giga wing)\b"),
    ("Strategy", r"\b(strategy|tactics|civilization|age of empires|command and conquer|rts|total war|dynasty warriors tactics|romance of the three|nobunaga|sim city|simcity|railroad|tycoon|commandos|worms|advance wars|risk|kessen|battle realms|myth|rise of nations)\b"),
    ("Simulation", r"\b(simulator|simulation|sims|the sims|flight|farm|harvest moon|zoo|theme park|sim\b|gran turismo concept|train|rail|bus|airline|tycoon)\b"),
    ("Puzzle & party", r"\b(puzzle|puzzles|quiz|trivia|party|mahjong|shogi|chess|poker|casino|bingo|card|cards|board|monopoly|scrabble|pinball|mario party|buzz|eyetoy|family|minigame|mini game|tetris|bust a move|bubble|pac man|lumines|katamari|sudoku|crossword|who wants|millionaire|wheel of fortune|jeopardy|are you smarter|world quiz|kids|dora|spongebob|barbie|sesame|bob the builder|thomas|disney|pixar|shrek|cartoon)\b"),
    ("Adventure", r"\b(adventure|mystery|detective|sherlock|myst|syberia|broken sword|gabriel knight|phoenix wright|ace attorney|point and click|escape|ico|shadow of the colossus|okami|prince of persia|tomb raider|indiana jones|lara croft|uncharted|jak|ratchet|sly cooper|spyro|crash bandicoot|sonic|klonoa|rayman|psychonauts|mario|platform|hero|legend of|kuon|fahrenheit|indigo prophecy|beyond good|ghost master)\b"),
]
FIXES = {}


def by_keywords(key):
    for name, pattern in KEYWORDS:
        if re.search(pattern, key):
            return name
    return None


def bucket(genre):
    first = genre.split(" / ")[0].strip()
    return BUCKETS.get(first, "Other")


def build(records):
    votes = {}
    for record in records:
        genre, name = record.get("genre"), record.get("name")
        if not isinstance(genre, str) or not isinstance(name, str):
            continue
        title = re.sub(r"(\s*\([^)]*\))+$", "", name).replace(" _ ", " and ").replace("_", " ").strip()
        key = search_terms(title)[0]
        if key:
            votes.setdefault(key, collections.Counter())[bucket(genre)] += 1
    return {key: counter.most_common(1)[0][0] for key, counter in votes.items()}


def main():
    records = parse_rdb(Path(sys.argv[1]).read_bytes())
    genres = build_covers.add_aliases(build(records))
    from_data = len(genres)
    library = set()
    for path, field in (("data/ps2_database.json", None), ("search_extra_titles.json", "titles")):
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        library.update(search_terms(t)[0] for t in (data.get(field, []) if field else data) if isinstance(t, str))
    guessed = 0
    for key in sorted(library):
        if key and key not in genres and (guess := by_keywords(key)):
            genres[key] = guess
            guessed += 1
    genres.update(FIXES)
    print(f"{from_data} from the database, {guessed} from title words")
    names = [name for name in ORDER if name != "Other" and name in set(genres.values())]
    index = {name: i for i, name in enumerate(names)}
    doc = {"what": "A genre bucket for each game (key = priceKey()); 'names' is the list the numbers point into. Games with no genre are not listed.",
           "source": "https://github.com/libretro/libretro-database (rdb/Sony - PlayStation 2.rdb)", "checked": date.today().isoformat(),
           "names": names, "genres": {key: index[genre] for key, genre in sorted(genres.items()) if genre in index}}
    Path("genres.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(doc['genres'])} games in {len(names)} genres")


if __name__ == "__main__":
    main()
