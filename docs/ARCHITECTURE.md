# How it works

The tracker reads gaming news sites, Reddit, YouTube channels and podcasts, matches every
headline, video title and episode title against the PS2 library, flags remaster/remake chatter,
scores sentiment and shows the result on a static dashboard. Everything runs on GitHub: a
workflow scrapes, commits the data, and the page reads the committed files.

```
                 feeds.json  ◄──────── save (GitHub API or copy/paste) ────────┐
                     │                                                          │
                     ▼                                                          │
     scraper.py  (GitHub Actions: hourly, and right after feeds.json changes)  │
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
| `type` | `news` (RSS/Atom site feed), `reddit` (one subreddit), `youtube` (one channel) or `podcast` (one show's RSS feed) |
| `name` | Display name. YouTube and podcast items are labelled `YouTube: <name>` / `Podcast: <name>` |
| `url` / `subreddit` / `channel_id` / `channel_url` | Where to read it: feed URL for news and podcasts, subreddit name, or a YouTube channel ID (`UC…`). A YouTube channel can instead be given by its link (`channel_url`, e.g. `https://www.youtube.com/@IGN`); the scraper looks the ID up |
| `group` | Display grouping. For Reddit it also decides which subreddits share one combined request |
| `role` | One of the roles below; sets the default weight |
| `enabled` | `false` keeps the source listed but stops fetching it and hides its items on the dashboard |
| `weight` | Optional per-source override of the role weight (0–10) |
| `note` | Optional explanation, e.g. why a source is off |
| `stats` | Optional snapshot (subscribers, views, Apple ratings, chart rank, last upload…) with the date it was `checked` |

Top level: `roles` (label and weight per role), `poll_every_hours` (how often each source type
is fetched) and `version`.

Every source has a stable key used to link it to its items and its health entry:
`youtube:<channel_id>` (or `youtube:<channel link, lowercase>` for a channel added by link),
`reddit:<subreddit, lowercase>`, or the feed URL for news and podcasts.
The same rule is implemented in `scraper.source_key()` and in the dashboard's `sourceKey()`.

## A scraper run, step by step

1. **Load and validate `feeds.json`.** On any problem the run stops with a readable list
   (`sources[12]: invalid channel_id` and so on). The workflow fails and the previous data stays.
2. **Load the PS2 title index.** The EU and US serial databases are merged with the cached
   index and the built-in fallback list (this step is unchanged).
3. **Decide what is due.** The job is scheduled every hour at :17, but GitHub delays or skips
   scheduled runs. News, Reddit and YouTube (`poll_every_hours` 1) are fetched on every run. A
   slower type (podcasts: 6) is fetched once that many hours, minus 20 minutes of slack, have
   passed since it was last fetched. That time is recorded in `data/poll_state.json`. Manual runs
   and runs triggered by a push that changes `feeds.json`/`scraper.py` set `FULL_RUN=1` and fetch
   everything. The workflow checks out the branch head, so a run that waited behind another starts
   from that run's data commit.
4. **Build the fetch list.** News and podcast URLs are used as they are. YouTube channels become
   `https://www.youtube.com/feeds/videos.xml?channel_id=…`. A channel added by link is looked up
   once: the scraper reads the channel page's canonical `/channel/UC…` link and remembers the ID
   in `data/youtube_channels.json`. A link that doesn't resolve, or that points at a channel
   already in the list, is reported as *Failing* and skipped. Subreddits that share a `group`
   become one multireddit URL (`/r/a+b+c/.rss?limit=50`), exactly as before. News and Reddit
   ("core") come first, then YouTube and podcasts ("extras").
5. **Fetch.** Core feeds wait and retry once when rate limited (HTTP 429), as before. Extras never
   wait. After 3 consecutive host-level failures on one host (connection errors, timeouts, 5xx or
   429, e.g. youtube.com down) the rest of that host is skipped for this run. A dead feed (404,
   410...) doesn't count, because it says nothing about the host. Extras still pending after 10
   minutes are skipped too. Together these keep a platform outage from pushing the job past its
   15-minute limit.
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
7. **Record feed health** in `data/feed_status.json`, one entry per source key:
   `{"ok": true, "latest": "<newest item>"}` or
   `{"ok": false, "error": "HTTP 404", "failing_since": "…", "latest": "…"}`.
8. **Abort rule.** If more than half of the due news/Reddit feeds failed, or nothing was
   collected, the run exits non-zero and writes nothing.
9. **Merge and save.** New items replace the same link in the previous snapshot, items older than
   14 days drop out, and the files are only rewritten when something changed. A ceiling of
   12,000 items guards the file's size; two weeks is about 8,400 at the current number of
   sources, so the 14 days are what normally applies.

## The dashboard

`index.html` loads `data/sentiment_feed.json`, `feeds.json` and `data/feed_status.json`, and, when
they exist, `data/demand.json`, `data/prices/latest.json` and `ebay_watchlist.json`.

- **Three pages in one file.** A tab bar switches between *Tracker*, *Most mentioned* and
  *eBay prices*; each is a wrapper (`viewDashboard`, `viewMentions`, `viewPrices`) and only
  one is displayed. `#mentions` and `#prices` in the address select the second and third; any
  other fragment selects the Tracker and scrolls to the part it names, so the header's
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
- **Two lists fold away.** The Demand Index renders up to 25 rows and shows five; Most
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

