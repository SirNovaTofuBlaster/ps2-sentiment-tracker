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

# 2026-10-14, second pass (Library page): spellings the library has, written as the collection's key. Each pair was read by eye:
# a typo, a regional name, a publisher's name added or dropped, or the same game's other title. Sequels never share a picture.
MANUAL.update({
    "all stars baseball 2004": "all star baseball 2004",
    "aliens vs predator extinction": "aliens versus predator extinction",
    "athens 04": "athens 2004",
    "asterix obilex xxl kick buttix": "asterix obelix xxl kick buttix",
    "bvb 09 club football 2005 borussia dortmund": "club football 2005 borussia dortmund",
    "backyard baseball 2010": "backyard baseball 10",
    "barbie horse adventure": "barbie horse adventures riding camp",
    "batman 2 the rise of sin tsu": "batman rise of sin tzu",
    "blood omen 2 legend of kain": "blood omen 2 the legacy of kain series",
    "legacy of kain blood omen 2": "blood omen 2 the legacy of kain series",
    "brian lara cricket 2005": "brian lara international cricket 2005",
    "buzz jr jungle party": "buzz junior jungle party",
    "buzz jr robojam": "buzz junior robojam",
    "buzz junior robojam buzz junior jungle party": "buzz junior jungle party",
    "ct special forces fire for effect": "counter terrorist special forces fire for effect",
    "club football real madri 2005": "club football real madrid",
    "club football juventus 2003 2004 season": "club football juventus",
    "club football liverpool 2003 2004 season": "club football liverpool fc",
    "crash bandicoot twinsanity": "crash twinsanity",
    "crash bandicoot nitro kart": "crash bandicoot bakusou nitro kart",
    "def jam fight for new york": "def jam fight for ny",
    "delta force team sabre": "delta force dlack hawk down team sabre",
    "devil may cry 3 dantes awakening special edition": "devil may cry 3 dantes awakening",
    "disneys classics treasure planet": "disneys treasure planet",
    "disneys jungle book groove party": "walt disneys the jungle book groove party",
    "disneys jungle book rhythm groove": "walt disneys the jungle book rhythm n groove",
    "disneys meet the robinsons": "walt disney pictures presents meet the robinsons",
    "disneys stitch 926": "disneys stitch experiment 626",
    "dynasty warriors 4 extreme edition": "dynasty warriors 4 xtreme legends",
    "ea sports cricket 2004": "cricket 2004",
    "ea sports cricket 2005": "cricket 2005",
    "euro 2004": "uefa euro 2004",
    "ufea euro 2004": "uefa euro 2004",
    "eve of extinction": "e o e eve of extinction",
    "escape from monkey island 4": "escape from monkey island",
    "monkey island 4": "escape from monkey island",
    "eyetoy eyetoy play": "eyetoy play",
    "eyetoy disney move": "disney move",
    "fantastic 4 rise of silver surfer": "fantastic four rise of the silver surfer",
    "final night 2004": "fight night 2004",
    "final night round 2": "fight night round 2",
    "franklin a birthday surprise": "franklin the turtle a birthday surprise",
    "funkmaster flex digital hitz factory": "digital hitz factory",
    "guilty gear x2 reloaded": "guilty gear xx reload the midnight carnival",
    "harley davidson race to the rally": "harley davidson motorcycles race to the rally",
    "harry potter kammer d schreckens": "harry potter und die kammer des schreckens",
    "harry potter og fangen fra azkaban": "harry potter i wiezien azkabanu",
    "harry potter og hemmelighedernes kammer": "harry potter och hemligheternas kammare",
    "high heat baseball 2002": "high heat major league baseball 2002",
    "history channels civil war secret mission": "history civil war secret missions",
    "incredible hulk 2 ultimate destruction": "incredible hulk ultimate destruction",
    "incredibles rise of the underminers": "disney pixar the incredibles rise of the underminer",
    "jak daxter 2 renegade": "jak 2 renegade",
    "jak daxter 2": "jak 2 jak x daxter 2",
    "jeremy mcgrath supercross world 2002": "jeremy mcgrath supercross world",
    "judge dredd vs judge death": "judge dredd dredd vs death",
    "lego dome racers": "drome racers",
    "lego football mania": "football mania",
    "lemony snickets una serie disfortunati eventi": "lemony snicket una serie di sfortunati eventi",
    "mlb 04": "mlb 2004",
    "mtv music generator 3 this is the remix": "mtv music generator 3",
    "mx superfly featuring ricky carmichael": "mx 2002 featuring ricky carmichael",
    "mx unleashed migrated": "mx unleashed",
    "mary kate ashley sweet sixteen licensed to drive": "mary kate ashley sweet 16 licensed to drive",
    "monster trux off road edition": "monster trux extreme offroad edition",
    "nba street 3": "nba street v3",
    "nfl quarterback club 2002": "nfl qb club 2002",
    "nhra countdown to the championship 2007": "nhra drag racing countdown to the championship",
    "network adapter start up disc ver 2 5": "network adapter start up disc",
    "network adapter start up disc ver 3 0": "network adapter start up disc",
    "new york race": "nyr new york race",
    "p t o 4 pacific theater of operations 4": "p t o 4 pacific theater of operations",
    "pbr out of the chute": "pro bull riding out of the chute",
    "pippa funnell 2 ranch rescue": "pippa funnell ranch rescue",
    "playmobil hype the time quest": "hype the time quest",
    "premier manager 2003 2004": "premier manager 2003 04",
    "project zero 3 tormented": "project zero 3",
    "pryzm dark unicorn": "pryzm chapter one dark unicorn",
    "puzzle collection crosswords more": "puzzle challenge crosswords more",
    "r a d robot alchemic drive": "robot alchemic drive",
    "rtl ski jump 2005": "rtl skispringen 2005",
    "rtl ski jumping 2004": "rtl skispringen 2004",
    "rtl ski jumping 2006": "rtl skispringen 2006",
    "rtl ski jumping 2007": "rtl skispringen 2007",
    "ratchet clank 2 going commando": "ratchet clank going commando",
    "ratchet clank 3 up your arsenal": "ratchet clank up your arsenal",
    "ready 2 rumble round 2": "ready 2 rumble boxing round 2",
    "ricky ponting international cricket": "ricky ponting international cricket 2007",
    "riding spirits": "rs riding spirits",
    "rock university presents the naked brothers the videogame": "nickelodeon the naked brothers band the video game",
    "s l a i steel lancer arena international phantom crash": "s l a i steel lancer arena international",
    "score international baja 1000": "score international baja 1000 the official game",
    "scorpion king rise of an akkadian": "scorpion king rise of the akkadian",
    "scrabble interactive 2003 edition": "scrabble interactive",
    "seed war zone": "seed the warzone",
    "seed warzone": "seed the warzone",
    "shadow hearts 2 covenant": "shadow hearts covenant",
    "shadow man 2 the second coming": "shadow man 2econd coming",
    "shadow man second coming": "shadow man 2econd coming",
    "shaman king power of spirit": "shonen jumps shaman king power of spirit",
    "sims 2 pets": "sims 2 the pets",
    "singstar popworld events code": "singstar popworld",
    "sly racoon 2 band of thieves": "sly 2 band of thieves",
    "smash cars racing": "smash cars",
    "snow x racing": "sxr snow x racing",
    "spongebob squarepants the battle for bikini bottoms": "spongebob squarepants battle for bikini bottom",
    "spongebob squarepants friends untie": "nickelodeon spongebob squarepants friends unite",
    "spyro the dragon enter the dragonfly": "spyro enter the dragonfly",
    "star ocean 3 till the end of time": "star ocean till the end of time",
    "star ocean 3": "star ocean till the end of time",
    "surfing h30": "surfing h3o",
    "swat global strike force": "swat global strike team",
    "t m n t teenage mutant ninja turtles": "teenage mutant ninja turtles",
    "tak 2 the stuff of dreams": "nickelodeon tak 2 the staff of dreams",
    "tenchu 3 wrath of heaven": "tenchu wrath of heaven",
    "tenchu 4 fatal shadows": "tenchu fatal shadows",
    "terminator rise of the machines": "terminator 3 rise of the machines",
    "timesplitters 3 future perfect": "timesplitters future perfect",
    "tom clancys splinter cell 2 pandora tomorrow": "tom clancys splinter cell pandora tomorrow",
    "tom clancys splinter cell 3 chaos theory": "tom clancys splinter cell chaos theory",
    "tomb raider angel of darkness": "lara croft tomb raider the angel of darkness",
    "tomb raider legend": "lara croft tomb raider legend",
    "tomb raider legends": "lara croft tomb raider legend",
    "top trumps dogs dinosaurs": "top trumps adventures vol 2 dogs dinosaurs",
    "top trumps horror predators": "top trumps adventures vol 1 horror predators",
    "tour de france le centenary edition": "tour de france le 1903 2003 centenary edition",
    "trixie in toyland": "myth makers trixie in toyland",
    "ty the tasmanian tiger 3 night of the quinkan": "ty the tasmanian tiger night of the quinkan",
    "uefa champions league 2005": "uefa champions league 2004 2005",
    "unison dead or alive 2 hardcore": "dead or alive 2 hardcore",
    "usa racer": "us racer",
    "v8 supercars 2": "v8 supercars australia 2",
    "v8 supercars 3": "v8 supercars australia 3",
    "toca race driver 3 v8 supercars australia 3": "v8 supercars australia 3",
    "wwe smackdown 4 shut your mouth": "wwe smackdown shut your mouth",
    "wwii paratroopers": "combat elite wwii paratroopers",
    "warhammer 40k fire warrior": "warhammer 40 000 fire warrior",
    "fire warrior": "warhammer 40 000 fire warrior",
    "yazuka 2": "yakuza 2",
    "yazuka fury": "yakuza fury",
    "yourself fitness lifestyle": "yourself fitness",
    "yu gi oh the beginning of destiny": "yu gi oh gx the beginning of destiny",
    "ape escape million monkeys": "saru get you million monkeys",
    "life line voice action adventure": "lifeline voice action adventure",
    "lentraineur 5 saison 04 05": "entraineur 5 l saison 04 05",
    "lera glaciale 3 lalba dei dinosauri": "era glaciale 3 l lalba dei dinosauri",
    "namcollection namco 50th anniversary": "namco museum 50th anniversary",
    "psikyo shooting collection vol 1 strikers 1 2": "psikyo shooting collection vol 1 strikers 1945 i 2",
    "sakura taisen mysterious paris": "sakura taisen monogatari mysterious paris",
    "hannspree ten kate honda sbk world superbikes 07": "hannspree ten kate honda sbk superbike world championship",
    "gunbarl collection with time crisis": "gunvari collection time crisis",
    "fmx freestyle metalx": "fmx freestyle metal x",
    "fu un bakumatsu den": "fuuun bakumatsuden",
    "virtua quest aka virtua fighter cyber generation": "virtua fighter cyber generation",
    "tony hawks american wasteland collectors edition": "tony hawks american wasteland",
    "adventures of jimmy neutron attack of the twonkies": "nickelodeon jimmy neutron boy genius attack of the twonkies",
    "adventures of jimmy neutron boy genius attack of the twonkies": "nickelodeon jimmy neutron boy genius attack of the twonkies",
    "adventures of jimmy neutron boy genius jet fusion": "nickelodeon the adventures of jimmy neutron boy genius jet fusion",
    "jimmy neutron jet fusion": "nickelodeon the adventures of jimmy neutron boy genius jet fusion",
    "jimmy neutron attack of the twonkies": "nickelodeon jimmy neutron boy genius attack of the twonkies",
    "disney pixar buscando a nemo": "disney pixar findet nemo",
    # third pass: the collection files the game under a shorter or longer title than the library's
    "atv off road 2": "atv offroad fury 2",
    "aggressive inline skating": "aggressive inline",
    "ar tonelico": "ar tonelico melody of elemia",
    "asterix obelix xxl 2 mission las vegum": "asterix obelix xxl 2",
    "athens 2004 olympic summer games": "athens 2004",
    "backyard football 2008": "backyard football 08",
    "backyard football 2009": "backyard football 09",
    "battlestar galactica apostasy": "battlestar galactica",
    "champions of norrath realms of everquest": "champions of norrath",
    "corvette 50th anniversary": "corvette",
    "crescent suzuki racing superbikes super sidecars": "crescent suzuki racing",
    "cyclone circus power sail racing": "cyclone circus",
    "destroy all humans 2 make war not love": "destroy all humans 2",
    "espn winter x games snowboarding 2": "espn winter x games snowboarding 2002",
    "fifa world cup 2006": "fifa world cup germany 2006",
    "fifa world cup 06": "fifa world cup germany 2006",
    "fifa world cup germany 06": "fifa world cup germany 2006",
    "fifa 2008": "fifa 08",
    "fifa 2009": "fifa 09",
    "final fantasy 11 vanadiel collection 2008": "final fantasy 11 vanadiel collection",
    "flushed away": "dreamworks aardman flushed away",
    "forbidden siren viviendo la pesadilla": "forbidden siren",
    "freedom fighters the battle for liberty island": "freedom fighters",
    "garfield 2 tale of two kitties": "garfield 2",
    "ghosthunter hunter on the spectres": "ghosthunter",
    "gran turismo 3 a spec nissan 350z edition": "gran turismo 3 a spec",
    "grooverider slot car thunder": "grooverider",
    "italian job l a heist": "italian job",
    "larryboy the bad apple": "big ideas veggietales larryboy the bad apple",
    "marvel ultimate alliance special edition": "marvel ultimate alliance",
    "mercenaries playground of destruction": "mercenaries",
    "minority report": "minority report everybody runs",
    "monsterit oy": "disney pixar monsterit oy saeikkysaari",
    "motor mayhem": "vehicular combat league presents motor mayhem",
    "motor mayhem vehicular combat league": "vehicular combat league presents motor mayhem",
    "nba 06 featuring the life vol 1": "nba 06",
    "nightmare of druaga": "nightmare of druaga the fushigi no dungeon",
    "open season rebelles de la foret": "open season",
    "play it chess challenger": "chess challenger",
    "police madness": "london racer police madness",
    "primal civilization is only skin deep": "primal",
    "riding spirits 2": "rsii riding spirits",
    "run like hell hunt or be hunted": "run like hell",
    "shamus deep sea adventures": "seaworld adventure parks shamus deep sea adventures",
    "shreks carnival craze": "dreamworks shreks carnival craze party games",
    "shrek smash crash": "dreamworks shrek smash n crash racing",
    "shrek super slam": "dreamworks shrek superslam",
    "silent scope 2": "silent scope 2 dark silhouette",
    "ski alpin 2006": "ski racing 2006",
    "sly 3": "sly 3 honor among thieves",
    "spider man the movie": "spider man",
    "street hoops king of the court": "street hoops",
    "dog island": "artlist collection the dog island",
    "sopranos": "sopranos the road to respect",
    "torino 2006 the official game of the xx olympic winter games": "torino 2006",
    "victorious boxers": "hajime no ippo victorious boxers",
    "virtual on marz": "cyber troopers virtual on marz",
    "woody woodpecker escape from buzz buzzard park": "woody woodpecker",
    "xenosaga episode 2": "xenosaga episode 2 jenseits von gut und boese",
    "board games gallery 10 games": "board games gallery",
    "burnout revenge battle racing ignited": "burnout revenge",
    "champions return to arms aka champions of norrath 2": "champions return to arms",
    "disney th nk fast": "disney think fast",
    "eyetoy oosawagi ukkiiuki game tenkomori": "eyetoy saru eyetoy oosawagi ukkiuki game tenkomori",
    "eyetoy play 3 spytoy": "eyetoy play 3",
    "super robot taisen original generations": "super robot taisen og original generations",
    "tokyo bus guide 2": "superlite 2000 vol 41 tokyo bus guide 2",
    "x men wolverines revenge": "x2 wolverines revenge",
    "world soccer winning eleven 9 international": "world soccer winning eleven 9",
    "kunoichi shinobi": "kunoichi",
    "dora the explorer dora saves the mermaids": "nick jr dora the explorer dora saves the mermaids",
    "dora the explorer to the purple planet": "nick jr dora the explorer journey to the purple planet",
    "dora the explorer journey to the purple planet": "nick jr dora the explorer journey to the purple planet",
    "go diego go safari rescue": "nick jr go diego go safari rescue",
    "monster co lisola dello spavento": "disney pixar monsters co lisola dello spavento",
    "knights of the temple": "knights of the temple infernal crusade",
    "driver 3": "driv3r",
    "dark angel": "james camerons dark angel",
    "hack g u vol 1 rebirth terminal disc": "dot hack g u vol 1 rebirth terminal disc",
    "hack g u terminal disc the end of the world": "dot hack g u terminal disc the end of the world",
    "hack fragment": "dot hack fraegment",
    "nba live 2006": "nba live 06",

    "call of duty 2 big red one special edition": "call of duty 2 big red one",
    "ty the tasmanian tiger 3": "ty the tasmanian tiger night of the quinkan",
})


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
    "resident evil the essentials": "covers/resident-evil-the-essentials.jpg",
    "resident evil essentials": "covers/resident-evil-the-essentials.jpg",
    "yazuka": "covers/yazuka.jpg",
    # 2026-10-17, first batch (88 pictures; the maintainer named each file after its game):
    "1945 i 2 the arcade games": "covers/1945-i-ii-the-arcade-games.jpg",
    "4 fantastiques les": "covers/4-fantastiques-les.jpg",
    "4x4 evolution 2": "covers/4x4-evolution-ii.jpg",
    "4x4 evolution": "covers/4x4-evolution.jpg",
    "adibou les voleurs denergie": "covers/adibou-les-voleurs-d-energie.jpg",
    "agent collection": "covers/agent-collection.jpg",
    "alarm for cobra 11 autobahn": "covers/alarm-for-cobra-11-autobahn.jpg",
    "alex ferguson player manager 2002": "covers/alex-ferguson-player-manager-2002.jpg",
    "alien humanoid": "covers/alien-humanoid.jpg",
    "alone in the dark 4": "covers/alone-in-the-dark-4.jpg",
    "americas army rise of a soldier": "covers/america-s-army-rise-of-a-soldier.jpg",
    "amplitude p o d": "covers/amplitude-p-o-d.jpg",
    "army men real time strategy": "covers/army-men-real-time-strategy.jpg",
    "backyard wrestling there goes the neighborhood": "covers/backyard-wrestling-there-goes-the-neighborhood.jpg",
    "bakuso mountain bikers": "covers/bakuso-mountain-bikers.jpg",
    "baphomets curse the sleeping dragon": "covers/baphomet-s-curse-the-sleeping-dragon.jpg",
    "bass fishing duel sega sports": "covers/bass-fishing-duel-sega-sports.jpg",
    "beni no umi 2": "covers/beni-no-umi-2.jpg",
    "bob o construtor festival do divertimento": "covers/bob-o-construtor-festival-do-divertimento.jpg",
    "borussia dortmund club football saison 2003 2004": "covers/borussia-dortmund-club-football-saison-2003-2004.jpg",
    "bounty hunter seek destroy": "covers/bounty-hunter-seek-destroy.jpg",
    "burnout anthology": "covers/burnout-anthology.jpg",
    "csi 3 dimensions of murder": "covers/csi-3-dimensions-of-murder.jpg",
    "cabelas outdoor adventures 2006": "covers/cabela-s-outdoor-adventures-2006.jpg",
    "call of duty le jour de glorie": "covers/call-of-duty-le-jour-de-glorie.jpg",
    "call of duty legacy": "covers/call-of-duty-legacy.jpg",
    "chessmaster 9000": "covers/chessmaster-9000.jpg",
    "conan the dark axe": "covers/conan-the-dark-axe.jpg",
    "crash bandicoot action pack": "covers/crash-bandicoot-action-pack.jpg",
    "crash twinsanity spyro a heros tail": "covers/crash-twinsanity-spyro-a-hero-s-tail.jpg",
    "cubix showdown": "covers/cubix-showdown.jpg",
    "dj decks fx": "covers/dj-decks-fx.jpg",
    "dtm race driver 2 the ultimate racing simulator also just ultimate racing simulator": "covers/dtm-race-driver-2-the-ultimate-racing-simulator-also-just-ultimate-racing-simulator.jpg",
    "dance dance revolution max 2": "covers/dance-dance-revolution-max-2.jpg",
    "dance dance revolution max": "covers/dance-dance-revolution-max.jpg",
    "dancing stage fever megamix": "covers/dancing-stage-fever-megamix.jpg",
    "deadly skies 2": "covers/deadly-skies-ii.jpg",
    "devil may cry 5th anniversary collection": "covers/devil-may-cry-5th-anniversary-collection.jpg",
    "disneys donald duck phantomias platyrhynchos kineticus": "covers/disney-s-donald-duck-phantomias-platyrhynchos-kineticus.jpg",
    "disneys lilla kycklingen": "covers/disney-s-lilla-kycklingen.jpg",
    "disneys peter pan adventures in neverland": "covers/disney-s-peter-pan-adventures-in-neverland.jpg",
    "dragon ball z trilogy": "covers/dragon-ball-z-trilogy.jpg",
    "dragon quest v bride of the sky": "covers/dragon-quest-v-bride-of-the-sky.jpg",
    "dreamworks beesten bij de buren": "covers/dreamworks-beesten-bij-de-buren.jpg",
    "dreamworks madagascar 2 escape 2 africa": "covers/dreamworks-madagascar-2-escape-2-africa.jpg",
    "dynasty warriors tactics": "covers/dynasty-warriors-tactics.jpg",
    "esa foundation compilation set": "covers/esa-foundation-compilation-set.jpg",
    "espn nfl 2k4": "covers/espn-nfl-2k4.jpg",
    "espn nhl hockey 2k4": "covers/espn-nhl-hockey-2k4.jpg",
    "extreme g racing xg3": "covers/extreme-g-racing-xg3.jpg",
    "f1 06": "covers/f1-06.jpg",
    "f1 2000 championship edition": "covers/f1-2000-championship-edition.jpg",
    "fc bayern munich club football 2005": "covers/fc-bayern-munich-club-football-2005.jpg",
    "far east of eden": "covers/far-east-of-eden.jpg",
    "fast the furious tokyo drift": "covers/fast-and-the-furious-the-tokyo-drift.jpg",
    "fatman slim": "covers/fatman-slim.jpg",
    "final fantasy 11 wings of the goddess": "covers/final-fantasy-xi-wings-of-the-goddess.jpg",
    "final fantasy 11": "covers/final-fantasy-xi.jpg",
    "football manager 2004": "covers/football-manager-2004.jpg",
    "formula one 2004": "covers/formula-one-2004.jpg",
    "formula one 2005": "covers/formula-one-2005.jpg",
    "fussball manager 2005": "covers/fussball-manager-2005.jpg",
    "gaelic football 2005": "covers/gaelic-football-2005.jpg",
    "gallop racer": "covers/gallop-racer.jpg",
    "god of war 2 the colossus battle": "covers/god-of-war-ii-the-colossus-battle.jpg",
    "gran turismo concept nissan 350z edition": "covers/gran-turismo-concept-nissan-350z-edition.jpg",
    "gran turismo special edition 2004 toyota": "covers/gran-turismo-special-edition-2004-toyota.jpg",
    "grand theft auto double pack": "covers/grand-theft-auto-double-pack.jpg",
    "grand theft auto liberty city stories vice city stories": "covers/grand-theft-auto-liberty-city-stories-vice-city-stories.jpg",
    "gravity sucks": "covers/gravity-sucks.jpg",
    "groove rider slot car racing": "covers/groove-rider-slot-car-racing.jpg",
    "guitar hero guitar hero 2 dual pack": "covers/guitar-hero-guitar-hero-ii-dual-pack.jpg",
    "hdd utility disc ver 1 10": "covers/hdd-utility-disc-ver-1-10.jpg",
    "hamburg sv club football 2005": "covers/hamburg-sv-club-football-2005.jpg",
    "hamburger sv club football saison 2003 2004": "covers/hamburger-sv-club-football-saison-2003-2004.jpg",
    "heroes of the indianapolis 500": "covers/heroes-of-the-indianapolis-500.jpg",
    "hitman trilogy": "covers/hitman-trilogy.jpg",
    "hot shots golf 3 parappa the rapper 2": "covers/hot-shots-golf-3-parappa-the-rapper-2.jpg",
    "i fantastici quattro": "covers/i-fantastici-quattro.jpg",
    "innocent life harvest moon pure": "covers/innocent-life-harvest-moon-pure.jpg",
    "inter club football 2005": "covers/inter-club-football-2005.jpg",
    "international superstar soccer 2002": "covers/international-superstar-soccer-2002.jpg",
    "iron eagle max": "covers/iron-eagle-max.jpg",
    "jak daxter complete trilogy": "covers/jak-and-daxter-complete-trilogy.jpg",
    "james bond 007 from russia with love need for speed most wanted ssx world tour": "covers/james-bond-007-from-russia-with-love-need-for-speed-most-wanted-ssx-world-tour.jpg",
    "johnny bravo date o rama": "covers/johnny-bravo-date-o-rama.jpg",
    "four fantastiques les": "covers/four-fantastiques-les.jpg",
    "four fantasticos los": "covers/four-fantasticos-los.jpg",
    "donald duck phantomias platyrhynchos kineticus": "covers/disney-s-donald-duck-phantomias-platyrhynchos-kineticus.jpg",
    "jak daxter trilogy": "covers/jak-and-daxter-complete-trilogy.jpg",
    # 2026-10-18, second batch (104 pictures; each file named after its game):
    "kiki kai kai": "covers/kiki-kai-kai.jpg",
    "killzone public beta v1 0": "covers/killzone-public-beta-v1-0.jpg",
    "king of fighters 2002 2003": "covers/king-of-fighters-2002-and-2003.jpg",
    "konami preview disc": "covers/konami-preview-disc.jpg",
    "le monde des bleus 2003": "covers/le-monde-des-bleus-2003.jpg",
    "lemony snicket schauriger schlamassel": "covers/lemony-snicket-schauriger-schlamassel.jpg",
    "les chevaliers de baphomet": "covers/les-chevaliers-de-baphomet.jpg",
    "london racer world challenge": "covers/london-racer-world-challenge.jpg",
    "m m s adventure": "covers/m-and-m-s-adventure.jpg",
    "mlb 2k6": "covers/mlb-2k6.jpg",
    "madden nfl 2006": "covers/madden-nfl-2006.jpg",
    "manchester united manager 2005": "covers/manchester-united-manager-2005.jpg",
    "mashed": "covers/mashed.jpg",
    "medal of honor collection": "covers/medal-of-honor-collection.jpg",
    "medical engineering joint entrance quiz": "covers/medical-and-engineering-joint-entrance-quiz.jpg",
    "melbourne cup challenge": "covers/melbourne-cup-challenge.jpg",
    "metal gear solid the essential collection": "covers/metal-gear-solid-the-essential-collection.jpg",
    "monde des bleus 2004 le nouvelle generation": "covers/monde-des-bleus-2004-le-nouvelle-generation.jpg",
    "monster rancher 5": "covers/monster-rancher-5.jpg",
    "monster trux extreme": "covers/monster-trux-extreme.jpg",
    "monsterspass": "covers/monsterspass.jpg",
    "monstros e companhia ilha assustadora": "covers/monstros-e-companhia-ilha-assustadora.jpg",
    "mortal kombat kollection": "covers/mortal-kombat-kollection.jpg",
    "mr bean": "covers/mr-bean.jpg",
    "nba 2001": "covers/nba-2001.jpg",
    "nba 2k4": "covers/nba-2k4.jpg",
    "nba jam 2004": "covers/nba-jam-2004.jpg",
    "ncaa basketball 2k3 sega sports": "covers/ncaa-basketball-2k3-sega-sports.jpg",
    "ncaa football 2006": "covers/ncaa-football-2006.jpg",
    "ngt next generation tennis": "covers/ngt-next-generation-tennis.jpg",
    "nrl rugby league 2": "covers/nrl-rugby-league-2.jpg",
    "nrl rugby league": "covers/nrl-rugby-league.jpg",
    "namco classic fighter collection": "covers/namco-classic-fighter-collection.jpg",
    "naruto ultimate collection": "covers/naruto-ultimate-collection.jpg",
    "need for speed collectors series": "covers/need-for-speed-collectors-series.jpg",
    "next generation tennis 2003": "covers/next-generation-tennis-2003.jpg",
    "official review of the 2000 fia formula 1 world championship": "covers/official-review-of-the-2000-fia-formula-1-world-championship.jpg",
    "om droit au bit club football 2005": "covers/om-droit-au-bit-club-football-2005.jpg",
    "onimusha essentials": "covers/onimusha-essentials.jpg",
    "online start up disc 4 0": "covers/online-start-up-disc-4-0.jpg",
    "pac man power pack": "covers/pac-man-power-pack.jpg",
    "pajeczyna charlotty": "covers/pajeczyna-charlotty.jpg",
    "paris dakar 2": "covers/paris-dakar-2.jpg",
    "peanuts all star": "covers/peanuts-all-star.jpg",
    "peter pan legenden om onskeoen": "covers/peter-pan-legenden-om-onskeoen.jpg",
    "pinball hall of fame": "covers/pinball-hall-of-fame.jpg",
    "plan th3": "covers/plan-th3.jpg",
    "play it pinball": "covers/play-it-pinball.jpg",
    "polaroid pete": "covers/polaroid-pete.jpg",
    "ponkotsu roman daikatsugeki bumpy trot": "covers/ponkotsu-roman-daikatsugeki-bumpy-trot.jpg",
    "popolocrois the law of the moon": "covers/popolocrois-the-law-of-the-moon.jpg",
    "puzzle party 10 games": "covers/puzzle-party-10-games.jpg",
    "quantum of solice the game": "covers/quantum-of-solice-the-game.jpg",
    "rtl ski alpine 2005": "covers/rtl-ski-alpine-2005.jpg",
    "rapala pro bass fishing 2010": "covers/rapala-pro-bass-fishing-2010.jpg",
    "ratchet clank 2 locked loaded": "covers/ratchet-and-clank-2-locked-and-loaded.jpg",
    "red card football": "covers/red-card-football.jpg",
    "red card soccer 2003": "covers/red-card-soccer-2003.jpg",
    "roland garros virtual tour 06": "covers/roland-garros-virtual-tour-06.jpg",
    "roland garros virtual tour": "covers/roland-garros-virtual-tour.jpg",
    "rollercoaster tycoon the peeps": "covers/rollercoaster-tycoon-the-peeps.jpg",
    "rugby 2002": "covers/rugby-2002.jpg",
    "scee catalogue video 3 plus": "covers/scee-catalogue-video-3-plus.jpg",
    "scee catalogue video": "covers/scee-catalogue-video.jpg",
    "ssx snowboarding": "covers/ssx-snowboarding.jpg",
    "saint seiya le chevaliers du zodiaque hades": "covers/saint-seiya-le-chevaliers-du-zodiaque-hades.jpg",
    "salt lake city 2002 olympic winter games": "covers/salt-lake-city-2002-olympic-winter-games.jpg",
    "sea world shamus big adventure": "covers/sea-world-shamus-big-adventure.jpg",
    "sega superstars eyetoy bundle": "covers/sega-superstars-eyetoy-bundle.jpg",
    "sim chemist": "covers/sim-chemist.jpg",
    "sing star nrj music tour": "covers/sing-star-nrj-music-tour.jpg",
    "singstar african hits": "covers/singstar-african-hits.jpg",
    "singstar apres ski party 2": "covers/singstar-apres-ski-party-2.jpg",
    "singstar apres ski party": "covers/singstar-apres-ski-party.jpg",
    "singstar big dreams": "covers/singstar-big-dreams.jpg",
    "singstar chartbreaker": "covers/singstar-chartbreaker.jpg",
    "singstar die toten hosen": "covers/singstar-die-toten-hosen.jpg",
    "singstar disney songs": "covers/singstar-disney-songs.jpg",
    "singstar eska hits on time": "covers/singstar-eska-hits-on-time.jpg",
    "singstar finnishfavorites": "covers/singstar-finnishfavorites.jpg",
    "singstar finnishhits": "covers/singstar-finnishhits.jpg",
    "singstar finnishpop": "covers/singstar-finnishpop.jpg",
    "singstar finnishrock": "covers/singstar-finnishrock.jpg",
    "singstar football hits": "covers/singstar-football-hits.jpg",
    "singstar german rock pop": "covers/singstar-german-rock-pop.jpg",
    "singstar holiday party": "covers/singstar-holiday-party.jpg",
    "singstar italian party 2": "covers/singstar-italian-party-2.jpg",
    "singstar italian party": "covers/singstar-italian-party.jpg",
    "singstar italian singers": "covers/singstar-italian-singers.jpg",
    "singstar kent": "covers/singstar-kent.jpg",
    "singstar magical songs of disney": "covers/singstar-magical-songs-of-disney.jpg",
    "singstar mallorca party": "covers/singstar-mallorca-party.jpg",
    "singstar mecano": "covers/singstar-mecano.jpg",
    "singstar miliki": "covers/singstar-miliki.jpg",
    "singstar norsk pa norsk": "covers/singstar-norsk-pa-norsk.jpg",
    "singstar norske hits": "covers/singstar-norske-hits.jpg",
    "singstar norwegian hits": "covers/singstar-norwegian-hits.jpg",
    "singstar polish hits 2": "covers/singstar-polish-hits-2.jpg",
    "singstar polish hits": "covers/singstar-polish-hits.jpg",
    "singstar pop 2009": "covers/singstar-pop-2009.jpg",
    "singstar svenska hits schlager": "covers/singstar-svenska-hits-schlager.jpg",
    "singstar turkish party": "covers/singstar-turkish-party.jpg",
    "singstar the disney magic": "covers/singstar-and-the-disney-magic.jpg",
    # 2026-10-18, third batch (53 pictures; each file named after its game):
    "singstar pop hits 2": "covers/singstar-pop-hits-2.jpg",
    "singstar pop hits 3": "covers/singstar-pop-hits-3.jpg",
    "singstar pop hits 4": "covers/singstar-pop-hits-4.jpg",
    "singstar pop hits top 40": "covers/singstar-pop-hits-top-40.jpg",
    "singstar schlager": "covers/singstar-schlager.jpg",
    "singstar studio 100": "covers/singstar-studio-100.jpg",
    "singstar swedish stars": "covers/singstar-swedish-stars.jpg",
    "singstar the golden age of spanish pop": "covers/singstar-the-golden-age-of-spanish-pop.jpg",
    "singstar the wiggles": "covers/singstar-the-wiggles.jpg",
    "singstar vasco": "covers/singstar-vasco.jpg",
    "singstar made in germany": "covers/singstar-made-in-germany.jpg",
    "skijumping 2006": "covers/skijumping-2006.jpg",
    "soccer slam sega sports": "covers/soccer-slam-sega-sports.jpg",
    "space race": "covers/space-race.jpg",
    "sphinx the shadow of set": "covers/sphinx-and-the-shadow-of-set.jpg",
    "spongebob happy squared pack": "covers/spongebob-happy-squared-pack.jpg",
    "starcraft ghost": "covers/starcraft-ghost.jpg",
    "strawberry shortcake adventures in the land of dreams": "covers/strawberry-shortcake-adventures-in-the-land-of-dreams.jpg",
    "street cricket champions 2": "covers/street-cricket-champions-2.jpg",
    "street cricket champions": "covers/street-cricket-champions.jpg",
    "super robot wars alpha 2nd": "covers/super-robot-wars-alpha-2nd.jpg",
    "super trucks racing 2": "covers/super-trucks-racing-2.jpg",
    "txr drift 2": "covers/txr-drift-2.jpg",
    "taiko no tatsujin appare sandaime": "covers/taiko-no-tatsujin-appare-sandaime.jpg",
    "taiko no tatsujin atsumare matsuri da yondaime": "covers/taiko-no-tatsujin-atsumare-matsuri-da-yondaime.jpg",
    "taiko no tatsujin doki shinkyoku darake no haru matsuri": "covers/taiko-no-tatsujin-doki-shinkyoku-darake-no-haru-matsuri.jpg",
    "tales of destiny": "covers/tales-of-destiny.jpg",
    "big sports quiz": "covers/the-big-sports-quiz.jpg",
    "great german football quiz": "covers/the-great-german-football-quiz.jpg",
    "this is football 5": "covers/this-is-football-5.jpg",
    "this is football": "covers/this-is-football.jpg",
    "tiger woods pga tour 2006": "covers/tiger-woods-pga-tour-2006.jpg",
    "transformers armada prelude to energon": "covers/transformers-armada-prelude-to-energon.jpg",
    "ufc sudden impact": "covers/ufc-sudden-impact.jpg",
    "ufc ultimate fighting championship throwdown": "covers/ufc-ultimate-fighting-championship-throwdown.jpg",
    "vans warped tour 01": "covers/vans-warped-tour-01.jpg",
    "velocity": "covers/velocity.jpg",
    "venus braves": "covers/venus-and-braves.jpg",
    "virtual racer jaques villeneuve": "covers/virtual-racer-jaques-villeneuve.jpg",
    "wrc 4 fia world rally championship": "covers/wrc-4-fia-world-rally-championship.jpg",
    "wwe smackdown vs raw superstar series": "covers/wwe-smackdown-vs-raw-superstar-series.jpg",
    "wacky races": "covers/wacky-races.jpg",
    "welcome to the world of online gaming for your playstation 2": "covers/welcome-to-the-world-of-online-gaming-for-your-playstation-2.jpg",
    "who wants to be a millionaire 2": "covers/who-wants-to-be-a-millionaire-2.jpg",
    "winback 2nd operation": "covers/winback-2nd-operation.jpg",
    "winter sports 2 the ultimate challenge": "covers/winter-sports-2-the-ultimate-challenge.jpg",
    "world poker tour 2k6": "covers/world-poker-tour-2k6.jpg",
    "world rally championship 3": "covers/world-rally-championship-3.jpg",
    "world rally championship 2 extreme": "covers/world-rally-championship-ii-extreme.jpg",
    "world superbikes 07": "covers/world-superbikes-07.jpg",
    "11 go": "covers/xi-go.jpg",
    "yoshitsune eiyuuden": "covers/yoshitsune-eiyuuden.jpg",
}


