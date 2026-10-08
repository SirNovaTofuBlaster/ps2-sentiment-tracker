"""Offline tests for ebay_prices.py and its workflow. Nothing here talks to eBay.

Run:  python -m unittest discover -s tests -v
A fake stands in for eBay's API, and a throwaway server on this machine checks
the real request code. Between them they check which games get priced and how
often, what the script asks eBay for, what it does with the answer, what it
writes, and above all that the key never leaks."""

import base64
import contextlib
import io
import json
import re
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ebay_prices  # noqa: E402

CLIENT_ID = "TestApp-PRD-0123456789ab-cdef0123"
CLIENT_SECRET = "PRD-topsecretcertid-4567-89ab"
BASIC = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
TOKEN = "v^1.1#i^1#fake-application-token-zzzz"
SECRETS = (CLIENT_ID, CLIENT_SECRET, BASIC, TOKEN)
KEY = {"EBAY_CLIENT_ID": CLIENT_ID, "EBAY_CLIENT_SECRET": CLIENT_SECRET}
WORKFLOW = ROOT / ".github" / "workflows" / "ebay.yml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
SCRAPER_WORKFLOW = ROOT / ".github" / "workflows" / "scraper.yml"

US = ebay_prices.MARKETS["EBAY_US"]
GB = ebay_prices.MARKETS["EBAY_GB"]
NOON = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def game(title, search=None, exclude=(), siblings=(), level="normal", pinned=False):
    name, queries = ebay_prices.search_terms(search or title)
    return {"title": title, "key": ebay_prices.key_of(title), "search": name, "queries": queries,
            "exclude": list(exclude), "siblings": list(siblings), "level": level, "pinned": pinned,
            "mentions": 0, "surging_until": None}


SH2 = game("Silent Hill 2")


class FakeHttp:
    """Answers the token request, then hands each search to `answer(params, headers)`."""

    def __init__(self, answer=None, token_answer=None):
        self.token_calls, self.searches = [], []
        self.answer = answer or (lambda params, headers: page())
        self.token_answer = token_answer or (200, {"access_token": TOKEN, "expires_in": 7200,
                                                   "token_type": "Application Access Token"})

    def send(self, url, headers, body=None):
        if url == ebay_prices.TOKEN_URL:
            self.token_calls.append({"headers": headers, "body": body})
            status, payload = self.token_answer
        else:
            parts = urlsplit(url)
            params = {key: values[0] for key, values in parse_qs(parts.query, strict_parsing=True).items()}
            self.searches.append({"url": url, "base": url.split("?")[0], "query": parts.query,
                                  "params": params, "headers": headers, "body": body})
            result = self.answer(params, headers)
            if isinstance(result, Exception):
                raise result
            status, payload = result
        return status, payload if isinstance(payload, str) else json.dumps(payload)


def listing(title, price, currency="USD", item_id="111", postage=None, **extra):
    item = {
        "title": title,
        "legacyItemId": str(item_id),
        "price": {"value": f"{price:.2f}", "currency": currency},
        "condition": "Good",
        "itemCreationDate": "2026-10-05T09:00:00.000Z",
    }
    if postage is not None:
        costs = postage if isinstance(postage, (list, tuple)) else [postage]
        item["shippingOptions"] = [{"shippingCostType": "FIXED",
                                    "shippingCost": {"value": f"{cost:.2f}", "currency": currency}}
                                   for cost in costs]
    item.update(extra)
    return item


def page(*items, total=None, **extra):
    return 200, {"total": len(items) if total is None else total, "itemSummaries": list(items), **extra}


def two_copies(params, headers, low=24.99, high=31.5):
    """A believable answer: two copies of whatever was asked for, in the site's own currency."""
    currency = "GBP" if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB" else "USD"
    name = params["q"].replace(" ps2", "")
    return page(listing(f"{name} PS2", low, currency=currency, item_id=1, postage=3.49),
                listing(f"{name} PS2 boxed", high, currency=currency, item_id=2))


def mention(title, hours_ago, source, headline=None, where="title", now=NOON):
    when = now - timedelta(hours=hours_ago)
    return {"headline": headline or f"{title} news from {source}", "source": source,
            "matched_games": [title], "matched_game": title, "matched_in": where,
            "timestamp": when.strftime(ebay_prices.FEED_TIME_FORMAT)}


class Sandbox:
    """Throwaway copies of every file the script reads or writes, and a clock that can be moved."""

    LIBRARY = ["Silent Hill 2", "Silent Hill 2: Director's Cut", "Silent Hill 3", "Kuon", "Okami", "God Hand",
               "Kingdom Hearts", "Kingdom Hearts II", "Kingdom Hearts Re:Chain of Memories",
               "Getaway, The: Black Monday", "Shin Megami Tensei: Persona 4", "Grand Theft Auto: San Andreas",
               "Jak and Daxter: The Precursor Legacy", "Black", "Combat Ace"]

    def __init__(self, test, pinned=(), never=(), feed=(), archive=()):
        folder = tempfile.TemporaryDirectory()
        test.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.data = self.root / "data"
        (self.data / "archive").mkdir(parents=True)
        self.out = self.root / "out" / "ebay_prices.json"
        self.now = NOON
        self.write("ebay_watchlist.json", {"games": list(pinned), "never": list(never)})
        self.write("data/ps2_database.json", self.LIBRARY)
        self.feed(feed)
        if archive:
            self.write("data/archive/2026-09.json", [{"g": title, "d": "2026-09-01 10:00 UTC", "s": "x", "h": "y"}
                                                     for title in archive])
        for name, value in (("WATCHLIST_PATH", self.root / "ebay_watchlist.json"),
                            ("RARE_PATH", self.root / "rare_games.json"),
                            ("CONSOLES_PATH", self.root / "rare_consoles.json"),
                            ("FEED_PATH", self.data / "sentiment_feed.json"),
                            ("ARCHIVE_DIR", self.data / "archive"),
                            ("LIBRARY_PATH", self.data / "ps2_database.json"),
                            ("PRICES_DIR", self.data / "prices"),
                            ("utc_now", lambda: self.now)):
            patcher = mock.patch.object(ebay_prices, name, value)
            patcher.start()
            test.addCleanup(patcher.stop)
        sleeper = mock.patch.object(ebay_prices.time, "sleep", lambda seconds: None)
        sleeper.start()
        test.addCleanup(sleeper.stop)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def feed(self, items):
        self.write("data/sentiment_feed.json", {"items": list(items)})

    def run(self, fake=None, env=KEY, argv=()):
        """main() against a fake eBay; returns (exit code, everything printed, the fake)."""
        fake = fake or FakeHttp(two_copies)
        printed = io.StringIO()
        with mock.patch.object(ebay_prices, "Http", lambda: fake), \
                mock.patch.dict(ebay_prices.os.environ, env, clear=True), \
                contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
            code = ebay_prices.main(["--out", str(self.out), *argv])
        return code, printed.getvalue(), fake

    @property
    def latest(self):
        return json.loads((self.data / "prices" / "latest.json").read_text(encoding="utf-8"))

    def history(self, month="2026-10"):
        path = self.data / "prices" / f"{month}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    @property
    def snapshot(self):
        return json.loads(self.out.read_text(encoding="utf-8"))


class Quiet(unittest.TestCase):
    """No real waiting, and nothing printed to the test output."""

    def setUp(self):
        self.slept = []
        for target, name, replacement in ((ebay_prices.time, "sleep", self.slept.append),
                                          (ebay_prices, "say", lambda text: None)):
            patcher = mock.patch.object(target, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)


# ---------------------------------------------------------------------------- the key

class TokenTests(Quiet):
    def test_token_request_is_the_client_credentials_grant(self):
        fake = FakeHttp()
        self.assertEqual(ebay_prices.get_token(fake, CLIENT_ID, CLIENT_SECRET), (TOKEN, BASIC))
        (call,) = fake.token_calls
        self.assertEqual(call["headers"], {"Authorization": f"Basic {BASIC}",
                                           "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(parse_qs(call["body"].decode()), {
            "grant_type": ["client_credentials"], "scope": ["https://api.ebay.com/oauth/api_scope"]})
        self.assertEqual(ebay_prices.TOKEN_URL, "https://api.ebay.com/identity/v1/oauth2/token")

    def test_refused_key_explains_itself_without_showing_the_key(self):
        echo = f"client authentication failed for {CLIENT_ID} / {CLIENT_SECRET} / Basic {BASIC}"
        fake = FakeHttp(token_answer=(401, {"error": "invalid_client", "error_description": echo}))
        with self.assertRaises(ebay_prices.EbayError) as caught:
            ebay_prices.get_token(fake, CLIENT_ID, CLIENT_SECRET)
        message = str(caught.exception)
        self.assertIn("HTTP 401: client authentication failed for *** / *** / Basic ***", message)
        self.assertIn("disabled", message)
        for secret in SECRETS:
            self.assertNotIn(secret, message)

    def test_an_answer_that_is_not_json_is_a_refusal_not_a_crash(self):
        for answer in ((503, "<html>down</html>"), (200, "[]"), (200, {"access_token": ""})):
            with self.assertRaises(ebay_prices.EbayError):
                ebay_prices.get_token(FakeHttp(token_answer=answer), CLIENT_ID, CLIENT_SECRET)

    def test_a_network_failure_names_the_kind_of_failure_only(self):
        fake = FakeHttp()
        fake.send = mock.Mock(side_effect=ebay_prices.NetworkProblem("TimeoutError"))
        with self.assertRaises(ebay_prices.EbayError) as caught:
            ebay_prices.get_token(fake, CLIENT_ID, CLIENT_SECRET)
        self.assertEqual(str(caught.exception), "Could not reach eBay to sign in (TimeoutError).")
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)


# ---------------------------------------------------------------------- asking eBay

class RequestTests(Quiet):
    def test_each_site_is_asked_for_used_buy_it_now_ps2_copies_in_its_own_country(self):
        for market_id, country, location in (("EBAY_US", "US", "country%3DUS%2Czip%3D10001"),
                                             ("EBAY_GB", "GB", "country%3DGB")):
            fake = FakeHttp(lambda params, headers: page(listing("Silent Hill 2 PS2", 30)))
            ebay_prices.search(fake, TOKEN, market_id, "silent hill 2", {"searches": 0})
            (call,) = fake.searches
            self.assertEqual(call["base"], "https://api.ebay.com/buy/browse/v1/item_summary/search")
            self.assertIsNone(call["body"])
            self.assertEqual(call["headers"], {
                "Authorization": f"Bearer {TOKEN}",
                "X-EBAY-C-MARKETPLACE-ID": market_id,
                "X-EBAY-C-ENDUSERCTX": f"contextualLocation={location}"})
            self.assertEqual(call["params"], {
                "q": "silent hill 2",
                "category_ids": "139973",
                "filter": "conditionIds:{2750|3000|4000|5000|6000},buyingOptions:{FIXED_PRICE},"
                          f"itemLocationCountry:{country}",
                "aspect_filter": "categoryId:139973,Platform:{Sony PlayStation 2}",
                "limit": "200"})

    def test_the_address_is_encoded_the_way_ebays_examples_are(self):
        query = urlsplit(ebay_prices.search_url("EBAY_GB", "silent hill 2")).query
        self.assertIn("q=silent%20hill%202&", query)
        self.assertIn("Platform%3A%7BSony%20PlayStation%202%7D", query)
        self.assertIn("conditionIds%3A%7B2750%7C3000%7C4000%7C5000%7C6000%7D%2CbuyingOptions", query)
        for raw in ("+", "{", "}", "|", " "):
            self.assertNotIn(raw, query)

    def test_the_keyword_search_drops_the_item_specific_and_adds_ps2(self):
        params = parse_qs(urlsplit(ebay_prices.search_url("EBAY_US", "kuon", by_aspect=False)).query)
        self.assertEqual(params["q"], ["kuon ps2"])
        self.assertNotIn("aspect_filter", params)

    def test_a_failed_search_is_tried_three_times_and_every_try_is_counted(self):
        for failure in ((503, {}), ebay_prices.NetworkProblem("TimeoutError")):
            answers = iter([failure, failure, page(listing("Silent Hill 2", 30))])
            fake = FakeHttp(lambda params, headers: next(answers))
            counter = {"searches": 0}
            self.slept.clear()
            status, payload = ebay_prices.search(fake, TOKEN, "EBAY_US", "silent hill 2", counter)
            self.assertEqual((status, counter["searches"], len(fake.searches)), (200, 3, 3))
            self.assertEqual(self.slept, [2, 8])

    def test_a_bad_request_is_not_retried(self):
        fake = FakeHttp(lambda params, headers: (400, {"errors": [{"message": "Invalid filter"}]}))
        counter = {"searches": 0}
        status, payload = ebay_prices.search(fake, TOKEN, "EBAY_US", "x", counter)
        self.assertEqual((status, counter["searches"]), (400, 1))
        self.assertEqual(ebay_prices.error_text(status, payload), "HTTP 400: Invalid filter")

    def test_a_429_that_will_not_clear_is_its_own_signal_with_ebays_words(self):
        fake = FakeHttp(lambda params, headers: (429, {"errors": [{"message": "Too many requests"}]}))
        counter = {"searches": 0}
        with self.assertRaises(ebay_prices.LimitReached) as caught:
            ebay_prices.search(fake, TOKEN, "EBAY_US", "x", counter)
        self.assertEqual(str(caught.exception), "HTTP 429: Too many requests")
        self.assertEqual(counter["searches"], 3)

    def test_a_dropped_connection_becomes_an_error_row_naming_only_the_kind(self):
        fake = FakeHttp(lambda params, headers: ebay_prices.NetworkProblem("ConnectionResetError"))
        result = ebay_prices.check_market(fake, TOKEN, SH2, "EBAY_US", {"searches": 0})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "no answer: network problem (ConnectionResetError)")
        self.assertIs(result["answered"], False)
        self.assertEqual(len(fake.searches), 3, "no keyword search after a failure")


# ------------------------------------------------------------------ words and names

class WordsTests(unittest.TestCase):
    def test_accents_fold_apostrophes_vanish_and_symbols_separate(self):
        self.assertEqual(ebay_prices.words("Ōkami™ (PS2)"), ["okami", "ps2"])
        self.assertEqual(ebay_prices.words("Okami⭐️Complete"), ["okami", "complete"])
        self.assertEqual(ebay_prices.words("Pokémon: Déjà Vu!"), ["pokemon", "deja", "vu"])
        self.assertEqual(ebay_prices.words("Director's Cut / Collector’s"), ["directors", "cut", "collectors"])
        self.assertEqual(ebay_prices.words(None), [])

    def test_two_spellings_of_one_name_compare_equal(self):
        same = [("Kingdom Hearts II", "kingdom hearts 2"), ("Jak & Daxter", "Jak and Daxter"),
                ("Final Fantasy XII", "final fantasy 12"), ("Ratchet and Clank", "ratchet clank")]
        for one, other in same:
            self.assertEqual(ebay_prices.name_words(one), ebay_prices.name_words(other), one)
        self.assertEqual(ebay_prices.name_words("Ubisoft XIII"), ebay_prices.name_words("ubisoft 13"))
        self.assertEqual(ebay_prices.name_words("Mega Man X"), ["mega", "man", "x"], "a lone X or V is a letter")

    def test_one_key_for_a_game_however_the_library_files_it(self):
        self.assertEqual(ebay_prices.key_of("Getaway, The: Black Monday"), ebay_prices.key_of("The Getaway: Black Monday"))
        self.assertEqual(ebay_prices.key_of("ICO"), ebay_prices.key_of("Ico"))
        self.assertEqual(ebay_prices.readable("Godfather, The: Collector's Edition"), "The Godfather: Collector's Edition")
        self.assertEqual(ebay_prices.readable("Okami"), "Okami")

    def test_search_words_come_from_the_title(self):
        cases = {
            "Silent Hill 2": ("silent hill 2", ["silent hill 2"]),
            "Kingdom Hearts II": ("kingdom hearts 2", ["kingdom hearts ii", "kingdom hearts 2"]),
            "Jak and Daxter: The Precursor Legacy": ("jak daxter the precursor legacy", ["jak daxter the precursor legacy"]),
            "Godfather, The: Collector's Edition": ("godfather collectors edition", ["godfather collectors edition"]),
            "Simpsons, The: Hit & Run": ("simpsons hit run", ["simpsons hit run"]),
            "Grand Theft Auto III": ("grand theft auto 3", ["grand theft auto iii", "grand theft auto 3"]),
            "The Thing": ("thing", ["thing"]),
            "A-Train 6": ("a train 6", ["a train 6"]),
            "XIII": ("13", ["xiii"]),
        }
        for title, expected in cases.items():
            self.assertEqual(ebay_prices.search_terms(title), expected, title)


