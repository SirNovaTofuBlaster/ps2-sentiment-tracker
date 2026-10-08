# Verification

How the YouTube, podcast and configurable-sources change (see [CHANGELOG.md](CHANGELOG.md)) was
checked before it was published: first by the author, then by two independent skeptical reviews
whose findings were all fixed. Every check can be re-run with the commands at the end.

## Summary

| Check | Result |
|---|---|
| Original sources kept | All 18 news URLs and 26 subreddits byte-identical, same order and groups; the scraper builds the same 21 requests as the old `RSS_FEEDS` |
| News/Reddit behaviour unchanged | Old (`main`) and new scraper give **identical** snapshots on the same real feed content: 591 items, same order, same PS2 matches and remaster flags, before and after the review fixes |
| Code meant to stay the same | Identical syntax trees for every matching, sentiment, title-cleaning, merge and retention function and constant |
| Dashboard edits | Every changed line of the original `index.html` reviewed; all original functions (search, filters, pagination, fallback mock data, Radar) still present |
| Live run, all sources | 196 feeds in 254 s. 195 read; the 1 failure was Time Extension, blocked from the test network only. 0 YouTube/podcast failures. 1539 items, 67 new PS2 matches from YouTube/podcasts |
| YouTube channel links | A real channel link resolved to its ID and was read; a non-existent one was reported as "Failing: channel link: HTTP 404" without affecting the run |
| Offline tests | 42 Python tests and 18 dashboard checks pass; page and scraper validators agree on 38 configs |
| Static site | Page, guide, feeds.json and data files served with the right types (curl smoke test); inline scripts pass `node --check` |
| Independent reviews | 2 reviewers; every finding fixed or documented (below) |
| Publishing hygiene | Every commit authored and committed with the contributor's GitHub no-reply address; a scan of all files, commits and the PR text found no personal data |

## Details

### Original sources kept

The 18 news feeds and 26 subreddits were moved from `scraper.py` into `feeds.json` by a script
that parsed the old lists straight out of `git show origin/main:scraper.py`. Nothing was retyped.
Checks:

- **Same URLs, same order, all enabled.** The news URLs match byte for byte and the subreddits
  match in spelling and order.
- **Same requests.** `build_jobs()` produces exactly the old `RSS_FEEDS`: the 18 URLs, then the
  same 3 multireddit URLs.
- **Same PS2 context and counts.** The subreddits that count as PS2 context are the same 4, and
  the old `TOTAL_SOURCES` (44) equals the enabled news and Reddit sources.
- **Kept in the future too.** `tests/test_scraper.py` pins both lists, so a future change can't
  drop one by accident.

### News/Reddit behaviour unchanged

`tools/regression_check.py` downloads the 21 news/Reddit feeds once, then runs the scraper from
`origin/main` and the working tree offline on the identical content. Both runs use the same PS2
title list, an empty previous snapshot and temporary output folders. Result, on two different
days' content:

```
Both versions fetch the same 21 news/Reddit feeds.
reference (origin/main): 591 items, total_tracked_feeds=44
working tree:          591 items, total_tracked_feeds=44
IDENTICAL: same items, same order (ignoring fields only the new version writes).
```

The only difference in the output is the two new fields every item carries: `source_type` and
`feed`.

### Code meant to stay the same

A syntax-tree comparison of `origin/main:scraper.py` and the new `scraper.py` found the following
identical: `clean_title`, `read_cached_titles`, `load_ps2_titles`, `TitleMatcher.__init__`,
`TitleMatcher.summary`, `analyze_sentiment`, `entry_timestamp`, `item_key`,
`load_previous_items`, `_retry_delay`, and every matching, sentiment and limit constant
(aliases, fallback titles, word lists, patterns, thresholds, retention, user agent). Changed on
purpose: the fetch loop, `fetch_feed` (a flag so only news/Reddit wait on HTTP 429), the matcher's
PS2-context hook (now the `ps2` role), `entry_source` and `analyze_entry`. To repeat:

```python
import ast, subprocess
old = subprocess.run(["git", "show", "origin/main:scraper.py"], capture_output=True, text=True).stdout
new = open("scraper.py", encoding="utf-8").read()
def defs(src):
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out[node.name] = node
            out.update({f"{node.name}.{s.name}": s for s in getattr(node, "body", []) if isinstance(s, ast.FunctionDef)})
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            out[node.targets[0].id] = node
    return out
o, n = defs(old), defs(new)
print("unchanged:", sorted(k for k in o if k in n and ast.dump(o[k]) == ast.dump(n[k])))
print("changed:  ", sorted(k for k in o if k in n and ast.dump(o[k]) != ast.dump(n[k])))
print("removed:  ", sorted(k for k in o if k not in n))
```

### Live runs

These full runs of every enabled source ran in a scratch copy with `FULL_RUN=1`, so the
repository's `data/` stayed untouched:

- **First run:** 196 feeds, 1513 items, 0 YouTube/podcast failures, 66 new PS2 matches from
  YouTube and podcasts. Examples: "Beating EVERY PS2 Game #145 - Persona 4", "Tekken 5 - E3 2005
  Trailer".
- **After the review fixes:** 196 feeds in 254 s, 1539 items, 67 new PS2 matches. The Besties now
  keeps its 2 recent episodes as separate items; before the fix it had 0, see finding A2.
- **In both runs the only failure** was Time Extension, which blocks the test network but not
  GitHub's runners.
- **YouTube channel links:** a real handle resolved to its channel ID and was fetched. A made-up
  handle showed "channel link: HTTP 404" and the run continued.
