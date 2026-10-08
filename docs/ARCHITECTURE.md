# How it works

The tracker reads gaming news sites, Reddit, forums, 4chan's game boards, YouTube channels and
podcasts, matches every headline, thread, video title and episode title against the PS2 library,
flags remaster/remake chatter, scores sentiment and shows the result on a static dashboard.
From 4chan it keeps only which games a thread names (see [4chan boards](#4chan-boards)).
Everything runs on GitHub: a workflow scrapes, commits the data, and the page reads the
committed files.

```
                 feeds.json  ◄──────── save (GitHub API or copy/paste) ────────┐
                     │                                                          │
                     ▼                                                          │
     scraper.py  (scrape_loop.py keeps it running; restarted on feeds.json)   │
                     │                                                          │
          ┌──────────┴──────────────┐                                           │
          ▼                         ▼                                           │
 data/sentiment_feed.json   data/feed_status.json                               │
          └──────────┬──────────────┘                                           │
                     ▼                                                          │
                index.html  ── Sources & Weights panel ──────────────────────────┘
```

## feeds.json

One file lists every source. The scraper only reads it, and the dashboard edits it.

| Field | Meaning |
|---|---|
| `type` | `news` (RSS/Atom site feed), `reddit` (one subreddit), `forum` (the RSS feed of one board of a forum), `4chan` (one board), `youtube` (one channel) or `podcast` (one show's RSS feed) |
| `name` | Display name. Forum, YouTube and podcast items are labelled `Forum: <name>` / `YouTube: <name>` / `Podcast: <name>`; a board's items are labelled `4chan /<board>/` |
| `url` / `subreddit` / `board` / `channel_id` / `channel_url` | Where to read it: feed URL for news, forums and podcasts, subreddit name, a 4chan board's short name (`vr` for /vr/, 1–6 lowercase letters or digits), or a YouTube channel ID (`UC…`). A YouTube channel can instead be given by its link (`channel_url`, e.g. `https://www.youtube.com/@IGN`); the scraper looks the ID up |
| `group` | Display grouping. For Reddit it also decides which subreddits share one combined request |
| `role` | One of the roles below; sets the default weight |
| `enabled` | `false` keeps the source listed but stops fetching it and hides its items on the dashboard |
| `weight` | Optional per-source override of the role weight (0–10) |
| `note` | Optional explanation, e.g. why a source is off |
| `stats` | Optional snapshot (subscribers, views, Apple ratings, chart rank, last upload…) with the date it was `checked` |

Top level: `roles` (label and weight per role), `poll_every_hours` (how often each source type
is fetched: 0.25 or 0.5, or whole hours from 1 to 24; unset means 1) and `version`.

Every source has a stable key used to link it to its items and its health entry:
`youtube:<channel_id>` (or `youtube:<channel link, lowercase>` for a channel added by link),
`reddit:<subreddit, lowercase>`, `4chan:<board>`, or the feed URL for news, forums and podcasts.
The same rule is implemented in `scraper.source_key()` and in the dashboard's `sourceKey()`.

## Digital-only news (added 2026-10-08)

Every item gets `is_digital_only` from `is_digital_only(headline)` in `scraper.py`
(`PHYSICAL_GOING_PATTERN`, and `DIGITAL_WORDING_PATTERN` unless the headline is about an event,
a sale or an edition, `DIGITAL_EVENT_PATTERN`; a how-to, `DIGITAL_HOWTO_PATTERN`, never counts): headlines about a game released digital-only or about discs being phased out,
whether or not they name a PS2 game. It reads the headline alone, and every write flags the whole
snapshot again (copies, so the "nothing changed" check still compares with the file as read), so
items saved before the flag existed are counted, and a change of its words reaches the whole
two weeks at once. The yardstick is "Phantom Blade Zero Confirmed Digital-Only Despite Promised
Physical Release" (Power Up Gaming, carried by r/playstation on 2026-10-08). It counts
"digital-only", "all/fully/entirely digital", "going digital", "discless", "no / without / skip /
lack / ditch / end / stop making ... physical (release, edition, discs)", "physical ... cancelled /
no longer", game-key cards, code-in-box, "physical media", "physical vs digital", and a few
Portuguese and Spanish phrasings (two of the news feeds), "won't get / will not have a physical
release", disc drives and cartridges. Not counted: "an all-digital showcase", "digital only sale",
"no disc required", "no physical copies left", "ditch the disc: install to HDD". A whole-word "disc" keeps Discord and
"discovered" out; "Digital Deluxe Edition", the PS5 Digital Edition and Digital Foundry are not
counted. On the snapshot of 2026-10-08 it flagged 22 of 7,279 items. The dashboard's menu has
**Digital-Only News**; `tools/regression_check.py` ignores the field. `archive.py` keeps every
flagged story for good in `data/archive/digital/YYYY-MM.json` (d, h, s, t and the link `l`; the
same story is the same source and headline), with `index.json` holding the total, per month and
per day; the dashboard adds "N archived since …" from it. A kept story that is still in the
snapshot but no longer flagged (a change of the rules) is taken out again; one that has only
aged out of the snapshot stays. It is read from the snapshot, so it
costs no request to Reddit or any other site: Reddit's budget stays spent on the PS2
subreddits. The PS2 archive's index globs only its own folder, so the two never mix.

## A scraper run, step by step

1. **Load and validate `feeds.json`.** On any problem the run stops with a readable list
   (`sources[12]: invalid channel_id` and so on). The workflow fails and the previous data stays.
2. **Load the PS2 title index.** The EU and US serial databases are merged with the cached
   index and the built-in fallback list (this step is unchanged).
3. **Decide what is due.** Every source type has its own clock (`poll_every_hours`; in
   `feeds.json` 4chan 0.25, news and forums 0.5, Reddit and YouTube 1, podcasts 6). A type is
   due once that long, less a twentieth of it (at most 20 minutes), has passed since it was last
   fetched (`next_poll()`). The time of each type's last fetch is in `data/poll_state.json`.
   `FULL_RUN=1` fetches everything. Who starts the scraper and when is the job of
   `scrape_loop.py` (see "Always running" below).
4. **Build the fetch list.** News, forum and podcast URLs are used as they are. A board becomes
   `https://a.4cdn.org/<board>/catalog.json`. YouTube channels become
   `https://www.youtube.com/feeds/videos.xml?channel_id=…`. A channel added by link is looked up
   once: the scraper reads the channel page's canonical `/channel/UC…` link and remembers the ID
   in `data/youtube_channels.json`. A link that doesn't resolve, or that points at a channel
   already in the list, is reported as *Failing* and skipped. Subreddits that share a `group`
   are asked for three at a time (`REDDIT_SUBS_PER_REQUEST`), as one multireddit listing of
   their newest posts (`/r/a+b+c/new/.rss?limit=100`), a minute apart (`REDDIT_REQUEST_GAP`):
   26 subreddits in 3 groups make 10 requests. News and Reddit
   ("core") come first, then the "extras": forums and boards (a handful of quick requests),
   then YouTube and podcasts (hundreds, which can use up the time budget).
5. **Fetch.** Core feeds wait and retry once when rate limited (HTTP 429), as before. Extras never
   wait. After 3 consecutive host-level failures on one host (connection errors, timeouts, 5xx or
   429, e.g. youtube.com down) the rest of that host is skipped for this run. A dead feed (404,
   410...) doesn't count, because it says nothing about the host. Extras still pending 10 minutes
   after the first extra was asked for are skipped too (`FETCH_TIME_BUDGET`; Reddit's waits come
   before and do not count). A type whose feeds were all skipped is not marked as fetched, so it
   is due again in the next round. Together these keep a platform outage from making a round run
   on and on. Reddit requests are spaced a minute apart, counted from the end of the previous
   one, so a wait for a 429 is never followed by a request straight away; and once Reddit still
   answers 429 after the wait, the rest of that round's Reddit requests are not sent (they
   count as failed). Boards are asked one at a time, at least 1.1 seconds apart, and each
   request hands back the date the board's server gave last time (`If-Modified-Since`), so a
   board nobody has posted on since answers "not modified" and is not sent again.
6. **Analyse each entry** (up to 50 per feed; YouTube and podcast entries are sorted newest first
   because some podcast feeds list the oldest episode first):
   - *PS2 match*: known abbreviations (`gta sa`, `mgs3`, …), then exact short titles, then fuzzy
     matching. One-word titles that are also ordinary words ("Black", "Bully") only count with
     PS2 context: "PS2"/"PlayStation 2"/"PCSX2" in the title, or a source with the `ps2` role.
   - *Remaster flag*: remaster, remake, reboot, collection, port, "returns"…
   - *Sentiment*: 50 + 10 per positive keyword − 15 per negative keyword, clamped to 10–100.
   - The item stores `source`, `source_type`, `feed` (the source key) and `link`. The link also
     tells items apart, so a podcast episode uses its audio file URL when it has no page link of
     its own: no link, a bare guid, or a link that other episodes in the feed share (e.g. every
     episode of The Besties links to the show's homepage).
   A board's threads are not analysed this way: see [4chan boards](#4chan-boards).
7. **Record feed health** in `data/feed_status.json`, one entry per source key:
   `{"ok": true, "latest": "<newest item>"}` or
   `{"ok": false, "error": "HTTP 404", "failing_since": "…", "latest": "…"}`.
8. **Abort rule.** If more than half of the due news/Reddit feeds failed, or nothing was
   collected, the run exits non-zero and leaves the snapshot alone. It still writes the news and
   Reddit feeds' health and when those two were tried, so a site that refused us is asked again
   after its usual interval, not in the next round. The extras' results go with the aborted run,
   so their health and clocks are left as they were and they are fetched again next round.
9. **Merge and save.** New items replace the same link in the previous snapshot, items older than
   14 days drop out, and the files are only rewritten when something changed. A ceiling of
   12,000 items (`MAX_ITEMS`) guards the file's size. Reading Reddit's newest posts brings about
   29 posts an hour from the 26 subreddits (measured from GitHub's servers on 2026-10-08), some
   700 a day where the "hot" listing brought about 250, so two weeks of everything now come close
   to the ceiling. Past it, the oldest items that name no PS2 game go first (`within_ceiling()`);
   items naming a game are kept for the full 14 days. The archive, the Demand Index, eBay's
   levels and every game count are therefore unaffected; the item count, the mood average and
   the remaster-news count then cover fewer days of items that name no game.

## 4chan boards

4chan's boards are tracked for one thing: which PS2 games people bring up. The maintainer's
decision of 2026-10-07 is that **nothing a poster wrote is stored, shown or printed**, so a
board is handled differently from every other source.

- **What is read.** One request per board to 4chan's read-only API
  (`a.4cdn.org/<board>/catalog.json`), which returns the post that opens every live thread:
  an optional subject and a comment. Replies are not read. The API's terms are followed: at
  most one request a second, `If-Modified-Since` on each request, 4chan named as the source
  of every row, and a link back to the thread.
- **What counts as naming a game** (`games_in_post()`). A post is chat, not a headline, so
  three things a headline gets away with are not allowed. Each is judged on the very words
  that matched, which is why the reader keeps track of how every word was written
  (`post_words()`):
  - *The whole name, spelt as the library spells it.* "Dragon Age" is not *Dragon Rage*,
    and half a title ("the room", "substance") is not *Silent Hill 4: The Room*, even when
    the post says PS2. Titles longer than the matcher's six-word runs are found whole
    (`long_titles()`), and a shorter title inside one is not counted beside it.
  - *Written as a name* (`written_as_a_name()`): with a number written as a number ("silent
    hill 2", "kingdom hearts ii"), or with a capital on every word the library gives one
    ("the thing is" does not name *The Thing*). A lone I, V or X is not taken as a number
    (it is also a pronoun and a letter). A number followed by a unit of time is counting
    ("yakuza 2 days ago"). A title that is only a number counts only as the library writes
    it (*XIII*, not "13"). One everyday word that is also a title does not count as the
    first word of a sentence or line ("Black screen on my PS2"). A post written all in
    capitals marks nothing with them.
  - *Not another entry of the series* (`another_entry()`). A name that runs straight into
    a sequel number it does not have ("Max Payne 2", "Kingdom Hearts 3") is left to the
    library title with that number, if there is one. "Silent Hill 2, 3 and 4" and "Okami
    10/10" are let be.

  The matcher's built-in abbreviations ("mgs3", "gta sa") count however they are written.
  The subject is read first; only when it names nothing is the comment read (its first 120
  words, as for any body text). Where the words as written cannot be lined up with the
  words the matcher read (rare scripts), only the abbreviations count.
- **What is kept** (`analyze_thread()`). One item per thread that names a game: the games,
  the board, when the thread was started and the link to it. The `headline` is written by
  the scraper, "Thread on /vr/ naming Silent Hill 2" (three games at most, then "and 2
  more"). `sentiment` is `null` and `is_remaster_rumor` is always false, because the text
  is not scored. `matched_in` is `title` for a subject and `body` for a comment, so
  a game named only in a comment is a mention but not a headline (the eBay "surging" level
  goes by headlines). Threads that name no game leave no trace at all.
- **When it counts.** A thread is dated by when it was started, and that never changes, so
  the item is stable from run to run. Slow boards keep threads live for months or years; a
  thread started before the feed's 14 days is left out. Pinned threads (the board's rules)
  are skipped, and so is a thread whose date is not a plausible one (dates are compared as
  text, so year 322 or 2300 would never age out).
- **On the dashboard.** The row shows a dash instead of a score, `itemWeight()` gives every
  4chan row 0 whatever its role or source weight says, and a board has no weight box. The
  role `anonymous` (weight 0) exists so that a board has a role like every other source.
- **In the archive.** Every thread about one game on one board has the same generated
  headline, so `archive.py` tells 4chan rows apart by the thread's start time as well. The
  rows have no `n` (mood score), because they were never scored.
- **Health.** A board's `latest` in `feed_status.json` is its newest thread, whether or not
  it named a game. Its `modified` is the `Last-Modified` date the board's server gave, kept
  only to be sent back word for word on the next request; it says when the board changed,
  not when it was checked, and a failed read drops it so the next one is a full read. A
  board that cannot be read is reported as *Failing* like any extra.

`tools/try_sources.py` shows what a board or forum would give without writing anything, and
prints only counts and game names for boards. The *Live checks* workflow runs it on every
pull request that touches the scraper or `feeds.json`, because sites treat GitHub's servers
differently from a home connection: four forum feeds that answered a development machine
returned HTTP 403 there (see [SOURCES.md](../SOURCES.md#forums)).

## The dashboard

`index.html` loads `data/sentiment_feed.json`, `feeds.json` and `data/feed_status.json`, and, when
they exist, `data/demand.json`, `data/prices/latest.json`, `ebay_watchlist.json`,
`rare_games.json` and `rare_consoles.json`.

- **Four pages in one file.** A tab bar switches between *Tracker*, *Rarest*, *Most mentioned*
  and *eBay prices*; each is a wrapper (`viewDashboard`, `viewRare`, `viewMentions`,
  `viewPrices`) and only one is displayed. `#rare`, `#mentions` and `#prices` in the address
  select the other three; any other fragment selects the Tracker and scrolls to the part it names, so the header's
  *Sources* link works from every page. Changing page adds one entry to the browser's
  history, so Back returns to the page before; links, Back and Forward all go through
  `showViewFromAddress()`, which also runs once more when the first load has finished.
- **eBay medians beside every game.** `gamePricesHtml(title)` is what goes under a game's name
  in the Demand Index, Most Mentioned Games and the feed table: the medians for eBay US and UK
  when the game is priced (`priceFiguresHtml`), then the lookup chips. Prices are loaded
  before those lists are drawn. The *eBay prices* page lists every tracked game with the
  full figures and a search box. A read that fails (anything but a plain 404) keeps the
  prices already loaded; with nothing loaded, the page says the file could not be read
  rather than that the job has not run.
- **Which price belongs to which name.** The price file names a game by its library title;
  the feed may say "Persona 4" or "Kingdom Hearts 2". `priceKey()` reduces a title to the name
  `search_terms()` in `ebay_prices.py` gives it (article dropped, "and" dropped, Roman
  numerals as digits, "Getaway, The" turned round), and the price index is keyed by that. A
  pinned game's `search` words in `ebay_watchlist.json` are a second key for it. This is the
  rule the script itself uses to decide two titles are one game.
- **Games first.** Most items name no PS2 game (of the 654 published in the day before
  this was built, 53 named one), so the Tracker leads with the ones that do. *Named in the
  last 24 hours* (`recentGames()`) lists every game named by an item published in the last
  day, with an hour's grace for a source whose clock runs ahead. "Published" is the item's
  `timestamp`: the date its source gave it, or the time the scraper first saw it when the
  source gives none, so a new source without dates would put its backlog in the list.
  `recentGames()` orders them by most headlines first, so a game found only in body text
  (`matched_in: "body"`, the source of most wrong matches) comes after every game a
  headline named; then all mentions, then the most recent, then by name. The list then
  shows them most expensive first (`byPrice()`): by the eBay UK median, then by the US
  median for a game with no UK figure (the two currencies are never compared), then the
  games with no price. Games at the same price, and the games with no price, keep the order
  above. `gamesOf()` gives the games an item names
  (`matched_games`, or `matched_game` for older items, repeats and non-names dropped) and is
  the one definition the list, Most Mentioned Games, the table's menu, its search and its
  rows share: an item that names three games is a mention of each, as it is for
  `archive.py`, `demand.py` and `ebay_prices.py`. (Until this change Most Mentioned Games
  counted an item's first game only, and left out a game that was only ever named second.)
- **A game's name opens the table on that game.** `showGameRows()` sets `gameFilter`, and
  the table then shows the items whose games include exactly that name, from the whole
  feed, with the box and the menus put aside. It is not a text search: "Final Fantasy X"
  begins "Final Fantasy XII" and "Retro" is in a subreddit's name. *Back to every game*, or
  any change to the box or a menu (`onFeedFilterChange()`), clears it; a reload of the
  data and a change of page keep it. Both buttons hand the keyboard to the line over the
  table (`tabindex="-1"`), since the one that was pressed is far up the page or gone.
- **The table opens on the items that name a game** (`filterSelect` starts on `matched`).
  The line over the table (`#feedSummary`, on a row of its own so that its length does
  not push the box and the menus about) is written from the rows that are showing, with the box and the menus applied,
  and says how many are left out; *Everything* shows the rest. It never starts with
  "Showing", which is how the line under the table counts the rows of the page. A row
  leads with the item's first game (or the one the table was opened on) and lists up to
  four others under it, the ones the search box found first. Nothing is dropped from the
  snapshot: this is a view.
- **Three lists fold away.** The last 24 hours renders every game and shows ten; the Demand
  Index renders up to 25 rows and shows five; Most
  Mentioned Games renders every game and shows 25 (`LIST_FOLD`). Rows past that point are
  marked, and a class on the list hides them until the button under it is pressed. The stylesheet does the hiding, so the script only flips a class and rewrites the
  button. An opened list stays open when the data reloads, its "Show fewer" button follows the
  reader down the list, and folding it returns to the top of its section.
- **Every second row is tinted** in the lists and in the feed table (`.zebra` in `retro.css`).
- **The item count is a window, not a total.** The first tile is labelled with how far back
  the feed goes ("Items · 9 days"), worked out from the oldest item, because a count that
  has levelled off was read as a feed that had stopped.

- **Weights** (next section) drive the *Global Net Sentiment* card (a weighted average) and the
  order of the *Remaster Radar* (matched PS2 games first, then heavier sources, then the newest).
  Items with a weight other than 1 show a small `×0.5`-style badge.
- **Switched-off sources** disappear from every card and table immediately. The scraper stops
  collecting them on its next run, and their old items age out within 14 days. The exception is
  items collected before this version, which carry no source key; those only age out.
- **Sources & Weights panel**: one tab per source type. It has search, sorting (subscribers, total
  views, Apple ratings, chart rank, latest activity), an on/off switch, role and weight per
  source, live status badges, and an *Add source* form. The *Weights & schedule* tab edits the
  role weights and `poll_every_hours`. Status badges come from `feed_status.json`:

  | Badge | Meaning |
  |---|---|
  | Active | newest item at most 14 days old |
  | Quiet | 15–120 days |
  | Stale | older than 120 days (e.g. VG247, r/Steelbook) |
  | Failing | the last fetch failed (hover for the error and since when) |
  | Not checked yet | the scraper hasn't fetched it since it was added (a source switched back on shows its last known status until the next run) |
  | OK · no dated items | readable, but its items carry no dates |

- **Adding sources.** People paste what they already have:
  - a normal YouTube channel link, resolved later by the scraper as described above
  - an Apple Podcasts link, which the page turns into the show's name and RSS feed through
    Apple's lookup API (it allows browser requests)
  - a feed link or a subreddit name

  Pasted links are tidied the way a browser would (`https:/site.com/feed` becomes
  `https://site.com/feed`) and must then match the same pattern the scraper uses. A channel
  already listed under the same handle, or a show whose feed is already listed, is refused;
  other links to a listed channel are caught by the scraper ("already listed as ..."). Spotify
  links are refused with an explanation, because Spotify publishes no feeds.
- **Saving.** Edits apply on the page immediately. To make the scraper use them, feeds.json has
  to be committed, and *Save changes* does it one of two ways:
  - *Without a token* (the default): the new feeds.json is copied and a guided box opens
    GitHub's editor with 3 steps (select all, paste, commit).
    - If the account can't edit the repository, GitHub asks it to *Fork this repository*
      first. The user pastes, clicks *Propose changes*, then *Create pull request*, and the
      change applies once the owner accepts it. *Download* is the fallback.
    - *I've saved it* marks exactly the copied text as saved, so edits made after copying stay
      unsaved.
    - Web commits use the account's email settings; *Keep my email addresses private* gives the
      no-reply address.
  - *With a token* entered under *GitHub settings*: one click commits feeds.json through the
    GitHub API. The commit uses the token owner's `<id>+<login>@users.noreply.github.com`
    address. The repository owner can use a fine-grained token limited to this repository
    (Contents, plus Actions for *Run scraper now*). GitHub doesn't support fine-grained tokens
    for collaborators on another user's repository, so a collaborator needs a classic token
    with the `public_repo` scope. *Run scraper now* would need the broad `repo` scope, which
    isn't necessary because a save starts the scraper anyway.

  Either way the commit triggers the scraper.

  The website (GitHub Pages) can lag a few minutes behind a save. So the page:
  - loads `feeds.json` from the GitHub API when it differs from the website's copy
  - checks the committed file again right before either kind of save

  If it changed since the page loaded (someone else's save, or your own that the website hasn't
  caught up with), the page offers to load the latest list first instead of silently undoing it.
  The user guide [`guide.html`](../guide.html) walks through all of this step by step for
  non-technical users.
- **Removing.** Sources that are already saved can only be switched off, never deleted from the
  page. Only an addition that hasn't been saved yet has a remove button, to undo a typo.

## eBay asking prices

`ebay_prices.py` runs once an hour, started by the scraper's loop, and after each scraper run ends (`.github/workflows/ebay.yml`); it is separate
from the scraper on purpose: it is the only code that holds a key, and it must never be able to
break a scrape.

```
 data/sentiment_feed.json ─┐
 data/archive/*.json ──────┼─► ebay_prices.py ──► data/prices/latest.json ──► index.html
 data/ps2_database.json ───┤        │         └─► data/prices/YYYY-MM.json    (medians beside each game, eBay prices page)
 ebay_watchlist.json ──────┘        └─► this run's listings ──► ebay-data branch (latest run only)
```

**Which games.** Every game the feed has ever named (the snapshot plus the archive) that is in
the PS2 library, plus the games pinned in `ebay_watchlist.json`. A one-word title is tracked
only if nothing else is called that (`ONE_WORD_TITLES`, such as Kuon and Okami) or it is pinned, because a
search for "Black" returns every "black label" listing. Titles on the watchlist's `never` list
are skipped. Two library spellings that come to the same name are one game.

**How often.** Each run gives every game a level from its mentions in the snapshot:

| Level | When | Checked |
|---|---|---|
| `surging` | At most 1 headline mention in the rest of the window, then named in headlines by 2 or more sources, under different headlines, within 24 hours | Every run, until 48 hours after the last such mention |
| `staple` | Named in headlines on 5 or more days of the window; never surging | Every 6 hours |
| `normal` | Any other mention in the window, or pinned | Every 6 hours |
| `dormant` | Mentioned before, not in the window | Once a day |
| `rare` | On the Rarest page and not tracked otherwise | Once a day, on its list's site only |

A mention found only in an item's body text keeps a game `normal` but never makes it surge. A
run uses at most 500 searches and stops for the day at 4,500 of eBay's 5,000; surging games go
first, then pinned ones, then whatever is longest overdue. What is left waits for the next run.

**What it asks.** eBay's Browse API, with an application token from the client-credentials
grant, which can read public listings and nothing else. One search per game and site: used
conditions, Buy It Now, located in that country, in the Video Games category with the PS2
platform item specific. If nothing carries the item specific it asks again by keyword. A title
with a Roman numeral is searched both ways ("kingdom hearts ii", "kingdom hearts 2") and the
results are merged.

**What counts as a copy.** The listing must contain the game's whole name, words together and
in order, with spellings evened out ("&" and "and", "II" and "2", apostrophes). It is left out
if it names a different library game containing that name (`other_games()`: "Ultimate
Spider-Man" for "Spider-Man", "Kingdom Hearts II" for "Kingdom Hearts"), another number in the
series, another console, an import, or something that is not the game (case only, soundtrack,
cheat disc, demo, job lot, merchandise). When eBay returns listings and none names the game,
the game is `unmatched`: no figure, no history row, and a note on the dashboard.

**Regional names (added 2026-10-08).** `load_regional_names()` reads `regional_names` from
`ebay_watchlist.json`: per site, renames of the start of a game's name ("Fatal Frame" to "Project
Zero"). `apply_regional_names()` gives each matching game its own search words, queries and
siblings for that site, and `check_market()` uses them (`for_market()`). Only the search
changes: the game keeps its library title in `latest.json` and the history. The plan's log line
names the renamed games, never a price. The dashboard's own eBay UK search links still use the
title.

**The Rarest page's games (added 2026-10-08).** `rare_games.json` holds two ranked lists of a
hundred, `PAL` and `US`, with each entry's sources (see *The rarest games* below).
`load_rare()` reads it and `add_rare_games()` adds its games to the plan after the regional
names are applied. An entry is the game the feed already tracks when that game is searched
on the list's site under the entry's words or under the entry's name ("Project Zero 2: Crimson
Butterfly" is the feed's *Fatal Frame 2*), or has the same name; it is then priced as before and
its figures serve the list. Otherwise the entry is looked up on its own, even when it is the
same game under other words: the tracked *King's Field IV: The Ancient City* is searched under
that full name, which PAL sellers of *King's Field IV* do not write. Never by the other region's name: the feed's *Tokyo Xtreme Racer:
Drift 2* is searched on eBay UK under that name, and the PAL list's *Kaido Racer 2* is not.
Every other entry becomes a game of level `rare`: checked once a day (`CHECK_EVERY_HOURS`),
only on its list's site (`RARE_SITES`: PAL on eBay UK, US on eBay US, recorded as `sites` in
`latest.json`), after every other due lookup. A game on both lists is one game on both sites.
An entry can name words a listing must also contain (`require`, for an edition such as
*Scarface ... Collector's Edition*: searched as "scarface collectors", never the tracked
*Scarface*), words that leave a listing out (`exclude`, "fes" for *Persona 3*), and junk phrases
an edition comes with (`allow`: "art book" for a limited edition, "plush" for the Raiho
Edition), which then do not mark a listing as "not a copy". An entry searched under one word
that is not in `ONE_WORD_TITLES` and has no `require` is not priced (Obscure, Buccaneer,
Nightshade, Hanuman), as for the feed's games; the page shows it as "not priced". Library names
of the same game ("R.A.D. Robot Alchemic Drive") are not taken for other games. `latest.json`
gains `rare`: for each list, which title in `games` holds each entry's figures. A file or an
entry that cannot be used is named in the log and left out; it never stops the run. 133
games are priced for the lists alone: about 150 lookups a day.

**What is kept.** Under `data/prices/`, numbers only: `latest.json` (per game and site: copies,
lowest, median, typical postage, when checked, and `week`, the median of a week before; the
game's level; the day's search count) and
`YYYY-MM.json` (a row of time, game, site, copies, lowest, median whenever the three figures
change, and at least once a day). `latest.json` is also the job's memory: when each game was
last checked and until when it is surging. Neither file is ever rebuilt from nothing; if one
cannot be read the run stops before asking eBay. `week` is worked out on every run that writes
`latest.json`, from the history: the latest row of that game and site recorded between 7 and 9
days before the check (`CHANGE_DAYS`, `CHANGE_SLACK_DAYS`; a quiet game is checked only daily),
and only when it found copies. History is matched by `key_of(title)`, so a title spelt another
way from one run to the next ("Ico", "ICO") keeps its history; a value that is not a finite
positive number is never copied. Early in a month that row is in the month before, which is read
but never written; if it cannot be read, those figures go without a `week` and the run goes
on. The dashboard shows the change in brackets beside the median (`priceChangeHtml()`), in
the shortened form under a game's name and on the eBay prices page. The difference and the
percentage are worked out from the two prices as they are written (whole pounds or dollars
from 100), so the bracket adds up with what the reader sees; an overdue figure's bracket is
dimmed with it. Listings and links go to the `--out` file,
which the workflow publishes as a single replaced commit on the `ebay-data` branch.

**The PS2 price index (added 2026-10-08).** After writing `latest.json`, the run reads every
month of history and writes `data/prices/index.json`: per site, `[day, index, games compared]`
from the first day with at least `INDEX_MIN_GAMES` games priced (100), finished UTC days only (a
day under way moved it on whichever games were checked first: in the review, the US index read
97.45 at 02:00 and 99.95 by 08:00). `daily_medians()` takes each
game's last median of the day with at least `INDEX_MIN_COPIES` copies; `price_index()` moves the
index each day by the geometric mean of each game's change since its previous priced day, if
that was at most `INDEX_MAX_GAP_DAYS` before and the change is within ×`INDEX_MAX_MOVE` either
way; a day with fewer than `INDEX_MIN_GAMES` comparisons keeps the day before's value. This is a
chained Jevons index, as statistics offices use without quantities: it weighs every game alike,
and games joining or leaving do not move it. A change of search words of less than ×2 does move
it, once. Consoles are left out: those marked `kind: "console"` in `latest.json`, every name in
`rare_consoles.json` (priced or not), and every key left out before (`left_out` in the file), so a
console renamed or dropped from the list never brings its history in. With a year of history the
calculation takes a few seconds per run. A month
that cannot be read leaves the old index in place and is named in the log. The dashboard shows
it at the top of the eBay prices page (`renderIndex()`): the latest value, the change since the
day before and over a week (`indexChange()`), and an SVG line of every day.

**When it gives up.** A run stops early if eBay does not answer three lookups in a row, if its
first ten lookups all fail, or if eBay says the allowance is used. Nothing is written when
more than half the lookups failed, or when games that had copies last time now return nothing
at all (a broken search, not an empty market).

## The rarest games

`rare_games.json` (added 2026-10-08) is the Rarest page's data: `lists.PAL` and `lists.US`, a
hundred entries each, ranked by `value_usd.cib`, PriceCharting's market price for a complete
copy read on `checked`. Nobody counts copies, so price is the measure of rarity collectors use.
Each entry has `title`, `other_title` (the other region's name, where it differs), `search`
(and `require`/`exclude`, see *eBay asking prices*), `flags` (`weak`, `one_source`, `edition`,
`india`, explained in the file's `flags`) and `evidence` (source link, figure, date). The file's
`method`, `gaps` and `sources` say how it was made and what is missing: the order is complete
down to about $60 (PAL) and $90 (US); below that a game with no loose price may be missing.

It was built from PriceCharting's console tables sorted by price, Racketboy (2022), GIGA (2026),
Destructoid (CeX prices, 2025), PPE.pl (2023, 2024), whynow (2022) and Retro Dodo (2020/2024).
RFGeneration and consolevariations.com were not read: their robots.txt asks robots to stay out.
Nothing reads PriceCharting automatically; the figures are a dated snapshot.

The page (`renderRare()`) shows one list at a time (PAL or US), 25 rows folded, each with its
guide value, flags, other name, the eBay median on its own site (`rarePrices()`: the game
`latest.json`'s `rare` names, else the game of the same `priceKey()`) and its source links (https
only). `RARE_SITE` in the page and `RARE_SITES` in the script must agree (tested). Without the
file the page says so; a failed reload keeps the list on screen.

### The rarest consoles

`rare_consoles.json` (added 2026-10-08): 37 official PS2 consoles and Sony devices with a PS2
inside, ranked in four tiers (a stated run of 5,000 or fewer; never sold in shops or through one
shop or bundle; one country's limited colour; wider limited runs), and by PriceCharting value
within a tier. Each entry has its model numbers, regions, release, `units` when a source states
them, `why_rare`, `not_retail` for development units, `confidence`, `value` (PriceCharting, USD,
dated) and `evidence`. Built from Wikipedia (English and Japanese), Obsolete Sony, Sony's press
releases, PriceCharting's systems tables, GamePro.de, hardware.com.br, TechSpot, AV Watch and
collector forums; consolevariations.com was not read (robots.txt). Its `gaps` lists what is
unconfirmed: the car-paint colours' Japanese and European model numbers, several production
figures, and no UK prices.

`load_consoles()` turns each priced entry into a thing to price of `kind: "console"`, level
`rare`, on both sites or its `sites`. `check_market()` sends it through `search_url(...,
console=category)`: the consoles category (`CONSOLE_CATEGORY_ID`, or every category for the PSX
and the Bravia), every condition but for parts (`CONSOLE_CONDITION_IDS`), Buy It Now, no
location filter (most are sold from Japan), the entry's own queries (at most 3).
`console_reject_reason()` counts a listing that has every `require` phrase and one `require_any`
phrase, names no other console and none of `CONSOLE_JUNK` or the entry's `exclude`. A bundle
counts. A listing that names a part (`CONSOLE_PARTS`: controller, remote, cable, hard drive...)
counts only when it says it is a console ("console", "system", an SCPH number) or that the console
comes with the part ("with remote", "+ controller"), so a coloured controller or a PSX remote is
never taken for the console. Figures, history and the week's change are kept as for games, under the console's name;
`kind` keeps them off the eBay prices page and away from names in the feed. Entries with
`"price": false` (the one-off show unit, two unconfirmed models) say why on the page. The page
splits them by `regions` into US (US, CA), Japan (JP) and PAL (EU, UK), a console in each list
it was sold in, and sorts each list by price (`consoleSortPrice()`): the eBay median of the
region's own site (UK for PAL, US otherwise), then the other site's, then `value.usd`; the file's
rarity order is shown as the tier. 34
consoles priced: 64 lookups a day, two searches each.

## Weights

| Role | Default weight | Used for |
|---|---:|---|
| `ps2` PS2-dedicated | 1.5 | r/ps2, r/ps2homebrew, r/PCSX2, r/playstation2, PS2 YouTube channels and PS2-history podcasts |
| `official` Official | 1 | PlayStation.Blog, Xbox Wire, platform and publisher channels, official PlayStation podcasts |
| `press` Press & news media | 1 | News sites, news channels and news podcasts |
| `community` Community (Reddit & forums) | 1 | The other subreddits and general forums |
| `retro` Retro | 1 | Retro reviews, history, hardware and emulation |
| `collector` Collectors & resellers | 0.5 | Game hunting, flipping and restoration channels (Phoenix Resale, Chase After The Right Price, TronicsFix, …) |
| `creator` Entertainment creators | 0.5 | Big let's-play channels and comedy gaming podcasts |
| `anonymous` Anonymous boards (4chan) | 0 | The 4chan boards. Their rows have no mood score, so they count 0 whatever is set here |

`effective weight = the source's own weight if set, else its role's weight, else 1`.
A weight of 0 keeps items visible but leaves them out of the average.

## Why it is built this way

**One `feeds.json` instead of lists inside `scraper.py`.** Sources now number in the hundreds, and
the dashboard has to read and edit them. A data file can be edited from the page and validated
on both sides. It also keeps source changes out of code diffs. The 18 news URLs and 26
subreddits were moved over unchanged, and a test proves the scraper still builds the exact same
21 news/Reddit requests.

**YouTube through channel RSS feeds, not the YouTube Data API.** The feeds are public, need no
API key or quota, and parse with the `feedparser` library the scraper already uses. The cost is
that a feed only holds the latest 15 uploads, which is plenty for hourly polling. Channels are
stored by channel ID because the feed only accepts IDs and handles can be renamed.

**Podcasts through their own RSS feeds, ranked with Apple data.** Every podcast already is an RSS
feed, so it fits the same pipeline. Podcasts publish no listener or subscriber numbers, so
popularity comes from Apple Podcasts' Video Games chart (US and UK) and the number of US ratings.
Feed URLs come from Apple's lookup API, and each one was fetched and parsed before it was added.

**What starts switched on.** The goal is PS2 and retro signal, not raw volume. Gaming news,
platforms/publishers, retro and PS2 sources start on. Most of the very largest gaming channels
start off: they are non-English (the keyword sentiment only understands English) or focused on
Minecraft, Roblox or Fortnite. They are all listed with their numbers and are one click from
being on. Anything with nothing new for 120+ days starts off as well. The reason for every "off"
is in the source's `note`.

**Weights apply to totals, not to single headlines.** A headline's own score stays readable ("+10
per positive keyword"). Weights only decide how much each item counts in the aggregate numbers,
which is where a flood of hype titles ("INSANE PS2 HAUL!!") from reseller channels would
otherwise skew things. Roles give one knob per kind of source, and per-source overrides handle
exceptions. The page applies weights live because every item records its source key, so tuning
needs no rescrape.

**The `ps2` role also gives PS2 context.** Before, only the dedicated PS2 subreddits could match
ambiguous one-word titles. Tying that to the role keeps exactly that behaviour for them and
extends it to PS2 YouTube channels and podcasts, whose titles rarely repeat "PS2".

**News and Reddit decide whether a run failed; YouTube and podcasts can't.** The abort rule
protects the snapshot from a broken run. With 175 extra feeds, one YouTube or podcast outage
would otherwise abort every run and freeze the whole dashboard. Extra-feed failures are counted,
logged and shown as *Failing* instead.

**No rate-limit waits for extras, a per-host breaker and a time budget.** Reddit needs its
wait-and-retry. For 111 YouTube feeds on one host, waiting 60–90 s per feed would blow the
job's time limit. Failing fast, skipping a host after 3 straight failures and capping extras at
10 minutes keeps every round bounded.

**Always running (`scrape_loop.py`, added 2026-10-08).** GitHub starts scheduled runs late or
not at all: in the first week of October 2026, 24 of about 130 hourly runs happened, about one
every 5½ hours. So one run of the scraper workflow now stays up for `LOOP_MINUTES` (330): it
pulls `main`, works out when the next type is due from `poll_state.json`, sleeps until then,
runs `scraper.py` in a process of its own, commits and pushes `data/` if it changed, and waits
at least `MIN_GAP` (2 minutes) before the next round, or `FAILED_WAIT` (15 minutes) after a
round that failed, so a site refusing us is never hammered. Once an hour it starts the eBay
prices workflow (`gh workflow run`, with the workflow's own token). At the end it starts its
successor with `mode=continue`, also after an error but not after a cancel. The concurrency
group is per branch (`scraper-<branch>`): a push or *Run scraper now* cancels the running loop
on that branch and starts a fresh one whose first round fetches everything (`FULL_FIRST`); the
hourly schedule and the successor wait for the running loop, so there is only ever one, and
only a loop on `main` starts the eBay job and a successor. If the chain does break (a run that
hit the job's time limit), the hourly schedule starts a loop again, but it fires late, so that
can take a few hours. A round may take `ROUND_TIMEOUT` (40 minutes) before it is stopped; the
last one starts with at least `ROUND_RESERVE` (45 minutes) to spare, inside the job's limit
of 355 minutes. Files are written whole (`write_whole()`: a temporary file, then a rename), so
a round stopped part-way never leaves a cut-off file to be committed.

Commits: every round rewrites `poll_state.json`, and a busy board's `Last-Modified` date in
`feed_status.json` changes almost every time it is read. When those two are all that changed,
they are committed at most once an hour (and at the hand-over), and a commit that a push could
not deliver goes up with the next one. The snapshot is rewritten only for new or changed items:
items that merely aged past 14 days go with the next write. New items are committed at once;
news every half hour brings some nearly every time, so expect three to five commits an hour
from the loop, plus the eBay job's: under GitHub Pages' soft limit of ten builds an hour. On a public repository the runner time is free. Only the first round of
a loop downloads the PS2 title index; later rounds use the copy it saved
(`TITLES_FROM_CACHE`).

**Podcasts every 6 hours.** The enabled podcast feeds add up to about 100 MB per fetch, because
feeds carry every episode ever released. Shows publish daily at most, so fetching every 6 hours
loses nothing and cuts traffic about six-fold. The interval is measured from the last podcast
fetch (`data/poll_state.json`), not tied to fixed UTC hours. Manual and push-triggered runs
fetch everything.

**Feed health only stores things that change when something happens.** The workflow commits
`data/` whenever it changes. Storing "last checked" times would create a commit every hour, so
`feed_status.json` keeps only `ok`, `latest`, `error` and `failing_since`. Quiet runs leave it
byte-for-byte identical, and a test checks this.

**Saving from a static page.** GitHub Pages can't run server code, so the page either walks you
through pasting the new file into GitHub's editor or commits through the GitHub API with your
own token. The guided route is the default because it needs no setup, and it also works for
people who can't edit the repository, via *Propose changes*. The token stays in the browser: it
is kept for the tab session unless you tick *Remember*, and it is only sent to api.github.com.
Commits made with it use the GitHub no-reply address so no personal email ends up in the
history.

**Links in, IDs resolved where possible.** Non-technical users have channel and show links, not
channel IDs or RSS URLs. Apple's lookup API allows browser requests, so the page converts an
Apple Podcasts link on the spot. YouTube doesn't allow that, so a channel link is stored as it is
and the scraper resolves it on its next run. It remembers the answer in
`data/youtube_channels.json` so each link is looked up only once. Channel IDs still work and are
used as-is.

**Canonical JSON.** `feeds.json` is written as `json.dumps(indent=2, ensure_ascii=False)`. Whole
numbers are written without `.0`, which matches `JSON.stringify(config, null, 2)` byte for byte,
so a save from the page shows only the lines that really changed.

**Validation in two places, tested for agreement.** The page validates before saving and the
scraper validates before running. Feed links are checked with one shared pattern: ASCII host
name with a dot, optional port, printable ASCII after that. Browsers "repair" links like
`https:/site.com/feed` that Python would reject; the page stores the repaired link, which then
matches the same pattern. A link that one side accepts and the other rejects would otherwise
stop every run. A test feeds the same good and broken configs to both validators and requires
identical verdicts. That set includes the malformed links found in the independent review.

**Game names in two places, tested for agreement.** `priceKey()` in the page and
`search_terms()` in `ebay_prices.py` must give a title the same name, or a price goes missing
from a row or lands on the wrong game. A test runs both over every title in the PS2 library,
the watchlist and a set of awkward spellings, and requires identical answers.

**Security.** Everything written into the page from feeds, config or GitHub/Apple responses is
HTML-escaped, and links must be http(s). The optional token lives in the browser: session storage
by default, local storage only with *Remember*, and the local copy is shared by every page of
that github.io site. It is only sent to api.github.com. Like any script on the page, the Tailwind
CDN script the dashboard already loaded before this change could read it. That is one more
reason saving without a token is the default and tokens should be short-lived.

## Known limitations

- eBay figures are asking prices of copies still for sale, never sold prices, and loose discs
  are counted with complete copies. A game with more than 200 listings on a site is priced
  from the first 200. Search words come from the library title, so a game sellers abbreviate
  is `unmatched` until it is pinned with its own search words.
- The "surging" level inherits the matcher's mistakes: in a replay of one week, 6 of 12 flags
  were the wrong game matched.
- Until 2026-10-07 the snapshot held at most 5,000 items, which had cut it to nine days. The
  ceiling is now 12,000 and the window refills to 14 days as new items arrive; until it has,
  the eBay levels are worked out from less than two weeks of mentions.
- Fuzzy matching still maps franchise names to the PS2 entry, e.g. "God of War Laufey" becomes
  *God of War*. Sequel numbers are checked, but new subtitles aren't. This shows most on
  4chan's /vg/, whose long-running threads are about a series ("Monster Hunter", "The Sims").
- 4chan: only the post that opens a thread is read, never the replies. A real mention
  written in lower case without a number is not counted. A busy board is seen only as it
  stands when a run happens, and GitHub often starts runs hours late, so threads that come
  and go in between are never seen. Thread links stop working when 4chan deletes the thread,
  while the row stays for 14 days.
- Forums: many sit behind a check that refuses GitHub's runners (HTTP 403), whatever the
  request says about itself. Only the two that answered from there are listed.
- Forums: a thread's link is its own page (`thread_link()`: `<comments>`, then a `<guid>`
  that is an address, then `<link>`). Lemmy puts the article a post shares in `<link>`;
  used as the item's link it would be the same as the article's own row from a news feed,
  and rows are told apart by their link. A forum row that still has the link of another
  source's row is left out of the run rather than replace it.
- Sentiment is a keyword count in English. Non-English titles score a neutral 50.
- Subscriber, view, rating and chart numbers in `feeds.json`/`SOURCES.md` are a snapshot from the
  `checked` date. Live activity comes from `feed_status.json`.
- Reddit is read from the newest posts, three subreddits per request, up to 100 posts each,
  once an hour (since 2026-10-08; before, the combined "hot" listing of a whole group, 50
  posts). On 2026-10-08 the busiest request (r/pcmasterrace, r/NintendoSwitch, r/PlayStation)
  had about 11 new posts an hour and its 100 reached back almost 9 hours; every other request
  reached back more than 20. The *Live checks* report shows this for every request.
- On 2026-09-30, VG247's feed had nothing newer than 2026-06-02. Time Extension sits behind a
  Cloudflare check that blocks some networks, though not GitHub's runners. r/Steelbook and
  r/xboxone contribute only old posts.

## Tests

`python -m unittest discover -s tests -v` runs everything offline (fixture feeds, no network):

- **feeds.json**: valid, canonical formatting, unique keys, every original news feed and
  subreddit still present, measured stats dated.
- **Validation**: 48 kinds of broken config rejected, including:
  - YouTube video links and un-normalised channel links
  - the malformed feed links from the independent review
  - odd hand edits: a list as role, a huge or `null` interval

  Channel links are accepted, the error on load is readable, and a file saved with a BOM loads.
- **Fetch plan**: the original Reddit groups become their newest-posts requests, three subreddits each, disabled
  sources skipped, core feeds first, channel links wait for their ID.
- **Schedule**: every type waits for its own clock, a quarter of an hour included, with the
  slack at a twentieth; podcasts wait 6 hours even across skipped runs; unreadable state means
  due; `FULL_RUN` fetches all; Reddit requests a minute apart; past the size ceiling, items
  naming no game go first.
- **The loop** (`test_scrape_loop.py`, added 2026-10-08), on a fake clock: each type on its
  clock for five and a half hours, a full first round on a fresh start, the eBay job hourly,
  the successor at the end, failed rounds and a broken `feeds.json` waited out, nothing run with
  every source off, no round past the job's limit; and the workflow's triggers, concurrency,
  rights and time limit.
- **Entries**: podcast audio-link fallback, newest-first sorting for extras only, labels and
  keys, PS2 context from the role.
- **Feed health**: `latest` only moves forward, `failing_since` survives repeated failures.
- **Whole runs** against fixture feeds of every type:
  - items land with the right labels, keys and links
  - a YouTube failure doesn't abort the run
  - a mostly failed core run aborts without writing
  - a failing host is skipped after 3 failures
  - a quiet re-run rewrites nothing
  - health entries of removed sources are dropped
  - a YouTube channel link is resolved once, remembered and fetched under its own key
  - a channel link that can't be resolved is reported and skipped
  - a link to a channel that is already listed isn't fetched twice
  - podcast episodes that share one link stay separate items
  - dead feeds (404) don't make a host look down
  - podcasts aren't fetched again before their interval has passed
- **Dashboard** (needs Node.js): the inline script runs in a sandbox with a stub DOM:
  - feeds.json validates
  - a save reproduces the file byte for byte
  - weights, hiding and type inference behave as described
  - every tab and the weights panel render with the real feeds.json
  - the sentiment card shows the weighted average and the Radar puts matched PS2 games first
  - switching a source off or changing a role weight updates the cards, and Discard restores them
  - adding a source validates its input, rejects duplicates and video links, and only unsaved
    additions can be removed
  - pasted YouTube channel links are normalised and stored as `channel_url`
  - an Apple Podcasts link fills in the show's name and feed; unknown shows and Spotify links
    get a clear message
  - *Save changes* without a token copies the file, shows the GitHub editor link and steps
    (including the fork / Propose changes / Create pull request path), and *I've saved it* marks
    only the copied text as saved
  - a newer feeds.json on GitHub triggers the "load the latest list first" choice instead of an
    overwrite
  - a token save sends the loaded `sha`, the branch and the `<id>+<login>@users.noreply.github.com`
    identity, and the token goes to api.github.com only
  - pasted links are tidied (`https:/...`, `m.reddit.com/r/...`, old `itunes.apple.com` links),
    a handle that starts with "UC" stays a handle, and saved sources can't be removed
  - the base64 helpers round-trip non-ASCII text
  - the repository is detected from a GitHub Pages address
  - the page and scraper validators agree on 67 configs

- **Matcher** (`test_matcher_fixtures.py`): precision and recall on 268 hand-labelled real
  headlines must not fall below their floors, and each matching rule has a named test.
- **eBay prices** (`test_ebay_prices.py`, 136 tests): a fake stands in for eBay's API and a
  throwaway local server exercises the real request code.
  - the key, the token and the Basic header never reach the log or any written file; redirects
    are refused; network errors name only the kind of failure
  - each site is asked for used Buy It Now PS2 copies in its own country; a failed search is
    tried three times; a bad request is not retried
  - real listing titles from the live runs are sorted the way a person would sort them
  - levels: what is and is not a surge, the 48-hour hold, staples, dormant and pinned games
  - which lookups are due, in what order, and what the per-run and per-day allowances stop
  - `data/prices/` holds numbers only; history gains a row on a change or a new day and not
    otherwise; a failed lookup keeps the old figures; unreadable price files stop the run
  - the workflow: who can start it, that it runs `main`, that the key reaches one step, that
    it installs nothing, and that only `data/prices` is committed
  - the median of a week before (added 2026-10-08): the 7-to-9-day window and both its edges,
    the newest row in it, an unchanged price kept, nothing a week old yet, none found, the
    month before on the 1st and in January, a damaged month before, rows in other shapes,
    another spelling of the title, NaN and Infinity, a figure that no longer holds
- **Scraper, added 2026-10-07**: the snapshot keeps two weeks, newest first, and past its
  ceiling it is the oldest items that go.
- **Dashboard, added 2026-10-08 (price order and the week's change)**: the order by UK median,
  then US, then no price, with ties kept and click targets in step; the line that says so; the
  bracket's wording up, down and unchanged, its rounding (pennies, whole pounds from 100, a
  tenth of a per cent, 10 and 100 per cent), its hint and local date, escaping, the figures it
  refuses, its place on the eBay prices page, and its styles.
- **Dashboard, added 2026-10-07 (games first)**: which items count as the last 24 hours, the
  order of the games, what each line shows and escapes, the three empty states, the fold at
  ten, a feed of 1,200 items; that a click on a name shows exactly that game's items, on
  every page of them, and how it is undone; every wording of the line over the table,
  down to one item and none; rows that name several games; that Most Mentioned Games
  counts the same way; that the page draws the list by itself, a switched-off source
  leaves it at once and a reload keeps the chosen game; every rule in the stylesheet about
  the new parts.
- **Dashboard, added 2026-10-06 and 2026-10-07**: the ranked lists fold (five rows, 25
  rows) and open again, and Most Mentioned Games leaves no game out; the eBay prices page orders, formats and escapes its rows, narrows them with the
  search box, dims a price only when it is overdue for its level, and says what to do when
  there is no price file; the medians appear under a game's name in all four places, find
  the game under another spelling, and show nothing rather than another game's figure; a
  price file the page cannot draw leaves the rest of the page working; prices are fetched from
  the site with no token, before the lists are drawn; the pages switch by tab and by
  address, with exactly one on screen; the item count is labelled with how far back it goes; rows name their cells for the phone layout; a phone gets 25 rows to a page.
- **Page and price script agree on names**: `priceKey()` against `search_terms()` on the whole
  library.
- **Forums and 4chan boards, added 2026-10-07**:
  - a forum's threads become items like any other feed, and a forum that refuses the run
    (HTTP 403) is reported without stopping it
  - a board gives one row per thread that names a game, and none of the words a poster
    wrote (a rude one, an ordinary one, the name field) reach the snapshot or the health file
  - the request: the catalog is flattened, the server's own date is sent back as
    `If-Modified-Since` (and nothing that is not such a date is sent or stored), a "not
    modified" answer keeps what was collected and leaves the health file alone, anything
    that is not a catalog is a failure
  - `tools/sample_fixtures.py` never draws a 4chan row as a headline to test the matcher on
  - boards are asked one at a time with the pause between them, in the order listed
  - a post names a game only when the whole name is there, written as a name, and not
    followed by another entry's number: about 150 short posts, each rule with the cases it
    lets through and the ones it stops
  - threads without a usable number or a plausible time, pinned threads and threads started
    before the feed's two weeks are left out
  - every other field a poster fills in (name, tripcode, file name, flag, the link's slug,
    replies) is in the fixtures as a marker word, and none of them reaches the snapshot,
    the health file or the log; the same against answers of every wrong shape, read by the
    real reader
  - a forum thread that links to an article keeps to its own page and never replaces the
    article's row, in the run that sees both and in a later one
  - a forum that fails is never counted towards calling a run off, nor waited on
  - the pause between boards, on a clock that only moves when the scraper sleeps
  - `tools/try_sources.py`: for boards, counts and game names only in its output, its
    notices and its summary page; a forum headline cannot start a line of its own
  - five boards failing cannot stop a run, and the rest of the host is skipped after three
  - the dashboard: the rows, the dash for the score, a weight that can never count, the
    type filter, the two new tabs, adding a board by name or link and a forum by feed link
  - the archive keeps two threads about one game as two mentions (`tests/test_archive.py`)
  - the *Live checks* workflow holds no key, can write nothing and cannot start the eBay job

The *Tests* workflow runs the suite on every push to `main` that touches code, `feeds.json` or
the tests, and on every pull request.
