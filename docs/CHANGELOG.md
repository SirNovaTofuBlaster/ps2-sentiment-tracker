# Changelog

## 2026-10-07: prices beside every game, three tabs, and a feed that keeps its two weeks

### What was asked

- The eBay prices were meant to show on every entry that names a game, not as a list in the
  middle of the page. Keep the list, but give it a tab of its own.
- Move Most Mentioned Games to a tab of its own too.
- The site looked as if it had stopped collecting at 5,000 items.

### What changed

**Dashboard: `index.html`, `retro.css`, `guide.html`**
- **eBay median beside every game.** Wherever a game's name appears (Demand Index, Most
  Mentioned Games, the feed table) a line under it gives the median asking price on eBay US
  and eBay UK. Each figure opens that site's listings, and its tooltip says how many copies it
  covers, the cheapest and when it was checked. A game that is not priced shows no line.
- **Three pages.** A tab bar under the banner switches between **Tracker** (the numbers, the
  Demand Index, the feed and the sources), **Most mentioned** (the ranking of games by
  mentions) and **eBay prices** (every tracked game in full, with a box to find one).
  `#mentions` and `#prices` in the address open the second and third, so they can be
  bookmarked, and the browser's Back button returns to the page before. Neither list sits
  between the Demand Index and the feed any more.
- **Most Mentioned Games ranks every game**, not the first 25: it shows 25 and a button opens
  the rest. The number on its tab is how many games the feed names.
- **The prices page says when it is empty,** and tells "the job has not run yet" from "the
  file could not be read". Before, the section was hidden until the price job had run, which
  looked like something missing. A failed refresh keeps the prices already on screen.
- **One name per game.** The price file uses library titles; the feed says "Persona 4" and
  "Kingdom Hearts 2". `priceKey()` evens a title out the way `search_terms()` in
  `ebay_prices.py` does, and `ebay_watchlist.json` is read for the search words of pinned
  games. A test compares the two functions on the whole PS2 library.
- **The item count says how far back it goes** ("Items · 9 days") instead of "Items
  scraped", which read as a running total.