- **Dashboard logic** ran over the 1513 real items in Node: 64 ms to render. The status badges
  matched the data. VG247, r/Steelbook and r/xboxone show as Stale, and Time Extension (from the
  test network) as Failing.

## Independent reviews

Two reviewers, each with fresh context and read-only access, were told to prove the change wrong
and to report only findings backed by a concrete failure scenario. One covered the scraper,
`feeds.json`, the workflows and the Python tests; the other covered the dashboard, the guide, the
docs and the Node checks.

### Scraper, workflows and tests

| # | Finding | Resolution |
|---|---|---|
| A1 | **Bug:** a malformed link the page accepted (`https:/site.com/feed`) would make the scraper reject feeds.json on every run | One shared link pattern (`FEED_URL_PATTERN` = `FEED_URL_RE`); the page stores the browser-repaired link; parity test covers the reviewers' inputs |
| A2 | **Bug:** podcast episodes that share one `<link>` (The Besties) collapsed into one item, usually dropped | Episodes with a shared, missing or non-URL link use their audio file; test |
| A3 | **Bug:** a run that waited in the concurrency queue checked out a stale commit and failed to push | Checkout uses `ref: ${{ github.ref }}`. The reviewer reproduced the failure in a local git simulation and showed that checking out the branch head avoids it |
| A4 | **Risk:** podcasts were due only at fixed UTC hours, but GitHub fired 3 of about 16 scheduled runs here | Due once the interval has passed since the last fetch (`data/poll_state.json`); tests |
| A5 | **Risk:** dead feeds (404) counted towards skipping a whole host | Only connection errors, timeouts, 5xx and 429 count; test |
| A6 | **Nits:** a bare `<guid>` used as the link; a BOM stopped the scraper; odd hand-edited values raised tracebacks | Fixed; tests |

Confirmed by this reviewer:

- **Original feeds:** all 18 news feeds and 26 subreddits are present, and `build_jobs()`
  produces identical multireddit URLs.
- **Output:** 591 identical items from the same 21 live feeds.
- **Unchanged rules:** the abort threshold and the core-only 429 retry.
- **New sources:** all 175 enabled YouTube/podcast feeds return 200 and parse.
- **YouTube links:** the lookup works on real `@handle`, `/user/` and `/c/` pages.
- **Workflow:** the `FULL_RUN` expression is correct, and bot commits can't retrigger the workflow.
- **Tests:** no Python 3.13-only syntax and no expiring dates.

### Dashboard, guide and docs

| # | Finding | Resolution |
|---|---|---|
| B1 | **Bug:** same as A1, plus `"poll_every_hours": null` accepted by the page only | Same fix; `null` rejected on both sides |
| B2 | **Bug:** *I've saved it* also marked edits made after copying as saved | Only the copied text becomes the saved baseline; test |
| B3 | **Risk:** the page's copy of feeds.json comes from the website, which lags a save by minutes, so a second save could undo the first | The page loads the committed file from the GitHub API when it differs, and checks it before both kinds of save, offering to load the latest list first; tests |
| B4 | **Risk:** token exposure (a CDN script on the page, Remember sharing the github.io site, the reach of a classic `public_repo` token) | Documented in the settings box, the guide and ARCHITECTURE.md; saving without a token stays the default. The CDN script was already on the page before this change |
| B5 | **Bug:** a channel ID was taken from anywhere in pasted text (`@UCBerkeley...` became an ID) | Only a bare ID or a `/channel/` link counts; test |
| B6 | **Doc error:** the "Propose changes" path missed the fork and "Create pull request" steps | Guide, save box and ARCHITECTURE.md corrected; test checks the text |
| B7 | **Doc error:** "Not checked yet" was said to appear after switching a source back on | Wording corrected (it shows the last known status) |
| B8 | **Bug:** old `itunes.apple.com` podcast links were stored as feeds | Recognised and looked up; test |
| B9 | **Risk:** "How to use" links opened in the same tab and could lose unsaved edits | They open in a new tab |
| B10 | **Nits:** duplicate-channel wording, Reddit links without `https://`, repository names with a dot, items from before this change, "stats as of" date, token texts, revoke links, an undocumented badge, untested paths | All fixed or documented; tests added for the remove button, the token save path and the conflict check |

Confirmed by this reviewer:

- **Escaping:** every place data is written into the page is escaped.
- **Token:** it is sent only to api.github.com, never in commits or messages.
- **GitHub API:** calls use the right endpoints, `sha` and branch, and commits use the no-reply
  identity.
- **Validators:** the page and scraper agree on key and validation rules, and lowercase handles
  identically.
- **Existing dashboard:** search, filters, pagination, fallback data and the Radar work as before.
- **Docs:** the guide's instructions match the UI, and every row of SOURCES.md matches feeds.json.

## 2026-10-06: eBay asking prices and the dashboard lists

How `ebay_prices.py`, its workflow and the dashboard changes of 2026-10-06 were checked.