# Words that differ between the library's spelling and the collection's for one game: a publisher's name in front, "volume"
# for "vol", the same word run together. loose_key() drops them and ignores word order, so "Club Football 2005 Arsenal" and
# "Arsenal: Club Football 2005", or "Disney's Finding Nemo" and "Disney Pixar Finding Nemo", meet. Numbers are never dropped.
LOOSE_SUBS = {"volume": "vol", "fuer": "for", "offroad": "off road", "disneys": "disney", "pixars": "pixar", "astroboy": "astro boy",
              "airforce": "air force", "beatdown": "beat down", "jr": "junior", "pes": ""}
LOOSE_PREFIXES = ("james bond", "snk", "disney pixar", "walt disney pictures presents", "walt disney", "disney", "nickelodeon", "nick jr",
                  "dreamworks", "eyetoy", "rtl", "sega sports", "ea sports", "project", "jim hensons", "lara croft", "operative", "jet li", "shonen jumps")
# The same game under its American, European and translated names: whole phrases that mean the same.
LOOSE_PHRASES = (("fifa soccer", "fifa"), ("fifa football", "fifa"), ("fifa fussball weltmeisterschaft", "fifa world cup"),
                 ("mondiali fifa", "fifa world cup"), ("mundial fifa", "fifa world cup"), ("coupe du monde fifa", "fifa world cup"))