class TitleTests(unittest.TestCase):
    def reason(self, title, wanted, market=US, keyword=False):
        item = listing(title, 10, currency=market["currency"])
        return ebay_prices.reject_reason(item, wanted, market, keyword)

    def test_the_2_in_playstation_2_is_not_the_2_in_silent_hill_2(self):
        for title in ("Silent Hill 3 (Sony PlayStation 2, 2003)",
                      "Silent Hill 4: The Room (Sony PlayStation 2, 2004)",
                      "Silent Hill Origins PlayStation 2 PS2",
                      "Silent Hill Shattered Memories - Play Station 2",
                      "Silent Hill PS 2"):
            self.assertEqual(self.reason(title, SH2), "other_game", title)
        self.assertEqual(self.reason("Silent Hill 2 (Sony PlayStation 2) 3 disc", game("Silent Hill 3")),
                         "other_game")

    def test_real_copies_are_counted_however_the_seller_words_them(self):
        for title in ("Silent Hill 2 (Sony PlayStation 2, 2001)",
                      "Silent Hill 2: Director's Cut PS2 Complete",
                      "Silent Hill 2 Greatest Hits PS2 2 Disc Set",
                      "PS2 - Silent Hill 2 - 9/10 condition",
                      "Silent Hill 2 18+ with manual playstation2"):
            self.assertIsNone(self.reason(title, SH2), title)
        self.assertIsNone(self.reason("Shin Megami Tensei: Persona 4 (PS2)", game("SMT P4", "Persona 4")))
        self.assertIsNone(self.reason("Ōkami (Sony PlayStation 2, 2006)", game("Okami")))

    def test_sets_and_sequels_are_not_the_game(self):
        for title in ("Silent Hill 2 3 4 PS2", "Silent Hill 2 & 3 PS2", "Silent Hill 2 and 3 PS2"):
            self.assertEqual(self.reason(title, SH2), "other_game", title)
        hearts = game("Kingdom Hearts")
        for title in ("Kingdom Hearts II PS2", "Kingdom Hearts 2 PS2"):
            self.assertEqual(self.reason(title, hearts), "other_game", title)
        for title in ("Kingdom Hearts PS2 black label", "Kingdom Hearts (Sony PlayStation 2) 3 day post",
                      "Kingdom Hearts PS 2 2 disc"):
            self.assertIsNone(self.reason(title, hearts), title)
        self.assertEqual(self.reason("Persona 3 FES PS2", game("SMT P4", "Persona 4")), "other_game")

    def test_a_numbered_game_is_found_under_either_way_of_writing_its_number(self):
        hearts2 = game("Kingdom Hearts II")
        for title in ("Kingdom Hearts II (Sony PlayStation 2, 2006)", "Kingdom Hearts 2 PS2 complete",
                      "Kingdom Hearts II: Final Mix+ PS2"):
            self.assertIsNone(self.reason(title, hearts2), title)
        for title in ("Kingdom Hearts PS2", "Kingdom Hearts 1 & 2 PS2", "Kingdom Hearts III"):
            self.assertEqual(self.reason(title, hearts2), "other_game", title)
        jak = game("Jak and Daxter: The Precursor Legacy")
        self.assertIsNone(self.reason("Jak & Daxter: The Precursor Legacy PS2", jak))
        self.assertIsNone(self.reason("Jak and Daxter The Precursor Legacy (PS2)", jak))

    @staticmethod
    def different(title, library):
        """The names that must not be counted as `title`, given a library of raw titles."""
        catalogue = []
        for other in library:
            owners = {" ".join(ebay_prices.words(owner + "s")) for owner in re.findall(r"([A-Za-z]+)'s\b", other)}
            catalogue.append({"name": ebay_prices.search_terms(other)[0], "title": ebay_prices.readable(other),
                              "possessive": owners})
        return ebay_prices.other_games(title, ebay_prices.search_terms(title)[0], catalogue)

    def test_another_game_whose_name_contains_this_one_is_left_out(self):
        library = ["Kingdom Hearts", "Kingdom Hearts II", "Kingdom Hearts Re:Chain of Memories",
                   "Spider-Man", "Ultimate Spider-Man", "Spider-Man: Friend or Foe", "Spider-Man: The Movie",
                   "Bully", "Ant Bully, The", "Yakuza", "Wreckless: The Yakuza Missions"]
        self.assertEqual(self.different("Kingdom Hearts", library),
                         ["kingdom hearts 2", "kingdom hearts re chain of memories"])
        self.assertEqual(self.different("Spider-Man", library),
                         ["spider man friend or foe", "spider man the movie", "ultimate spider man"])
        self.assertEqual(self.different("Bully", library), ["ant bully"])
        self.assertEqual(self.different("Yakuza", library), ["wreckless the yakuza missions"])
        hearts = game("Kingdom Hearts", siblings=self.different("Kingdom Hearts", library))
        self.assertEqual(self.reason("Kingdom Hearts Re:Chain of Memories PS2", hearts), "other_game")
        self.assertIsNone(self.reason("Kingdom Hearts PS2 Greatest Hits", hearts))
        spider = game("Spider-Man", siblings=self.different("Spider-Man", library))
        self.assertEqual(self.reason("Ultimate Spider-Man PS2", spider), "other_game")
        self.assertIsNone(self.reason("Spider-Man (Sony PlayStation 2, 2002)", spider))

    def test_the_same_game_under_a_longer_name_is_not_another_game(self):
        library = ["Silent Hill 2", "Silent Hill 2: Director's Cut", "Splinter Cell", "Tom Clancy's Splinter Cell",
                   "Tom Clancy's Splinter Cell: Chaos Theory", "Tarzan Untamed", "Disney's Tarzan Untamed",
                   "Jak X", "Jak X: Combat Racing", "Dynasty Warriors 3", "Dynasty Warriors 3: Xtreme Legends",
                   "Metal Gear Solid 2", "Metal Gear Solid 2: Sons of Liberty", "Metal Gear Solid 2: Substance",
                   "Midnight Club", "Midnight Club: Street Racing", "Midnight Club II", "Midnight Club 3: DUB Edition"]
        self.assertEqual(self.different("Silent Hill 2", library), [], "an edition")
        self.assertEqual(self.different("Splinter Cell", library), ["tom clancys splinter cell chaos theory"],
                         "an owner's name in front is the same game; a subtitle after it is not")
        self.assertEqual(self.different("Tarzan Untamed", library), [], "a brand in front")
        self.assertEqual(self.different("Jak X", library), [], "the library's one full name for it")
        self.assertEqual(self.different("Dynasty Warriors 3", library), ["dynasty warriors 3 xtreme legends"],
                         "an expansion is not the game's full name")
        self.assertEqual(self.different("Metal Gear Solid 2", library), ["metal gear solid 2 substance"])
        self.assertEqual(self.different("Midnight Club", library),
                         ["midnight club 2", "midnight club 3 dub edition"])
        jak = game("Jak X", siblings=self.different("Jak X", library))
        self.assertIsNone(self.reason("Jak X: Combat Racing (Sony PlayStation 2, 2005)", jak))

    def test_whole_words_decide_what_is_not_a_copy(self):
        okami = game("Okami")
        for title in ("Okami PS2 demo", "Capcom Okami - Sony PlayStation 2 Case & Manual Only", "Okami PS2 job lot",
                      "Okami PS2 Manual Booklet", "Okami PS2 NO GAME", "Okami PS2 repro cover",
                      "Okami Sony PlayStation 2 (Cover Art Only)", "Okami PS2 Box And Manual ONLY!! PAL"):
            self.assertEqual(self.reason(title, okami), "not_a_copy", title)
        for title in ("Okami PS2 Demolition seller", "Okami PS2 reproduced nowhere", "Okami PS2 pilot"):
            self.assertIsNone(self.reason(title, okami), title)

    def test_a_games_own_exclude_words_apply(self):
        ico = game("Ico", exclude=["colossus"])
        self.assertIsNone(self.reason("ICO - Sony Playstation 2 PS2", ico))
        self.assertEqual(self.reason("Ico & Shadow of the Colossus PS2", ico), "not_a_copy")

    def test_a_copy_made_for_another_region_is_left_out(self):
        kuon = game("Kuon")
        self.assertEqual(self.reason("Kuon PS2 Japan Import NTSC-J", kuon), "import")
        self.assertEqual(self.reason("Kuon PS2 PAL complete", kuon, US), "import")
        self.assertIsNone(self.reason("Kuon PS2 PAL complete", kuon, GB))
        self.assertEqual(self.reason("Kuon PS2 NTSC USA", kuon, GB), "import")
        self.assertIsNone(self.reason("Kuon PS2 NTSC-U", kuon, US))

    def test_titles_seen_on_real_runs_are_sorted_correctly(self):
        rose, persona, okami, ico = game("Rule of Rose"), game("SMT P4", "Persona 4"), game("Okami"), game("Ico")
        sh3, god_hand, colossus = game("Silent Hill 3"), game("God Hand"), game("Shadow of the Colossus")
        left_out = [
            ("Silent Hill 2 Pyramid Head Hat", SH2, US, "not_a_copy"),
            ("Silent Hill 2 Restless Dreams Original Xbox CIB? Horror Konami Tested", SH2, US, "other_platform"),
            ("SILENT HILL 2 Saigo no Uta Konami Dendo SLPM-65631 PS2 Playstation 2 JP", SH2, US, "import"),
            ("Action Replay Ultimate Cheats For Silent Hill 2 - PS2", SH2, GB, "not_a_copy"),
            ("Action Replay Ultimate Codes for Silent Hill 3 (PlayStation 2 PS2) CIB Complete", sh3, US, "not_a_copy"),
            ("Famitsu 2003 XENOSAGA, Fatal Frame 2, Silent Hill 3 Promo DVD", sh3, GB, "not_a_copy"),
            ("PS2 Silent Hill 2 Special Edition Card Board Case & Silent hill 3 Manual Boxed", sh3, GB, "other_game"),
            ("Silent Hill PS2 PROMO Collection Silent Hill 2, Silent Hill 3, Silent Hill 4 PS2", sh3, GB, "other_game"),
            ("Rule of Rose Original Soundtrack OST CD - Atlus - Sony PlayStation 2 PS2 Promo", rose, US, "not_a_copy"),
            ("Rule of Rose Soundtrack PS2", rose, US, "not_a_copy"),
            ("Rule of Rose \U0001F339 Original Music Soundtrack Promo CD ATLUS PlayStation 2", rose, US, "not_a_copy"),
            ("Underground Jampack Summer 2001 Sony PlayStation 2 PS2 Red Faction ATV Kain ICO", ico, US, "not_a_copy"),
            ("Persona 4 (Sony PlayStation 2 PS2, 2008) JP Version US Seller", persona, US, "import"),
            ("Atlus Persona 4 Persona Series Sony PlayStation 2,Clean,jap,cib banger game !!", persona, US, "import"),
            ("Okami (JP PlayStation 2, 2006) CIB", okami, US, "import"),
            ("Okami PS2 SLES-54439 complete", okami, US, "import"),
            ("Okami PS2 SLUS-21115 complete", okami, GB, "import"),
        ]
        for title, wanted, market, reason in left_out:
            self.assertEqual(self.reason(title, wanted, market), reason, title)
        counted = [
            # Left out by the first version of the rules, though each is a real copy.
            ("Silent Hill 2 Complete With Original Case, Manual With Registration Card & Disc", SH2, US),
            ("PS2 Silent Hill 2 Video Game With Case And Manual + ORIGINAL PURCHASE RECEIPT", SH2, US),
            ("Silent Hill 2 (PlayStation 2, 2001) PS2 w/ Manual and Case", SH2, US),
            ("Silent Hill 3 + soundtrack Sony Playstation 2 PS2 CIB", sh3, US),
            ("Silent Hill 3 & Soundtrack PS2 complete", sh3, US),
            ("Silent Hill 3 + Original Soundtrack PS2", sh3, US),
            ("Capcom God Hand Sony PlayStation 2 PS2 w/ Case + Manual M NTSC-U/C 2006", god_hand, US),
            ("God Hand - PlayStation 2 PS2 PAL PEGI 16+ with Case & Manual VG++", god_hand, GB),
            ("ICO /PlayStation 2, 2001/CIB w/Case And Manual Sony", ico, US),
            ("Sony Shadow of the Colossus Greatest Hits PS2 Game Disc Case Manual T NTSC", colossus, US),
            ("Persona 4 PlayStation 2 Complete with Case, Manual, and Bonus Disc", persona, US),
            ("Persona 4 [PS2] - Complete PAL version + OST, pristine condition", persona, GB),
            ("Okami⭐️Complete CIB Original⭐️Sony PlayStation 2 PS2 Authentic Black Label", okami, US),
            ("Ōkami™ (PlayStation 2) [S-Grade, Complete & Tested] EU Version", okami, GB),
            ("Silent Hill 2 PlayStation 2 PS2 Greatest Hits Disc Only", SH2, US),
            ("Silent Hill 2 Special 2-Disc Set PlayStation 2 In Very Good Condition PAL UK", SH2, GB),
            ("Silent Hill 2 Special Edition 2 Disc Set PAL Survival Horror PS2 (15)", SH2, GB),
            ("Konami Silent Hill 3 PS2 Disc w/ Soundtrack Survival Horror M NTSC-U/C 2003", sh3, US),
            ("Silent Hill 3 For Ps2, Soundtrack Missing", sh3, US),
            ("Silent Hill 3 PS2 (Unofficial case with soundtrack)", sh3, US),
            ("Silent Hill 3 Playstation 2 Game & Manual VG+!! Tested! HTF!! NO SOUNDTRACK", sh3, US),
            ("Persona 4 PS2 - Manual Included without Original Soundtrack", persona, GB),
            ("Shin Megami Tensei Persona 4 PS2, Manual and Soundtrack CD", persona, GB),
            ("Rule of Rose (Sony PlayStation 2, 2006) PS2 Game Disc & Case! No Manual TESTED!", rose, US),
            ("Rule of Rose PS2 PAL French Cover and Manual Disc in English", rose, GB),
            ("ICO - PS2 PLAYSTATION GAME 2006 - FULL GAME PROMO-TESTED-DISC ONLY", ico, GB),
            ("Okami PS2 PAL Disc Only SLES-54439#", okami, GB),
            ("Okami, Capcom, PlayStation 2 (PS2), 2006, T, NTSC-U/C, Disc Only", okami, US),
            ("Sony Computer Entertainment Europe Ico PS2 PAL PEGI 7 (2001) 1 Player Puzzle", ico, GB),
        ]
        for title, wanted, market in counted:
            self.assertIsNone(self.reason(title, wanted, market), title)

    def test_a_keyword_search_only_counts_titles_that_say_ps2(self):
        rose = game("Rule of Rose")
        self.assertEqual(self.reason("Rule of Rose", rose, keyword=True), "other_game")
        self.assertIsNone(self.reason("Rule of Rose", rose, keyword=False))
        self.assertIsNone(self.reason("Rule of Rose PlayStation 2", rose, keyword=True))