| Check | Result |
|---|---|
| Live runs against eBay | Three runs on 2026-10-06 (20:26, 20:40, 20:47 UTC) for 10 pinned games on both sites. All 20 lookups answered each time; the last counted 685 of the 1,167 listings eBay returned |
| What the first run showed | The request format written from eBay's documentation worked unchanged. A US postcode had to be added before eBay quoted postage for every US listing (it had for about half) |
| Listing rules against real titles | The 10 cheapest counted listings and up to 5 left-out titles per reason, for every game and site, were read by hand after each run. Run 1 let through soundtracks, cheat discs, a hat and an Xbox copy; run 2 wrongly left out 13 real copies of 172 sampled ("with case and manual", "+ OST", an emoji glued to the name). Both were fixed and the titles became test cases |
| Rewrite did not change verdicts | After the script was rewritten to price every mentioned game, all 690 real titles from runs 2 and 3 were replayed through the new rules: the only differences were the 13 fixes above |
| Levels on the real feed | A replay of the last 7 days flagged 12 games as surging: 5 real, 1 the same post in two subreddits, 6 the wrong game matched. Recorded as a known limit |
| Plan on the real feed | 182 games tracked (10 pinned), 15 one-word titles left out, 364 lookups due on a first run, capped at 500 searches |
| Not yet run live | Everything added after the third run: pricing all mentioned games, levels, the two-way search for Roman numerals, the price files, and the automatic trigger |
| Workflow steps | The save-to-main and publish steps were run against a local stand-in repository, including a competing push between checkout and save, and three consecutive publishes (the branch held one commit each time) |
| Offline tests | 176 Python tests (42 scraper, 9 matcher, 125 eBay) and 24 dashboard checks pass |
| Rendering | The page was rendered at 1280px and at 427px, with sample price data and without any: no sideways scroll, no script errors, lists fold and open, stripes alternate, "Show fewer" stays on screen in an opened list and folding returns to the section's heading |
| Do the dashboard checks bite | Twelve one-line breakages of `index.html` and `retro.css` (prices never loaded, a quiet game sorted with the rest, no folding, an unescaped price, hover on touch screens, and so on): the checks failed on every one |

### Independent reviews

Three reviews with fresh context, each told to report only findings backed by a concrete failure.

**First (the 10-game version).** Must-fix findings and what was done:

| Finding | Resolution |
|---|---|
| The "2" in "PlayStation 2" satisfied "Silent Hill 2", so every Silent Hill listing counted | The name must appear as words together and in order; a following single number means a sequel or a set |
| A run where eBay returned nothing for every game was green and published an empty file | Such a run now fails and writes nothing |
| One success in twenty overwrote a good file | More than half failing fails the run |
| Log lines appeared out of order | Every line is flushed as it is printed |
| The job holding the key installed three unpinned packages | The script was rewritten on the standard library; the job installs nothing |
| `conditions:{USED}` might not match the category's condition names | The search names the condition numbers, and a search check prints counts for both forms |
| Spaces were sent as "+" | Queries are percent-encoded the way eBay's examples are |

**Second (pricing every mentioned game).** Must-fix findings and what was done:

| Finding | Resolution |
|---|---|
| A failing run spent up to 500 searches an hour and recorded none of them | A run whose first ten lookups all fail stops there |
| Three unanswered lookups discarded everything learned before them | The run stops and keeps what it has; the usual checks decide whether to write |
| An unreadable month of history was silently replaced by the new rows | A price file that exists but cannot be read stops the run before eBay is asked |
| The library files one game as "Jak X" and as "Jak X: Combat Racing", and the longer name was treated as another game | The single full name a title has in the library is the same game; expansions and other subtitles are not |
| "Ultimate Spider-Man" counted as "Spider-Man", "The Ant Bully" as "Bully" | A listing naming another library game that contains this one's name is left out |
| Dropping the Roman numeral made the search franchise-wide | Both spellings are searched and merged, each listing once |
| "Getaway" and "The Getaway" were tracked twice | Titles that come to the same name are one game |
| A pull request could add a workflow with the scraper's name and so start the price job | The job refuses runs started by pull requests or from another repository |

Left for later, by the reviewer's own ranking: dormant games are checked daily for ever; state
is keyed by a game's display title in `latest.json` (lookups go by a spelling-independent key);
11 names the scraper can emit from its built-in fallback list are not in `ps2_database.json`.

**Third (the dashboard changes, the docs and the two workflows).** Findings and what was done:

| Finding | Resolution |
|---|---|
| On a phone, the last feed card tapped kept its hover tint and broke the stripes | Row hover applies only where the device can hover |
| A flat six-hour rule dimmed every quiet game, which is checked once a day by design | Each level has its own limit: 3 hours surging, 8 normal and staple, 30 quiet |
| Dimming a whole line made "search needs tuning" and "none listed" hard to read | Only the price is dimmed |
| The dashboard check reads `retro.css`, but a change to that file did not start the Tests workflow | `retro.css` added to the workflow's paths |
| "Show all 25" under a list of 142 games read as "all" | The button says how many more it opens |
| The mention count on an eBay row differs from Most Mentioned Games (headlines only, 14 days) | The row says "in headlines", and the guide explains the difference |
| A price file the page could not draw would have stopped the rest of the page loading | Drawing is guarded; the section hides itself |
| After opening 180 games the only way to fold them was at the far end | "Show fewer" follows the reader; folding returns to the section's heading |
| Stale counts and wording (219 sources in the banner, SOURCES.md totals, "most days" for a staple) | Corrected against `feeds.json` and the script's settings |
| Six breakages the checks did not notice | A check added for each |

Left for later: the price history is stored but not drawn; the eBay list has no search box;
`fixtures.yml`, started by hand only, still pushes without a retry.

## 2026-10-07: prices beside every game, three tabs, the feed's two weeks

How the dashboard changes of 2026-10-07 and the `MAX_ITEMS` change in `scraper.py` were checked.

