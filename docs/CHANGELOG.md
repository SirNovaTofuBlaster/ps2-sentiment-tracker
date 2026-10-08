# Changelog

## 2026-10-08: eBay UK searched under the European name

- Asked: why *Fatal Frame 2* had no eBay UK price. In Europe the series is *Project Zero*; the
  UK search for "Fatal Frame 2" found no PAL copy (0 copies, against 16 on eBay US).
- `regional_names` in `ebay_watchlist.json` renames the start of a game's name for one site, and
  the price job searches eBay UK under that name: 13 rules, among them Fatal Frame → Project
  Zero, Siren → Forbidden Siren, Bully → Canis Canem Edit, Dark Cloud 2 → Dark Chronicle,
  Ratchet: Deadlocked → Ratchet: Gladiator, Sly Cooper and the Thievius Raccoonus → Sly Raccoon,
  Shin Megami Tensei: Nocturne → Lucifer's Call. On the current list five tracked games change.
- A renamed game's UK bracket compares two different searches for its first week.
- The dashboard's eBay UK link under a name still searches the US title.

## 2026-10-08: the scraper keeps running, each source on its own clock; Reddit by newest posts

### What was asked

- "Squeeze more data from the scraper ... so that they are constantly feeding more data to the
  site ... without being rate banned." The maintainer chose an always-on loop over a schedule
  every 10 minutes, and agreed to Reddit being read by its newest posts.

### What was measured first

- GitHub started 24 of about 130 hourly scheduled runs between 2026-10-02 and 2026-10-08:
  about one every 5½ hours. That gap, not the sources, was where most data was lost.
- 4chan: 27 game threads in 7 days; a thread on /v/ is gone within a couple of hours.
- Reddit: 3 requests a run of the 50 "hot" posts per group; the busy group filled those 50 in
  its busiest six hours.

### What changed

**`scrape_loop.py` (new) and `.github/workflows/scraper.yml`**
- One run of the workflow stays up five and a half hours. It runs `scraper.py` whenever a source
  type is due, commits the new data, starts the eBay prices job once an hour, and at the end
  starts the next run itself. The hourly schedule is only a backstop.
- *Run scraper now* and saving sources replace the running loop with a fresh one that fetches
  everything first. One loop per branch; only the loop on `main` starts the eBay job and a
  successor. A cancelled run starts nothing.