# What a title can end with (or carry) without being another game.
LOOSE_TRAILING = re.compile(r"\s+(sega sports|the game|the video game|video game|videogame|game)$")
LOOSE_STOP = {"the", "of", "and", "a", "in", "de", "to", "le", "la", "les", "der", "die", "das", "el", "fc", "vol"}


def loose_key(key):
    key = LOOSE_TRAILING.sub("", key)
    for phrase, plain in LOOSE_PHRASES:
        key = key.replace(phrase, plain)
    key = re.sub(r"\b0+(\d)", r"\1", " ".join(LOOSE_SUBS.get(word, word) for word in key.split()))
    for prefix in LOOSE_PREFIXES:
        if key.startswith(prefix + " ") and len(key) > len(prefix) + 1:
            key = key[len(prefix) + 1:]
    return " ".join(sorted(word for word in key.split() if word not in LOOSE_STOP))


# Library spellings read by eye as one game that no rule above finds (2026-10-14): a translated or regional title, a longer
# or shorter subtitle, a typo of a different shape. Each line is one game; the keys are search_terms() keys of library names.
NOT_SAME = [("in the groove", "eyetoy groove")]   # (spelling, other): never one game, whatever the joins say
SAME_GAME = (
    ("ace combat the belkan war", "ace combat zero the belkan war"),
    ("air ranger rescue helicopter", "air rescue ranger"),
    ("ajax club football", "club football ajax amsterdam"),
    ("ajax club football 2005", "club football 2005 ajax amsterdam"),
    ("arc the lad twilight of the spirits", "arc twilight of the spirits"),
    ("backyard baseball 07", "backyard sports baseball 2007"),
    ("backyard basketball 07", "backyard sports basketball 2007"),
    ("black buccaneer", "pirates legend of the black buccaneer"),
    ("buzz hollywood", "buzz the hollywood quiz"),
    ("cat in the hat", "dr seuss the cat in the hat"),
    ("chicken little aventures intergalactiques", "disney chicken little asso spaziale", "disneys chicken little ace in action"),
    ("crash bandicoot nitro kart", "crash nitro kart"),
    ("deus ex", "deus ex the conspiracy"),
    ("devil may cry 3", "devil may cry 3 dantes awakening"),
    ("dreamworks shark tale hajar som hajar", "shark tale"),
    ("espn international winter sports 2002", "espn winter sports 2002"),
    ("espn winter games snowboarding", "espn winter x games snowboarding", "winter x games snowboarding"),
    ("fuga da monkey island", "fuga de monkey island la"),
    ("ghostmaster", "ghost master the gravenville chronicles", "gravenville ghost master"),
    ("guitar hero encore rocks the 80s", "guitar hero rocks the 80s"),
    ("gun club", "nra gun club"),
    ("jak 2", "jak 2 renegade", "jak daxter 2"),
    ("jak daxter complete trilogy", "jak daxter trilogy"),
    ("jimmy neutron boy genius jet fusion", "jimmy neutron jet fusion"),
    ("kings field 4", "kings field 4 the ancient city"),
    ("m m s adventure", "m ms adventure"),
    ("magix music maker", "music maker"),
    ("magna carta", "magna carta tears of blood", "magna carta les larmes de sang"),
    ("mark of kri", "primal the mark of kri"),
    ("mercedes bens world racing", "world racing"),
    ("mountain bike adrenaline", "mountain bike adrenaline featuring salomon"),
    ("muppets party cruise", "muppets party cruise jim hensons"),
    ("mx unleashed", "mx vs atv unleashed"),
    ("nba street 2", "nba street vol 2"),
    ("ncaa college football 2k3", "ncaa football 2k3"),
    ("nhl 2k6", "nhl hockey 2k6"),
    ("nickelodeon spongebob schwammkopf der film", "nickelodeon spongebob schwammkopf film ab"),
    ("nickelodeon spongebob squarepants movin with friends", "spongebob friends movin"),
    ("nightmare of druaga", "nightmare of druaga fushigino dungeon"),
    ("off road wide open", "test drive off road wide open"),
    ("operation winback 2 project poseidon", "winback 2 project poseidon"),
    ("padrino el", "padrino il", "godfather"),
    ("pac man rally", "pac man world rally"),
    ("pool paradise", "pool paradise international edition"),
    ("pro tennis wta tour", "wta tour tennis"),
    ("puyo pop fever", "puyo puyo fever"),
    ("red baron", "wwi red baron"),
    ("riding star", "tim stockdales riding star"),
    ("road trip", "road trip adventure"),
    ("sing star nrj music tour", "singstar nrj music tour"),
    ("singstar after ski party", "singstar apres ski party"),
    ("singstar after ski party 2", "singstar apres ski party 2"),
    ("singstar swedish hits", "singstar svenska hits"),
    ("singstar svenska hits schlager", "singstar swedish hits schlager"),
    ("deutsch rock pop", "singstar german rock pop vol 2"),
    ("ski doo snow x racing", "snow x racing"),
    ("sudoku carol vondermans", "sudoku carol vordermans"),
    ("sum of all fears", "tom clancys the sum of all fears"),
    ("summer athletics", "summer athletics the ultimate challenge"),
    ("super trucks", "super trucks racing"),
    ("suzuki tt superbikes real road racing", "suzuki tt superbikes real road racing championship", "tt superbikes real road racing championship"),
    ("tiger woods pga tour 2002", "tiger woods usa tour 2002"),
    ("ty the tasmanian tiger", "ty the tazmanian tiger"),
    ("tour de france le", "tour de france le centenary edition"),
    ("torino 2006 the official game of the xx olympic winter games", "torino 2006 the official video game of the xx olympic winter games"),
    ("world rally championship 4", "wrc 4 fia world rally championship"),
    ("wrc rally evolved", "wrc world rally championship rally evolved"),
    ("x men 2 wolverines revenge", "x2 wolverines revenge"),
    # 2026-10-15: pairs the Library showed twice with the same picture (the collection's files are byte-for-byte equal), each read
    # as one game under a regional, translated or longer name. Different games that share a file by the collection's mistake
    # (Zombie Hunters 1 and 2, FIFA 2002 and FIFA World Cup 2002, the Club Football teams) are not here.
    ("tak le pouvoir de juju", "tak the power of juju"),
    ("star ocean 3", "star ocean till the end of time"),
    ("bdfl manager 2004", "lma manager 2004"),
    ("bdfl manager 2003", "lma manager 2003"),
    ("bdfl manager 2002", "football manager campionato 2002", "lma manager 2002", "manager de liga 2002", "roger lemerre la selection des champions 2002"),
    ("lma manager 2005", "roger lemerre la selection des champions 2005"),
    ("disneys jungle book groove party", "disneys jungle book rhythm groove"),
    ("saturday night speedway", "stock car speedway"),
    ("r racing", "r racing evolution"),
    ("harvest fishing", "river king a wonderful journey"),
    ("victorious boxers", "victorious boxers ippos road to glory"),
    ("tom clancys splinter cell 3 chaos theory", "tom clancys splinter cell chaos theory"),
    ("disneys stitch 926", "disneys stitch experiment 626"),
    ("dsf fussball manager 2002", "guy roux manager 2002"),
    ("tenchu 4 fatal shadows", "tenchu fatal shadows"),
    ("pro evolution soccer 3", "winning eleven 7 world soccer international"),
    ("pro evolution soccer 4", "world soccer winning eleven 8 international"),
    ("pro evolution soccer 5", "world soccer winning eleven 9 international"),
    ("international cue club", "real pool"),
    ("amf xtreme bowling", "amf xtreme bowling 2006"),
    ("nba 06", "nba 06 featuring the life vol 1"),
    ("star wars episode 3 die rache der sith", "star wars episode 3 la revanche des sith", "star wars episode 3 revenge of the sith"),
    ("fifa 2008", "fifa soccer 08"),
    ("mx 2002 featuring ricky carmichael", "mx superfly featuring ricky carmichael"),
    ("qui veut gagner des millions", "who wants to be a millionaire 2nd edition"),
    ("surfing h30", "surfing h3o"),
    ("dtm race driver 3", "v8 supercars 3"),
    ("nba live 06", "nba live 2006"),
    ("millennium european paintball series championship paintball 2009", "nppl championship paintball 2009"),
    ("batman 2 the rise of sin tsu", "batman rise of sin tzu"),
    ("goldeneye au service du mal", "goldeneye rogue agent"),
    ("egg mania eggstreme madness", "eggo mania"),
    ("tenchu 3 wrath of heaven", "tenchu wrath of heaven"),
    ("escape from monkey island", "escape from monkey island 4"),
    ("incredible hulk 2 ultimate destruction", "incredible hulk ultimate destruction"),
    ("harry potter kammer d schreckens", "harry potter the chamber of secrets"),
    ("harry potter og fangen fra azkaban", "harry potter the prisoner of azkaban"),
    ("medal of honor european assault", "medal of honor les faucons de guerre"),
    ("tom clancys splinter cell 2 pandora tomorrow", "tom clancys splinter cell pandora tomorrow"),
    ("drive to survive", "mashed fully loaded"),
    ("flipnic", "flipnic ultimate pinball"),
    ("ratchet clank 2 going commando", "ratchet clank going commando"),
    ("london racer 2", "paris marseille racing 2"),
    ("jeremy mcgrath supercross world", "jeremy mcgrath supercross world 2002"),
    ("shadow man 2 the second coming", "shadow man second coming"),
    ("athens 04", "athens 2004"),
    ("espn winter x games snowboarding 2", "espn winter x games snowboarding 2002"),
    ("timesplitters 3 future perfect", "timesplitters future perfect"),
    ("maximo", "maximo ghosts to glory"),
    ("mary kate ashley sweet 16", "mary kate ashley sweet sixteen licensed to drive"),
    ("friends celui qui repond a toutes les questions", "friends das trivia game", "friends the one with all the trivia"),
    ("lego football mania", "soccer mania"),
    ("p t o 4 pacific theater of operations", "p t o 4 pacific theater of operations 4"),
    ("fifa world cup germany 06", "fifa world cup germany 2006"),
    ("mx world tour", "mx world tour featuring jamie little"),
    ("horsez", "pippa funnell take the reins"),
    ("lemony snickets a series of unfortunate events", "lemony snickets una serie disfortunati eventi"),
    ("wwe smackdown 4 shut your mouth", "wwe smackdown shut your mouth"),
    ("score international baja 1000", "score international baja 1000 world championship off road racing"),
    ("spongebob schwammkopf schlacht um bikini bottom", "spongebob squarepants battle for bikini bottom"),
    ("rugrats rescate real", "rugrats royal ransom"),
    ("this is football 2003", "world tour soccer 2003"),
    ("baphomets fluch der schlafende drache", "broken sword the sleeping dragon"),
    ("thunderhawk operation phoenix", "thunderstrike operation phoenix"),
    ("heavenly guardian", "legend of sayuki"),
    ("capcom vs snk 2 mark of the millennium", "capcom vs snk 2 mark of the millennium 2001"),
    ("pride fc", "pride fc fighting championships"),
    ("uefa champions league 2004 2005", "uefa champions league 2005"),
    ("shadow hearts 2 covenant", "shadow hearts covenant"),
    ("alarm for cobra 11 vol 2", "alarm for cobra 11 vol 2 hot pursuit"),
    ("shox", "shox rally reinvented"),
    ("dark chronicle", "dark cloud 2"),
    ("donald duck goin quackers", "donald duck quack attack"),
    ("disneys monster inc scare island", "monsterit oy", "monstruos s a la isla de los sustos"),
    ("world championship poker", "world championship poker 2 featuring howard lederer", "world championship poker featuring howard lederer all in"),
    ("championship manager 5", "lentraineur 5", "scudetto 5"),
    ("chicken little as en accion", "disneys chicken little ace in action", "himmel und huhn ace in action"),
    ("network adapter start up disc", "network adapter start up disc ver 2 5", "network adapter start up disc ver 3 0"),
    ("dtm race driver 2", "toca race driver 2 the ultimate racing simulator", "toca racer driver 2", "v8 supercars 2"),
    ("dtm race driver", "pro race driver", "toca race driver", "v8 supercars australia race driver"),
    ("fire warrior", "warhammer 40 000 fire warrior", "warhammer 40k fire warrior"),
    ("terminator 3 le macchine ribelli", "terminator 3 rise of the machines", "terminator rise of the machines"),
    ("tennis sega sports", "virtua tennis 2"),
)
# Spellings that look like another game's and are not (one entry per game that must keep its own tile).
KEEP_APART = {"dark angel vampire apocalypse", "eyetoy play sports"}


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
    loose = {}
    for key in covers:
        loose.setdefault(loose_key(key), key)
    for _ in range(3):      # an alias can point at another alias (the library spells one game three ways), so go round until nothing is added
        before = len(covers)
        add_pass(names, covers, compact, unpadded, spellings, loose)
        if len(covers) == before:
            break
    return covers