class SummaryTests(Quiet):
    def summary(self, *items, wanted=SH2, market=US, keyword=False, total=None, **extra):
        return ebay_prices.summarise(page(*items, total=total, **extra)[1], wanted, market, keyword)

    def test_median_and_lowest_come_from_the_copies_that_count(self):
        result = self.summary(
            listing("Silent Hill 2 PS2 complete", 40, item_id=1),
            listing("Silent Hill 2 Greatest Hits PlayStation 2", 20, item_id=2),
            listing("Silent Hill 2 Director's Cut", 300, item_id=3),
            listing("Silent Hill 2 CASE ONLY no game", 5, item_id=4),
            listing("Silent Hill 3 (Sony PlayStation 2, 2003)", 60, item_id=5),
            listing("Silent Hill 2 PS2 bundle with guide", 90, item_id=6),
            listing("Silent Hill 2 PS2 Japanese version", 8, item_id=7),
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual((result["on_ebay"], result["fetched"], result["counted"]), (7, 7, 3))
        self.assertEqual(result["skipped"], {"import": 1, "not_a_copy": 2, "other_game": 1})
        self.assertEqual(result["skipped_examples"], {
            "import": ["Silent Hill 2 PS2 Japanese version"],
            "not_a_copy": ["Silent Hill 2 CASE ONLY no game", "Silent Hill 2 PS2 bundle with guide"],
            "other_game": ["Silent Hill 3 (Sony PlayStation 2, 2003)"]})
        self.assertEqual((result["lowest"], result["median"]), (20.0, 40.0))
        self.assertEqual((result["currency"], result["platform_filter"]), ("USD", "item_specific"))
        self.assertFalse(result["truncated"])

    def test_one_silly_price_does_not_move_the_median(self):
        prices = [18, 20, 22, 24, 26]
        calm = self.summary(*[listing("Silent Hill 2", p, item_id=i) for i, p in enumerate(prices)])
        wild = self.summary(*[listing("Silent Hill 2", p, item_id=i) for i, p in enumerate(prices[:-1] + [900])])
        self.assertEqual(calm["median"], wild["median"])

    def test_the_median_is_worked_out_in_exact_pennies(self):
        result = self.summary(listing("Silent Hill 2", 24.99, item_id=1), listing("Silent Hill 2", 31.5, item_id=2))
        self.assertEqual(result["median"], 28.25)

    def test_only_a_few_left_out_titles_are_saved_per_reason(self):
        result = self.summary(*[listing(f"Silent Hill 2 PS2 case only {n}", 5, item_id=n) for n in range(9)],
                              listing("x" * 300 + " Silent Hill 3 PS2", 5, item_id=99))
        self.assertEqual(result["skipped"], {"not_a_copy": 9, "other_game": 1})
        self.assertEqual(len(result["skipped_examples"]["not_a_copy"]), 5)
        self.assertEqual(len(result["skipped_examples"]["other_game"][0]), 120)

    def test_more_listings_than_one_search_returns_is_flagged(self):
        result = self.summary(listing("Silent Hill 2", 20, item_id=1), listing("Silent Hill 2", 30, item_id=2),
                              total=1234)
        self.assertEqual((result["on_ebay"], result["fetched"]), (1234, 2))
        self.assertTrue(result["truncated"])
        line = ebay_prices.describe(SH2, US, result)
        self.assertEqual(line, "  Silent Hill 2 [US]: 2 of 2 listings counted (first 2 of 1234 on eBay)")

    def test_the_ten_cheapest_are_kept_cheapest_first_with_plain_links(self):
        items = [listing("Silent Hill 2 PS2", 50 - n, item_id=1000 + n) for n in range(14)]
        result = self.summary(*items)
        kept = result["listings"]
        self.assertEqual(len(kept), 10)
        self.assertEqual([row["price"] for row in kept], [37.0 + n for n in range(10)])
        self.assertEqual(kept[0], {
            "title": "Silent Hill 2 PS2", "price": 37.0, "postage": None, "condition": "Good",
            "listed": "2026-10-05T09:00:00.000Z", "url": "https://www.ebay.com/itm/1013"})
        self.assertEqual(result["counted"], 14)

    def test_uk_copies_link_to_the_uk_site_and_dollars_are_not_counted_as_pounds(self):
        result = self.summary(
            listing("Silent Hill 2 PS2 PAL", 25, currency="GBP", item_id=7),
            listing("Silent Hill 2 PS2", 30, currency="USD", item_id=8),
            market=GB)
        self.assertEqual((result["counted"], result["skipped"]), (1, {"no_price": 1}))
        self.assertEqual(result["listings"][0]["url"], "https://www.ebay.co.uk/itm/7")
        self.assertEqual(result["currency"], "GBP")

    def test_a_listing_without_a_real_price_is_not_counted(self):
        free = listing("Silent Hill 2 PS2", 0, item_id=1)
        blank = listing("Silent Hill 2 PS2", 5, item_id=2)
        blank["price"] = {"value": "n/a", "currency": "USD"}
        missing = listing("Silent Hill 2 PS2", 5, item_id=3)
        del missing["price"]
        result = self.summary(free, blank, missing, listing("Silent Hill 2 PS2", 22, item_id=4))
        self.assertEqual((result["counted"], result["skipped"], result["lowest"]), (1, {"no_price": 3}, 22.0))

    def test_a_link_that_is_not_on_ebay_is_never_saved(self):
        odd = listing("Silent Hill 2 PS2", 25, item_id="", itemWebUrl="https://evil.example/itm/1")
        lookalike = listing("Silent Hill 2 PS2", 25, item_id="", itemWebUrl="https://www.ebay.com.evil.example/itm/1")
        fine = listing("Silent Hill 2 PS2", 26, item_id="",
                       itemWebUrl="https://www.ebay.com/itm/silent-hill-2/99?hash=abc")
        result = self.summary(odd, lookalike, fine)
        self.assertEqual(result["skipped"], {"no_link": 2})
        self.assertEqual([row["url"] for row in result["listings"]],
                         ["https://www.ebay.com/itm/silent-hill-2/99?hash=abc"])

    def test_postage_is_the_cheapest_option_and_is_reported_apart_from_the_price(self):
        result = self.summary(
            listing("Silent Hill 2", 20, item_id=1, postage=[6, 4, 9]),
            listing("Silent Hill 2", 30, item_id=2, postage=0),
            listing("Silent Hill 2", 40, item_id=3))
        self.assertEqual([row["postage"] for row in result["listings"]], [4.0, 0.0, None])
        self.assertEqual((result["postage_known"], result["median_postage"]), (2, 2.0))
        self.assertEqual(result["median"], 30.0, "the median is the item price, postage not added")
        self.assertIsNone(self.summary(listing("Silent Hill 2", 20))["median_postage"])

    def test_incomplete_copies_are_counted_and_flagged(self):
        result = self.summary(
            listing("Silent Hill 2 PS2 disc only", 12, item_id=1),
            listing("Silent Hill 2 PS2 no manual", 18, item_id=2),
            listing("Silent Hill 2 PS2 complete", 35, item_id=3))
        self.assertEqual((result["counted"], result["incomplete_hint"]), (3, 2))
        self.assertNotIn("incomplete", result["listings"][0])

    def test_nothing_for_sale_is_not_the_same_as_an_error(self):
        result = self.summary()
        self.assertEqual((result["status"], result["counted"], result["fetched"]), ("none", 0, 0))
        for absent in ("median", "lowest", "listings", "error"):
            self.assertNotIn(absent, result)

    def test_ebays_warnings_are_passed_on(self):
        result = self.summary(listing("Silent Hill 2", 20),
                              warnings=[{"message": "short", "longMessage": "The aspect filter was ignored."}])
        self.assertEqual(result["warning"], "The aspect filter was ignored.")
        self.assertIn("eBay warning: The aspect filter was ignored.", ebay_prices.describe(SH2, US, result))


class FallbackTests(Quiet):
    def test_when_no_listing_carries_the_ps2_item_specific_it_asks_again_by_keyword(self):
        def answer(params, headers):
            if "aspect_filter" in params:
                return page()
            return page(listing("Kuon PS2 PAL", 400, currency="GBP", item_id=1),
                        listing("Kuon blu-ray film", 9, currency="GBP", item_id=2))
        fake = FakeHttp(answer)
        counter = {"searches": 0}
        result = ebay_prices.check_market(fake, TOKEN, game("Kuon"), "EBAY_GB", counter)
        self.assertEqual(counter["searches"], 2)
        self.assertEqual(fake.searches[1]["params"]["q"], "kuon ps2")
        self.assertNotIn("aspect_filter", fake.searches[1]["params"])
        self.assertEqual(result["platform_filter"], "keyword")
        self.assertEqual((result["counted"], result["skipped"]), (1, {"other_game": 1}))
        self.assertEqual(
            result["search_url"],
            "https://www.ebay.co.uk/sch/i.html?_nkw=kuon%20ps2&_sacat=139973"
            "&LH_ItemCondition=2750%7C3000%7C4000%7C5000%7C6000&LH_BIN=1&LH_PrefLoc=1")

    def test_a_title_with_a_roman_numeral_is_searched_both_ways_and_each_listing_counts_once(self):
        def answer(params, headers):
            if params["q"] == "kingdom hearts ii":
                return page(listing("Kingdom Hearts II PS2", 17, item_id=2), listing("Kingdom Hearts II Greatest Hits PS2", 19, item_id=4))
            return page(listing("Kingdom Hearts 2 PS2", 15, item_id=1), listing("Kingdom Hearts II Greatest Hits PS2", 19, item_id=4),
                        listing("Kingdom Hearts 1 & 2 PS2", 9, item_id=3), total=250)
        fake = FakeHttp(answer)
        counter = {"searches": 0}
        result = ebay_prices.check_market(fake, TOKEN, game("Kingdom Hearts II"), "EBAY_US", counter)
        self.assertEqual([call["params"]["q"] for call in fake.searches], ["kingdom hearts ii", "kingdom hearts 2"])
        self.assertEqual(counter["searches"], 2)
        self.assertEqual((result["fetched"], result["counted"], result["lowest"], result["median"]), (4, 3, 15.0, 17.0))
        self.assertEqual(result["skipped"], {"other_game": 1})
        self.assertEqual(result["on_ebay"], 2 + 250 - 1, "the listing both searches returned is counted once")
        self.assertTrue(result["truncated"], "one of the two searches had more than it returned")
        self.assertTrue(result["search_url"].startswith("https://www.ebay.com/sch/i.html?_nkw=kingdom%20hearts%202%20ps2"))

    def test_listings_that_never_name_the_game_are_unmatched_not_zero_copies(self):
        fake = FakeHttp(lambda params, headers: page(listing("Jak 3 PS2", 9, item_id=1), listing("Jak II PS2", 8, item_id=2)))
        jak = game("Jak X")
        result = ebay_prices.check_market(fake, TOKEN, jak, "EBAY_US", {"searches": 0})
        self.assertEqual((result["status"], result["fetched"], result["counted"]), ("unmatched", 2, 0))
        self.assertEqual(ebay_prices.describe(jak, US, result),
                         "  Jak X [US]: none of the 2 listings eBay returned names this game; it needs its own search words")
        self.assertEqual(ebay_prices.numbers_of(result, "2026-10-06T12:00Z"), {"checked": "2026-10-06T12:00Z", "unmatched": True})
        junk_only = ebay_prices.summarise(page(listing("Jak X PS2 case only", 3))[1], jak, US, False)
        self.assertEqual(junk_only["status"], "none", "the game was found, there is just no copy of it")

    def test_an_error_is_reported_with_ebays_own_words_and_no_second_search(self):
        fake = FakeHttp(lambda params, headers: (
            400, {"errors": [{"errorId": 12001, "message": "short", "longMessage": "The aspect filter is invalid."}]}))
        result = ebay_prices.check_market(fake, TOKEN, SH2, "EBAY_US", {"searches": 0})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "HTTP 400: The aspect filter is invalid.")
        self.assertIs(result["answered"], True)
        self.assertNotIn("median", result)
        self.assertEqual(len(fake.searches), 1)


# ------------------------------------------------------------------- the watchlist

class WatchlistTests(unittest.TestCase):
    def write(self, value):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "ebay_watchlist.json"
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def test_the_committed_watchlist_loads(self):
        pinned, never = ebay_prices.load_watchlist()
        self.assertLessEqual(len(pinned), ebay_prices.MAX_PINNED)
        self.assertTrue(all(entry["pinned"] and entry["search"] and entry["queries"] for entry in pinned))
        self.assertFalse({entry["key"] for entry in pinned} & never, "a game cannot be pinned and never priced")

    def test_the_committed_watchlist_names_real_ps2_games(self):
        library_path = ROOT / "data" / "ps2_database.json"
        if not library_path.exists():
            self.skipTest("no cached PS2 library")
        library = {ebay_prices.key_of(title) for title in json.loads(library_path.read_text(encoding="utf-8"))}
        pinned, never = ebay_prices.load_watchlist()
        for entry in pinned:
            self.assertIn(entry["key"], library, entry["title"])
        self.assertTrue(never <= library, never - library)

    def test_a_pinned_game_carries_its_own_search_words(self):
        pinned, never = ebay_prices.load_watchlist(self.write({
            "games": [{"title": "Shin Megami Tensei: Persona 4", "search": "Persona 4"},
                      {"title": "Jak II: Renegade", "search": "Jak II (Renegade, PAL)", "exclude": ["Demo!", ""]}],
            "never": ["Combat Ace", "Getaway, The: Black Monday"]}))
        self.assertEqual([(entry["title"], entry["search"], entry["queries"], entry["exclude"]) for entry in pinned], [
            ("Shin Megami Tensei: Persona 4", "persona 4", ["persona 4"], []),
            ("Jak II: Renegade", "jak 2 renegade pal", ["jak ii renegade pal", "jak 2 renegade pal"], ["demo"])])
        self.assertEqual(never, {"combat ace", "the getaway black monday"})

    def test_an_empty_list_of_pinned_games_is_allowed(self):
        self.assertEqual(ebay_prices.load_watchlist(self.write({"games": []})), ([], set()))

    def test_mistakes_get_a_readable_message(self):
        cases = {
            "{not json": "not valid JSON",
            json.dumps({"about": "x"}): '"games" list',
            json.dumps({"games": [{"name": "Ico"}]}): 'needs a "title"',
            json.dumps({"games": [{"title": "Ico"}, {"title": "ICO"}]}): "listed twice",
            json.dumps({"games": [{"title": "Ico", "search": "!!!"}]}): '"search"',
            json.dumps({"games": [{"title": "Ico", "exclude": "colossus"}]}): '"exclude"',
            json.dumps({"games": [{"title": "word " * 30}]}): "shorter",
            json.dumps({"games": [], "never": "Combat Ace"}): '"never"',
            json.dumps({"games": [{"title": f"Game {n}"} for n in range(101)]}): "most allowed",
        }
        for text, expected in cases.items():
            with self.assertRaises(ebay_prices.EbayError) as caught:
                ebay_prices.load_watchlist(self.write(text))
            self.assertIn(expected, str(caught.exception))

    def test_a_missing_file_is_an_error_not_a_crash(self):
        with self.assertRaises(ebay_prices.EbayError):
            ebay_prices.load_watchlist(ROOT / "no_such_watchlist.json")


# -------------------------------------------------- which games, and how often

class LevelTests(unittest.TestCase):
    @staticmethod
    def said(hours_ago, source, headline=None, in_headline=True):
        return {"key": "kuon", "when": NOON - timedelta(hours=hours_ago), "source": source,
                "headline": headline or f"kuon story from {source}", "in_headline": in_headline}

    def level(self, mentions, held=None, pinned=False, now=NOON):
        return ebay_prices.level_of(mentions, now, held, pinned)

    def test_a_quiet_game_named_by_two_sources_in_a_day_is_surging(self):
        level, named, until = self.level([self.said(20, "r/ps2"), self.said(3, "Eurogamer")])
        self.assertEqual((level, named), ("surging", 2))
        self.assertEqual(until, NOON - timedelta(hours=3) + timedelta(hours=48))

    def test_one_earlier_mention_does_not_stop_a_surge_but_two_do(self):
        recent = [self.said(20, "r/ps2"), self.said(3, "Eurogamer")]
        self.assertEqual(self.level(recent + [self.said(200, "IGN")])[0], "surging")
        self.assertEqual(self.level(recent + [self.said(200, "IGN"), self.said(100, "VG247")])[0], "normal")

    def test_what_does_not_count_as_a_surge(self):
        once = [self.said(3, "Eurogamer")]
        one_source_twice = [self.said(20, "r/ps2", "first"), self.said(3, "r/ps2", "second")]
        cross_posted = [self.said(20, "r/ps2", "game appreciation kuon"), self.said(19, "r/playstation2", "game appreciation kuon")]
        only_in_the_text = [self.said(20, "r/ps2", in_headline=False), self.said(3, "Eurogamer", in_headline=False)]
        too_far_apart = [self.said(25, "r/ps2"), self.said(3, "Eurogamer"), self.said(40, "IGN")]
        for mentions in (once, one_source_twice, cross_posted, only_in_the_text, too_far_apart):
            self.assertEqual(self.level(mentions)[0], "normal", mentions)

    def test_a_surge_is_held_for_two_days_after_the_last_mention_then_ends(self):
        mentions = [self.said(20, "r/ps2"), self.said(3, "Eurogamer")]
        level, named, until = self.level(mentions)
        for hours_later, expected in ((24, "surging"), (44, "surging"), (46, "normal")):
            later = NOON + timedelta(hours=hours_later)
            self.assertEqual(ebay_prices.level_of(mentions, later, until)[0], expected, hours_later)

    def test_a_game_named_on_many_days_is_a_staple_and_never_surges(self):
        daily = [self.said(24 * day + 2, f"source {day}") for day in range(5)]
        self.assertEqual(self.level(daily), ("staple", 5, None))
        burst = daily + [self.said(1, "Eurogamer"), self.said(3, "IGN")]
        self.assertEqual(self.level(burst, held=NOON + timedelta(hours=10))[0], "staple")
        self.assertEqual(self.level(daily[:4])[0], "normal", "four days is not yet a staple")
        one_busy_day = [self.said(hour, f"source {hour}") for hour in range(30, 36)]
        self.assertEqual(self.level(one_busy_day)[0], "normal", "six mentions on one day are not six days")
        unlabelled = [dict(self.said(20, "r/ps2"), in_headline=True), dict(self.said(3, "IGN"), in_headline=True)]
        self.assertEqual(self.level(unlabelled)[0], "surging")

    def test_old_mentions_make_a_game_dormant_unless_it_is_pinned(self):
        old = [self.said(24 * 20, "r/ps2")]
        self.assertEqual(self.level(old), ("dormant", 0, None))
        self.assertEqual(self.level([]), ("dormant", 0, None))
        self.assertEqual(self.level([], pinned=True), ("normal", 0, None))

    def test_a_mention_only_in_the_text_keeps_a_game_normal(self):
        self.assertEqual(self.level([self.said(50, "r/ps2", in_headline=False)]), ("normal", 0, None))

    def test_a_mention_dated_in_the_future_is_ignored(self):
        self.assertEqual(self.level([self.said(-5, "r/ps2"), self.said(-6, "IGN")])[0], "dormant")


class PlanTests(unittest.TestCase):
    def plan(self, sandbox, state=None):
        pinned, never = ebay_prices.load_watchlist()
        mentions, ever = ebay_prices.load_mentions()
        library, catalogue = ebay_prices.load_library()
        return ebay_prices.plan_games(sandbox.now, pinned, never, mentions, ever, library, catalogue, state or {})

    def test_every_mentioned_library_game_is_tracked_and_the_rest_is_explained(self):
        sandbox = Sandbox(self, pinned=[{"title": "Silent Hill 2"}], never=["Combat Ace"], feed=[
            mention("Kuon", 5, "r/ps2"), mention("Kingdom Hearts", 30, "IGN"), mention("Black", 2, "r/ps2"),
            mention("Combat Ace", 2, "IGN"), mention("Halo 2", 2, "IGN"),
            mention("The Getaway: Black Monday", 2, "r/ps2")], archive=["Okami", "Kuon"])
        games, left_out = self.plan(sandbox)
        self.assertEqual({entry["title"]: entry["level"] for entry in games}, {
            "Getaway, The: Black Monday": "normal", "Kingdom Hearts": "normal", "Kuon": "normal",
            "Okami": "dormant", "Silent Hill 2": "normal"})
        self.assertEqual([entry["title"] for entry in games], sorted((entry["title"] for entry in games), key=str.lower))
        self.assertEqual(left_out, {"one_word": ["Black"], "not_in_library": ["Halo 2"], "never": ["Combat Ace"]})
        hearts = next(entry for entry in games if entry["title"] == "Kingdom Hearts")
        self.assertEqual((hearts["search"], hearts["queries"], hearts["pinned"]),
                         ("kingdom hearts", ["kingdom hearts"], False))
        self.assertEqual(hearts["siblings"], ["kingdom hearts 2", "kingdom hearts re chain of memories"])

    def test_a_one_word_title_is_tracked_when_it_is_distinctive_or_pinned(self):
        feed = [mention("Okami", 3, "r/ps2"), mention("Black", 3, "r/ps2")]
        games, left_out = self.plan(Sandbox(self, feed=feed))
        self.assertEqual([(entry["title"], entry["pinned"]) for entry in games], [("Okami", False)])
        self.assertEqual(left_out["one_word"], ["Black"])
        games, left_out = self.plan(Sandbox(self, pinned=[{"title": "Black", "search": "Black Criterion"}], feed=feed))
        self.assertEqual([(entry["title"], entry["pinned"], entry["search"]) for entry in games],
                         [("Black", True, "black criterion"), ("Okami", False, "okami")])
        self.assertEqual(left_out["one_word"], [])

    def test_every_distinctive_one_word_title_is_a_real_library_title(self):
        library_path = ROOT / "data" / "ps2_database.json"
        if not library_path.exists():
            self.skipTest("no cached PS2 library")
        one_word = {ebay_prices.search_terms(title)[1][0]
                    for title in json.loads(library_path.read_text(encoding="utf-8"))}
        self.assertTrue(ebay_prices.ONE_WORD_TITLES <= one_word, sorted(ebay_prices.ONE_WORD_TITLES - one_word))
        for ordinary in ("black", "cars", "gift", "gun", "retro", "thing", "driven", "sims"):
            self.assertNotIn(ordinary, ebay_prices.ONE_WORD_TITLES)

    def test_the_feeds_short_name_for_a_pinned_game_counts_as_that_game(self):
        feed = [mention("Persona 4", 24 * day + 1, f"source {day}") for day in range(6)]
        sandbox = Sandbox(self, pinned=[{"title": "Shin Megami Tensei: Persona 4", "search": "Persona 4"}], feed=feed)
        games, left_out = self.plan(sandbox)
        self.assertEqual([(entry["title"], entry["level"], entry["mentions"]) for entry in games],
                         [("Shin Megami Tensei: Persona 4", "staple", 6)])
        self.assertEqual(left_out["not_in_library"], [])

    def test_two_library_spellings_of_one_game_are_tracked_once(self):
        sandbox = Sandbox(self, feed=[mention("Getaway, The: Black Monday", 3, "r/ps2"),
                                      mention("Getaway: Black Monday", 2, "IGN")])
        sandbox.write("data/ps2_database.json", ["Getaway, The: Black Monday", "Getaway: Black Monday"])
        games, left_out = self.plan(sandbox)
        self.assertEqual([(entry["title"], entry["mentions"]) for entry in games], [("Getaway: Black Monday", 2)])

    def test_an_item_that_does_not_say_where_the_name_was_counts_as_a_headline(self):
        feed = [mention("God Hand", 20, "r/ps2"), mention("God Hand", 3, "IGN")]
        for item in feed:
            del item["matched_in"]
        games, _ = self.plan(Sandbox(self, feed=feed))
        self.assertEqual((games[0]["level"], games[0]["mentions"]), ("surging", 2))

    def test_a_surge_is_remembered_between_runs(self):
        sandbox = Sandbox(self, feed=[mention("Kuon", 20, "r/ps2"), mention("Kuon", 3, "Eurogamer")])
        games, _ = self.plan(sandbox)
        self.assertEqual((games[0]["level"], games[0]["surging_until"]), ("surging", NOON + timedelta(hours=45)))
        sandbox.feed([])   # the mentions have gone, but the surge is on record
        games, _ = self.plan(sandbox, {"games": {"Kuon": {"surging_until": "2026-10-08T09:00Z"}}})
        self.assertEqual(games, [], "a game no longer mentioned anywhere is not tracked")
        sandbox.feed([mention("Kuon", 40, "r/ps2")])
        games, _ = self.plan(sandbox, {"games": {"Kuon": {"surging_until": "2026-10-08T09:00Z"}}})
        self.assertEqual(games[0]["level"], "surging")

    def test_the_real_feed_can_be_planned(self):
        if not (ROOT / "data" / "sentiment_feed.json").exists():
            self.skipTest("no scraped feed")
        pinned, never = ebay_prices.load_watchlist()
        mentions, ever = ebay_prices.load_mentions()
        library, catalogue = ebay_prices.load_library()
        games, left_out = ebay_prices.plan_games(ebay_prices.utc_now(), pinned, never, mentions, ever, library,
                                                 catalogue, {})
        titles = [entry["title"] for entry in games]
        self.assertEqual(len(titles), len(set(titles)))
        names = [entry["search"] for entry in games]
        self.assertEqual(len(names), len(set(names)), "two library spellings of one game are tracked once")
        for entry in games:
            self.assertTrue(all(0 < len(query) + 4 <= ebay_prices.MAX_QUERY_CHARS for query in entry["queries"]))
            self.assertNotIn(entry["search"], entry["siblings"])
        self.assertTrue({entry["title"] for entry in pinned} <= set(titles))
        for entry in games:
            self.assertIn(entry["level"], ebay_prices.CHECK_EVERY_HOURS)
            self.assertTrue(entry["pinned"] or " " in entry["search"]
                            or entry["queries"][0] in ebay_prices.ONE_WORD_TITLES, entry["title"])