| Check | Result |
|---|---|
| First live run for every game | 2026-10-06, 22:41 UTC: 182 games, 405 searches, every game checked on both sites. 39,283 listings returned, 23,827 counted. 177 games have a figure on at least one site; 22 game-and-site pairs are `unmatched` |
| Spot checks of that run | The cheapest counted listings and the left-out examples were read for *God of War*, *Kingdom Hearts*, *Monster Hunter* and *Dynasty Warriors 3* on both sites. Two wrong listings counted (a *Devil May Cry 3* copy "with Monster Hunter"; "Xtreme Legends: Dynasty Warriors 3"); recorded as open items |
| Was the feed stuck at 5,000 | No. The last nine snapshots in the git history were compared: after reaching 5,000, each run added new items and dropped as many (200, 95, 85, 26), and the newest item was always minutes old. The window had shrunk from 14 days to 9.3 |
| Only one thing changed in `scraper.py` | A comparison of the syntax trees of the old and new file: 40 functions and classes identical, one assignment different (`MAX_ITEMS`) |
| Not run | `tools/regression_check.py` and a `FULL_RUN=1` scratch run: both need the live feeds, which could not be reached from the machine the change was written on. The regression check collects about a thousand items, so neither limit can affect it |
| Does anything else assume 5,000 items | `archive.py`, `demand.py`, `ebay_prices.py` and the workflows were read: nothing is sized for it. A 12,000-item feed loads in about 3 seconds in a headless browser and redraws in under 0.3 |
| Page and price script agree on names | `priceKey()` against `search_terms()` on 3,317 titles (the library, the feed, the price file, awkward spellings): no difference. The reviewer's fuzz of 702,445 strings found differences only on characters no title uses |
| The right price on the right row | Every distinct game in the feed (144) and the Demand Index (58) was mapped by the page and by `plan_games()`: no disagreement. The mappings that differ in spelling are all the same game. 296 of 346 feed rows naming a game show a median; the 50 without are one-word or never-priced names and three games with nothing countable |
| Offline tests | 178 Python tests and 28 dashboard checks pass, in UTC and in four other time zones |
| Do the checks bite | 59 one-line breakages of `index.html`, `retro.css` and `scraper.py` across three rounds. Three were not noticed at first: two got a check, and the third turned out to be a line that did nothing and was removed |
| Rendering | Real data, at 1280, 768, 427, 360 and 320px, with a price file, without one and with a damaged one: no sideways scroll, no script errors, exactly one page on screen through every tab, link, Back and Forward tried, the tile labels on one line |

### Independent review

One review with fresh context, told to report only findings backed by a concrete failure.

| Finding | Resolution |
|---|---|
| The new check on the item label failed in time zones behind or ahead of UTC at certain hours (its fixture had no "UTC") | Fixture corrected; the checks were run in five time zones |
| The changelog said dropped items do not return; 203 of the 392 the limit had cut are still listed by their sources and come back on the first run | Changelog corrected, with what the tile will read meanwhile |
| The guide told readers to look an unpriced game up on the prices tab, where 16 of the 19 unpriced games do not appear | Guide and the tab's empty message now say which games are never priced |
| The search box matched only the evened-out name, so "Kingdom Hearts I" found nothing while "II" was being typed and "The" hid titles | It also matches the text as typed |
| A failed REFRESH (a 503, a dropped connection) wiped every price and said "No prices yet… Run workflow" | A failed read keeps what is loaded; with nothing loaded the page says the file could not be read |
| "Items · last 14 days" wrapped on phones and pushed its number out of line | Shortened to "Items · 14 days", kept on one line down to 320px |
| A fresh load of `index.html#sourcesSection` stopped far above the panel (as it did before this change) | The address is read once more when the first load has finished |
| Back from another tab left the site | Changing page adds a history entry; Back and Forward go through the address |
| 14 breakages the checks did not notice (name rule variants, the tab's number, `aria-selected`, the search box's wiring, a missing element, rounding, a 13-day retention) | A check added for each; the sandbox's elements now keep attributes, and one check confirms every element the script asks for exists in the page |
| The median's tooltip said "Opens the listings" though the link is a plain search | Reworded |

Left as they are: arrow keys do not move between tabs; the name rules differ on characters no
title uses.

## 2026-10-07: forums and 4chan's game boards

How the two new source types were checked. The live checks ran on GitHub's own runners, as
the *Live checks* workflow on the pull request, because that is where the scraper runs and
sites treat those machines differently from a home connection.