`ebay_prices.py` runs after every scraper run (`.github/workflows/ebay.yml`) and is separate
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

**What is kept.** Under `data/prices/`, numbers only: `latest.json` (per game and site: copies,
lowest, median, typical postage, when checked; the game's level; the day's search count) and
`YYYY-MM.json` (a row of time, game, site, copies, lowest, median whenever the three figures
change, and at least once a day). `latest.json` is also the job's memory: when each game was
last checked and until when it is surging. Neither file is ever rebuilt from nothing; if one
cannot be read the run stops before asking eBay. Listings and links go to the `--out` file,
which the workflow publishes as a single replaced commit on the `ebay-data` branch.

**When it gives up.** A run stops early if eBay does not answer three lookups in a row, if its
first ten lookups all fail, or if eBay says the allowance is used. Nothing is written when
more than half the lookups failed, or when games that had copies last time now return nothing
at all (a broken search, not an empty market).

## Weights

| Role | Default weight | Used for |
|---|---:|---|
| `ps2` PS2-dedicated | 1.5 | r/ps2, r/ps2homebrew, r/PCSX2, r/playstation2, PS2 YouTube channels and PS2-history podcasts |
| `official` Official | 1 | PlayStation.Blog, Xbox Wire, platform and publisher channels, official PlayStation podcasts |
| `press` Press & news media | 1 | News sites, news channels and news podcasts |
| `community` Community | 1 | The other subreddits |
| `retro` Retro | 1 | Retro reviews, history, hardware and emulation |
| `collector` Collectors & resellers | 0.5 | Game hunting, flipping and restoration channels (Phoenix Resale, Chase After The Right Price, TronicsFix, …) |
| `creator` Entertainment creators | 0.5 | Big let's-play channels and comedy gaming podcasts |

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
15-minute job limit. Failing fast, skipping a host after 3 straight failures and capping extras at
10 minutes keeps every run bounded.

**Podcasts every 6 hours.** The enabled podcast feeds add up to about 100 MB per fetch, because
feeds carry every episode ever released. Shows publish daily at most, so fetching every 6 hours
loses nothing and cuts traffic about six-fold. The interval is measured from the last podcast
fetch (`data/poll_state.json`), not tied to fixed UTC hours: in this repository's history GitHub
fired only 3 of about 16 expected hourly runs, which would rarely have landed on the right hour.
The state only changes when podcasts are fetched, so it adds no hourly commits. Manual and
push-triggered runs fetch everything.

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
  *God of War*. Sequel numbers are checked, but new subtitles aren't.
- Sentiment is a keyword count in English. Non-English titles score a neutral 50.
- Subscriber, view, rating and chart numbers in `feeds.json`/`SOURCES.md` are a snapshot from the
  `checked` date. Live activity comes from `feed_status.json`.
- Reddit is read from the combined "hot" listing (unchanged). A small subreddit whose posts never
  reach the combined top 50 shows up as *Quiet* or *Stale* even if it is active.
- On 2026-09-30, VG247's feed had nothing newer than 2026-06-02. Time Extension sits behind a
  Cloudflare check that blocks some networks, though not GitHub's runners. r/Steelbook and
  r/xboxone contribute only old posts.

## Tests

`python -m unittest discover -s tests -v` runs everything offline (fixture feeds, no network):

- **feeds.json**: valid, canonical formatting, unique keys, every original news feed and
  subreddit still present, measured stats dated.
- **Validation**: 33 kinds of broken config rejected, including:
  - YouTube video links and un-normalised channel links
  - the malformed feed links from the independent review
  - odd hand edits: a list as role, a huge or `null` interval

  Channel links are accepted, the error on load is readable, and a file saved with a BOM loads.
- **Fetch plan**: the original Reddit groups produce the original multireddit URLs, disabled
  sources skipped, core feeds first, channel links wait for their ID.
- **Schedule**: podcasts wait until 6 hours (minus the slack) have passed since their last fetch,
  even across skipped runs; unreadable state means due; `FULL_RUN` fetches all.
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
  - the page and scraper validators agree on 38 configs

- **Matcher** (`test_matcher_fixtures.py`): precision and recall on 268 hand-labelled real
  headlines must not fall below their floors, and each matching rule has a named test.
- **eBay prices** (`test_ebay_prices.py`, 125 tests): a fake stands in for eBay's API and a
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
- **Scraper, added 2026-10-07**: the snapshot keeps two weeks, newest first, and past its
  ceiling it is the oldest items that go.
- **Dashboard, added 2026-10-06 and 2026-10-07**: the two ranked lists fold (five rows, 25
  rows) and open again, and Most Mentioned Games leaves no game out; the eBay prices page orders, formats and escapes its rows, narrows them with the
  search box, dims a price only when it is overdue for its level, and says what to do when
  there is no price file; the medians appear under a game's name in all three places, find
  the game under another spelling, and show nothing rather than another game's figure; a
  price file the page cannot draw leaves the rest of the page working; prices are fetched from
  the site with no token, before the lists are drawn; the three pages switch by tab and by
  address, with exactly one on screen; the item count is labelled with how far back it goes; rows name their cells for the phone layout; a phone gets 25 rows to a page.
- **Page and price script agree on names**: `priceKey()` against `search_terms()` on the whole
  library.

The *Tests* workflow runs the suite on every push to `main` that touches code, `feeds.json` or
the tests, and on every pull request.
