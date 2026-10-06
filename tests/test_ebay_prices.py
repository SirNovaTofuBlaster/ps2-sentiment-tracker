"""Offline tests for ebay_prices.py and its workflow. Nothing here talks to eBay.

Run:  python -m unittest discover -s tests -v
A fake stands in for eBay's API, and a throwaway server on this machine checks
the real request code. Between them they check what the script asks for, what
it does with the answer, and above all that the key never leaks."""

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
WORKFLOW = ROOT / ".github" / "workflows" / "ebay.yml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"

US = ebay_prices.MARKETS["EBAY_US"]
GB = ebay_prices.MARKETS["EBAY_GB"]


def game(title, search=None, exclude=()):
    return {"title": title, "search": " ".join(ebay_prices.words(search or title)), "exclude": list(exclude)}


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


def run_main(fake, argv, env=None):
    """main() against a fake eBay; returns (exit code, everything printed)."""
    if env is None:
        env = {"EBAY_CLIENT_ID": CLIENT_ID, "EBAY_CLIENT_SECRET": CLIENT_SECRET}
    printed = io.StringIO()
    with mock.patch.object(ebay_prices, "Http", lambda: fake), \
            mock.patch.object(ebay_prices.time, "sleep", lambda seconds: None), \
            mock.patch.dict(ebay_prices.os.environ, env, clear=True), \
            contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
        code = ebay_prices.main(argv)
    return code, printed.getvalue()


class Quiet(unittest.TestCase):
    """No real waiting, and nothing printed to the test output."""

    def setUp(self):
        self.slept = []
        for target, name, replacement in ((ebay_prices.time, "sleep", self.slept.append),
                                          (ebay_prices, "say", lambda text: None)):
            patcher = mock.patch.object(target, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)


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


class RequestTests(Quiet):
    def test_each_site_is_asked_for_used_buy_it_now_ps2_copies_in_its_own_country(self):
        for market_id, country in (("EBAY_US", "US"), ("EBAY_GB", "GB")):
            fake = FakeHttp(lambda params, headers: page(listing("Silent Hill 2 PS2", 30)))
            ebay_prices.search(fake, TOKEN, market_id, "silent hill 2", {"searches": 0})
            (call,) = fake.searches
            self.assertEqual(call["base"], "https://api.ebay.com/buy/browse/v1/item_summary/search")
            self.assertIsNone(call["body"])
            self.assertEqual(call["headers"], {
                "Authorization": f"Bearer {TOKEN}",
                "X-EBAY-C-MARKETPLACE-ID": market_id,
                "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country%3D{country}"})
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

    def test_whole_words_decide_what_is_not_a_copy(self):
        okami = game("Okami")
        for title in ("Okami PS2 demo", "Okami PS2 case and manual", "Okami PS2 job lot",
                      "Okami PS2 Manual Booklet", "Okami PS2 NO GAME", "Okami PS2 repro cover"):
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
        self.assertEqual((result["lowest"], result["median"]), (20.0, 40.0))
        self.assertEqual((result["currency"], result["platform_filter"]), ("USD", "item_specific"))
        self.assertFalse(result["truncated"])

    def test_one_silly_price_does_not_move_the_median(self):
        prices = [18, 20, 22, 24, 26]
        calm = self.summary(*[listing("Silent Hill 2", p, item_id=i) for i, p in enumerate(prices)])
        wild = self.summary(*[listing("Silent Hill 2", p, item_id=i) for i, p in enumerate(prices[:-1] + [900])])
        self.assertEqual(calm["median"], wild["median"])

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
        self.assertNotIn("median_with_postage", result)
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

    def test_an_error_is_reported_with_ebays_own_words_and_no_second_search(self):
        fake = FakeHttp(lambda params, headers: (
            400, {"errors": [{"errorId": 12001, "message": "short", "longMessage": "The aspect filter is invalid."}]}))
        result = ebay_prices.check_market(fake, TOKEN, SH2, "EBAY_US", {"searches": 0})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "HTTP 400: The aspect filter is invalid.")
        self.assertIs(result["answered"], True)
        self.assertNotIn("median", result)
        self.assertEqual(len(fake.searches), 1)