| Check | Result |
|---|---|
| Do the sources answer where the scraper runs | `tools/try_sources.py forum 4chan` ran on every push to the pull request, eight times between 13:09 and 17:25 UTC. Forums: of the six that had answered from outside GitHub, only the two Lemmy feeds did; NeoGAF, both GBAtemp boards and PSX-Place returned HTTP 403 from behind Cloudflare, also under a feed reader's name. 4chan: all seven boards answered in each of those runs |
| What the boards give | The eighth run, the first with the rules for posts as merged: 1,138 live threads, 29 naming a PS2 game, 24 of them started in the last 14 days: 28 mentions of 20 games. The headline rules would have counted 32 more mentions; by their names most were another game or an ordinary phrase. The per-board table is in SOURCES.md |
| News and Reddit output unchanged | `tools/regression_check.py --ref origin/main` ran in the same workflow on the same live feeds. Runs 1 to 3 failed at the refused forums; in runs 4 to 8 both steps passed, and the comparison passes only when the two snapshots are identical |
| Only what was meant to change in `scraper.py` | A comparison of the syntax trees of the old and new file: 108 functions, methods and settings before, 101 identical, 7 changed (`SOURCE_TYPES`, `SOURCE_PREFIX`, `entry_link`, `source_key`, `validate_config`, `build_jobs`, `run_scraper`) and 28 added. `TitleMatcher` is untouched: the rules for posts sit beside it |
| Nothing a poster wrote is kept | The test fixtures carry a marker word in the subject, the comment and every other field a poster fills in (name, tripcode, ID, flag, file name, tag, the link's slug, replies). None reaches the snapshot, the health file or the log, with well-formed catalogs and with 14 answers of the wrong shape read by the real reader. The reviewer's fuzz of 4,000 junk catalogs produced 9,495 rows with no marker anywhere, every matched title a library title, every row with exactly the 14 expected fields |
| The page and the scraper agree on a valid source | The two validators give the same verdict on `feeds.json` and on 66 altered configs, 29 of them about forums and boards; the reviewer tried 63 more (Unicode digits, a trailing newline, non-strings, a board that also has a `url`) without a disagreement |
| Offline tests | 204 Python tests and 29 dashboard checks pass, here with rapidfuzz in pure Python and on GitHub with its compiled build (the two split words differently at an underscore, which the rules for posts allow for) |
| Do the checks bite | 54 one-line breakages of `scraper.py`, `archive.py`, `index.html` and the two tools. 53 were noticed. The other one lets `match_all()` return near misses for posts, which changes nothing: a name must also be found word for word where it stands |
| Not checked | What real posts say: nobody working on this could read the boards, so the rules for posts were judged from game names and counts, and from made-up posts. The dashboard in a browser: its script was run in the Node sandbox only (rule 11) |

### Independent review

One review with fresh context, told to report only findings backed by a concrete failure
and to prove them by running code in a copy.

| Finding | Resolution |
|---|---|
| A forum item replaced a news item with the same link: Lemmy gives the shared article as a post's `<link>`, and the forum, fetched later, won the merge. The news/Reddit comparison cannot see it | A thread's link is its own page (`<comments>`, then `<guid>`), and a forum row never replaces another source's row. Tested in the run that sees both and in a later one. Checked against the live feed: 8 of 20 posts in *Lemmy games* were link posts |
| `games_in_post()` accepted what the docs said it rejected: half-titles once a post said PS2 ("the room"), "13" for *XIII*, a sentence's first word ("Obscure PS2 games"), capitals elsewhere in the post ("Top tier. Gun..."), numbers that were counting ("Yakuza 2 days ago"), the pronoun "I" as a 1 | The rules were rewritten to judge the words that matched, where they stand; each of these has a test |
| Correct names were rejected or filed under another game: titles the library writes with a lower-case word, titles longer than six words, a long title counted as the shorter one inside it | Capitals are asked only where the library has them; long titles are found whole and the shorter one is not counted beside them. "Max Payne 2" is no longer counted as *Max Payne* |
| Rule 12 was tested only for the two data files, and only with a name in the fixtures: five leaks went unnoticed (printing a post, the slug in the link, a file name field, the answer in an error message, the tool printing subjects) | Fixtures carry every poster field; the log and the tool's output are checked as well as the files; all five are now noticed |
| A catalog with `"threads": 5` stopped the whole run with a `TypeError`, news included | Anything of the wrong shape is passed over |
| A forum headline with a line break could start a line of its own in the Live checks log, where GitHub reads `::error` as a command | Headlines are printed on one line |
| Three behaviours no test pinned: the length of the pause between boards, what it is counted from, a forum being an extra | Tested, the pause on a clock that only moves when the scraper sleeps |
| A thread dated in year 322 or 2300 sorted above everything and never aged out | A thread without a plausible date is left alone |
| The tests did not run on pushes that change only `archive.py`, `tools/` or `live-checks.yml` | Added to the test workflow's paths |
| Docs: no entry here; rule 12 forbade fields the rows carry; "If-Modified-Since on each request" though the check tool sends none; a forum "read exactly like a news feed"; a made-up 50 archived for good; a number that could not be traced | This entry; rule 12 reworded; the docs say which reader sends the date; threads carry no score at all (`null`, and no `n` in the archive); numbers re-measured from one run |

Left as they are: the branch's commits were made under an Anthropic no-reply address, not a
GitHub one (the commit that lands on `main` is GitHub's squash, under the maintainer's
no-reply address); a browser tab left open on the old page weighs new 4chan rows at 1 until
it is reloaded.

## 2026-10-07: start-up screen colours

How the re-colouring of `retro.css` and the banner change were checked. No browser was used
(rule 11); the maintainer chose the direction from a separate mock-up.

| Check | Result |
|---|---|
| What changed | `retro.css` (the values at the top, the strip, the tag, the tab line, two tints, two overrides of Tailwind), the banner and three class names in `index.html`, wording and the mark in `guide.html`. `scraper.py`, `feeds.json` and the data are untouched, so the live checks did not apply |
| Readable | Worked out, not eyeballed: every colour that carries text against the page, the banner, a field, a striped row and both kinds of row under the pointer is at least 4.5 to 1. The lowest are the quiet grey and the red on a hovered striped row. The check is part of the test suite |
| One job per colour | No rule but a price link's uses the yellow, no colour is written out below the list at the top of the stylesheet, and the pages carry no yellow class of their own |
| Nothing left of the old palette | All 17 old values, one that was written out in a rule, the guide's three older ones and the old tint are searched for in the stylesheet and both pages |
| Layout | By reading: the strip is a block above the banner's content on both pages, outside the phone grid and the guide's fixed-height row; the three parts left in the phone banner each have their place; the new classes win where they should and the phone rules only change sizes |
| Offline tests | 204 Python tests and 30 dashboard checks pass |
| Do the checks bite | 32 one-line breakages of the stylesheet and the two pages, including every one the reviewer slipped past the first version of the check: all noticed |
| Static files | `index.html`, `guide.html`, `retro.css`, `feeds.json` and the snapshot served by `python -m http.server` and fetched with curl: all 200 |
| Not checked | How it looks. The contrast figures are arithmetic and the cascade was reasoned from the selectors, with Tailwind's own rules taken from its documentation rather than from a loaded page |

### Independent review

One review with fresh context and no browser, told to report only findings backed by a
concrete failure.

| Finding | Resolution |
|---|---|
| Two of the guide's three mentions still said "amber buttons" | All three say yellow; a check counts them |
| The new check required more than 200 enabled sources, so switching 31 off from the dashboard would have turned the tests red, and the guide quoted a number again | The number is out of the guide and the check |
| The stripe was barely there: 1.04 to 1 against the page, where it had been 1.13 | A lighter neutral (1.11 to 1), with a minimum in the check |
| "Meets the contrast standard on every ground" was false on a hovered row (the quiet grey 4.2, the red tag 4.3) and on switched-off rows | Quiet greys and the red lightened, the pointer's tint made fainter, hovered rows added to the check; the changelog says what is not covered |
| Ten breakages the first version of the check missed: yellow by another variable, a written-out hex or a Tailwind class; old values outside its short list; a role swapped; the strip hidden; a later rule undoing the tag; a light label on a filled button; a paragraph back under another name | Each is now noticed |
| The tests did not run on pushes that change only `guide.html` | Added to the workflow's paths |
| The stylesheet's comment claimed each colour has one job; red and teal also mark failing and healthy, falling and rising | Comment and changelog say what the code does; *Run scraper now*, the one teal button, is blue |
| The guide's new sentence said games link to "what they sell for" while the guide says the buttons are searches, not prices | Reworded |
| The changelog said the light direction needed only new values at the top of the stylesheet | Corrected, with what else it needs |
| Two colours from outside the palette, both older than this change: ticked boxes in Tailwind's cyan, row lines in its slate | Both overridden |

Left as they are: *Remaster flags* is red at zero and *Active feeds* is teal whatever the
sources' health (it counts the ones switched on); the branch's commit was made under an
Anthropic no-reply address and lands on `main` as GitHub's squash under the maintainer's.

## 2026-10-07: games first

How the new list on the Tracker and the table's opening view were checked. No browser was
used (rule 11).

| Check | Result |
|---|---|
| What changed | `index.html` (a section, three functions for the list, the table's filter, its summary line and its game column, and which games Most Mentioned Games counts), a few rules in `retro.css`, `guide.html`. `scraper.py`, `feeds.json`, the workflows and everything under `data/` are untouched, so the live checks and the regression check did not apply |
| Nothing else moved | `git diff origin/main -- index.html` read line by line: outside the new code, the changes are the three handlers on the search box and the menus, the menu's order and default, where the line over the table sits, the table's game cell and the loop in `renderTopGames()`. The second reviewer compared 126 settings of the box and the menus with the page before the change: the same rows and pages, but for the search that now sees every game |
| Against real data | The page loaded with the snapshot of 2026-10-07 17:44 UTC: in the 24 hours before its newest item 654 items, 53 naming a game, 59 games; the table opens on 412 of 5,586; Most Mentioned Games ranks 209 games |
| Offline tests | 204 Python tests and 31 dashboard checks pass |
| Do the checks bite | 159 one-line breakages of the new code (the window, the order, every count and wording, escaping, the click and its undoing, paging and reloading with a game chosen, the wiring into the page, the markup, the stylesheet's rules): all noticed. That is after three rounds: the second reviewer broke the page 73 ways of their own, about 30 of them real and unnoticed, then 27 more, nine of them real and unnoticed. Each of those has a case now but one: a line that follows the browser's language instead of English reads the same on the test machine |
| Static files | `index.html`, `guide.html`, `retro.css`, `feeds.json` and the snapshot served by `python -m http.server` and fetched with curl: all 200; `node --check` on the inline scripts |
| Not checked | How it looks, on a desk or a phone. The phone rules were reasoned from the selectors |

### Independent reviews

Two reviews, each with fresh context and no browser, working in a copy, told to report only
findings backed by a concrete failure. The first ran the page's functions on ten earlier
snapshots from the repository's history.

| Finding | Resolution |
|---|---|
| A click on a game put its name in the search box, so *Final Fantasy X* also showed *Final Fantasy XII*, and *Retro* showed every row from r/retrogaming | The click now shows the items whose games include exactly that name (`gameFilter`); the search box is left empty |
| The line over the table gave the same count whatever the search box and the second menu left on show | It is written from the rows that are showing |
| A row showed only an item's first game, so a click on its second game opened rows that seemed to be about something else | A row leads with the game the table was opened on and lists the others |
| Nothing checked that the page draws the list, or that a switched-off source leaves it; 14 one-line breakages went unnoticed | The check was rewritten; see "Do the checks bite" |
| The wording said "collected in the last 24 hours" while the code goes by the date of publication | "Published" everywhere, with the reason in the guide and the changelog |
| The documented order (headline before text, then mentions) was not the order the code used | The code was simplified to one order and the documents say that one |
| `font: inherit` on the name's button undid the bold of the first name, and the phone rule for buttons applied to it unplanned | Removed; the name keeps the full height on a phone on purpose and the button in the sentence has its own rule |
| Before the first scrape the list said the robot had found nothing in the last day | It says it is waiting for the first scrape |
| Three passages in the guide and the architecture notes still described the Tracker without the list | Corrected |
| A change to the table was not announced to a screen reader | The line over the table is a live region |
| "Names a game" was decided two ways (`matched_game` in one place, the list in another) | One function, `gamesOf()`, used by all four |

The second review, of the state after those fixes:

| Finding | Resolution |
|---|---|
| 15 of the 59 games in the new list were missing from Most Mentioned Games, which counted an item's first game only, while the guide says it ranks every game | It counts every game an item names, like the list and the three scripts; 162 games became 209 on the measured snapshot |
| The check was weaker than this page said: about 30 real one-line breakages went unnoticed, and the case labelled "a reload" did not reload | Each has a case now, the reload included; the figure above is the new one |
| A search could find an item by a game that the row then hid behind "and 12 more" | The games the search found are listed first |
| *Back to every game* destroyed the button that had the keyboard, and a click on a game left the keyboard up in the list | Both hand it to the line over the table |
| The line's changing length shared a row with the search box and the menus and would have pushed them about (reasoned, not seen) | The line has a row of its own |
| 654 items could not be reproduced from the snapshot's own time (652) | The documents say what the 24 hours were counted from |
| "Published is the date the source gave" is not so for a source that gives none | Said in the guide, the changelog and the architecture notes |
| "Showing the 412 of 5,586" over a table whose footer says "Showing 1–100 of 412" | The line no longer starts with "Showing" |
| "1 of 1 item that name", and "waiting for the first scrape" when a load had failed | Singular forms throughout; the empty list says no feed has been loaded |

The same reviewer then checked those fixes. Eight of nine held; nothing else had moved in
126 settings of the box and the menus, and Most Mentioned Games matched a count made
independently (532 mentions, 209 games, no game's count lower than before).

| Finding | Resolution |
|---|---|
| A space after the search words (a phone's keyboard adds one) left the searched game behind "and 12 more" again | The words are trimmed before the games are compared |
| Three of the earlier breakages were still unnoticed, though this page said none: the list built from part of the feed, 4chan left out of it, and an opened list folding at the next reload after a click | A feed of 1,201 items with a 4chan thread goes through the page itself, and the list is looked at after the reload |
| Nothing would notice the keyboard being taken from the search box on every keystroke, or on every reload | Both are counted |
| Nine new breakages unnoticed: a search in capitals, a game found in the middle of a name, a second found game, Most Mentioned Games counting two games of three, a rule hiding the line by its position | Each has a case; the check now holds the full list of what the stylesheet hides |
| The guide's "so" joined the wrong two things; "moves nothing" was more than is true (the table below still shifts when the line wraps) | Reworded |

Left as they are: the list promotes wrong matches along with right ones, since it is only as
good as the matcher; a game the table was opened on stays chosen through a reload of the
data even if no item names it any more, and the line then says so; the line over the table
is read out again on every keystroke in the search box, which is talkative and was not
tried with a screen reader.

## 2026-10-08: the last day's games by price, and each median's change over a week

How the price order on the front list, the brackets beside the medians and the new `week`
figure in `latest.json` were checked. No browser was used (rule 11), and the price job could
not be run against eBay from here.

| Check | Result |
|---|---|
| What changed | `index.html` (`medianOf()`, `byPrice()`, `weekBefore()`, `priceChangeHtml()`, the list's line, the two places a median is drawn), `retro.css` (the bracket's colours and dimming), `ebay_prices.py` (`history_index()`, `week_before()`, `add_week_before()`, reading the month before), the guide and the docs. `scraper.py`, `feeds.json` and the workflows are untouched |
| The price job stays safe | It asks eBay nothing new, prints nothing new, and writes only numbers and stamps to `latest.json`; the month before is read and never written; a damaged one, rows in other shapes, NaN and Infinity cost only the brackets. The reviewer found no way for the change to stop a run |
| Against real data | The front list on the feed snapshot of 2026-10-08 01:04 UTC with that morning's price file: *Metal Gear Solid 3: Subsistence* (£98.98) first, down to *Smuggler's Run* (£4.95); then *Siren*, which has only a US price ($75); then *Retro* and *Black*, which have none. The real history moved a week back gave 380 of the 401 medians a week-old figure, in 0.02 seconds |
| Offline tests | 215 Python tests and 32 dashboard checks pass |
| Do the checks bite | 53 one-line breakages of the new code in the page, the stylesheet and the price job: 49 noticed. The other four change nothing that can happen (a tie order that the stable sort already keeps; guards against shapes the price job never writes) |
| Not checked | How the brackets look, and a real run of the price job a week on: the first `week` figures are due after 2026-10-13 22:41 UTC |

### Independent review

One review with fresh context and no browser, working in a copy, told to report only findings
backed by a concrete failure. It moved the real history a week back to see real brackets and
fuzzed the history reader with 20,000 sets of junk rows.

| Finding | Resolution |
|---|---|
| Four gaps in the tests let real breaks pass: a window of ten days, an unchanged price dropped, the month before worked out as 31 days back, the unchanged hint unescaped; and three guards could be removed | Each has a test; the mutation pass above includes them |
| A NaN or Infinity in the history would reach `latest.json`, which no browser can read | Only finite positive figures are copied |
| From £100 the median is written in whole pounds, so "£150 (£50.50 ▲ 51%)" did not add up | The bracket is worked out from the prices as written |
| "10.0%" for 9.96 per cent, and "100%" for a fall short of everything | Rounded once; a near-total fall reads ">99%" |
| The hint's date was in UTC while the page shows local time | Local time |
| After a change of search words a bracket compares two different searches for a week | Said in the guide and the changelog |
| A title spelt another way ("Ico", "ICO") lost its history | History is matched by `key_of(title)` |
| An overdue median was dimmed but its bracket was not | Both are |
| The guide said "the cheapest last" while US-only and unpriced games follow it; "each group keeps its order" was true only for ties; "from 13 October" was early for most games | Reworded |
| The test list in the architecture notes and this log had no entry | Both added |

Left as it is: a game with only a US price comes after the cheapest UK-priced game, however
dear, because dollars and pounds are never compared; the guide and the list's own line say so.

## 2026-10-08: the scraper keeps running; Reddit by newest posts

How the always-on loop, the per-type clocks and the Reddit change were checked. No browser was
used (rule 11). The sites are unreachable from the development machine, so everything live was
measured by *Live checks* from GitHub's servers and read from its notices.

| Check | Result |
|---|---|
| What changed | `scrape_loop.py` and `tests/test_scrape_loop.py` (new); `scraper.py` (clocks, Reddit requests, budget clock, abort bookkeeping, ceiling, whole-file writes, cached title index); `.github/workflows/scraper.yml`, `live-checks.yml`; the clocks in `feeds.json`; the schedule menu and run-now request in `index.html`; `tools/`; the guide and docs. `ebay.yml` only in a comment |
| How often GitHub ran the old schedule | 24 scheduled runs between 2026-10-02 23:48 and 2026-10-08 07:27 UTC, about 130 hours: one every 5½ hours |
| Reddit, live from GitHub | All 10 new requests answered with 100 posts. The busiest (r/pcmasterrace, r/NintendoSwitch, r/PlayStation) had about 11 new posts an hour and reached back 8.7 hours; the others 21 to 811 hours. About 29 new posts an hour in all |
| News, live from GitHub | `regression_check.py --types news`: the old and new scraper give identical snapshots from the same live feeds. Reddit's comparison reports "fetch plans differ" (3 requests before, 10 now), which is the change |
| The loop, offline | On a fake clock for a whole run: 4chan every 14 minutes, news every 28–30, podcasts once; rounds at least 2 minutes apart, 15 after a failure; the eBay job hourly; no round starts without 45 minutes left; the successor at the end, after an error too, never after a cancel, never from another branch |
| Offline tests | 262 Python tests (221 before this change), 32 dashboard checks |
| Do the checks bite | Two sets of one-line breakages: 32 of mine and the reviewer's 65 (58 of them still apply to the final code): all noticed |
| Not checked | A real run of the loop on GitHub: it starts when this is merged. The first hours on `main` are the test, and the Actions page shows each round's lines |

### Independent review

Two rounds by one reviewer with fresh context and no network, working in a copy, told to report
only findings backed by a concrete failure. It ran the real scraper on a fake clock to time
rounds, and a real local git remote to test pushing.

| Finding | Resolution |
|---|---|
| Reddit's ten waits used up the 10-minute budget of the extras: in a full round 23 of 114 YouTube feeds and no podcasts were read | The budget starts with the first extra |
| After a 429 two Reddit requests went out a second apart | The gap counts from the end of the request before |
| A Reddit outage aborted every round and retried Reddit about three times an hour | The round still records news and Reddit as tried, so they wait their interval; and once Reddit refuses after waiting, the round asks it no more |
| About eight commits an hour, close to GitHub Pages' ten builds | Bookkeeping alone is committed hourly; the snapshot is not rewritten only for items ageing out |
| No time limit on a round; a run could pass the job's limit; a crash started no successor | 40-minute round limit, 45 minutes reserved, hand-over after an error, not after a cancel |
| A run on another branch could take over the chain | One loop per branch; only `main` starts the eBay job and a successor |
| Reddit's newest posts will bring the snapshot near its 12,000 ceiling | Measured (about 700 posts a day); past the ceiling the oldest items naming no game go first; documented |
| An aborted round marked the extras as fetched although their items were thrown away | Only news and Reddit are marked on an abort |
| A commit whose push failed was dropped at the hand-over | Unpushed commits go up with the next save |
| A round stopped while writing could leave a cut-off snapshot | Files are written whole |
| A full round with several 429s could run past the round's time limit and repeat | 40-minute limit, and Reddit stops after a refusal |
| Docs: the 15-minute limit, comments, "four commits an hour", "an hourly backup starts one" | Corrected |
| Twelve, then seven, real breakages went unnoticed by the tests | Each has a test |

Left as they are: a scheduled run cancelled in the queue still starts an eBay run (harmless;
the eBay job only asks what is due); a type whose every source is a YouTube link that never
resolves is due every round (none exist).

## Re-running the checks

```sh
python -m unittest discover -s tests -v   # offline; includes the dashboard checks when Node.js is installed
python tools/regression_check.py          # old vs new scraper on identical real feeds (~3 min, network)
python tools/try_sources.py forum 4chan   # what the live forums and boards give; writes nothing
python -m py_compile scraper.py
FULL_RUN=1 python scraper.py              # in a copy of the repo, not in the checkout you commit from
python ebay_prices.py --plan              # the price plan on the real feed; needs no key, asks nobody
```

For the next change, the checklist in [AGENTS.md](../AGENTS.md#making-a-change-the-skeptical-checklist)
lists what to prove before calling it done.