class DueTests(unittest.TestCase):
    @staticmethod
    def state(**checked):
        """state(Kuon=("2026-10-06T06:00Z", None)) -> Kuon was checked on the US site only."""
        return {"games": {title.replace("_", " "): {label: {"checked": stamp} for label, stamp in zip(("US", "UK"), stamps) if stamp}
                          for title, stamps in checked.items()}}

    def due(self, games, state=None, now=NOON):
        return [(entry["title"], market_id) for entry, market_id in ebay_prices.due_lookups(games, state or {}, now)]

    def test_a_game_never_checked_is_due_on_both_sites(self):
        self.assertEqual(self.due([game("Kuon")]), [("Kuon", "EBAY_GB"), ("Kuon", "EBAY_US")])

    def test_each_level_waits_its_own_time(self):
        hours = {"normal": 6, "staple": 6, "dormant": 24}
        self.assertEqual({level: ebay_prices.CHECK_EVERY_HOURS[level] for level in hours}, hours)
        self.assertEqual(ebay_prices.CHECK_EVERY_HOURS["surging"], 0, "a surging game is checked on every run")
        for level, wait in hours.items():
            entry = game("Kuon", level=level)
            just_checked = (NOON - timedelta(hours=wait - 1)).strftime(ebay_prices.STAMP_FORMAT)
            long_enough = (NOON - timedelta(hours=wait)).strftime(ebay_prices.STAMP_FORMAT)
            self.assertEqual(self.due([entry], self.state(Kuon=(just_checked, just_checked))), [], level)
            self.assertEqual(len(self.due([entry], self.state(Kuon=(long_enough, long_enough)))), 2, level)
        minute_ago = (NOON - timedelta(minutes=1)).strftime(ebay_prices.STAMP_FORMAT)
        self.assertEqual(len(self.due([game("Kuon", level="surging")], self.state(Kuon=(minute_ago, minute_ago)))), 2)

    def test_a_check_may_come_half_an_hour_early_so_six_hours_does_not_become_seven(self):
        entry = game("Kuon")
        for minutes_ago, expected in ((5 * 60 + 29, 0), (5 * 60 + 31, 2)):
            stamp = (NOON - timedelta(minutes=minutes_ago)).strftime(ebay_prices.STAMP_FORMAT)
            self.assertEqual(len(self.due([entry], self.state(Kuon=(stamp, stamp)))), expected, minutes_ago)

    def test_each_site_keeps_its_own_clock(self):
        hour_ago = (NOON - timedelta(hours=1)).strftime(ebay_prices.STAMP_FORMAT)
        self.assertEqual(self.due([game("Kuon")], self.state(Kuon=(hour_ago, None))), [("Kuon", "EBAY_GB")])

    def test_surging_games_go_first_then_pinned_then_the_longest_overdue(self):
        stamp = lambda hours: (NOON - timedelta(hours=hours)).strftime(ebay_prices.STAMP_FORMAT)   # noqa: E731
        games = [game("Okami"), game("God Hand"), game("Kuon", level="surging"),
                 game("Silent Hill 2", pinned=True), game("Silent Hill 3")]
        state = self.state(Okami=(stamp(7), stamp(7)), God_Hand=(stamp(30), stamp(30)), Kuon=(stamp(1), stamp(1)),
                           Silent_Hill_2=(stamp(6), stamp(6)))
        order = [title for title, market_id in self.due(games, state) if market_id == "EBAY_US"]
        self.assertEqual(order, ["Kuon", "Silent Hill 2", "Silent Hill 3", "God Hand", "Okami"])


class BudgetTests(Quiet):
    def lookups(self, count):
        return [(game(f"Game Number {n}"), "EBAY_US") for n in range(count)]

    def test_a_run_stops_when_its_allowance_of_searches_is_used(self):
        fake = FakeHttp(two_copies)
        run = ebay_prices.check_all(fake, CLIENT_ID, CLIENT_SECRET, self.lookups(10), allowance=7)
        self.assertEqual((len(run["results"]), run["searches"]), (6, 6), "a seventh lookup might need two searches")
        self.assertIn("allowance", run["stopped"])

    def test_a_run_stops_when_its_time_is_up(self):
        clock = iter(range(0, 100000, 150))
        with mock.patch.object(ebay_prices.time, "monotonic", lambda: next(clock)):
            run = ebay_prices.check_all(FakeHttp(two_copies), CLIENT_ID, CLIENT_SECRET, self.lookups(10), allowance=500)
        self.assertEqual(len(run["results"]), 2, "the clock passes seven minutes before the third lookup")
        self.assertIn("time is up", run["stopped"])

    def test_ebay_saying_stop_ends_the_run_but_keeps_what_was_learned(self):
        calls = {"n": 0}

        def answer(params, headers):
            calls["n"] += 1
            return two_copies(params, headers) if calls["n"] <= 3 else (429, {"errors": [{"message": "Limit hit"}]})
        run = ebay_prices.check_all(FakeHttp(answer), CLIENT_ID, CLIENT_SECRET, self.lookups(10), allowance=500)
        self.assertEqual((len(run["results"]), run["searches"]), (3, 6))
        self.assertIn("HTTP 429: Limit hit", run["stopped"])

    def test_the_settings_fit_inside_ebays_daily_allowance(self):
        self.assertLessEqual(ebay_prices.DAILY_SEARCHES, 5000)
        self.assertLessEqual(ebay_prices.MAX_SEARCHES_PER_RUN, ebay_prices.DAILY_SEARCHES)


# ------------------------------------------------------------------ what gets written

class RecordTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = Sandbox(self, pinned=[{"title": "Silent Hill 2"}], feed=[mention("Kuon", 5, "r/ps2")])

    def test_the_first_run_records_every_game_on_both_sites(self):
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        latest = self.sandbox.latest
        self.assertEqual(list(latest["games"]), ["Kuon", "Silent Hill 2"])
        self.assertEqual(latest["games"]["Kuon"], {
            "level": "normal", "mentions": 1,
            "US": {"checked": "2026-10-06T12:00Z", "copies": 2, "lowest": 24.99, "median": 28.25,
                   "postage": 3.49, "recorded": "2026-10-06"},
            "UK": {"checked": "2026-10-06T12:00Z", "copies": 2, "lowest": 24.99, "median": 28.25,
                   "postage": 3.49, "recorded": "2026-10-06"}})
        self.assertIs(latest["games"]["Silent Hill 2"]["pinned"], True)
        self.assertEqual(latest["currencies"], {"US": "USD", "UK": "GBP"})
        self.assertEqual(latest["searches"], {"day": "2026-10-06", "used": 4})
        self.assertIn("Not sold prices", latest["what"])
        self.assertEqual(sorted(self.sandbox.history()), [
            ["2026-10-06T12:00Z", "Kuon", "UK", 2, 24.99, 28.25],
            ["2026-10-06T12:00Z", "Kuon", "US", 2, 24.99, 28.25],
            ["2026-10-06T12:00Z", "Silent Hill 2", "UK", 2, 24.99, 28.25],
            ["2026-10-06T12:00Z", "Silent Hill 2", "US", 2, 24.99, 28.25]])

    def test_what_is_kept_under_data_is_numbers_only(self):
        self.sandbox.run()
        kept = "".join(path.read_text(encoding="utf-8") for path in (self.sandbox.data / "prices").iterdir())
        for forbidden in ("http", "ebay.com", "ebay.co.uk", "/itm/", "boxed", "Good", "2026-10-05T09", "title",
                          "url", "seller", "condition"):
            self.assertNotIn(forbidden, kept, forbidden)
        for secret in SECRETS:
            self.assertNotIn(secret, kept)
        self.assertIn("/itm/", self.sandbox.out.read_text(encoding="utf-8"), "the listings file is where links go")

    def test_nothing_is_asked_again_until_a_game_is_due(self):
        self.sandbox.run()
        self.sandbox.now = NOON + timedelta(hours=2)
        self.sandbox.out.unlink()
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0)
        self.assertIn("Nothing is due, so eBay was not asked.", printed)
        self.assertEqual((fake.token_calls, fake.searches), ([], []))
        self.assertFalse(self.sandbox.out.exists())
        self.assertEqual(len(self.sandbox.history()), 4)

    def test_unchanged_prices_add_no_rows_the_same_day_and_one_row_the_next(self):
        self.sandbox.run()
        self.sandbox.now = NOON + timedelta(hours=7)
        self.sandbox.run()
        self.assertEqual(len(self.sandbox.history()), 4, "same day, same numbers: nothing new to record")
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["US"]["checked"], "2026-10-06T19:00Z")
        self.sandbox.now = NOON + timedelta(hours=14)
        self.sandbox.run()
        history = self.sandbox.history()
        self.assertEqual(len(history), 8, "a new day gets its own row even when nothing moved")
        self.assertEqual(history[-1][0], "2026-10-07T02:00Z")
        self.assertEqual(self.sandbox.latest["searches"], {"day": "2026-10-07", "used": 4})

    def test_a_changed_price_is_recorded_straight_away(self):
        self.sandbox.run()
        self.sandbox.now = NOON + timedelta(hours=7)
        self.sandbox.run(FakeHttp(lambda params, headers: two_copies(params, headers, low=19.99)))
        history = self.sandbox.history()
        self.assertEqual(len(history), 8)
        self.assertIn(["2026-10-06T19:00Z", "Kuon", "US", 2, 19.99, 25.75], history)
        self.assertEqual(self.sandbox.latest["searches"], {"day": "2026-10-06", "used": 8})

    def test_a_game_the_search_cannot_find_is_marked_and_kept_out_of_the_history(self):
        def answer(params, headers):
            if params["q"].startswith("kuon"):
                return page(listing("Some other game PS2", 5, currency="GBP" if "GB" in headers["X-EBAY-C-MARKETPLACE-ID"] else "USD"))
            return two_copies(params, headers)
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["US"], {"checked": "2026-10-06T12:00Z", "unmatched": True})
        self.assertEqual([row[1] for row in self.sandbox.history()], ["Silent Hill 2", "Silent Hill 2"])
        self.assertIn("Kuon [US]: none of the 1 listings eBay returned names this game", printed)
        self.sandbox.now = NOON + timedelta(hours=2)
        self.assertIn("Nothing is due", self.sandbox.run()[1], "it is still only checked at its usual pace")

    def test_no_copies_for_sale_is_recorded_as_none_not_as_zero_pounds(self):
        def answer(params, headers):
            return page() if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB" else two_copies(params, headers)
        self.sandbox.run(FakeHttp(answer))
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["UK"], {
            "checked": "2026-10-06T12:00Z", "copies": 0, "lowest": None, "median": None, "postage": None,
            "recorded": "2026-10-06"})
        self.assertIn(["2026-10-06T12:00Z", "Kuon", "UK", 0, None, None], self.sandbox.history())

    def test_a_failed_lookup_keeps_the_old_figures_and_is_tried_again_next_run(self):
        self.sandbox.run()
        before = self.sandbox.latest["games"]["Kuon"]["UK"]
        self.sandbox.now = NOON + timedelta(hours=7)

        def answer(params, headers):
            if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB" and params["q"].startswith("kuon"):
                return 500, {"errors": [{"message": "oops"}]}
            return two_copies(params, headers)
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["UK"], before)
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["US"]["checked"], "2026-10-06T19:00Z")
        self.sandbox.now = NOON + timedelta(hours=8)
        code, printed, fake = self.sandbox.run()
        self.assertEqual([call["params"]["q"] for call in fake.searches], ["kuon"])
        self.assertEqual(fake.searches[0]["headers"]["X-EBAY-C-MARKETPLACE-ID"], "EBAY_GB")

    def test_history_is_one_row_per_line_and_months_get_their_own_file(self):
        self.sandbox.run()
        text = (self.sandbox.data / "prices" / "2026-10.json").read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual((lines[0], lines[-1], len(lines)), ("[", "]", 6))
        self.assertTrue(all(line.startswith('  ["2026-10-06T12:00Z",') for line in lines[1:-1]))
        self.sandbox.now = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)
        self.sandbox.run()
        self.assertEqual(len(self.sandbox.history("2026-11")), 4)
        self.assertEqual(len(self.sandbox.history("2026-10")), 4)

    def test_a_surging_game_is_checked_on_every_run_and_the_log_says_so(self):
        self.sandbox.feed([mention("Kuon", 20, "r/ps2"), mention("Kuon", 3, "Eurogamer")])
        code, printed, fake = self.sandbox.run()
        self.assertIn("  surging: Kuon\n", printed)
        self.assertIn("  Kuon [US]: 2 of 2 listings counted (surging)\n", printed)
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["level"], "surging")
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["surging_until"], "2026-10-08T09:00Z")
        self.assertEqual([call["params"]["q"] for call in fake.searches[:2]], ["kuon", "kuon"], "surging goes first")
        self.sandbox.now = NOON + timedelta(hours=1)
        code, printed, fake = self.sandbox.run()
        self.assertEqual([call["params"]["q"] for call in fake.searches], ["kuon", "kuon"])


class WeekTests(unittest.TestCase):
    """Beside each median, the median of a week before, for the change the dashboard shows."""

    def setUp(self):
        self.sandbox = Sandbox(self, feed=[mention("Kuon", 5, "r/ps2")])

    def kuon(self, site="UK"):
        return self.sandbox.latest["games"]["Kuon"][site]

    def test_a_week_later_each_median_carries_the_one_recorded_a_week_before(self):
        self.sandbox.run()
        self.assertNotIn("week", self.kuon(), "nothing a week old yet")
        self.sandbox.now = NOON + timedelta(days=6)
        self.sandbox.run(FakeHttp(lambda params, headers: two_copies(params, headers, low=19.99)))
        self.assertNotIn("week", self.kuon(), "six days is not a week")
        self.sandbox.now = NOON + timedelta(days=7)
        self.sandbox.run(FakeHttp(lambda params, headers: two_copies(params, headers, low=29.99)))
        self.assertEqual(self.kuon(), {"checked": "2026-10-13T12:00Z", "copies": 2, "lowest": 29.99, "median": 30.75,
                                       "postage": 3.49, "recorded": "2026-10-13",
                                       "week": {"checked": "2026-10-06T12:00Z", "median": 28.25}})
        self.assertEqual(self.kuon("US")["week"], {"checked": "2026-10-06T12:00Z", "median": 28.25})
        self.sandbox.now = NOON + timedelta(days=7, hours=1)
        code, printed, fake = self.sandbox.run()
        self.assertIn("Nothing is due", printed)
        self.assertEqual(self.kuon()["week"]["median"], 28.25, "a run that asks nobody leaves the file alone")

    def test_the_latest_figure_from_up_to_two_days_further_back_is_used_and_no_older(self):
        self.sandbox.write("data/prices/2026-10.json", [
            ["2026-10-03T12:00Z", "Kuon", "UK", 4, 10.0, 12.5],     # ten days before: too old to be "a week"
            ["2026-10-05T11:00Z", "Kuon", "UK", 4, 10.0, 14.0],     # eight days and a hour: the one to use
            ["2026-10-04T12:00Z", "Kuon", "UK", 4, 10.0, 13.0],     # older, though written later
            ["2026-10-07T12:00Z", "Kuon", "UK", 4, 10.0, 99.0],     # six days: too recent
            ["2026-10-05T11:00Z", "Kuon", "US", 4, 10.0, 15.0]])
        self.sandbox.now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
        self.sandbox.feed([mention("Kuon", 5, "r/ps2", now=self.sandbox.now)])
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertEqual(self.kuon()["week"], {"checked": "2026-10-05T11:00Z", "median": 14.0})
        self.assertEqual(self.kuon("US")["week"], {"checked": "2026-10-05T11:00Z", "median": 15.0})
        self.sandbox.write("data/prices/2026-10.json", [["2026-10-03T12:00Z", "Kuon", "UK", 4, 10.0, 12.5]])
        self.sandbox.now += timedelta(hours=7)
        self.sandbox.run()
        self.assertNotIn("week", self.kuon(), "nothing from the right days: no change shown")

    def test_early_in_a_month_the_week_before_comes_from_the_month_before(self):
        self.sandbox.write("data/prices/2026-09.json", [["2026-09-29T12:00Z", "Kuon", "UK", 3, 20.0, 25.0]])
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertEqual(self.kuon()["week"], {"checked": "2026-09-29T12:00Z", "median": 25.0})
        self.assertNotIn("week", self.kuon("US"), "each site has its own history")
        self.assertEqual(self.sandbox.history("2026-09"), [["2026-09-29T12:00Z", "Kuon", "UK", 3, 20.0, 25.0]],
                         "the month before is only read")

    def test_no_copies_a_week_ago_or_none_now_means_no_change_to_show(self):
        self.sandbox.write("data/prices/2026-09.json", [["2026-09-29T12:00Z", "Kuon", "UK", 0, None, None],
                                                        ["2026-09-29T12:00Z", "Kuon", "US", 3, 20.0, 25.0]])
        self.sandbox.run(FakeHttp(lambda params, headers: page() if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
                                  else two_copies(params, headers)))
        self.assertNotIn("week", self.kuon())
        self.assertNotIn("week", self.kuon("US"))

    def test_a_damaged_month_before_costs_the_changes_not_the_run(self):
        (self.sandbox.data / "prices").mkdir(parents=True, exist_ok=True)
        (self.sandbox.data / "prices" / "2026-09.json").write_text("[not json", encoding="utf-8")
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertNotIn("week", self.kuon())
        self.assertEqual((self.sandbox.data / "prices" / "2026-09.json").read_text(encoding="utf-8"), "[not json")

    def test_rows_in_another_shape_are_passed_over(self):
        self.sandbox.write("data/prices/2026-09.json", [
            "junk", ["2026-09-29T12:00Z", "Kuon", "UK"], ["yesterday", "Kuon", "UK", 3, 20.0, 25.0],
            ["2026-09-29T12:00Z", "Kuon", "UK", 3, 20.0, True], ["2026-09-29T12:00Z", "Kuon", "UK", 3, 20.0, "25"],
            ["2026-09-29T12:00Z", "Kuon", "US", 3, 20.0, 26.0]])
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertNotIn("week", self.kuon())
        self.assertEqual(self.kuon("US")["week"], {"checked": "2026-09-29T12:00Z", "median": 26.0})

    def test_nine_days_is_the_furthest_back_and_the_same_price_is_kept_as_no_change(self):
        self.sandbox.write("data/prices/2026-09.json", [
            ["2026-09-27T11:59Z", "Kuon", "UK", 3, 20.0, 99.0],    # nine days and a minute: too old
            ["2026-09-27T12:00Z", "Kuon", "US", 3, 20.0, 28.25]])  # nine days exactly: used, same as now
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertNotIn("week", self.kuon())
        self.assertEqual(self.kuon("US")["week"], {"checked": "2026-09-27T12:00Z", "median": 28.25},
                         "an unchanged price is kept, for the dashboard to say so")

    def test_the_month_before_is_found_on_the_first_of_a_month_and_in_january(self):
        for now, month, row_time in ((datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc), "2026-09", "2026-09-24T12:00Z"),
                                     (datetime(2027, 1, 5, 12, 0, tzinfo=timezone.utc), "2026-12", "2026-12-29T12:00Z")):
            with self.subTest(month=month):
                sandbox = Sandbox(self, feed=[mention("Kuon", 5, "r/ps2", now=now)])
                sandbox.now = now
                sandbox.write(f"data/prices/{month}.json", [[row_time, "Kuon", "UK", 3, 20.0, 25.0]])
                code, printed, fake = sandbox.run()
                self.assertEqual(code, 0, printed)
                self.assertEqual(sandbox.latest["games"]["Kuon"]["UK"]["week"], {"checked": row_time, "median": 25.0})

    def test_the_title_may_be_spelt_another_way_from_one_week_to_the_next(self):
        self.sandbox.write("data/prices/2026-09.json", [["2026-09-29T12:00Z", "KUON", "UK", 3, 20.0, 25.0]])
        self.sandbox.run()
        self.assertEqual(self.kuon()["week"]["median"], 25.0)

    def test_figures_no_browser_can_read_never_reach_the_file(self):
        (self.sandbox.data / "prices").mkdir(parents=True, exist_ok=True)
        (self.sandbox.data / "prices" / "2026-09.json").write_text(
            '[["2026-09-29T12:00Z","Kuon","UK",3,20.0,Infinity],["2026-09-29T12:00Z","Kuon","US",3,20.0,NaN]]', encoding="utf-8")
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        text = (self.sandbox.data / "prices" / "latest.json").read_text(encoding="utf-8")
        self.assertNotIn("Infinity", text)
        self.assertNotIn("NaN", text)

    def test_a_figure_from_a_week_before_goes_when_it_no_longer_holds_and_odd_entries_pass(self):
        latest = {"games": {
            "Kuon": {"UK": {"checked": "2026-10-13T12:00Z", "copies": 2, "median": 30.0,
                            "week": {"checked": "2026-10-06T12:00Z", "median": 1.0}},
                     "US": {"checked": "not a time", "copies": 2, "median": 30.0},
                     "level": "normal"}}}
        rows = [["2026-10-06T12:00Z", 7, "UK", 3, 20.0, 25.0], ["2026-10-06T12:00Z", "Kuon", 7, 3, 20.0, 25.0],
                ["2026-10-06T12:00Z", "Kuon", "US", 3, 20.0, 25.0]]
        ebay_prices.add_week_before(latest, rows)
        self.assertNotIn("week", latest["games"]["Kuon"]["UK"], "no row for it any more: the old figure goes")
        self.assertNotIn("week", latest["games"]["Kuon"]["US"], "a check time that cannot be read gets none")