- When only the bookkeeping changed (when each type was fetched, a board's date), it is
  committed at most once an hour, to stay well under GitHub Pages' ten builds an hour.

**`scraper.py`, `feeds.json`**
- Clocks: 4chan every 15 minutes, news sites and forums every 30, Reddit and YouTube every
  hour, podcasts every 6 hours. `poll_every_hours` now also takes 0.25 and 0.5.
- Reddit: the newest posts, three subreddits a request, up to 100 posts each, a minute apart:
  10 requests where there were 3. Measured from GitHub's servers: about 29 new posts an hour in
  all, and every request's 100 posts reach back at least 8½ hours, so hourly misses nothing.
- The 10-minute budget for YouTube and podcasts starts with the first of them, so Reddit's
  waits don't use it up. A round that aborts still records what it tried, so a site that
  refused us is asked again after its usual interval, not straight away.
- Past the 12,000-item ceiling, the oldest items that name no game go first.
- Rounds after a loop's first reuse the PS2 title index instead of downloading it again.
- Once Reddit still says "too many requests" after waiting, the rest of that round's Reddit
  requests are not sent. The snapshot is no longer rewritten only because old items aged out.
  Data files are written whole, so a round stopped at its time limit leaves nothing cut off.

**Dashboard, guide**
- The schedule in Sources & Weights is a menu from 15 minutes to 24 hours. The guide describes
  the always-running robot and Reddit's rounds.

**Tools and checks**
- `regression_check.py --types news|reddit` (news must stay identical; it does), never writes
  the repository's `data/`. *Live checks* also tries Reddit and reports how far back each
  request reaches. 262 Python tests (was 221), with `tests/test_scrape_loop.py` new.

### Behaviour changes to be aware of

- About 700 Reddit posts a day enter the feed instead of about 250. Most name no game. With
  them the snapshot comes close to its ceiling, where the oldest items naming no game are
  dropped first: the item count, the mood average and the remaster-news count may then cover
  less than two weeks. Every item that names a game is kept for 14 days.
- The scraper workflow now shows one run lasting about five and a half hours at a time; that is
  normal. To stop the robot, disable the workflow on GitHub (cancelling a run does stop it, but
  the hourly backstop starts a new one).
- A runner busy around the clock is free on a public repository; GitHub's terms ask that
  Actions serve the project, which publishing this site's data does.

## 2026-10-08: the last day's games by price, and each median's change over a week

### What was asked

- Sort the games in *Named in the last 24 hours* by price, most expensive at the top and the
  cheapest at the bottom.
- Beside a median, in brackets, how much it moved and by what percentage, with an arrow up or
  down, ready for when the price has been checked again a week later. The example given:
  Persona 4 £73.49 (£2.30 ▲ and the percentage).

### What changed

**Dashboard: `index.html`, `retro.css`**
- *Named in the last 24 hours* is ordered by the eBay UK median, dearest first. A game with no
  UK figure follows, by its US median: dollars and pounds are never compared. Games with no
  price come last. Games at the same price, and the games with no price, keep the order they
  had (headlines, then mentions, then the most recent). The line under the heading says so
  when any game in it is priced.
- Beside each median, wherever one is shown (under a game's name on the Tracker and Most
  mentioned pages, and on the eBay prices page): `(£2.30 ▲ 3.2%)` when it went up since a week before, `(£1.10 ▼
  4.5%)` when it went down, `(no change)` when it is the same. Up in teal and down in red, as
  in the Demand Index; the arrow carries it without the colour. Hovering shows the week-old
  figure and its date. Nothing is shown where there is no week-old figure. The difference
  and the percentage are worked out from the prices as written (whole pounds or dollars from
  100), so the bracket adds up with what is on screen. An overdue figure's bracket is dimmed
  with it.

**Price job: `ebay_prices.py`**
- `latest.json` now carries, per game and site, `week`: the median recorded a week before
  that figure was checked (the latest history row from 7 to 9 days before, only if it found
  copies), with the time of that row. Numbers only, like everything else under
  `data/prices/`. It is worked out from the month's history, and from the month before early
  in a month; that file is only read, and if it cannot be read the run carries on without
  those figures. History is matched whatever the spelling of the title, and only finite
  positive figures are copied. No new request to eBay and nothing else changes in what is
  asked or kept.

**Guide, docs, tests**
- The guide describes the order and the brackets. 32 dashboard checks (was 31) and eleven
  new tests of the price job (215 Python tests, was 204).

### When the brackets appear

- The price history began on 2026-10-06 at 22:41 UTC, so the first brackets appear with the
  first checks after 2026-10-13 22:41 UTC, as each game comes up for its next check (every 6
  hours for most, daily for quiet ones). Until then the list is already ordered by price.

### Behaviour changes to be aware of

- The front list no longer puts the most-mentioned game first: a game named once with a dear
  UK median comes above one named twenty times. Wrong matches with a price (a modern
  *Monster Hunter* matched to the PS2 one, say) are placed by that price.
- These are asking prices, so a week's change says what sellers ask now against a week ago,
  not what copies sold for. A median over a handful of copies can move a lot when one
  listing comes or goes.
- When a game's search words are changed (pinning it with its own `search`, say), its bracket
  compares two different searches for a week.
- A game with only a US price comes after the cheapest UK-priced game, however dear it is:
  the two currencies are never compared.

## 2026-10-07: games first

### What was asked

- "Reduce the irrelevant noise and push all the titles to the forefront of the page": if a
  day's scrape finds six PS2 games in a hundred items, put the six on the front and keep the
  rest at the bottom or away.
- Whether all the data is being saved.

### What changed

**Dashboard: `index.html`, `retro.css`**
- **Named in the last 24 hours**, a new list first on the Tracker: every PS2 game named by
  an item published in the last day, with how many items named it, which sources, and its
  prices. The game named in the most headlines comes first, and one found only in the text
  under a headline (marked "in the text only") comes after every game a headline named;
  then all mentions, then the most recent. It shows ten games and folds the rest away.
- **A game's name in that list opens the table on exactly the items that name it**, from
  the whole feed. *Back to every game* over the table, or any change to the search box or
  a menu, undoes it.
- **The table opens on the items that name a PS2 game.** A line over the table says how
  many those are and out of how many, whatever the search box and the menus are set to,
  and *Everything* in the first menu shows the rest. The menu now reads *PS2 Games Only*,
  *Remaster News Only*, *Everything*. The line sits on a row of its own, between the menus
  and the table.
- **A row names every game its item names**: the first with its prices, the others under it
  ("also names …", four at most and then a count; a game the search box found comes
  first). Before, only the first was shown.
- The search box looks at every game an item names, not only the first.
- **Most Mentioned Games counts every game an item names**, as the new list does and as the
  archive, the Demand Index and the eBay prices always have. It used to count an item's
  first game only, so a game that was only ever named second was missing from the page.

**Guide: `guide.html`**
- Describes the new list, what the table opens on and where the rest is.

**Tests**
- 31 dashboard checks (was 30); the check of the eBay medians now covers the new list too.
  The test sandbox opens with the menus the page opens with.

### What was measured (2026-10-07, the snapshot of 17:44 UTC)

- The 24 hours before its newest item (17:41 UTC): 654 items, 53 naming a PS2 game (32 in a
  headline, 21 only in the text): 59 games, 25 of them by a headline.
- Whole feed: 5,586 items, 412 naming a game.
- Most Mentioned Games: 532 mentions across 209 games, where it showed 412 across 162.

### Behaviour changes to be aware of

- The table no longer shows everything when the page opens: about nine items in ten are
  behind *Everything*. The item count at the top still counts them all.
- Nothing is removed from the data. The snapshot, the archive and the prices are written
  exactly as before; this change is to what the page shows first.
- Wrong matches are now on the front as well. On the measured day the headline matches
  included *Retro*, *Tomb Raider: Anniversary* (for "Happy 23rd Anniversary to Backyard
  Wrestling") and *Battlestar Galactica* (an article about the television series). The list
  is only as good as the matcher.
- The numbers on the *Most mentioned* page and on its tab went up (see above), and every
  share on it changed with them: nothing new was found, more of what was found is counted.
- "The last 24 hours" goes by the date a source gave an item, not by when the robot fetched
  it. When a source is first added, its older items do not flood the list; an item whose
  source dates it more than an hour into the future is left out of the list as well. A
  source that gives no dates is the exception: its items are dated when first seen.
- Before any feed has loaded, and when the feed cannot be loaded, the list says so; the two
  cases look the same to the page.
- A click on a game shows its items from the whole two weeks, so the table can show more
  items than the list's count for the last day.

### What is kept, for the record

- Every mention of a PS2 game, permanently: `data/archive/YYYY-MM.json` (576 mentions since
  2026-09-20 when this was written).
- eBay's figures, permanently and as numbers only: `data/prices/`.
- Everything else, the items that name no game, for 14 days in the snapshot and then not at
  all. That was the decision when the archive was built.

## 2026-10-07: start-up screen colours

### What was asked

- "The theme is still not sitting right with me": something inspired by the colours of two
  pictures the maintainer showed, a console maker's logo and its start-up screens (red,
  yellow, teal and blue, on light grey and on black).
- A preview first. Two directions were mocked up with the day's real rows, one dark and one
  light; the dark one was chosen.
- On the preview: a different line under the name, and the paragraph in the banner taken out
  and left to the How it works page.

### What changed

**Theme: `retro.css`**
- A near-black ground in place of the navy, and four colours, each with its own kind of job:
  - **yellow** for price links and nothing else, still the one highlighted thing in a row;
  - **blue** for what can be followed: game names, links and buttons;
  - **red** for remaster news (the tag in the table and beside a game's rank, the *Remaster
    flags* number, the line under the open page's tab) and for whatever is low or failing:
    a low mood score, a falling trend, a source that cannot be read, an error;
  - **teal** for live and well: the sync dot, the *Active feeds* number, a high mood score,
    a rising trend, a success.
- All four meet in a strip across the top of both pages and in the rings of the mark. Only
  the palette is borrowed: no logo, lettering or shape of anyone else's.
- The quiet text colours are lighter than before, so the small print (ages, notes, hints)
  now meets the usual contrast standard (4.5 to 1) on the page, the banner, a field, a
  striped row and a row under the pointer. A switched-off source's row is dimmed as a
  whole, as before, and does not.
- Striped rows are a neutral shade lighter than the page; the pointer's tint on a row is
  fainter than it was, so the red tag stays readable on it.
- Ticked boxes are the theme's blue (they were Tailwind's own cyan), and the lines between
  table rows its neutral grey (Tailwind's slate was winning there).

**Dashboard and guide: `index.html`, `guide.html`**
- The line under the name reads "PS2 news, mentions and prices".
- The banner no longer carries the paragraph about what the site does. The guide's first
  section says it, including that every recognised game gets links out to shops and price
  guides and eBay's asking prices beside its name.
- *Net sentiment* is no longer tinted. *Run scraper now* is blue like the other buttons.
- The guide says "yellow buttons" and "a lighter shade" where it said amber and blue.

**Tests**
- 30 dashboard checks (was 29): every text colour against every ground it sits on, rows
  under the pointer included; a stripe that can be seen; yellow used by nothing but price
  links, by any route; the red and teal jobs; the strip; the mark on both pages; the
  banner's contents; and no colour of the previous palette left behind.
- The test workflow also runs on pushes that change `guide.html`.

### Behaviour changes to be aware of

- Nothing but colours and the banner changed: layout, type, sizes and the phone layout are
  as they were. On a phone the banner is one block shorter.
- A browser may show the previous colours until the page is reloaded.

### Open items

- The light direction of the preview was not built. It would take more than new values at
  the top of `retro.css`: the pages use Tailwind's `text-white` and `text-black` directly
  (over a hundred times in the guide), and the mark's colours, both `theme-color` lines and
  the pointer's tint are written out.
- Nobody has looked at the result in a browser as part of this change (rule 11): it was
  checked by the tests and by working the colours out. The preview was a separate mock-up.

## 2026-10-07: forums and 4chan's game boards

### What was asked

- Add forums as sources, after seeing a list of what could be added.
- Track seven 4chan boards (/v/, /vg/, /vm/, /vmg/, /vr/, /vrpg/, /vst/), because PS2 titles
  come up there: "censor any bad words or derogatory terms and just focus on the game titles
  being mentioned".
- The decision after the list: add the forums that work, and from 4chan show the games only.

### What changed

**Sources: `feeds.json`** (303 sources, 231 on; was 294 and 222)
- Two forums, both communities of lemmy.world read through their RSS feeds: *Lemmy games*
  and *Lemmy retrogaming*.
- Seven 4chan boards, under a new role `anonymous` ("Anonymous boards (4chan)", weight 0).
- The `community` role is now labelled "Community (Reddit & forums)".

**Scraper: `scraper.py`**
- Two new source types. `forum` is an RSS feed read like the other extras (YouTube,
  podcasts): newest first, labelled `Forum: <name>`, never waited on when it says "too many
  requests", and its failure never stops a run. `4chan` is read through 4chan's read-only
  API, one request per board, at least 1.1 seconds apart. Each request hands back the
  `Last-Modified` date the board's server gave last time (`If-Modified-Since`), so a board
  nobody has posted on since is not sent again.
- **From 4chan only game names are kept.** For each thread whose opening post names a PS2
  game the snapshot gets one row: the games, the board, when the thread was started and its
  link. The headline is written by the scraper ("Thread on /vr/ naming Silent Hill 2").
  Nothing a poster wrote is stored, shown or printed in the log. The text is not scored:
  `sentiment` is `null` and the remaster flag is never set.
- **Stricter matching for posts** (`games_in_post()`), judged on the very words that
  matched:
  - the whole name, spelt as the library spells it: no near misses, no half-titles, and
    titles longer than six words are found whole;
  - written as a name: with a number written as a number ("silent hill 2", "kingdom hearts
    ii"), or with a capital on every word the library gives one. A lone I, V or X is not
    taken as a number, a number followed by a unit of time is counting ("yakuza 2 days
    ago"), one everyday word that is also a title does not count as the first word of a
    sentence ("Black screen on my PS2"), and a post all in capitals marks nothing with them;
  - not another entry of the series: "Max Payne 2" and "Kingdom Hearts 3" are not counted
    for *Max Payne* and *Kingdom Hearts*.
  The matcher's built-in abbreviations ("mgs3") count however they are written.
- A thread counts on the day it was started; one started before the feed's 14 days is left
  out, and so is one whose date is not a plausible one.
- **A forum thread's link is its own page** (`thread_link()`). Lemmy gives the article a
  post shares as the post's link; with that, a post about an article had the same link as
  the article's own row from a news feed, and rows are told apart by their link, so the
  post replaced the article. The discussion page is used instead, and a forum row that
  still has another row's link is left out rather than take its place.
- Forums and boards are fetched before YouTube and podcasts, so the time budget cannot
  squeeze them out.
- News and Reddit are untouched: the old and new scraper gave identical output on the same
  live feeds (see VERIFICATION.md).

**Dashboard: `index.html`, `guide.html`**
- **Forums** and **4chan** tabs in Sources & Weights, and both in the table's source filter.
  A board is added by its short name ("vr", "/vr/") or its link; a forum by the RSS feed of
  one of its boards.
- A 4chan row shows a dash where the mood score would be and can never count towards the
  overall mood, whatever weight is set; a board has no weight box.
- The guide explains the 4chan rows, how to add a forum or a board, and what to expect when
  a forum refuses the robot or a thread's link has gone.

**Archive: `archive.py`**
- Two threads about one game on one board have the same generated headline, so 4chan rows
  are told apart by when the thread was started as well. They carry no mood score (`n`),
  because they have none. Nothing changes for other rows.

**Tools and workflows: `tools/try_sources.py`, `.github/workflows/live-checks.yml`**
- `try_sources.py` tries the enabled forums and boards (or any other extras) against the
  live sites and prints what the scraper would make of them, writing nothing. For boards it
  prints counts and game names only.
- *Live checks* runs it, and `tools/regression_check.py`, on every pull request that touches
  the scraper, `feeds.json` or `tools/`, from GitHub's own servers. It holds no key and can
  write nothing.
- `tools/sample_fixtures.py` leaves 4chan rows out when it draws headlines for the matcher's
  test corpus: their line is written by the scraper from the match itself.

**Tests**
- 204 Python tests (was 178) and 29 dashboard checks (was 28). New: `tests/test_archive.py`.
- The test workflow now also runs on pushes that change `archive.py`, `tools/` or
  `live-checks.yml`.

### What was measured (2026-10-07, from GitHub's servers)

- **Forums.** Six feeds answered when they were first checked, from outside GitHub. From
  GitHub only the two Lemmy feeds did; NeoGAF, both GBAtemp boards and PSX-Place returned HTTP 403
  from behind Cloudflare, twice, the second time under a feed reader's name. Those four were
  taken out again. So "the six that work" became two.
- **4chan.** All seven boards answered, in each of the check's first eight runs. In the
  eighth (17:25 UTC, the first with the rules as merged), of 1,138 live threads 29 named a PS2 game in their opening post, and 24 of
  those were started in the last 14 days: 28 mentions of 20 games. The first dry run, with
  the rules used for headlines, had counted 68 mentions of 50 games, many of them plainly
  wrong (Dragon Rage, Legend of Herkules, Happy Feet, The Thing); the rules for posts were
  written from that list and tightened again after the independent review. The per-board
  table is in SOURCES.md.
- **News and Reddit.** The old and the new scraper were run on the same live news and
  Reddit feeds in every one of those runs. The first three runs failed at the forums that
  refused; in the fourth to the eighth both steps passed, and the comparison passes only
  when the output is identical.

### Behaviour changes to be aware of

- The item count and Most Mentioned Games now include forum threads and 4chan rows. On the
  measured day that was 40 forum threads (the 20 newest of each community) and 24 board rows.
- Every game a board names becomes a game the eBay job prices, like any other mention. A
  game named in a thread's subject counts as a headline for the "surging" level; one named
  only in a comment does not.
- Series that have long-running threads on /vg/ (Monster Hunter, The Sims, Pro Evolution
  Soccer) will be counted for the PS2 game of that name on most days. This is the matcher's
  known habit of giving a series name to its PS2 entry.
- A 4chan row's button opens the thread on 4chan, unfiltered, and stops working when the
  thread is deleted there.
- `data/feed_status.json` gains nine entries. The seven for boards also hold `modified`,
  the date the board's server gave, and change whenever anything is posted on the board,
  which on the busy ones is every run.

### Open items

- Replies are not read, only the post that opens a thread. Reading replies would mean one
  request per thread (hundreds per board) and far more text to keep out.
- A busy board is sampled: GitHub starts the hourly run hours late on many days, and /v/'s
  whole catalog turned over in two days.
- No other forum has been found that both publishes a feed and answers GitHub's servers.
- Real mentions the rules for posts lose: a name in lower case without a number ("final
  fantasy x", "okami"), a one-word everyday title that starts a sentence ("Bully is great
  on PS2"), a sequel called by a short name the library does not have ("Max Payne 2" for
  *Max Payne 2: The Fall of Max Payne*), and anything in a post written all in capitals.
- The rules were written and judged from game names and counts alone: the check prints
  nothing a poster wrote, and nobody working on this could read the boards.
- Forum threads are matched with the rules for headlines and body text, and the two wrong
  matches in the Lemmy sample ("Retro", "Hardware: Online Arena") are the matcher taking an
  everyday word in a post's text for a one-word title once the post mentions the PS2. It
  does the same on Reddit; it is a matcher task, not changed here.

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

**Workflows: all six**
- `actions/checkout` v4 to v5, `actions/setup-python` v5 to v6 and `actions/setup-node` v4 to
  v5: the same actions built for Node.js 24, which ends the "Node.js 20 is deprecated" warning
  on every run. Nothing else about them changes; the newer majors (checkout v6 and v7) alter
  how credentials are stored and what a `workflow_run` job may check out, and were left alone
  because the eBay job cannot be tried out before it is live.
- The tests run on Node.js 22 (was 20, which is no longer supported).

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