def add_pass(names, covers, compact, unpadded, spellings, loose):
    for title in names:
        key = search_terms(title)[0]
        if not key or key in covers:
            continue
        target = MANUAL.get(key) or compact.get(key.replace(" ", "")) or unpadded.get(key)
        if not target:
            target = loose.get(loose_key(key))
        if not target:
            starts = [other for other in covers if other.startswith(key + " ")]
            target = starts[0] if len(starts) == 1 else None
        if not target:
            target = typo_of(key, spellings, unpadded)
        if target in covers:
            covers[key] = covers[target]


def library_titles():
    """{key: (title, in the library file)} for every name the page's Library shows (library file first, then the search extras)."""
    out = {}
    for path, field, official in (("data/ps2_database.json", None, True), ("search_extra_titles.json", "titles", False)):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        for title in (data.get(field, []) if field else data):
            if isinstance(title, str) and search_terms(title)[0]:
                out.setdefault(search_terms(title)[0], (title, official))
    return out


def same_game(covers):
    """{spelling's key: the key the Library shows for that game}, only for spellings that are not shown themselves.

    Two library names are one game when the loose key (loose_key) is equal, or when they share the collection's file and the
    same numbers ("Ace Combat 04" / "Ace Combat 4"; "Ty the Tasmanian Tiger 2" and "3" keep the file of the first apart). The shown
    spelling is the library file's, and of those the one closest to the collection's title."""
    titles = library_titles()
    parent = {key: key for key in titles}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def join(keys):
        keys = list(keys)
        for other in keys[1:]:
            parent[find(other)] = find(keys[0])

    by_loose, by_file, by_compact = {}, {}, {}
    for key in titles:
        if key in KEEP_APART:
            continue
        by_loose.setdefault(loose_key(key), []).append(key)
        by_compact.setdefault(key.replace(" ", ""), []).append(key)
        if key in covers:
            numbers = tuple(re.findall(r"\d+", re.sub(r"\b0+(\d)", r"\1", key)))
            by_file.setdefault((covers[key][0], numbers), []).append(key)
    for keys in list(by_loose.values()) + list(by_file.values()) + list(by_compact.values()):
        join(keys)
    for keys in SAME_GAME:
        present = [key for key in keys if key in titles]
        if len(present) != len(keys):
            print(f"  SAME_GAME names a spelling the library lacks: {[key for key in keys if key not in titles]}")
        join(present)
    groups = {}
    for key in titles:
        groups.setdefault(find(key), []).append(key)
    # A misspelling ("yazuka", "homind") has a word nothing else in the library uses: such a spelling is never the one shown.
    seen = {}
    for key in titles:
        for word in set(key.split()):
            seen[word] = seen.get(word, 0) + 1
    rarest = lambda key: min(min(seen[word], 3) for word in key.split())
    out = {}
    for keys in groups.values():
        if len(keys) < 2:
            continue
        file_key = next((search_terms(covers[k][0])[0] for k in keys if k in covers), "")
        shown = max(keys, key=lambda k: (rarest(k), titles[k][1], difflib.SequenceMatcher(None, k, file_key).ratio(), -len(k)))
        out.update({k: shown for k in keys if k != shown})
    # Two different games the loose joins put together (checked 2026-10-17: EyeToy: Groove is a dancing game, In the Groove a dance-pad one).
    for spelling, shown in NOT_SAME:
        if out.get(spelling) == shown or out.get(shown) == spelling:
            out.pop(spelling, None)
            out.pop(shown, None)
    return out


def share_covers(covers, same):
    """A spelling with no picture takes its game's: the shown spelling's, else any other spelling's that has one."""
    groups = {}
    for key, shown in same.items():
        groups.setdefault(shown, [shown]).append(key)
    for members in groups.values():
        donor = next((covers[key] for key in members if key in covers), None)
        if donor:
            for key in members:
                covers.setdefault(key, donor)


def main():
    covers = add_aliases(build(sys.stdin))
    share_covers(covers, same_game(covers))
    doc = {"what": "Which Libretro box-art file belongs to which game (key = priceKey()); the pictures are not stored here.",
           "source": "https://github.com/libretro-thumbnails/Sony_-_PlayStation_2", "base": BASE,
           "checked": date.today().isoformat(), "local": {key: path for key, path in LOCAL.items() if Path(path).is_file()},
           "same": dict(sorted(same_game(covers).items())),
           "covers": dict(sorted(covers.items()))}
    Path("covers.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(covers)} games with covers, {len(doc['same'])} spellings folded into another")


if __name__ == "__main__":
    main()