class RareListTests(unittest.TestCase):
    """The Rarest page: each list priced once a day on its own region's site only."""

    def setUp(self):
        self.sandbox = Sandbox(self, feed=[mention("Silent Hill 2", 5, "r/ps2")])

    def lists(self, pal=(), us=()):
        self.sandbox.write("rare_games.json", {"lists": {"PAL": list(pal), "US": list(us)}})

    def test_without_the_file_nothing_changes(self):
        self.assertEqual(ebay_prices.load_rare(self.sandbox.root / "rare_games.json"), ([], []))
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertNotIn("rare", self.sandbox.latest)
        self.assertNotIn("Rarest", printed)

    def test_a_broken_file_or_entry_is_left_out_and_named_but_never_stops_the_run(self):
        (self.sandbox.root / "rare_games.json").write_text("{not json", encoding="utf-8")
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertIn("Rarest page, left out: rare_games.json cannot be read", printed)
        self.assertEqual(self.sandbox.latest["games"]["Silent Hill 2"]["UK"]["copies"], 2, "the other games are priced")
        self.lists(pal=[{"title": ""}, {"title": "Gun Club", "exclude": "nra"}, {"title": "Kuon"}])
        entries, problems = ebay_prices.load_rare(self.sandbox.root / "rare_games.json")
        self.assertEqual([entry["title"] for entry in entries], ["Kuon"])
        self.assertEqual(len(problems), 2, problems)
        self.sandbox.write("rare_games.json", {"lists": {"EU": []}})
        self.assertEqual(ebay_prices.load_rare(self.sandbox.root / "rare_games.json")[0], [])

    def test_each_list_is_priced_on_its_own_site_once_a_day(self):
        self.lists(pal=[{"rank": 1, "title": "Sengoku Anthology"}, {"rank": 2, "title": "Kuon"}],
                   us=[{"rank": 1, "title": "Kuon"}, {"rank": 2, "title": "Chulip"}])
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        asked = {(call["headers"]["X-EBAY-C-MARKETPLACE-ID"], call["params"]["q"]) for call in fake.searches}
        self.assertIn(("EBAY_GB", "sengoku anthology"), asked)
        self.assertNotIn(("EBAY_US", "sengoku anthology"), asked, "a PAL rarity is not looked for in America")
        self.assertIn(("EBAY_US", "chulip"), asked)
        self.assertNotIn(("EBAY_GB", "chulip"), asked)
        self.assertTrue({("EBAY_GB", "kuon"), ("EBAY_US", "kuon")} <= asked, "on both lists: both sites")
        self.assertEqual(sum(1 for site, q in asked if q == "kuon"), 2, "and once each")
        latest = self.sandbox.latest
        self.assertEqual(latest["rare"], {"PAL": {"Sengoku Anthology": "Sengoku Anthology", "Kuon": "Kuon"},
                                          "US": {"Kuon": "Kuon", "Chulip": "Chulip"}})
        sengoku = latest["games"]["Sengoku Anthology"]
        self.assertEqual((sengoku["level"], sengoku["sites"], sengoku["UK"]["copies"]), ("rare", ["UK"], 2))
        self.assertNotIn("US", sengoku)
        self.assertEqual(latest["games"]["Kuon"]["sites"], ["US", "UK"])
        self.assertIn("Rarest page: 4 entries, 2 PAL, 2 US; 3 of the games are priced for it alone.", printed)
        self.assertIn(["2026-10-06T12:00Z", "Sengoku Anthology", "UK", 2, 24.99, 28.25], self.sandbox.history())

        self.sandbox.now = NOON + timedelta(hours=7)
        code, printed, fake = self.sandbox.run()
        self.assertFalse({call["params"]["q"] for call in fake.searches} & {"sengoku anthology", "kuon", "chulip"},
                         "not again the same day")
        self.assertEqual(self.sandbox.latest["rare"]["PAL"]["Kuon"], "Kuon", "the lists stay in the file between checks")
        self.sandbox.now = NOON + timedelta(hours=24)
        code, printed, fake = self.sandbox.run()
        self.assertIn("sengoku anthology", {call["params"]["q"] for call in fake.searches}, "the next day")

    def test_a_game_the_feed_already_tracks_is_not_looked_up_twice(self):
        self.lists(pal=[{"rank": 1, "title": "Silent Hill 2"}, {"rank": 2, "title": "Project Zero 2", "search": "project zero 2"}],
                   us=[{"rank": 1, "title": "Silent Hill 2"}])
        self.sandbox.write("ebay_watchlist.json", {"games": [], "never": [], "regional_names": {"UK": [{"from": "Fatal Frame", "to": "Project Zero"}]}})
        self.sandbox.write("data/ps2_database.json", Sandbox.LIBRARY + ["Fatal Frame 2"])
        self.sandbox.feed([mention("Silent Hill 2", 5, "r/ps2"), mention("Fatal Frame 2", 4, "r/ps2")])
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        queries = [(call["headers"]["X-EBAY-C-MARKETPLACE-ID"], call["params"]["q"]) for call in fake.searches]
        self.assertEqual(queries.count(("EBAY_GB", "silent hill 2")), 1)
        self.assertEqual(queries.count(("EBAY_GB", "project zero 2")), 1, "the UK name the feed's game is searched under")
        latest = self.sandbox.latest
        self.assertEqual(latest["rare"]["PAL"], {"Silent Hill 2": "Silent Hill 2", "Project Zero 2": "Fatal Frame 2"})
        self.assertNotIn("sites", latest["games"]["Silent Hill 2"], "still priced on both sites")
        self.assertEqual(latest["games"]["Silent Hill 2"]["level"], "normal")
        self.assertNotIn("Project Zero 2", latest["games"])

    def test_the_other_regions_name_never_borrows_a_game_searched_under_that_name(self):
        self.lists(pal=[{"rank": 1, "title": "Kaido Racer 2", "other_title": "Tokyo Xtreme Racer: Drift 2"}])
        self.sandbox.write("data/ps2_database.json", Sandbox.LIBRARY + ["Tokyo Xtreme Racer: Drift 2"])
        self.sandbox.feed([mention("Tokyo Xtreme Racer: Drift 2", 4, "r/ps2")])
        code, printed, fake = self.sandbox.run()
        asked = {(call["headers"]["X-EBAY-C-MARKETPLACE-ID"], call["params"]["q"]) for call in fake.searches}
        self.assertIn(("EBAY_GB", "kaido racer 2"), asked)
        self.assertEqual(self.sandbox.latest["rare"]["PAL"], {"Kaido Racer 2": "Kaido Racer 2"})

    def test_an_edition_needs_its_own_words_and_is_never_the_ordinary_game(self):
        self.lists(us=[{"rank": 1, "title": "Scarface: The World Is Yours Collector's Edition", "search": "scarface",
                        "require": ["collectors"]},
                       {"rank": 2, "title": "Shin Megami Tensei: Persona 3", "search": "persona 3", "exclude": ["fes"]}])
        self.sandbox.feed([mention("Scarface", 3, "r/ps2")])
        self.sandbox.write("data/ps2_database.json", Sandbox.LIBRARY + ["Scarface"])

        def answer(params, headers):
            if params["q"] == "scarface collectors":
                return page(listing("Scarface The World Is Yours Collector's Edition PS2", 120, item_id=1),
                            listing("Scarface PS2 complete", 9, item_id=2))
            if params["q"] == "persona 3":
                return page(listing("Shin Megami Tensei Persona 3 PS2", 60, item_id=3),
                            listing("Persona 3 FES PS2", 40, item_id=4))
            return two_copies(params, headers)
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        games = self.sandbox.latest["games"]
        edition = games["Scarface: The World Is Yours Collector's Edition"]
        self.assertEqual((edition["US"]["copies"], edition["US"]["median"]), (1, 120.0))
        self.assertEqual(games["Shin Megami Tensei: Persona 3"]["US"]["median"], 60.0, "FES is left out")
        self.assertEqual(self.sandbox.latest["rare"]["US"]["Scarface: The World Is Yours Collector's Edition"],
                         "Scarface: The World Is Yours Collector's Edition")
        self.assertEqual(games["Scarface"]["US"]["copies"], 2, "the ordinary game keeps its own figures")
        self.assertNotIn("120", "\n".join(line for line in printed.splitlines() if "Rarest" in line))

    def test_a_game_on_both_lists_leaves_out_what_either_list_leaves_out(self):
        self.lists(pal=[{"rank": 1, "title": "Wild Arms 5"}],
                   us=[{"rank": 1, "title": "Wild Arms 5", "exclude": ["anniversary"]}])

        def answer(params, headers):
            currency = "GBP" if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB" else "USD"
            return page(listing("Wild Arms 5 PS2", 50, currency=currency, item_id=1),
                        listing("Wild Arms 5 10th Anniversary Edition PS2", 150, currency=currency, item_id=2))
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        entry = self.sandbox.latest["games"]["Wild Arms 5"]
        self.assertEqual(entry["sites"], ["US", "UK"])
        self.assertEqual((entry["US"]["copies"], entry["UK"]["copies"]), (1, 1))

    def test_a_one_word_name_that_is_an_ordinary_word_is_not_priced(self):
        self.lists(pal=[{"title": "Obscure"}, {"title": "Kuon"}, {"title": "Obscure Edition", "search": "obscure", "require": ["edition"]}])
        entries, problems = ebay_prices.load_rare(self.sandbox.root / "rare_games.json")
        self.assertEqual([entry["title"] for entry in entries], ["Kuon", "Obscure Edition"])
        self.assertEqual(problems, ['PAL "Obscure": not priced, "obscure" is an ordinary word'])
        game_ = dict(game("Obscure Edition", search="obscure"), require=["edition"])
        self.assertEqual(ebay_prices.reject_reason(listing("Kuon PS2 PAL rare obscure horror game", 300, "GBP"), game_, GB, False), "other_game")

    def test_an_edition_may_come_with_an_art_book_or_a_plush(self):
        self.lists(us=[{"rank": 1, "title": "Raiho Special Edition", "search": "king abaddon", "require": ["raiho"],
                        "allow": ["plush", "art book"]},
                       {"rank": 2, "title": "Wrong Thing", "allow": ["anything goes"]}])
        entries, problems = ebay_prices.load_rare(self.sandbox.root / "rare_games.json")
        self.assertEqual(len(problems), 1, "only junk phrases can be allowed")
        raiho = dict(game("Raiho Special Edition", search="king abaddon"), require=["raiho"], allow=entries[0]["allow"])
        plush = listing("Devil Summoner 2 Raidou Kuzunoha vs King Abaddon Raiho Edition w/ Plush PS2", 150)
        self.assertIsNone(ebay_prices.reject_reason(plush, raiho, US, False))
        self.assertEqual(ebay_prices.reject_reason(plush, dict(raiho, allow=[]), US, False), "not_a_copy")
        self.assertEqual(ebay_prices.reject_reason(listing("King Abaddon Raiho Edition strategy guide PS2", 20), raiho, US, False),
                         "not_a_copy", "what is not allowed still leaves a listing out")
        self.assertEqual(ebay_prices.reject_reason(listing("King Abaddon Raiho Edition Plush only PS2", 20), raiho, US, False),
                         "not_a_copy", "the extra on its own is not a copy")
        for title in ("Raiho Edition King Abaddon + Art Book PS2", "King Abaddon Raiho Edition, includes the plush, PS2",
                      "King Abaddon Raiho Edition & plush PS2"):
            self.assertIsNone(ebay_prices.reject_reason(listing(title, 150), raiho, US, False), title)

    def test_fifa_13_is_never_another_years_fifa(self):
        entries, _ = ebay_prices.load_rare(ROOT / "rare_games.json")
        fifa = next(entry for entry in entries if entry["title"] == "FIFA Soccer 13")
        game_ = dict(game("FIFA Soccer 13", search="fifa"), require=fifa["require"], exclude=fifa["exclude"])
        for title, reason in (("FIFA Soccer 13 (Sony PlayStation 2, 2012) CIB", None), ("FIFA 13 PS2 Legacy Edition", None),
                              ("FIFA 13 and FIFA 14 PS2", "not_a_copy"), ("FIFA Soccer 14 PS2 Complete - 13 available", "not_a_copy"),
                              ("FIFA 12 PS2", "other_game")):
            self.assertEqual(ebay_prices.reject_reason(listing(title, 90), game_, US, False), reason, title)

    def test_a_shorter_search_still_finds_the_tracked_game_by_its_name_on_that_site(self):
        self.lists(pal=[{"rank": 1, "title": "Project Zero 2: Crimson Butterfly", "search": "project zero 2"}])
        self.sandbox.write("ebay_watchlist.json", {"games": [], "never": [], "regional_names": {"UK": [{"from": "Fatal Frame", "to": "Project Zero"}]}})
        self.sandbox.write("data/ps2_database.json", Sandbox.LIBRARY + ["Fatal Frame 2: Crimson Butterfly"])
        self.sandbox.feed([mention("Fatal Frame 2: Crimson Butterfly", 4, "r/ps2")])
        code, printed, fake = self.sandbox.run()
        queries = [call["params"]["q"] for call in fake.searches if call["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB"]
        self.assertEqual(queries, ["project zero 2 crimson butterfly"], "one UK lookup, not two")
        self.assertEqual(self.sandbox.latest["rare"]["PAL"], {"Project Zero 2: Crimson Butterfly": "Fatal Frame 2: Crimson Butterfly"})

    def test_an_entry_never_takes_the_place_of_a_tracked_game_with_its_title(self):
        games = [game("Scarface")]
        entry = {"list": "US", "title": "Scarface", "other_title": None, "search": "scarface", "queries": ["scarface collectors"],
                 "require": ["collectors"], "exclude": [], "allow": []}
        placed = ebay_prices.add_rare_games(games, [entry], [])
        self.assertEqual(placed["US"], {}, "left off rather than writing over the tracked game's figures")
        self.assertEqual([entry["title"] for entry in games], ["Scarface"])
        self.assertNotIn("require", games[0])

    def test_the_librarys_other_spelling_of_the_same_game_is_not_another_game(self):
        self.sandbox.write("data/ps2_database.json", Sandbox.LIBRARY + ["R.A.D. Robot Alchemic Drive", "Robot Alchemic Drive Turbo"])
        _, catalogue = ebay_prices.load_library()
        entry = {"list": "US", "title": "Robot Alchemic Drive", "other_title": None, "search": "robot alchemic drive",
                 "queries": ["robot alchemic drive"], "require": [], "exclude": [], "allow": []}
        games = []
        ebay_prices.add_rare_games(games, [entry], catalogue)
        self.assertEqual(games[0]["siblings"], ["robot alchemic drive turbo"])
        self.assertIsNone(ebay_prices.reject_reason(listing("R.A.D. Robot Alchemic Drive PS2 complete", 200), games[0], US, False))

    def test_rare_lookups_wait_behind_the_games_the_feed_names(self):
        self.lists(pal=[{"rank": 1, "title": "Sengoku Anthology"}])
        games = [game("Silent Hill 2"), dict(game("Sengoku Anthology", level="rare"), sites=["EBAY_GB"])]
        order = [(entry["title"], market) for entry, market in ebay_prices.due_lookups(games, {}, NOON)]
        self.assertEqual(order[-1], ("Sengoku Anthology", "EBAY_GB"))
        self.assertEqual(len(order), 3)

    def test_the_committed_lists_are_complete_and_sourced(self):
        raw = json.loads((ROOT / "rare_games.json").read_text(encoding="utf-8"))
        entries, problems = ebay_prices.load_rare(ROOT / "rare_games.json")
        self.assertEqual(problems, [f'{name} "{title}": not priced, "{word}" is an ordinary word' for name, title, word in (
            ("PAL", "Buccaneer", "buccaneer"), ("PAL", "Jello", "jello"), ("PAL", "Hanuman: The Boy Warrior", "hanuman"),
            ("PAL", "Nightshade", "nightshade"),
            ("PAL", "Obscure", "obscure"), ("US", "Obscure", "obscure"))])
        for name in ("PAL", "US"):
            rows = raw["lists"][name]
            self.assertGreaterEqual(len(rows), 100, name)
            self.assertEqual([row["rank"] for row in rows], list(range(1, len(rows) + 1)), name)
            self.assertEqual(len({ebay_prices.key_of(row["title"]) for row in rows}), len(rows), f"{name}: no game twice")
            for row in rows:
                self.assertTrue(row["evidence"], row["title"])
                for proof in row["evidence"]:
                    self.assertTrue(proof["source"].startswith("https://"), row["title"])
                    self.assertRegex(proof["date"], r"20\d\d-\d\d", row["title"])
                self.assertLessEqual(set(row["flags"]), set(raw["flags"]), row["title"])
                cib = row["value_usd"]["cib"]
                self.assertTrue(isinstance(cib, (int, float)) and cib > 0, row["title"])
            values = [row["value_usd"]["cib"] for row in rows]
            self.assertEqual(values, sorted(values, reverse=True), f"{name} is ranked by the value it states")
        self.assertEqual(len(entries), sum(len(rows) for rows in raw["lists"].values()) - len(problems))


class ConsoleTests(unittest.TestCase):
    """The Rarest page's consoles: priced once a day on both sites, from sellers anywhere."""

    PEARL = {"rank": 1, "name": "PS2 Pearl White (SCPH-50000 PW)",
             "search": {"queries": ["ps2 pearl white", "scph-50000 pw"], "require_any": ["pearl", "50000 pw"],
                        "exclude": ["slim"], "category": "consoles"}}

    def setUp(self):
        self.sandbox = Sandbox(self, feed=[mention("Silent Hill 2", 5, "r/ps2")])

    def consoles(self, *rows):
        self.sandbox.write("rare_consoles.json", {"consoles": list(rows)})

    def test_without_the_file_nothing_changes(self):
        self.assertEqual(ebay_prices.load_consoles(self.sandbox.root / "rare_consoles.json"), ([], []))
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertEqual(set(self.sandbox.latest["games"]), {"Silent Hill 2"})

    def test_entries_that_cannot_be_used_are_named_and_left_out(self):
        self.consoles(self.PEARL, {"rank": 2, "name": "No Words", "search": {"queries": ["ps2 thing"]}},
                      {"rank": 3, "name": "Prototype", "price": False},
                      {"rank": 4, "name": "Bad Site", "sites": ["JP"], "search": {"queries": ["x y"], "require": ["y"]}},
                      {"rank": 5, "name": "Bad Category", "search": {"queries": ["x y"], "require": ["y"], "category": "tvs"}},
                      {"rank": 6, "name": "Too Many", "search": {"queries": ["a b", "c d", "e f", "g h"], "require": ["b"]}},
                      {"name": ""})
        consoles, problems = ebay_prices.load_consoles(self.sandbox.root / "rare_consoles.json")
        self.assertEqual([console["title"] for console in consoles], ["PS2 Pearl White (SCPH-50000 PW)"])
        self.assertEqual(len(problems), 5, problems)
        self.assertFalse(any("Prototype" in problem for problem in problems), "not priced on purpose is no problem")
        (self.sandbox.root / "rare_consoles.json").write_text("[", encoding="utf-8")
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        self.assertIn("Rarest page, left out: rare_consoles.json cannot be read", printed)

    def test_a_console_is_searched_among_consoles_from_sellers_anywhere_on_both_sites(self):
        self.consoles(self.PEARL, dict(self.PEARL, rank=2, name="PS2 Slim Pink (Europe)", sites=["UK"],
                                       search={"queries": ["ps2 slim pink"], "require": ["pink"], "require_any": ["slim"],
                                               "category": "any"}))

        def answer(params, headers):
            uk = headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB"
            currency = "GBP" if uk else "USD"
            if "pearl" in params["q"] or "50000" in params["q"]:
                return page(listing("Sony PS2 Pearl White SCPH-50000 PW console Japan boxed", 180, currency, item_id=1),
                            listing("PS2 Pearl White console with 2 controllers bundle", 140, currency, item_id=2),
                            listing("PS2 Pearl White custom shell housing", 30, currency, item_id=3),
                            listing("PS2 Pearl White for parts not working", 20, currency, item_id=4),
                            listing("PS2 Slim Pearl White", 90, currency, item_id=5),
                            listing("PS3 Pearl White", 99, currency, item_id=6),
                            listing("PS2 black SCPH-50000", 40, currency, item_id=7))
            return page(listing("PS2 Slim Pink console PAL", 70, currency, item_id=8))
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        pearl = [call for call in fake.searches if "pearl" in call["params"]["q"] or "50000" in call["params"]["q"]]
        self.assertEqual({call["headers"]["X-EBAY-C-MARKETPLACE-ID"] for call in pearl}, {"EBAY_US", "EBAY_GB"})
        self.assertEqual(len(pearl), 4, "two searches on each site, once")
        for call in pearl:
            self.assertEqual(call["params"]["category_ids"], ebay_prices.CONSOLE_CATEGORY_ID)
            self.assertNotIn("itemLocationCountry", call["params"]["filter"], "sellers anywhere: most are in Japan")
            self.assertNotIn("aspect_filter", call["params"])
            self.assertIn("buyingOptions:{FIXED_PRICE}", call["params"]["filter"])
            self.assertNotIn("7000", call["params"]["filter"], "never for parts")
        pink = [call for call in fake.searches if call["params"]["q"] == "ps2 slim pink"]
        self.assertEqual([call["headers"]["X-EBAY-C-MARKETPLACE-ID"] for call in pink], ["EBAY_GB"])
        self.assertNotIn("category_ids", pink[0]["params"], "a console with \"category\": \"any\" is looked for everywhere")
        games = self.sandbox.latest["games"]
        entry = games["PS2 Pearl White (SCPH-50000 PW)"]
        self.assertEqual((entry["kind"], entry["level"], entry["sites"]), ("console", "rare", ["US", "UK"]))
        self.assertEqual((entry["US"]["copies"], entry["US"]["median"]), (2, 160.0), "a bundle with controllers is a console")
        self.assertEqual(games["PS2 Slim Pink (Europe)"]["sites"], ["UK"])
        self.assertIn("Rarest page: 2 consoles priced.", printed)
        self.assertNotIn("160", printed, "never a price in the log")
        self.assertIn(["2026-10-06T12:00Z", "PS2 Pearl White (SCPH-50000 PW)", "UK", 2, 140.0, 160.0], self.sandbox.history())
        row = next(row for row in self.sandbox.snapshot["games"] if row["title"].startswith("PS2 Pearl"))
        self.assertIn("_nkw=ps2%20pearl%20white&_sacat=139971&LH_BIN=1", row["markets"]["EBAY_US"]["search_url"])

        self.sandbox.now = NOON + timedelta(hours=7)
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertFalse([call for call in fake.searches if "pearl" in call["params"]["q"]], "once a day")

    def test_a_console_never_takes_a_games_name_and_figures(self):
        games = [game("Silent Hill 2")]
        consoles, _ = ebay_prices.load_consoles(self.sandbox.root / "missing.json")
        clash = {"title": "Silent Hill 2", "key": "silent hill 2", "kind": "console"}
        self.assertEqual(ebay_prices.add_consoles(games, [clash, dict(clash)]), 0)
        self.assertEqual([entry.get("kind") for entry in games], [None])
        one = {"title": "PS2 Ocean Blue", "key": "ps2 ocean blue", "kind": "console"}
        self.assertEqual(ebay_prices.add_consoles(games, [one, dict(one)]), 1, "nor is one console added twice")

    def test_the_committed_rules_tell_the_console_from_bundles_parts_and_other_colours(self):
        consoles, _ = ebay_prices.load_consoles(ROOT / "rare_consoles.json")

        def verdict(name_part, title):
            console = next(entry for entry in consoles if name_part in entry["title"])
            return ebay_prices.console_reject_reason(listing(title, 100), console, US)
        for name_part, title, expected in (
                ("Final Fantasy XII", "Sony PS2 Slim Console SCPH-75003 Bundle Final Fantasy XII Kingdom Hearts", "other_game"),
                ("Final Fantasy XII", "PS2 Slim SCPH-75000 FF Final Fantasy XII pack Japan", None),
                ("Prologue", "Sony PS2 Fat Console Black SCPH-50003 + Gran Turismo 4 Prologue + 2 controllers", "other_game"),
                ("Ceramic White fat", "PS2 Fat Ceramic White SCPH-55000 GT Gran Turismo 4 Prologue pack", "not_a_copy"),
                ("Ocean Blue", "PS2 Fat Console Black SCPH-39003 with Ocean Blue DualShock 2 controller", "not_a_copy"),
                ("Ocean Blue", "PS2 Controller Ocean Blue DualShock 2", "not_a_copy"),
                ("Ocean Blue", "PS2 Ocean Blue SCPH-37000 L boxed with controller", None),
                ("Midnight Blue", "Sony PS2 Slim Black + Midnight Blue controller", "not_a_copy"),
                ("Midnight Blue", "PS2 Midnight Blue SCPH-50000 MB/NH with replacement laser fitted", None),
                ("250 GB", "Sony PSX DESR-7000 Remote Control RMT-P001", "not_a_copy"),
                ("250 GB", "Sony PSX DESR-7000 with remote and cables", None),
                ("160 GB", "Sony PSX DESR-5000 power cord AC adapter", "not_a_copy"),
                ("Bravia", "Sony Bravia KDL-22PX300 remote control", "not_a_copy"),
                ("Bravia", "Sony Bravia KDL-22PX300 TV with remote, built in PS2", None),
                ("DTL-T10000", "Sony PS2 DTL-T10000 TOOL hard drive HDD", "not_a_copy"),
                ("Silver limited edition (US", "PS2 Slim Satin Silver SCPH-79001 limited edition USA", None),
                ("Pearl White", "PS2 Pearl White console for parts or repair", "not_a_copy"),
                ("Pearl White", "PS2 Pearl White SCPH-50000 PW custom painted", "not_a_copy"),
                ("Pearl White", "PS2 Pearl White SCPH-50000 PW and PS3 bundle", "other_platform")):
            self.assertEqual(verdict(name_part, title), expected, title)

    def test_game_searches_are_untouched_by_the_console_settings(self):
        self.assertEqual(ebay_prices.search_url("EBAY_US", "silent hill 2"),
                         ebay_prices.search_url("EBAY_US", "silent hill 2", console=None))
        self.assertIn("aspect_filter", ebay_prices.search_url("EBAY_US", "silent hill 2"))
        self.assertIn("itemLocationCountry", ebay_prices.search_url("EBAY_US", "silent hill 2"))

    def test_the_committed_list_is_sourced_and_every_priced_entry_can_be_searched(self):
        raw = json.loads((ROOT / "rare_consoles.json").read_text(encoding="utf-8"))
        consoles, problems = ebay_prices.load_consoles(ROOT / "rare_consoles.json")
        self.assertEqual(problems, [])
        rows = raw["consoles"]
        self.assertEqual([row["rank"] for row in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(len(consoles), sum(1 for row in rows if row.get("price", True)))
        self.assertGreaterEqual(len(consoles), 30)
        for row in rows:
            self.assertTrue(row["evidence"], row["name"])
            for proof in row["evidence"]:
                self.assertTrue(proof["source"].startswith("https://"), row["name"])
            if row.get("price") is False:
                self.assertTrue(row["not_priced_because"], row["name"])
            value = row.get("value")
            if value and value.get("usd") is not None:
                self.assertGreater(value["usd"], 0)
                self.assertTrue(value["what"] and value["date"], row["name"])
        self.assertFalse({row["name"] for row in rows} & set(json.loads((ROOT / "rare_games.json").read_text(encoding="utf-8"))["lists"]),
                         "no console shares a name with a list")


class PriceIndexTests(unittest.TestCase):
    """The PS2 price index: 100 on the first day, moved by how each game's median moved."""

    @staticmethod
    def day(date, prices, site="UK", copies=5, hour="12:00"):
        return [[f"{date}T{hour}Z", title, site, copies, price - 1, price] for title, price in prices.items()]

    GAMES = {f"Game {n}": 10.0 for n in range(12)}

    def test_it_moves_by_the_geometric_mean_of_each_games_move(self):
        rows = self.day("2026-10-06", self.GAMES) + self.day("2026-10-07", {title: 11.0 for title in self.GAMES})
        self.assertEqual(ebay_prices.price_index(rows), {"UK": [["2026-10-06", 100.0, 12], ["2026-10-07", 110.0, 12]]})
        half = {title: (21.0 if n < 6 else 4.0) for n, title in enumerate(self.GAMES)}   # more than doubled or halved: left out
        mixed = dict(half, **{"Game 0": 12.0, "Game 1": 12.0, "Game 2": 12.0, "Game 3": 12.0, "Game 4": 12.0,
                              "Game 5": 12.0, "Game 6": 9.0, "Game 7": 9.0, "Game 8": 9.0, "Game 9": 9.0})
        rows = self.day("2026-10-06", self.GAMES) + self.day("2026-10-07", mixed)
        (first, second), = ebay_prices.price_index(rows).values()
        self.assertEqual(second[2], 10, "the two that halved are left out")
        self.assertAlmostEqual(second[1], round(100 * (1.2 ** 6 * 0.9 ** 4) ** (1 / 10), 2))

    def test_a_games_figure_for_the_day_is_its_last_one(self):
        rows = (self.day("2026-10-06", self.GAMES)
                + self.day("2026-10-07", {title: 15.0 for title in self.GAMES}, hour="23:00")
                + self.day("2026-10-07", {title: 11.0 for title in self.GAMES}, hour="09:00"))
        self.assertEqual(ebay_prices.price_index(rows)["UK"][-1], ["2026-10-07", 150.0, 12], "rows are put in time order first")

    def test_games_joining_leaving_thin_or_far_apart_never_move_it(self):
        rows = (self.day("2026-10-06", self.GAMES)
                + self.day("2026-10-07", dict(self.GAMES, **{"Newcomer": 500.0}))   # joins: nothing to compare
                + self.day("2026-10-07", {"Thin": 1.0}) + self.day("2026-10-08", {"Thin": 2.0}, copies=2)
                + self.day("2026-10-08", {title: 10.0 for title in list(self.GAMES)[:11]}))   # one leaves
        points = ebay_prices.price_index(rows)["UK"]
        self.assertEqual([point[1] for point in points], [100.0, 100.0, 100.0])
        self.assertEqual([point[2] for point in points], [12, 12, 11])
        later = rows + self.day("2026-10-20", {title: 12.0 for title in self.GAMES})
        self.assertEqual(ebay_prices.price_index(later)["UK"][-1], ["2026-10-20", 100.0, 0], "too long since: not compared")

    def test_a_day_with_too_few_games_keeps_the_value_and_the_start_needs_enough(self):
        few = dict(list(self.GAMES.items())[:5])
        self.assertEqual(ebay_prices.price_index(self.day("2026-10-05", few)), {}, "no start with five games")
        rows = self.day("2026-10-05", few) + self.day("2026-10-06", self.GAMES) + self.day("2026-10-07", {title: 20.0 for title in few})
        self.assertEqual(ebay_prices.price_index(rows)["UK"], [["2026-10-06", 100.0, 12], ["2026-10-07", 100.0, 5]])

    def test_each_site_has_its_own_index_and_consoles_are_left_out(self):
        rows = (self.day("2026-10-06", self.GAMES) + self.day("2026-10-07", {title: 12.0 for title in self.GAMES})
                + self.day("2026-10-06", self.GAMES, site="US") + self.day("2026-10-07", self.GAMES, site="US")
                + self.day("2026-10-06", {"PS2 Ocean Blue": 100.0}) + self.day("2026-10-07", {"PS2 Ocean Blue": 150.0}))
        latest = {"currencies": {"US": "USD", "UK": "GBP"}, "games": {"PS2 Ocean Blue": {"kind": "console"}}}
        index = ebay_prices.index_file(rows, latest, datetime(2026, 10, 8, tzinfo=timezone.utc))
        self.assertEqual(index["sites"]["UK"][-1], ["2026-10-07", 120.0, 12])
        self.assertEqual(index["sites"]["US"][-1], ["2026-10-07", 100.0, 12])
        self.assertEqual(index["currencies"], {"US": "USD", "UK": "GBP"})
        self.assertNotIn("Game", json.dumps(index["sites"]), "numbers and dates only")

    def test_a_console_once_left_out_stays_out_whatever_happens_to_the_lists(self):
        rows = (self.day("2026-10-06", dict(self.GAMES, **{"PS2 Ocean Blue": 100.0}))
                + self.day("2026-10-07", dict(self.GAMES, **{"PS2 Ocean Blue": 150.0})))
        now = datetime(2026, 10, 8, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            listed = Path(folder) / "rare_consoles.json"
            listed.write_text(json.dumps({"consoles": [{"name": "PS2 Ocean Blue", "price": False}]}), encoding="utf-8")
            with mock.patch.object(ebay_prices, "CONSOLES_PATH", listed):
                index = ebay_prices.index_file(rows, {"games": {}}, now)
            self.assertEqual(index["sites"]["UK"][-1], ["2026-10-07", 100.0, 12], "named in rare_consoles.json, even unpriced")
            self.assertEqual(index["left_out"], ["ps2 ocean blue"])
            with mock.patch.object(ebay_prices, "CONSOLES_PATH", Path(folder) / "gone.json"):
                self.assertEqual(ebay_prices.index_file(rows, {"games": {}}, now, index["left_out"])["sites"]["UK"][-1][1], 100.0,
                                 "the list unreadable or the console renamed: still left out")
                self.assertEqual(ebay_prices.index_file(rows, {"games": {}}, now)["sites"]["UK"][-1][2], 13,
                                 "(without that memory it would count)")

    def test_the_run_writes_it_and_a_damaged_month_leaves_it_as_it_was(self):
        sandbox = Sandbox(self, feed=[mention(title, 3, "r/ps2") for title in ("Silent Hill 2", "Kuon", "Okami", "God Hand")])
        sandbox.write("data/prices/2026-09.json", self.day("2026-09-29", self.GAMES) + self.day("2026-09-30", self.GAMES))

        def three_copies(params, headers):
            currency = "GBP" if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB" else "USD"
            name = params["q"]
            return page(*(listing(f"{name} PS2", 10 + n, currency=currency, item_id=n) for n in range(3)))
        code, printed, fake = sandbox.run(FakeHttp(three_copies))
        self.assertEqual(code, 0, printed)
        index = json.loads((sandbox.data / "prices" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["sites"]["UK"], [["2026-09-29", 100.0, 12], ["2026-09-30", 100.0, 12]],
                         "finished days only: today is still under way")
        sandbox.now = NOON + timedelta(days=1)
        sandbox.feed([mention("Silent Hill 2", 1, "r/ps2", now=sandbox.now), mention("Silent Hill 2", 2, "Eurogamer", now=sandbox.now)])
        code, printed, fake = sandbox.run(FakeHttp(three_copies))
        index = json.loads((sandbox.data / "prices" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["sites"]["UK"][-1], ["2026-10-06", 100.0, 0], "yesterday, with too few games to move it")
        self.assertEqual(index["min_games"], ebay_prices.INDEX_MIN_GAMES)
        (sandbox.data / "prices" / "2026-09.json").write_text("[", encoding="utf-8")
        before = (sandbox.data / "prices" / "index.json").read_text(encoding="utf-8")
        sandbox.now = NOON + timedelta(days=1, hours=7)
        sandbox.feed([mention("Silent Hill 2", 1, "r/ps2", now=sandbox.now), mention("Silent Hill 2", 2, "Eurogamer", now=sandbox.now)])
        code, printed, fake = sandbox.run(FakeHttp(three_copies))
        self.assertEqual(code, 0, printed)
        self.assertIn("The price index was not updated: data/prices/2026-09.json cannot be read.", printed)
        self.assertEqual((sandbox.data / "prices" / "index.json").read_text(encoding="utf-8"), before)


class RegionalNameTests(unittest.TestCase):
    """A game released in Europe under another name is searched on eBay UK under that name."""

    RULES = {"UK": [{"from": "Fatal Frame", "to": "Project Zero"}, {"from": "Siren", "to": "Forbidden Siren"},
                    {"from": "Ratchet & Clank: Up Your Arsenal", "to": "Ratchet & Clank 3"}]}

    def setUp(self):
        self.sandbox = Sandbox(self, feed=[mention("Fatal Frame 2: Crimson Butterfly", 5, "r/ps2"),
                                           mention("Fatal Frame", 4, "r/ps2"), mention("Kuon", 3, "r/ps2")])
        self.sandbox.write("data/ps2_database.json", Sandbox.LIBRARY + [
            "Fatal Frame", "Fatal Frame II: Crimson Butterfly", "Fatal Frame 2: Crimson Butterfly", "Fatal Frame 3: The Tormented"])
        self.sandbox.write("ebay_watchlist.json", {"games": [], "never": [], "regional_names": self.RULES})

    def rules(self):
        return ebay_prices.load_regional_names(self.sandbox.root / "ebay_watchlist.json")

    def test_a_name_is_renamed_from_its_start_and_only_as_whole_words(self):
        rules = self.rules()["EBAY_GB"]
        self.assertEqual(ebay_prices.renamed("fatal frame 2 crimson butterfly", rules), "project zero 2 crimson butterfly")
        self.assertEqual(ebay_prices.renamed("fatal frame ii crimson butterfly", rules), "project zero ii crimson butterfly",
                         "the search as sellers write it, Roman numeral and all")
        self.assertEqual(ebay_prices.renamed("fatal frame", rules), "project zero")
        self.assertEqual(ebay_prices.renamed("ratchet clank up your arsenal", rules), "ratchet clank 3")
        for untouched in ("sirens call", "the fatal frame", "fatal framework", "kuon"):
            self.assertIsNone(ebay_prices.renamed(untouched, rules), untouched)
        self.assertEqual(set(self.rules()), {"EBAY_GB"}, "nothing changes on eBay US")

    def test_each_site_is_asked_under_its_own_name_and_counts_its_own_copies(self):
        def answer(params, headers):
            uk = headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB"
            q = params["q"]
            if uk and q.startswith("project zero 2"):
                return page(listing("Project Zero II Crimson Butterfly PS2 PAL", 40, currency="GBP", item_id=1),
                            listing("Project Zero 2 Crimson Butterfly Sony PS2", 50, currency="GBP", item_id=2))
            if uk and q.startswith("project zero"):
                return page(listing("Project Zero PS2 complete", 30, currency="GBP", item_id=3),
                            listing("Project Zero 2 Crimson Butterfly PS2", 45, currency="GBP", item_id=4))
            if uk and q.startswith("fatal frame"):
                return page(listing("Fatal Frame NTSC US PS2", 99, currency="GBP", item_id=5))
            return two_copies(params, headers)
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        asked = {(call["headers"]["X-EBAY-C-MARKETPLACE-ID"], call["params"]["q"]) for call in fake.searches}
        self.assertIn(("EBAY_GB", "project zero 2 crimson butterfly"), asked)
        self.assertIn(("EBAY_US", "fatal frame 2 crimson butterfly"), asked)
        self.assertFalse({q for site, q in asked if site == "EBAY_GB" and q.startswith("fatal frame")}, "UK never asked for Fatal Frame")
        games = self.sandbox.latest["games"]
        sequel = next(entry for title, entry in games.items() if "Crimson" in title)
        self.assertEqual((sequel["UK"]["copies"], sequel["UK"]["median"]), (2, 45.0))
        self.assertEqual(sequel["US"]["copies"], 2)
        first = games["Fatal Frame"]
        self.assertEqual((first["UK"]["copies"], first["UK"]["median"]), (1, 30.0), "a listing of the sequel is not a copy of the first game")
        self.assertIn("Searched on eBay UK under the name it has there: 2 (Fatal Frame as project zero; ", printed)
        row = next(row for row in self.sandbox.snapshot["games"] if "Crimson" in row["title"])
        self.assertIn("_nkw=project%20zero%202%20crimson%20butterfly%20ps2", row["markets"]["EBAY_GB"]["search_url"],
                      "the link to the source is the UK search")
        self.assertIn("_nkw=fatal%20frame%202", row["markets"]["EBAY_US"]["search_url"])
        self.assertNotIn("45", printed.split("Searched on eBay UK")[1].split("\n")[0], "names in the log, never prices")

    def test_mistakes_get_a_readable_message(self):
        for value, message in (({"EU": []}, "must map US, UK"), ({"UK": {}}, "must be a list"),
                               ({"UK": [{"from": "Fatal Frame"}]}, 'rename 1 for UK needs "from" and "to"'),
                               ({"UK": [{"from": "", "to": "x"}]}, 'needs "from" and "to"'),
                               ({"UK": [{"from": "Bully", "to": "and"}]}, "does not work as eBay search words"),
                               ({"UK": [{"from": "Fatal Frame", "to": "Black"}]}, "two words or more"),
                               ({"UK": [{"from": "Fatal Frame", "to": "x " * 60}]}, "does not work as eBay search words")):
            self.sandbox.write("ebay_watchlist.json", {"games": [], "regional_names": value})
            with self.assertRaises(ebay_prices.EbayError) as raised:
                self.rules()
            self.assertIn(message, str(raised.exception))
        self.sandbox.write("ebay_watchlist.json", {"games": []})
        self.assertEqual(self.rules(), {}, "the list is optional")

    def test_the_committed_renames_load_and_rename_real_library_titles(self):
        rules = ebay_prices.load_regional_names(ROOT / "ebay_watchlist.json")["EBAY_GB"]
        for title, uk in (("Fatal Frame 2: Crimson Butterfly", "project zero 2 crimson butterfly"),
                          ("Dark Cloud 2", "dark chronicle"), ("Sly Cooper and the Thievius Raccoonus", "sly raccoon"),
                          ("Ace Combat 4: Shattered Skies", "ace combat distant thunder")):
            self.assertEqual(ebay_prices.renamed(ebay_prices.search_terms(title)[0], rules), uk, title)
        for title in ("Bully", "Shin Megami Tensei: Persona 4", "Ant Bully"):
            # Bully kept its name across most of Europe, and Persona its full name.
            self.assertIsNone(ebay_prices.renamed(ebay_prices.search_terms(title)[0], rules), title)

    def test_the_regional_name_is_never_one_of_its_own_other_games(self):
        catalogue = [{"name": name, "title": title, "possessive": set()} for title, name in (
            ("Siren", "siren"), ("Forbidden Siren", "forbidden siren"), ("Forbidden Siren 2", "forbidden siren 2"))]
        game = {"title": "Siren", "search": "siren", "queries": ["siren"],
                "siblings": ebay_prices.other_games("Siren", "siren", catalogue)}
        self.assertIn("forbidden siren", game["siblings"], "on eBay US, Forbidden Siren is another game")
        ebay_prices.apply_regional_names([game], {"EBAY_GB": [("siren", "siren", "forbidden siren", "forbidden siren")]}, catalogue)
        uk = game["markets"]["EBAY_GB"]
        self.assertEqual((uk["search"], uk["siblings"]), ("forbidden siren", ["forbidden siren 2"]))
        listing_ = listing("Forbidden Siren PS2 PAL complete with manual", 30, currency="GBP")
        self.assertIsNone(ebay_prices.reject_reason(listing_, ebay_prices.for_market(game | {"exclude": []}, "EBAY_GB"),
                                                    ebay_prices.MARKETS["EBAY_GB"], False))

    def test_a_game_filed_under_both_names_is_looked_up_once_on_that_site(self):
        fatal = {"title": "Fatal Frame", "key": "fatal frame", "search": "fatal frame", "queries": ["fatal frame"],
                 "siblings": [], "level": "normal", "pinned": False}
        zero = {"title": "Project Zero", "key": "project zero", "search": "project zero", "queries": ["project zero"],
                "siblings": [], "level": "normal", "pinned": False}
        ebay_prices.apply_regional_names([fatal, zero], {"EBAY_GB": [("fatal frame", "fatal frame", "project zero", "project zero")]})
        lookups = [(game["title"], market) for game, market in ebay_prices.due_lookups([fatal, zero], {}, NOON)]
        self.assertEqual(sorted(lookups), [("Fatal Frame", "EBAY_GB"), ("Fatal Frame", "EBAY_US"), ("Project Zero", "EBAY_US")])

    def test_the_search_check_and_the_listings_file_use_the_name_there(self):
        game = {"title": "Fatal Frame", "search": "fatal frame", "queries": ["fatal frame"], "siblings": ["fatal frame 2"],
                "level": "normal", "markets": {"EBAY_GB": {"search": "project zero", "queries": ["project zero"],
                                                            "siblings": ["project zero 2"]}}}
        asked = []

        def search(http_client, token, market_id, query, counter, **kwargs):
            asked.append((market_id, query))
            return 200, {"total": 0, "itemSummaries": []}
        with mock.patch.object(ebay_prices, "search", search), mock.patch.object(ebay_prices, "say"):
            ebay_prices.diagnose(None, "t", game, {"searches": 0}, ())
        self.assertEqual({query for market, query in asked if market == "EBAY_GB"}, {"project zero"})
        self.assertEqual({query for market, query in asked if market == "EBAY_US"}, {"fatal frame"})
        snapshot = ebay_prices.snapshot_of({"results": [(game, "EBAY_GB", {"status": "ok"}), (game, "EBAY_US", {"status": "ok"})],
                                            "searches": 2, "stopped": None}, NOON)
        row = snapshot["games"][0]
        self.assertEqual((row["markets"]["EBAY_GB"]["search_there"], row["markets"]["EBAY_GB"]["left_out_if_named_there"]),
                         ("project zero", ["project zero 2"]))
        self.assertNotIn("search_there", row["markets"]["EBAY_US"])


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = Sandbox(self, pinned=[{"title": "Silent Hill 2"}], never=["Combat Ace"], feed=[
            mention("Kuon", 5, "r/ps2"), mention("Black", 5, "r/ps2"), mention("Combat Ace", 5, "IGN"),
            mention("Halo 2", 5, "IGN")])

    def test_a_full_run_never_leaks_the_key(self):
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0, printed)
        written = "".join(path.read_text(encoding="utf-8") for path in self.sandbox.root.rglob("*.json"))
        for secret in SECRETS + ("Bearer", "Basic"):
            self.assertNotIn(secret, written)
            self.assertNotIn(secret, printed)
        self.assertEqual(len(fake.token_calls), 1)

    def test_the_listings_file_holds_this_runs_lookups(self):
        self.sandbox.run()
        snapshot = self.sandbox.snapshot
        self.assertEqual([row["title"] for row in snapshot["games"]], ["Silent Hill 2", "Kuon"])
        self.assertEqual(snapshot["searches_used"], 4)
        self.assertEqual(snapshot["stopped_early"], "")
        self.assertRegex(snapshot["fetched_at"], r"^2026-10-06T12:00:00Z$")
        first = snapshot["games"][0]["markets"]
        self.assertEqual(list(first), ["EBAY_GB", "EBAY_US"])
        self.assertEqual(first["EBAY_US"]["listings"][0]["url"], "https://www.ebay.com/itm/1")
        self.assertNotIn("answered", first["EBAY_US"])
        self.assertEqual(snapshot["markets"]["EBAY_GB"], {"label": "UK", "site": "www.ebay.co.uk", "currency": "GBP"})

    def test_the_public_log_explains_the_plan_and_holds_counts_but_no_prices(self):
        code, printed, fake = self.sandbox.run()
        self.assertIn("Tracking 2 games (1 pinned): 0 surging, 2 normal, 0 staple, 0 dormant.\n", printed)
        self.assertIn("Left out, one-word name that is also an ordinary word (pin it to track it): 1 (Black).\n", printed)
        self.assertIn("Left out, not in the PS2 library: 1 (Halo 2).\n", printed)
        self.assertIn('Left out, on the "never" list: 1 (Combat Ace).\n', printed)
        self.assertIn("Due now: 4 lookups. This run may use 500 searches.\n", printed)
        self.assertIn("  Silent Hill 2 [US]: 2 of 2 listings counted\n", printed)
        self.assertIn("4 searches used; 4 of 4 lookups answered; 0 left for the next run.\n", printed)
        self.assertIn("Wrote latest.json and added 4 rows to this month's price history.\n", printed)
        for price in ("24.99", "31.5", "28.2", "3.49"):
            self.assertNotIn(price, printed)

    def test_the_plan_can_be_shown_without_the_key_and_without_asking_ebay(self):
        code, printed, fake = self.sandbox.run(env={}, argv=["--plan"])
        self.assertEqual(code, 0)
        self.assertIn("Due now: 4 lookups.", printed)
        self.assertEqual((fake.token_calls, fake.searches), ([], []))
        self.assertFalse((self.sandbox.data / "prices").exists())

    def test_the_search_check_prints_counts_for_each_variation(self):
        fake = FakeHttp(lambda params, headers: page(listing("Silent Hill 2 PS2", 24.99), total=37))
        code, printed, fake = self.sandbox.run(fake, env={**KEY, "EBAY_DIAGNOSE": "true"})
        self.assertEqual(code, 0, printed)
        self.assertIn('Search check for "Silent Hill 2" (listings eBay reports):', printed)
        for site in ("US", "UK"):
            for label in ("the search this script uses", "platform by keyword, not item specific",
                          "condition asked for as USED", "any condition"):
                self.assertIn(f"  [{site}] {label}: 37\n", printed)
        filters = [call["params"]["filter"] for call in fake.searches[:4]]
        self.assertTrue(filters[0].startswith("conditionIds:{"))
        self.assertTrue(filters[2].startswith("conditions:{USED},"))
        self.assertEqual(filters[3], "buyingOptions:{FIXED_PRICE},itemLocationCountry:US")
        self.assertEqual(fake.searches[1]["params"]["q"], "silent hill 2 ps2")
        self.assertEqual(self.sandbox.latest["searches"]["used"], 8 + 4)
        self.assertNotIn("Search check", self.sandbox.run(env={**KEY, "EBAY_DIAGNOSE": ""})[1])
        self.assertNotIn("24.99", printed)

    def test_without_the_key_it_says_what_to_do_and_calls_nobody(self):
        code, printed, fake = self.sandbox.run(env={})
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: The eBay key is not set.", printed)
        self.assertIn("New repository secret", printed)
        self.assertEqual((fake.token_calls, fake.searches), ([], []))
        self.assertFalse((self.sandbox.data / "prices").exists())

    def test_a_refused_key_writes_nothing_and_shows_nothing_secret(self):
        echo = f"bad credentials {CLIENT_ID}:{CLIENT_SECRET}"
        code, printed, fake = self.sandbox.run(FakeHttp(two_copies, token_answer=(401, {"error_description": echo})))
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: eBay refused the key (HTTP 401: bad credentials ***:***)", printed)
        for secret in SECRETS:
            self.assertNotIn(secret, printed)
        self.assertEqual(fake.searches, [])
        self.assertFalse((self.sandbox.data / "prices").exists())
        self.assertFalse(self.sandbox.out.exists())

    def test_when_ebay_stops_answering_the_run_is_abandoned_early(self):
        fake = FakeHttp(lambda params, headers: ebay_prices.NetworkProblem("TimeoutError"))
        code, printed, fake = self.sandbox.run(fake)
        self.assertEqual(code, 1)
        self.assertIn("Stopped early: eBay did not answer 3 lookups in a row.", printed)
        self.assertIn("STOPPED: every lookup failed, so nothing was written.", printed)
        self.assertEqual(len(fake.searches), 9, "three lookups of three tries each, not all four")
        self.assertFalse((self.sandbox.data / "prices").exists())

    def test_what_was_learned_before_ebay_went_quiet_is_kept(self):
        library = [f"Game Number {n}" for n in range(8)]
        self.sandbox.write("data/ps2_database.json", library)
        self.sandbox.write("ebay_watchlist.json", {"games": []})
        self.sandbox.feed([mention(title, 5, "r/ps2") for title in library])
        calls = {"n": 0}

        def answer(params, headers):
            calls["n"] += 1
            return two_copies(params, headers) if calls["n"] <= 9 else ebay_prices.NetworkProblem("TimeoutError")
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        self.assertIn("Stopped early: eBay did not answer 3 lookups in a row.", printed)
        self.assertIn("9 of 12 lookups answered; 4 left for the next run.", printed)
        self.assertEqual(len(self.sandbox.history()), 9)

    def test_a_run_that_starts_with_ten_failures_gives_up_at_once(self):
        library = [f"Game Number {n}" for n in range(30)]
        self.sandbox.write("data/ps2_database.json", library)
        self.sandbox.write("ebay_watchlist.json", {"games": []})
        self.sandbox.feed([mention(title, 5, "r/ps2") for title in library])
        code, printed, fake = self.sandbox.run(FakeHttp(lambda params, headers: (403, {"errors": [{"message": "Forbidden"}]})))
        self.assertEqual(code, 1)
        self.assertEqual(len(fake.searches), 10, "ten lookups, not all sixty")
        self.assertIn("Stopped early: the first 10 lookups all failed or came back empty.", printed)
        self.assertIn("STOPPED: every lookup failed", printed)

    def test_when_most_lookups_fail_nothing_is_written(self):
        calls = {"n": 0}

        def answer(params, headers):
            calls["n"] += 1
            return two_copies(params, headers) if calls["n"] == 1 else (500, {"errors": [{"message": "oops"}]})
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: 3 of 4 lookups failed", printed)
        self.assertFalse((self.sandbox.data / "prices").exists())
        self.assertFalse(self.sandbox.out.exists())

    def test_many_answers_with_no_listings_at_all_are_treated_as_a_broken_search(self):
        library = [f"Game Number {n}" for n in range(6)]
        self.sandbox.write("data/ps2_database.json", library)
        self.sandbox.write("ebay_watchlist.json", {"games": []})
        self.sandbox.feed([mention(title, 5, "r/ps2") for title in library])
        code, printed, fake = self.sandbox.run(FakeHttp(lambda params, headers: page()))
        self.assertEqual(code, 1)
        self.assertIn("no copies counted, 0 returned (keyword search)", printed)
        self.assertIn("Stopped early: the first 10 lookups all failed or came back empty.", printed)
        self.assertIn("STOPPED: eBay answered but returned no listings for any game", printed)
        self.assertEqual(len(fake.searches), 20, "ten lookups of two searches each, then it gives up")
        self.assertFalse((self.sandbox.data / "prices").exists())

    def test_games_that_had_copies_and_now_return_nothing_at_all_mean_a_broken_search(self):
        library = [f"Game Number {n}" for n in range(6)]
        self.sandbox.write("data/ps2_database.json", library)
        self.sandbox.write("ebay_watchlist.json", {"games": []})
        self.sandbox.feed([mention(title, 5, "r/ps2") for title in library])
        self.assertEqual(self.sandbox.run()[0], 0)
        before = self.sandbox.latest
        self.sandbox.now = NOON + timedelta(hours=7)
        code, printed, fake = self.sandbox.run(FakeHttp(lambda params, headers: page()))
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: 12 games that had copies listed last time now return nothing at all", printed)
        self.assertEqual(self.sandbox.latest, before)
        self.assertEqual(len(self.sandbox.history()), 12)

    def test_a_few_obscure_games_with_no_listings_are_just_recorded(self):
        code, printed, fake = self.sandbox.run(FakeHttp(lambda params, headers: page()))
        self.assertEqual(code, 0, printed)
        self.assertEqual(self.sandbox.latest["games"]["Kuon"]["US"]["copies"], 0)

    def test_new_games_with_no_listings_do_not_fail_a_run_once_prices_are_known(self):
        self.assertEqual(self.sandbox.run()[0], 0)
        library = [f"Game Number {n}" for n in range(8)]
        self.sandbox.write("data/ps2_database.json", library + Sandbox.LIBRARY)
        self.sandbox.feed([mention(title, 5, "r/ps2") for title in library])
        self.sandbox.now = NOON + timedelta(hours=1)
        code, printed, fake = self.sandbox.run(FakeHttp(lambda params, headers: page()))
        self.assertEqual(code, 0, printed)
        self.assertEqual(self.sandbox.latest["games"]["Game Number 7"]["UK"]["copies"], 0)
        self.assertEqual(self.sandbox.latest["games"]["Silent Hill 2"]["US"]["copies"], 2, "not due, so untouched")

    def test_a_price_file_that_cannot_be_read_stops_the_run_before_ebay_is_asked(self):
        self.assertEqual(self.sandbox.run()[0], 0)
        self.sandbox.now = NOON + timedelta(hours=7)
        prices = self.sandbox.data / "prices"
        good = {name: (prices / name).read_text(encoding="utf-8") for name in ("latest.json", "2026-10.json")}
        for name, broken in (("2026-10.json", good["2026-10.json"].replace("\n]", ",\n]")),
                             ("2026-10.json", "{}"), ("latest.json", "{not json"),
                             ("latest.json", '{"games": []}'), ("latest.json", '{"searches": {"used": "many"}}')):
            (prices / name).write_text(broken, encoding="utf-8")
            code, printed, fake = self.sandbox.run()
            self.assertEqual(code, 1, (name, broken[:20]))
            self.assertIn(f"STOPPED: data/prices/{name}", printed)
            self.assertIn("Nothing was changed.", printed)
            self.assertEqual((fake.token_calls, fake.searches), ([], []))
            self.assertEqual((prices / name).read_text(encoding="utf-8"), broken, "left exactly as it was found")
            (prices / name).write_text(good[name], encoding="utf-8")
        self.assertEqual(self.sandbox.run()[0], 0)
        self.assertEqual(len(self.sandbox.history()), 4, "the four earlier rows are still there")

    def test_a_game_keeps_its_figures_when_its_spelling_changes(self):
        self.sandbox.write("ebay_watchlist.json", {"games": [{"title": "Ico"}]})
        self.sandbox.write("data/ps2_database.json", ["ICO"])
        self.sandbox.feed([mention("ICO", 5, "r/ps2")])
        self.assertEqual(self.sandbox.run()[0], 0)
        self.assertEqual(list(self.sandbox.latest["games"]), ["Ico"])
        self.sandbox.write("ebay_watchlist.json", {"games": []})     # unpinned: the library's spelling takes over
        self.sandbox.now = NOON + timedelta(hours=2)
        code, printed, fake = self.sandbox.run()
        self.assertIn("Nothing is due", printed)
        self.sandbox.now = NOON + timedelta(hours=7)
        self.assertEqual(self.sandbox.run()[0], 0)
        self.assertEqual(list(self.sandbox.latest["games"]), ["ICO"])
        self.assertEqual(len(self.sandbox.history()), 2, "same numbers, same day: no new rows under the new spelling")

    def test_an_error_from_ebay_is_scrubbed_before_it_is_shown_or_saved(self):
        def answer(params, headers):
            if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB" and params["q"].startswith("kuon"):
                return 500, {"errors": [{"message": f"Internal error for {headers['Authorization']}"}]}
            return two_copies(params, headers)
        code, printed, fake = self.sandbox.run(FakeHttp(answer))
        self.assertEqual(code, 0, printed)
        self.assertNotIn(TOKEN, self.sandbox.out.read_text(encoding="utf-8") + printed)
        kuon = next(row for row in self.sandbox.snapshot["games"] if row["title"] == "Kuon")
        self.assertEqual(kuon["markets"]["EBAY_GB"]["error"], "HTTP 500: Internal error for Bearer ***")
        self.assertIn("Kuon [UK]: FAILED HTTP 500: Internal error for Bearer ***", printed)

    def test_the_days_allowance_carries_over_between_runs_and_stops_the_day(self):
        self.sandbox.write("data/prices/latest.json", {"searches": {"day": "2026-10-06", "used": 4497}, "games": {}})
        code, printed, fake = self.sandbox.run()
        self.assertIn("This run may use 3 searches.", printed)
        self.assertEqual(len(fake.searches), 2)
        self.assertIn("Stopped early: this run's allowance of searches is used.", printed)
        self.assertIn("2 left for the next run.", printed)
        self.assertEqual(self.sandbox.latest["searches"], {"day": "2026-10-06", "used": 4499})
        code, printed, fake = self.sandbox.run()
        self.assertEqual(code, 0)
        self.assertIn("Today's allowance of eBay searches is used up", printed)
        self.assertEqual(fake.token_calls, [])
        self.sandbox.now = NOON + timedelta(days=1)
        code, printed, fake = self.sandbox.run()
        self.assertIn("This run may use 500 searches.", printed)

    def test_by_default_the_listings_file_goes_outside_the_repository(self):
        self.assertNotIn(ROOT, ebay_prices.DEFAULT_OUT.resolve().parents)


# ------------------------------------------------------------ the real request code

class _Handler(BaseHTTPRequestHandler):
    seen = []

    def _reply(self, status, body, headers=()):
        payload = body.encode("utf-8")
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except OSError:
            pass   # the test hung up on purpose

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else None
        type(self).seen.append({"method": self.command, "path": self.path, "body": body,
                                "headers": {key.lower(): value for key, value in self.headers.items()}})
        if self.path == "/redirect":
            self._reply(302, "", [("Location", "/stolen")])
        elif self.path == "/bad":
            self._reply(400, '{"errors": [{"message": "Invalid filter"}]}')
        elif self.path == "/slow":
            time.sleep(1.0)
            self._reply(200, "{}")
        else:
            self._reply(200, '{"ok": "é"}')

    do_GET = do_POST = _handle

    def log_message(self, *args):
        pass


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass   # a client that hangs up mid-answer is part of the test, not news


class RealRequestTests(unittest.TestCase):
    """The real request code against a server on this machine."""

    @classmethod
    def setUpClass(cls):
        cls.server = _QuietServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.seen.clear()

    def test_a_get_sends_the_headers_and_returns_status_and_text(self):
        status, text = ebay_prices.Http().send(self.base + "/ok?q=a%20b", {"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual((status, json.loads(text)), (200, {"ok": "é"}))
        (seen,) = _Handler.seen
        self.assertEqual((seen["method"], seen["path"], seen["body"]), ("GET", "/ok?q=a%20b", None))
        self.assertEqual(seen["headers"]["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(seen["headers"]["user-agent"], ebay_prices.USER_AGENT)

    def test_a_post_sends_its_body(self):
        ebay_prices.Http().send(self.base + "/token", {"Content-Type": "application/x-www-form-urlencoded"},
                                b"grant_type=client_credentials")
        (seen,) = _Handler.seen
        self.assertEqual((seen["method"], seen["body"]), ("POST", "grant_type=client_credentials"))

    def test_an_error_answer_comes_back_with_its_text(self):
        status, text = ebay_prices.Http().send(self.base + "/bad", {})
        self.assertEqual((status, ebay_prices.error_text(status, ebay_prices.parse(text))),
                         (400, "HTTP 400: Invalid filter"))

    def test_a_redirect_is_never_followed_so_the_key_cannot_be_sent_elsewhere(self):
        status, text = ebay_prices.Http().send(self.base + "/redirect", {"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(status, 302)
        self.assertEqual([seen["path"] for seen in _Handler.seen], ["/redirect"])

    def test_a_slow_or_absent_server_is_a_network_problem_that_names_no_request(self):
        with self.assertRaises(ebay_prices.NetworkProblem) as slow:
            ebay_prices.Http(timeout=0.2).send(self.base + "/slow", {"Authorization": f"Bearer {TOKEN}"})
        with self.assertRaises(ebay_prices.NetworkProblem) as absent:
            ebay_prices.Http(timeout=2).send("http://127.0.0.1:9/nothing", {"Authorization": f"Bearer {TOKEN}"})
        for caught in (slow, absent):
            self.assertRegex(str(caught.exception), r"^[A-Za-z]+$")
            self.assertTrue(caught.exception.__suppress_context__)

    def test_requests_give_up_after_a_fixed_time(self):
        self.assertEqual(ebay_prices.Http().timeout, ebay_prices.REQUEST_TIMEOUT)
        self.assertLessEqual(ebay_prices.REQUEST_TIMEOUT, 20)


# ------------------------------------------------------------------- the workflow

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.lines = [line for line in text.split("\n") if line.strip() and not line.lstrip().startswith("#")]
        self.code = "\n".join(self.lines)
        self.steps = self.code.split("\n      - ")[1:]

    def block(self, key):
        """The lines under a top-level key."""
        start = self.lines.index(f"{key}:")
        rest = self.lines[start + 1:]
        end = next((n for n, line in enumerate(rest) if not line.startswith(" ")), len(rest))
        return rest[:end]

    def test_it_runs_after_the_scraper_or_by_hand_and_never_on_pull_requests(self):
        triggers = [line.strip() for line in self.block("on") if re.match(r"^  \S", line)]
        self.assertEqual(triggers, ["workflow_run:", "workflow_dispatch:"])
        for trigger in ("pull_request:", "pull_request_target", "issue_comment", "schedule", "push:"):
            self.assertNotIn(trigger, self.code)

    def test_the_workflow_it_follows_is_the_scraper_which_never_runs_on_pull_requests(self):
        scraper = SCRAPER_WORKFLOW.read_text(encoding="utf-8")
        name = re.search(r"^name:\s*(.+?)\s*$", scraper, flags=re.MULTILINE).group(1)
        self.assertIn(f'workflows: ["{name}"]', self.code)
        self.assertIn("types: [completed]", self.code)
        self.assertNotIn("pull_request", scraper)

    def test_it_always_runs_the_code_on_main_never_the_code_that_triggered_it(self):
        checkout = next(step for step in self.steps if step.startswith("uses: actions/checkout"))
        self.assertIn("ref: main", checkout)
        self.assertIn("persist-credentials: false", checkout)
        for borrowed in ("head_sha", "head_branch", "head_ref", "github.sha", "github.ref"):
            self.assertNotIn(borrowed, self.code)

    def test_a_scraper_run_from_a_pull_request_or_another_repository_cannot_start_it(self):
        start = self.lines.index("    if: >-")
        condition = " ".join(line.strip() for line in self.lines[start + 1:start + 4])
        self.assertEqual(condition, "github.event_name == 'workflow_dispatch' || "
                                    "(github.event.workflow_run.event != 'pull_request' && "
                                    "github.event.workflow_run.head_repository.full_name == github.repository)")
        self.assertEqual(self.code.count("github.event.workflow_run"), 2, "used to decide whether to run, nowhere else")

    def test_one_run_at_a_time_with_limited_rights_and_a_time_limit(self):
        self.assertEqual(self.block("concurrency"), ["  group: ebay", "  cancel-in-progress: false"])
        self.assertEqual(self.block("permissions"), ["  contents: write"])
        self.assertIn("    timeout-minutes: 15", self.lines)
        self.assertIn("          EBAY_DIAGNOSE: ${{ inputs.diagnose }}", self.lines)

    def test_the_key_reaches_one_step_only(self):
        self.assertEqual(self.code.count("secrets."), 2)
        for name in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
            (line,) = [line for line in self.lines if f"secrets.{name}" in line]
            self.assertEqual(line, f"          {name}: ${{{{ secrets.{name} }}}}", "step-level env only")
        env_lines = [line for line in self.lines if line.strip() == "env:"]
        self.assertTrue(all(line == "        env:" for line in env_lines), "no workflow-level or job-level env")
        holders = [step for step in self.steps if "secrets.EBAY" in step]
        self.assertEqual(len(holders), 1)
        self.assertIn("run: python ebay_prices.py", holders[0])
        self.assertNotIn("git ", holders[0])
        self.assertNotIn("set -x", self.code)

    def test_the_job_that_holds_the_key_installs_nothing(self):
        self.assertNotIn("pip", self.code)
        self.assertNotIn("npm", self.code)
        uses = sorted(line.split("uses:")[1].strip() for line in self.lines if "uses:" in line)
        self.assertEqual(uses, ["actions/checkout@v5", "actions/setup-python@v6"])

    def test_only_the_price_numbers_are_saved_to_main(self):
        (save,) = [step for step in self.steps if step.startswith("name: Save the price history")]
        adds = re.findall(r"git add (.+)", save)
        self.assertEqual(adds, ["data/prices"])
        self.assertIn('git push -q "$remote" HEAD:main', save)
        self.assertIn("git pull -q --rebase", save)
        self.assertNotIn("--force", save)
        self.assertNotIn("ebay_prices.json", save)

    def test_listings_go_to_their_own_replaced_branch(self):
        (publish,) = [step for step in self.steps if step.startswith("name: Publish this run's listings")]
        self.assertIn('--out "$RUNNER_TEMP/ebay/ebay_prices.json"', self.code)
        self.assertIn("git init -q -b ebay-data", publish)
        self.assertIn("--force", publish)
        self.assertTrue(publish.rstrip().endswith(" ebay-data"))
        self.assertNotIn("data/", publish)
        self.assertNotIn("main", publish)

    def test_nothing_is_saved_or_published_after_a_failed_run(self):
        self.assertNotIn("always()", self.code)
        self.assertNotIn("continue-on-error", self.code)
        self.assertNotIn("\n        if:", self.code, "no step decides for itself whether to run")
        self.assertEqual(self.code.count("\n    if:"), 1, "only the job-level check on what started the run")

    def test_commits_use_the_no_reply_address(self):
        self.assertEqual(self.code.count("41898282+github-actions[bot]@users.noreply.github.com"), 2)
        self.assertEqual(self.code.count("git config user.email"), 2)

    def test_the_test_workflow_runs_when_the_price_script_changes(self):
        text = TESTS_WORKFLOW.read_text(encoding="utf-8")
        for path in ("- ebay_prices.py", "- ebay_watchlist.json", "- .github/workflows/ebay.yml"):
            self.assertIn(path, text)
        self.assertNotIn("secrets.", text)


class KeyStaysInOnePlaceTests(unittest.TestCase):
    def test_only_the_price_script_knows_about_the_key(self):
        for name in ("scraper.py", "demand.py", "archive.py", "index.html", "guide.html"):
            path = ROOT / name
            if path.exists():
                self.assertNotIn("EBAY_CLIENT", path.read_text(encoding="utf-8"), name)

    def test_the_price_script_needs_nothing_but_python(self):
        source = (ROOT / "ebay_prices.py").read_text(encoding="utf-8")
        imported = set(re.findall(r"^(?:import|from) ([a-z_0-9]+)", source, flags=re.MULTILINE))
        self.assertTrue(imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names))

    def test_the_price_script_only_writes_under_data_prices(self):
        self.assertEqual(ebay_prices.PRICES_DIR, ROOT / "data" / "prices")
        source = (ROOT / "ebay_prices.py").read_text(encoding="utf-8")
        self.assertEqual(source.count(".write_text("), 3, "latest.json, a month of history, and the --out file")


if __name__ == "__main__":
    unittest.main()