class WatchlistTests(unittest.TestCase):
    def write(self, value):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "ebay_watchlist.json"
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def test_the_committed_watchlist_loads(self):
        games = ebay_prices.load_watchlist()
        self.assertTrue(1 <= len(games) <= ebay_prices.MAX_GAMES)
        for entry in games:
            self.assertEqual(entry["search"], " ".join(ebay_prices.words(entry["search"])))

    def test_the_most_games_allowed_fits_ebays_daily_allowance_at_one_run_an_hour(self):
        self.assertLessEqual(ebay_prices.MAX_GAMES * len(ebay_prices.MARKETS) * 24, 5000)

    def test_the_committed_watchlist_names_real_ps2_games(self):
        library_path = ROOT / "data" / "ps2_database.json"
        if not library_path.exists():
            self.skipTest("no cached PS2 library")
        library = {" ".join(ebay_prices.words(title))
                   for title in json.loads(library_path.read_text(encoding="utf-8"))}
        for entry in ebay_prices.load_watchlist():
            self.assertIn(" ".join(ebay_prices.words(entry["title"])), library, entry["title"])

    def test_search_words_are_cleaned_before_they_reach_ebay(self):
        (entry,) = ebay_prices.load_watchlist(self.write(
            {"games": [{"title": "Jak II: Renegade", "search": "Jak II (Renegade, PAL)", "exclude": ["Demo!", ""]}]}))
        self.assertEqual(entry, {"title": "Jak II: Renegade", "search": "jak ii renegade pal", "exclude": ["demo"]})

    def test_mistakes_get_a_readable_message(self):
        cases = {
            "{not json": "not valid JSON",
            json.dumps({"games": []}): "at least one game",
            json.dumps({"games": [{"name": "Ico"}]}): 'needs a "title"',
            json.dumps({"games": [{"title": "Ico"}, {"title": "ICO"}]}): "listed twice",
            json.dumps({"games": [{"title": "Ico", "search": "!!!"}]}): '"search"',
            json.dumps({"games": [{"title": "Ico", "exclude": "colossus"}]}): '"exclude"',
            json.dumps({"games": [{"title": "word " * 30}]}): "too long",
            json.dumps({"games": [{"title": f"Game {n}"} for n in range(101)]}): "daily limit",
        }
        for text, expected in cases.items():
            with self.assertRaises(ebay_prices.EbayError) as caught:
                ebay_prices.load_watchlist(self.write(text))
            self.assertIn(expected, str(caught.exception))

    def test_a_missing_file_is_an_error_not_a_crash(self):
        with self.assertRaises(ebay_prices.EbayError):
            ebay_prices.load_watchlist(ROOT / "no_such_watchlist.json")


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.out = Path(folder.name) / "ebay" / "ebay_prices.json"
        self.argv = ["--out", str(self.out)]

    @staticmethod
    def answer(params, headers):
        currency = "GBP" if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB" else "USD"
        name = params["q"]
        return page(listing(f"{name} PS2", 24.99, currency=currency, item_id=1, postage=3.49),
                    listing(f"{name} PS2 boxed", 31.5, currency=currency, item_id=2))

    def test_a_full_run_writes_one_file_and_never_leaks_the_key(self):
        fake = FakeHttp(self.answer)
        code, printed = run_main(fake, self.argv)
        self.assertEqual(code, 0, printed)
        text = self.out.read_text(encoding="utf-8")
        data = json.loads(text)
        games = ebay_prices.load_watchlist()

        for secret in SECRETS + ("Bearer", "Basic"):
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, printed)
        self.assertEqual([row["title"] for row in data["games"]], [entry["title"] for entry in games])
        self.assertEqual(data["searches_used"], len(games) * 2)
        self.assertEqual(len(fake.token_calls), 1)
        self.assertFalse(data["limit_reached"])
        self.assertNotIn("limit_message", data)
        self.assertIn("Not sold prices", data["what"])
        self.assertRegex(data["fetched_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(data["markets"]["EBAY_GB"], {"label": "UK", "site": "www.ebay.co.uk", "currency": "GBP"})
        first = data["games"][0]["markets"]
        self.assertEqual(list(first), ["EBAY_US", "EBAY_GB"])
        self.assertEqual((first["EBAY_US"]["currency"], first["EBAY_GB"]["currency"]), ("USD", "GBP"))
        self.assertEqual((first["EBAY_US"]["median"], first["EBAY_US"]["lowest"]), (28.25, 24.99))
        self.assertNotIn("answered", first["EBAY_US"])
        self.assertTrue(text.endswith("}\n"))

    def test_the_public_log_holds_counts_but_no_prices(self):
        code, printed = run_main(FakeHttp(self.answer), self.argv)
        self.assertIn("Looking up 10 games on 2 eBay sites:", printed)
        self.assertIn("  Silent Hill 2 [US]: 2 of 2 listings counted\n", printed)
        self.assertIn("  Silent Hill 2 [UK]: 2 of 2 listings counted\n", printed)
        self.assertIn("20 searches used; 20 of 20 lookups answered.", printed)
        self.assertNotIn("Search check", printed)
        for price in ("24.99", "31.5", "28.2", "3.49"):
            self.assertNotIn(price, printed)

    def test_the_search_check_prints_counts_for_each_variation(self):
        fake = FakeHttp(lambda params, headers: page(listing("Silent Hill 2 PS2", 24.99), total=37))
        env = {"EBAY_CLIENT_ID": CLIENT_ID, "EBAY_CLIENT_SECRET": CLIENT_SECRET, "EBAY_DIAGNOSE": "true"}
        code, printed = run_main(fake, self.argv, env=env)
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
        self.assertEqual(json.loads(self.out.read_text(encoding="utf-8"))["searches_used"], 8 + 20)
        self.assertNotIn("24.99", printed)

    def test_without_the_key_it_says_what_to_do_and_calls_nobody(self):
        fake = FakeHttp(self.answer)
        code, printed = run_main(fake, self.argv, env={})
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: The eBay key is not set.", printed)
        self.assertIn("New repository secret", printed)
        self.assertEqual((fake.token_calls, fake.searches), ([], []))
        self.assertFalse(self.out.exists())

    def test_a_refused_key_writes_nothing_and_shows_nothing_secret(self):
        echo = f"bad credentials {CLIENT_ID}:{CLIENT_SECRET}"
        fake = FakeHttp(self.answer, token_answer=(401, {"error_description": echo}))
        code, printed = run_main(fake, self.argv)
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: eBay refused the key (HTTP 401: bad credentials ***:***)", printed)
        for secret in SECRETS:
            self.assertNotIn(secret, printed)
        self.assertEqual(fake.searches, [])
        self.assertFalse(self.out.exists())

    def test_when_ebay_stops_answering_the_run_is_abandoned_early(self):
        fake = FakeHttp(lambda params, headers: ebay_prices.NetworkProblem("TimeoutError"))
        code, printed = run_main(fake, self.argv)
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: eBay did not answer 3 lookups in a row", printed)
        self.assertEqual(len(fake.searches), 9, "three lookups of three tries each, not all twenty")
        self.assertFalse(self.out.exists())

    def test_when_most_lookups_fail_the_old_snapshot_is_left_alone(self):
        calls = {"n": 0}

        def answer(params, headers):
            calls["n"] += 1
            return self.answer(params, headers) if calls["n"] <= 9 else (500, {"errors": [{"message": "oops"}]})
        code, printed = run_main(FakeHttp(answer), self.argv)
        self.assertEqual(code, 1)
        self.assertIn("STOPPED: 11 of 20 lookups failed", printed)
        self.assertFalse(self.out.exists())

    def test_answers_with_no_listings_at_all_are_treated_as_a_broken_search(self):
        code, printed = run_main(FakeHttp(lambda params, headers: page()), self.argv)
        self.assertEqual(code, 1)
        self.assertIn("no listings counted, 0 returned (keyword search)", printed)
        self.assertIn("STOPPED: eBay answered but returned no listings for any game", printed)
        self.assertFalse(self.out.exists())

    def test_one_broken_site_does_not_lose_the_other_and_errors_are_scrubbed(self):
        def answer(params, headers):
            if headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB":
                return 500, {"errors": [{"message": f"Internal error for {headers['Authorization']}"}]}
            return self.answer(params, headers)
        code, printed = run_main(FakeHttp(answer), self.argv)
        self.assertEqual(code, 0, printed)
        text = self.out.read_text(encoding="utf-8")
        self.assertNotIn(TOKEN, text + printed)
        markets = json.loads(text)["games"][0]["markets"]
        self.assertEqual((markets["EBAY_US"]["status"], markets["EBAY_GB"]["status"]), ("ok", "error"))
        self.assertEqual(markets["EBAY_GB"]["error"], "HTTP 500: Internal error for Bearer ***")
        self.assertIn("Silent Hill 2 [UK]: FAILED HTTP 500: Internal error for Bearer ***", printed)

    def test_running_out_of_searches_stops_the_run_and_says_so(self):
        calls = {"n": 0}

        def answer(params, headers):
            calls["n"] += 1
            return self.answer(params, headers) if calls["n"] <= 3 else (429, {"errors": [{"message": "Limit hit"}]})
        fake = FakeHttp(answer)
        code, printed = run_main(fake, self.argv)
        self.assertEqual(code, 0, printed)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        statuses = [market["status"] for row in data["games"] for market in row["markets"].values()]
        self.assertTrue(data["limit_reached"])
        self.assertEqual(data["limit_message"], "HTTP 429: Limit hit")
        self.assertEqual(statuses[:3], ["ok", "ok", "ok"])
        self.assertEqual(set(statuses[3:]), {"not_checked"})
        self.assertEqual(len(fake.searches), 6, "three answers, then one search tried three times")
        self.assertIn("not checked, eBay's allowance of searches ran out", printed)
        self.assertIn("eBay's allowance of searches ran out (HTTP 429: Limit hit).", printed)

    def test_by_default_the_file_goes_outside_the_repository(self):
        self.assertNotIn(ROOT, ebay_prices.DEFAULT_OUT.resolve().parents)


class _Handler(BaseHTTPRequestHandler):
    seen = []

    def _reply(self, status, body, headers=()):
        payload = body.encode("utf-8")
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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


class RealRequestTests(unittest.TestCase):
    """The real request code against a server on this machine."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
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


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.lines = [line for line in text.split("\n") if line.strip() and not line.lstrip().startswith("#")]
        self.code = "\n".join(self.lines)

    def block(self, key):
        """The lines under a top-level key."""
        start = self.lines.index(f"{key}:")
        rest = self.lines[start + 1:]
        end = next((n for n, line in enumerate(rest) if not line.startswith(" ")), len(rest))
        return rest[:end]

    def test_it_only_runs_when_started_by_hand(self):
        triggers = [line.strip() for line in self.block("on") if re.match(r"^  \S", line)]
        self.assertEqual(triggers, ["workflow_dispatch:"])
        for trigger in ("pull_request", "pull_request_target", "issue_comment", "workflow_run", "schedule", "push:"):
            self.assertNotIn(trigger, self.code)

    def test_the_key_reaches_one_step_only(self):
        self.assertEqual(self.code.count("secrets."), 2)
        for name in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
            (line,) = [line for line in self.lines if f"secrets.{name}" in line]
            self.assertEqual(line, f"          {name}: ${{{{ secrets.{name} }}}}", "step-level env only")
        env_lines = [line for line in self.lines if line.strip() == "env:"]
        self.assertTrue(all(line == "        env:" for line in env_lines), "no workflow-level or job-level env")
        steps = self.code.split("\n      - ")
        holders = [step for step in steps if "secrets.EBAY" in step]
        self.assertEqual(len(holders), 1)
        self.assertIn("run: python ebay_prices.py", holders[0])
        self.assertNotIn("git ", holders[0])
        self.assertNotIn("echo", self.code)
        self.assertNotIn("set -x", self.code)

    def test_the_job_that_holds_the_key_installs_nothing(self):
        self.assertNotIn("pip", self.code)
        self.assertNotIn("npm", self.code)
        uses = sorted(line.split("uses:")[1].strip() for line in self.lines if "uses:" in line)
        self.assertEqual(uses, ["actions/checkout@v4", "actions/setup-python@v5"])
        self.assertIn("persist-credentials: false", self.code)

    def test_ebay_data_goes_to_its_own_replaced_branch_never_to_main_or_data(self):
        self.assertIn('--out "$RUNNER_TEMP/ebay/ebay_prices.json"', self.code)
        self.assertIn("git init -q -b ebay-data", self.code)
        self.assertIn("--force", self.code)
        self.assertTrue(self.code.rstrip().endswith(" ebay-data"))
        self.assertNotIn("data/", self.code)
        self.assertNotIn("main", self.code)

    def test_nothing_is_published_after_a_failed_lookup(self):
        self.assertNotIn("always()", self.code)
        self.assertNotIn("continue-on-error", self.code)
        self.assertNotIn("if:", self.code)

    def test_commits_use_the_no_reply_address(self):
        self.assertIn("41898282+github-actions[bot]@users.noreply.github.com", self.code)

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


if __name__ == "__main__":
    unittest.main()
