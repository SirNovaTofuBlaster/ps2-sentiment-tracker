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

## Re-running the checks

```sh
python -m unittest discover -s tests -v   # offline; includes the dashboard checks when Node.js is installed
python tools/regression_check.py          # old vs new scraper on identical real feeds (~3 min, network)
python -m py_compile scraper.py
FULL_RUN=1 python scraper.py              # in a copy of the repo, not in the checkout you commit from
python ebay_prices.py --plan              # the price plan on the real feed; needs no key, asks nobody
```

For the next change, the checklist in [AGENTS.md](../AGENTS.md#making-a-change-the-skeptical-checklist)
lists what to prove before calling it done.