- An address that names a part of the page (`#sourcesSection`, used by the guide's button)
  now arrives there on a fresh load; before, the page scrolled before its content existed.
- Prices are written as `$220` and `£105` for every reader (a UK browser showed `US$220`
  next to a "US" label).

**Scraper: `scraper.py`**
- `MAX_ITEMS` is 12,000 (was 5,000). The feed never stopped: on 2026-10-07 each run was still
  adding items (200, 95, 85 and 26 in the last four) and dropping the same number of the
  oldest, so the count stayed at exactly 5,000 while the two-week window shrank to nine days.
  With about 600 items a day, two weeks is roughly 8,400. The ceiling is now a safety net and
  `RETENTION_DAYS` (14) is the limit that applies. Nothing else in the file changed.

**Tests: `tests/dashboard_check.mjs`, `tests/test_scraper.py`**
- 28 dashboard checks (was 24) and 178 Python tests (was 176).

### Behaviour changes to be aware of

- The feed grows back to two weeks. Items the old limit pushed out return on the first run if
  their source still lists them (on 2026-10-07 that was 203 of 392, all YouTube uploads and
  podcast episodes); the rest of the gap fills over about five days. The tile can therefore
  read "13 days" or "14 days" at once while days 10 to 14 are still thin.
  `data/sentiment_feed.json` grows from 2.6 MB to about 4.5 MB.
- The eBay levels (`staple`, `surging`, `dormant`) are worked out from two weeks of mentions,
  so they are computed on fuller data once the window has refilled.
- Prices load before the lists are drawn, and the page now also fetches `ebay_watchlist.json`.
- eBay figures now sit in the same rows as the Price Charting and CeX search links. They were
  first kept in a block of their own because eBay's API License Agreement asks for its
  content to be set apart; the maintainer chose this layout for a personal tool.

### Open items

- `tools/regression_check.py` and a `FULL_RUN=1` scratch run were not done for the
  `scraper.py` change: both need the live feeds, which the machine the change was written on
  cannot reach. The change is one number that only matters above 5,000 items (the regression
  check collects about a thousand), and a comparison of the two files' syntax trees shows
  nothing else differs. Run both from a machine with network access to close this.
- The page's name rule and the price script's differ on a few characters no title uses
  (combining marks outside the Latin accents, some control characters). A fuzz of 700,000
  strings found no other difference.
- Arrow keys do not move between the tabs; Tab, Enter and Space do.
- On the first run for every game (2026-10-06, 22:41 UTC) 177 of 182 games got a figure on at
  least one site. 22 game-and-site pairs came back "search needs tuning", among them both
  sites for *The Godfather: Collector's Edition*, *King's Field IV: The Ancient City* and
  *Virtua Fighter: 10th Anniversary Edition*.
- Two wrong listings seen in that run's spot checks: a *Devil May Cry 3* copy "with Monster
  Hunter" (a demo) counted for *Monster Hunter*, and "Xtreme Legends: Dynasty Warriors 3"
  counted for *Dynasty Warriors 3* because the expansion's name came first.
- 19 of the 142 games in the feed that day have no figure: 15 have names that come down to
  one ordinary word ("Black", "The Sims"), one is on the never-price list, and three came back
  unmatched or with nothing listed.

## 2026-10-06: eBay asking prices, a measured matcher, phones, and lists that fold

### What was asked

- Find out how good the game matcher is, and make it better without guessing.
- Make the site work on a phone (a Pixel 9 Pro).
- Use the newly approved eBay developer key: price the games the feed mentions on eBay US and
  UK, check a game more often when it is suddenly being talked about, and keep an archive of
  the prices as numbers only.
- Show the prices on the dashboard, let the long lists fold down to five rows, and give every
  second row a lighter shade.

### What changed

**Matcher: `scraper.py`, `tests/test_matcher_fixtures.py`, `tests/fixtures/headlines.json`**
- A corpus of 274 real headlines, 268 of them labelled by hand, measures the matcher on every
  test run: precision 0.635 and recall 0.948 at the time of writing, with floors of 0.60 and
  0.93 that fail the tests if a change makes it worse.
- Rules added with the corpus as the judge: word order is part of a title ("Combat Ace" is not
  "Ace Combat"), a title filed as "Getaway, The: Black Monday" is read as "The Getaway: Black
  Monday", a word containing a digit has to be in the text, and one game is claimed once per
  headline.
- `tools/sample_fixtures.py` and the *fixtures* workflow draw new headlines to label.

**Phones: `index.html`, `retro.css`, `guide.html`**
- Below 640px the two tables become stacks of cards, the banner folds into one column, the
  price chips sit on one line that swipes, and pages hold 25 rows instead of 100. Nothing
  changes on a wider screen.

**eBay asking prices: `ebay_prices.py`, `ebay_watchlist.json`, `.github/workflows/ebay.yml` (new)**
- Prices every game the feed has ever mentioned that is in the PS2 library, plus the games
  pinned in `ebay_watchlist.json` (182 in all on the day it was built), on eBay US and eBay UK, through
  eBay's official Browse API. It asks for used, Buy It Now listings located in that country
  and keeps the count, the lowest and the median asking price, and the typical postage.
- Listings that are not a copy of the game are left out: other games in the series, sequels,
  sets, empty cases, soundtracks, cheat discs, demo discs, job lots, merchandise, copies for
  another console and imports. The rules were tuned on three live runs and their real titles
  are now test cases.
- How often a game is checked follows how it is being mentioned: `surging` (rarely named, then
  named in headlines by two or more sources within a day) on every run for 48 hours; `normal`
  and `staple` (named on 5 or more of the last 14 days) every 6 hours; `dormant` once a day.
- It writes numbers only: `data/prices/latest.json` and a monthly history that gains a row
  when a game's figures change and at least once a day. Listings with their links are kept
  for the latest run only, on the `ebay-data` branch.
- The workflow runs after every scraper run and by hand. It is the only job that holds a key;
  it installs nothing, always runs the code on `main`, and refuses runs started by pull
  requests or from another repository.

**Dashboard: `index.html`, `retro.css`, `guide.html`**
- **eBay Asking Prices** (new section): each tracked game with its median, cheapest and number
  of copies per site, when it was checked, and a tag when it is surging, a staple or quiet.
  A price that has gone longer than usual without a check is dimmed. The section is hidden
  until the price job has run.
- **Demand Index**, **Most Mentioned Games** and **eBay Asking Prices** show five rows; a
  button under each opens the rest (up to 25 for the two ranked lists) and folds it again.
- Every second row of those lists and of the feed table sits on a lighter blue.

**Workflows: `archive.yml`, `demand.yml`, `tests.yml`**
- The archive and the demand index now take a competing commit and retry instead of failing
  when another job saved to `main` first, as the scraper already did.
- The Tests workflow also runs when `retro.css` changes: the dashboard checks read it.

**Docs**
- [SOURCES.md](../SOURCES.md) counts the three YouTube channels added from the dashboard
  (159 channels, 114 on; 294 sources, 222 on) and lists them without figures, since they were
  not part of the 2026-09-30 measurement. The dashboard's banner no longer quotes a number
  that goes out of date.

### Decisions the maintainer made

- **Numbers from eBay are kept permanently; listings are not.** eBay's API License Agreement
  limits what may be stored, shown and worked out from its data. The maintainer chose to keep
  derived figures only and to treat the tracker as a personal tool. Nobody has asked eBay
  whether this use is permitted.
- **AGENTS.md rule 8 was reworded**: the scraper stays keyless, and `ebay_prices.py` is the one
  script that may use a key.

### Behaviour changes to be aware of

- The Demand Index showed 10 games and Most Mentioned Games 15. Both now show 5, with up to
  25 a click away.
- The #1 row of those two lists no longer sits in a box; the stripes do that job.
- The guide's sections are renumbered from 4 onwards to make room for the eBay section.

### Open items

- About half of the first week's "surging" flags were the matcher naming the wrong game.
  The level is only as good as the matcher.
- Search words come from library titles. Games that sellers abbreviate show "search needs
  tuning" until they are pinned with their own search words.
- A game with more than 200 listings on one site is priced from eBay's first 200.
- The price history is not drawn anywhere yet; the dashboard shows the latest figures only.
- The scraper's snapshot holds at most 5,000 items, about 11 days at the current number of
  sources, so "the last 14 days" in the level rules is at present a little less.
- The body-text path of the matcher is not measured: the corpus holds headlines only.

## 2026-09-30: YouTube channels, podcasts and configurable sources

### What was asked

- Widen the scope of the RSS feeds, starting with YouTube videos and podcasts.
- Rank gaming and retro-gaming YouTube channels by subscribers and views, and do the same for
  podcasts, so they can be added as feeds.
- Update the code without deleting any of the existing RSS URLs.
- Also, as the work progressed:
  - make sources and weights configurable from the dashboard
  - show which sources are inactive
  - count resellers lower
  - explain how it works and why
  - add tests
  - make adding and saving sources easy for non-technical users, with a guide
  - document everything for people and for AI agents

### What changed

**Sources: `feeds.json` (new)**
- One file lists all 291 sources, 219 of them on by default:

  | Type | Listed | On |
  |---|---:|---:|
  | News sites (moved unchanged from `scraper.py`) | 18 | 18 |
  | Subreddits (moved unchanged) | 26 | 26 |
  | YouTube channels | 156 | 111 |
  | Podcasts | 91 | 64 |

- Every source has a role that sets its weight: PS2-dedicated 1.5, collectors & resellers
  and entertainment creators 0.5, everything else 1. A per-source override is possible.
- `poll_every_hours`: podcasts are fetched every 6 hours, everything else every hour.
- Each YouTube and podcast source carries a snapshot (subscribers, total views, Apple ratings
  and chart rank, last activity) measured on 2026-09-30, and a `note` saying why it's off when
  it is.

**Scraper: `scraper.py`**
- Reads and validates `feeds.json`. A broken file stops the run with a readable message, and the
  old data stays.
- The fetch plan puts the news and Reddit feeds first, using exactly the same URLs and Reddit
  groups as before. Then come YouTube channel feeds (`/feeds/videos.xml?channel_id=`) and podcast
  RSS feeds.
- YouTube and podcast items go through the same matching, remaster flag and sentiment scoring.
  They are labelled `YouTube: <name>` / `Podcast: <name>`, and every item now records
  `source_type` and `feed`, the key of its source.
- Only news/Reddit failures can abort a run. YouTube and podcast feeds fail fast (no rate-limit
  waits). A host that fails 3 times in a row is skipped for the rest of the run, and extras stop
  after 10 minutes.
- The `ps2` role gives PS2 context for ambiguous titles, exactly as the PS2 subreddits did before.
- Podcast entries are sorted newest first. Episodes without a page link use their audio file.
- New `data/feed_status.json` records per-feed health. It is written only when something changes.
- YouTube channels can be given by link (`channel_url`). The ID is looked up once and remembered
  in `data/youtube_channels.json`.

**Workflows**
- The scraper also runs on pushes to `main` that change `feeds.json` or `scraper.py`, and those
  runs fetch everything (`FULL_RUN=1`).
- New *Tests* workflow.

**Dashboard: `index.html`**
- New *Sources & Weights* panel with a tab per source type:
  - search and sorting (subscribers, total views, Apple ratings, chart rank, latest activity)
  - on/off switches, role and weight per source, role weights and fetch schedule
  - live status badges: Active, Quiet, Stale, Failing, Not checked yet
- *Global Net Sentiment* is a weighted average. The Remaster Radar lists matched PS2 games
  first, then heavier sources, then the newest. The feed table gets a source-type filter, icons
  and weight badges.
- To add a source, paste a YouTube channel link, an Apple Podcasts link (the name and RSS feed
  are filled in), a feed link or a subreddit name.
- *Save changes* works two ways:
  - without a token, a guided copy/paste into GitHub's editor, with *Propose changes* or
    *Download* for people without write access
  - with a token, one click; commits use the no-reply email
- *Run scraper now*.
- Saved sources can only be switched off in the page, never deleted.

**Guide, docs and tooling**
- `guide.html` ("How to use") explains the dashboard step by step for non-technical users.
- README, [SOURCES.md](../SOURCES.md) (ranked lists), [ARCHITECTURE.md](ARCHITECTURE.md) (how
  and why), [VERIFICATION.md](VERIFICATION.md) (how it was checked) and
  [AGENTS.md](../AGENTS.md) (rules for AI agents; `CLAUDE.md` loads it).
- `tests/`: an offline Python suite plus Node checks of the dashboard script.
- `tools/regression_check.py`: compares old and new scraper output on identical feeds.

### Fixed after the independent review

Two skeptical reviewers went through the whole change before it was published (details in
[VERIFICATION.md](VERIFICATION.md)). Fixed:

- **Validator mismatch:** the page and the scraper disagreed on malformed links like
  `https:/site.com/feed`. One saved typo would have stopped every scraper run. Now both use one
  shared pattern, and the page stores the repaired link.
- **Lost podcast episodes:** episodes that share one link (e.g. The Besties) collapsed into one
  item. They now use their audio file.
- **Queued workflow runs:** a run that waited behind another started from a stale commit and
  failed to push. The workflow now checks out the branch head.
- **Podcast schedule:** podcasts were tied to fixed UTC hours that GitHub's irregular schedule
  rarely hits. They are now polled once 6 hours have passed since the last fetch
  (`data/poll_state.json`).
- **Host breaker:** dead feeds (404) counted towards skipping a whole host. Only connection
  errors, timeouts, 5xx and 429 count now.
- **Guided save:**
  - *I've saved it* also marked edits made after copying as saved; now only the copied text
    counts.
  - The page trusted the website's copy of feeds.json, which lags a few minutes behind a save.
    It now reads the committed file from GitHub, and asks before a save would undo a newer one.
- **Add form:**
  - A channel ID was taken from anywhere in the pasted text; now only a bare ID or a
    `/channel/` link counts.
  - Old `itunes.apple.com` links and Reddit links without `https://` weren't recognised.
- **Guide and docs:**
  - The "Propose changes" steps now include forking and creating the pull request.
  - The guide explains the token's reach and the Remember option.
  - "How to use" links open in a new tab so unsaved edits aren't lost.
  - The status-badge and repository-detection wording is accurate.
- **Hand-edited feeds.json:** a file with a UTF-8 BOM loads, and odd values produce clear
  messages instead of crashes.

### How the source lists were made

Candidates came from:
- Playboard's all-time gaming ranking and Wikipedia's most-subscribed list
- YouTube's own channel search (24 queries, 477 channels)
- well-known retro channels
- Apple Podcasts' Video Games charts (US and UK)
- iTunes searches

Every candidate was measured live. Wrong matches were removed: namesake handles, spam podcasts
and dead feeds. Details and the full tables are in [SOURCES.md](../SOURCES.md).

### What we found about the existing feeds

- **VG247**: the feed loads but its newest article is from 2026-06-02.
- **Time Extension**: behind a Cloudflare check that blocks some networks. It works from GitHub's
  runners.
- **r/Steelbook** and **r/xboxone**: only posts from 2018 and 2024 reach the combined feed.

All of them were kept, and the dashboard marks them Stale.

### Behaviour changes to be aware of

- *Global Net Sentiment* is now weighted. With every weight set to 1 it equals the old number.
- The Remaster Radar order is now matched PS2 games, then weight, then newest (before: newest).
- *Active Worldwide Feeds* counts enabled sources: 219 instead of 44.
- Items carry two new fields (`source_type`, `feed`). Old items without them still work.
- Nothing else about the news and Reddit feeds changed. On identical feed content the old and
  new scraper produce the same items in the same order (see [VERIFICATION.md](VERIFICATION.md)).

### Open items

- The subscriber and rating numbers are a snapshot; nothing refreshes them automatically.
- YouTube and podcast fetching has been tested outside GitHub. Check the first
  GitHub Actions run after merging (the Failing badges show any problem).
- Fuzzy matching still maps franchise names to the PS2 entry (e.g. "God of War Laufey" becomes
  *God of War*). This behaviour predates the change.
- More scope without code changes: search feeds such as Google News
  (`https://news.google.com/rss/search?q=...`) can be added as news sources from the dashboard.
