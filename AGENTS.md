# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot, ...) and for developers
working on this repository. `CLAUDE.md` loads this file. Non-technical users should read
`guide.html` (the dashboard's **How to use** page) instead.

## What this project is

A PS2 sentiment and remaster tracker. `scraper.py`, kept running by `scrape_loop.py` in GitHub Actions, reads every
enabled source in `feeds.json`: news-site RSS, Reddit, forum RSS, 4chan board catalogs, YouTube
channel feeds and podcast RSS. It matches each headline, thread, video title and episode title
against the PS2 library, flags remaster/remake news and scores sentiment. From 4chan it keeps
only which games a thread names (rule 12). It writes:

- `data/sentiment_feed.json`: the snapshot
- `data/sentiment_recent.json`: the same snapshot without the rows that name no game (and, for those, only counts per source); the dashboard opens on it and loads the full file when Everything is chosen
- `data/feed_status.json`: per-feed health
- `data/youtube_channels.json`: remembered IDs for YouTube channels added by link
- `data/poll_state.json`: when each source type was last fetched (each has its own clock)

The static `index.html` dashboard (GitHub Pages) renders those files and edits `feeds.json`
through its **Sources** panel (no sentiment or weights are shown: removed 2026-10-15; the scraper still writes `sentiment` and `feeds.json` keeps weights).

- How it works and why: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- What changed and when: [docs/CHANGELOG.md](docs/CHANGELOG.md)
- How changes were verified: [docs/VERIFICATION.md](docs/VERIFICATION.md)
- Ranked source lists: [SOURCES.md](SOURCES.md)

## Map

| Path | What it is |
|---|---|
| `feeds.json` | Every source (news / reddit / forum / 4chan / youtube / podcast), roles (and weights, no longer shown), `poll_every_hours` (0.25, 0.5 or 1–24) |
| `scrape_loop.py` | Keeps the scraper running for 5½ hours per workflow run: runs it when a type is due, commits `data/`, starts the eBay job hourly and its own successor |
| `tests/test_scrape_loop.py` | Offline tests for the loop (fake clock) and `scraper.yml` |
| `scraper.py` | Config validation, fetch plan, YouTube link resolution, matching, sentiment, reading 4chan boards for game names, feed health, snapshot merge |
| `index.html` | Dashboard, nine pages in one file (Tracker, Rarest, Demand, Most mentioned, eBay prices, Library, Marketplace, Gacha, Underrated; My collection is opened by a header button beside REFRESH, not a tab); its inline script mirrors `validate_config()`, `source_key()` and the game-name rule of `ebay_prices.py`. Also reads `data/demand.json`, `data/prices/latest.json`, `index.json` and `series.json` there, `ebay_watchlist.json` and `rare_games.json`, and works without them; draws charts with TradingView's Lightweight Charts, or a plain line without it |
| `manifest.webmanifest`, `sw.js`, `icons/` | Make the site installable on a phone. `sw.js` is network first (the saved copy is used only when the network fails, so it never shows old numbers while online), same-origin GETs only, and holds nothing of the visitor's. The My collection tab keeps the visitor's games in `localStorage` (`ps2-sentiment-tracker.collection`) and a backup file; the list goes nowhere except, for a signed-in visitor, to their own account (below); adding a game needs an anonymous account (made on My collection, or in the dialog when Add is pressed on the Library or Underrated page; `requireAccount()`, `crowd` in index.html, [docs/CROWD.md](docs/CROWD.md)), and a signed-in page sends per-game counts of sealed, complete and loose copies, and the list itself (title, region, condition, count; never a price) so another browser can load it with the key. There is no login with a name or email (no wallet: it would still need storage). Cover pictures are the visitor's own browser loading an `<img>` from thumbnails.libretro.com (Libretro's box-art collection; Wikipedia's page images were tried first and gave blank tiles); `covers.json` only maps each `priceKey()` to a file name (rebuild it with `tools/build_covers.py`, see its docstring) and nothing else is stored; `Show cover images` switches it off; the page and guide say the server learns the game name and the visitor's address. Bump `CACHE` in `sw.js` only if its logic changes |
| `guide.html` | Plain-language user guide; must match the UI |
| `data/` | Written only by workflows (the scraper's, the archive, the demand index and eBay prices, each its own files); never edit or commit it by hand |
| `tests/test_scraper.py` | Offline unittest suite; also runs `tests/dashboard_check.mjs` when Node.js exists |
| `tests/dashboard_check.mjs` | Runs the dashboard script in a Node sandbox with a stub DOM |
| `tools/regression_check.py` | Proves a scraper change leaves news/Reddit output identical to a git ref |
| `tools/try_sources.py` | Tries enabled forums, boards, channels or podcasts against the live sites and prints what the scraper would make of them; writes nothing |
| `.github/workflows/live-checks.yml` | On pull requests that touch the scraper, `feeds.json` or `tools/`: runs `try_sources.py forum 4chan` and `regression_check.py` from GitHub's servers. Holds no key and can write nothing |
| `tests/test_archive.py` | Offline tests for `archive.py`: which mentions count as the same mention |
| `.github/workflows/scraper.yml` | Runs `scrape_loop.py`; a push to `feeds.json`/`scraper.py`/`scrape_loop.py` or *Run scraper now* replaces the running loop; an hourly schedule restarts it if the chain breaks |
| `.github/workflows/tests.yml` | The test suite on pushes and pull requests |
| `archive.py`, `.github/workflows/archive.yml` | Appends every PS2 game mention to `data/archive/YYYY-MM.json`, and every digital-only story (any game, with its link) to `data/archive/digital/YYYY-MM.json`, four times a day. Reads the snapshot only: it fetches nothing |
| `demand.py`, `.github/workflows/demand.yml` | Builds `data/demand.json` (the Demand Index, v2: mentions trend, sources, YouTube `views` the scraper records, eBay week change from `latest.json`, Wikipedia pageviews) daily, and `data/wiki_checks.json` (each game's article read in full: PS2 game? calls it a collectible?). Reads `data/` only; no key |
| `fx.py`, `.github/workflows/fx.yml` | Saves `data/fx.json` (euros per US dollar, pound, zloty and franc, from the European Central Bank's public rate file) each weekday for the dashboard's EUR button. Standard library only, no key; leaves the old file when the ECB cannot be read |
| `tests/test_fx.py` | Offline tests for `fx.py` and its workflow |
| `ebay_prices.py` | eBay asking prices (US and UK) for every library game the feed has mentioned, through eBay's official API; decides how often each game is checked. The only script that uses a key |
| `ebay_watchlist.json` | Games pinned for pricing (always tracked, with their own search words), titles never to price, the names games have on eBay UK (`regional_names`), and `same_game`: names of one game the library files apart, which the dashboard lets share a site's figure |
| `search_extra_titles.json` | Names the dashboard's search box knows beyond `data/ps2_database.json` (808 names: 805 NTSC-U/PAL names from PCSX2's game list, 2026-10-14, and three .hack discs). Search only: no script reads it |
| `genres.json`, `tools/build_genres.py` | A genre per `priceKey()` for the Library page: the Libretro database's genre where it has one (about 30% of the library), else a keyword guess from the title; about two thirds of games get one, the rest are "Other". Approximate by design. Rebuilt by hand (command in the tool's docstring) |
| `covers.json`, `tools/build_covers.py` | (The Library's US/PAL exclusive buttons read the region tags of its two suffixes: `libraryExclusive()`.) Which Libretro box-art file belongs to which game (`priceKey()` -> title, NTSC-U suffix, PAL suffix), so the page can build the picture's address; the collection's pictures are not kept here. The exception is `local` (`LOCAL` in the tool): about two hundred and fifty small (240 px) pictures the maintainer supplied on 2026-10-14, 2026-10-17 and 2026-10-18 (a first batch of 88, a second of 104 and a third of 53 named after the games in the missing-covers list, plus Resident Evil: The Essentials and Yazuka) for games the collection lacks, kept in `covers/` and served from the site; they beat the collection's file. Add one only when the maintainer supplies it. `same` says which library spellings are one game (the Library page shows one tile for them, and every spelling shows the price of one that has a figure: `shareSpellingPrices()`; `NOT_SAME` in the tool lists pairs the joins must not make). Rebuilt by hand from the collection's file list (command in the tool's docstring); `tests/test_covers.py` checks it |
| `wiki_overrides.json` | Hand fixes for the Demand Index: a title's Wikipedia article, or `null` to leave it out |
| `marketplace.json`, Marketplace tab | The Marketplace page's listings (kind, title, region, price). **All 9 are invented samples (2026-10-18, `"sample": true`) and must be removed or replaced with real listings the next time the Marketplace is changed; remind the maintainer, who asked for that.** The page shows a yellow notice and a SAMPLE tag while the flag is true. Game cards use `collectionValue()` for the reference figure; consoles come from `rare_consoles.json` names. Nothing can be bought; listing titles and links from eBay must never be stored |
| `gacha.json` | The Gacha page's four machines (Survival Horror, Action, Open World, RPG), made by hand: 20 capsules each (5 common games x3, 1 uncommon x4, 1 super rare x1), tiers relative to the machine and chosen from the eBay US medians and copies listed of 2026-10-15. Every title must be a library name (a Node check). The page reads it only when the Gacha tab is opened. Coins (`daily_coins`), what is left in each machine and the prizes won are kept in the visitor's `localStorage` (`ps2-sentiment-tracker.gacha`) and sent nowhere; prizes show under My collection > My gacha prizes and are never added to My games. Free, no purchase, no random call to a server |
| `underrated.json` | The Underrated page: 100 underrated games in reveal order (`launch` 2026-10-15; position k is the pick of day launch + k and nothing is shown before its day), each with a genre, a year or null and an original one-line reason; `via` says whether a public list (`lists`) named it or it is a general-knowledge pick; `never` names famous classics that stay off. No scores or ranks. After the last day the rounds repeat in a seeded shuffle. Add a game at the end, only if it is not a classic |
| `rare_games.json` | The Rarest page: the rarest PAL and US games (100+ each), ranked by PriceCharting's complete-copy value, each with its sources, a short release `note` with its own `note_sources` links (read from public pages; not `evidence`), eBay search words and an estimate of copies sold (`copies`; how it was made is at the top). `ebay_prices.py` prices each list daily on its own site (since 2026-10-26 the 50 rarest PAL games also on the euro sites: `RARE_EURO_SITES`, mirrored in index.html) |
| `editions.json` | Known limited, collector's, premium and steelbook editions (PAL and US), each with contents, release, `require` words and a source link. `ebay_prices.py` prices each once a day on its list's site as `kind: "edition"` (`latest["editions"]`); the game page shows them. Made by hand from public pages; add an entry only with a source you read. An entry's `cover` (`covers/x.jpg`, 240 px, supplied by the maintainer, 13 on 2026-10-17) is its own box picture, shown on its tile and card; add one only when the maintainer supplies it |
| `rare_reference_prices.json`, `tools/compare_reference.py` | Dated price points for rare games read from public articles (2020-2026; numbers and short labels only), to cross-check `rare_games.json`. Mostly copies of PriceCharting; only `basis: eBay sold` / `completed sales` points are sales. Nothing reads it yet but `tests/test_reference.py` and the compare script; `python tools/compare_reference.py` prints the gaps. TheGamer is `robots`-blocked and not read |
| `rare_consoles.json` | The Rarest page's consoles: the rarest official PS2 hardware, in tiers, with model numbers, sources and eBay search rules. `ebay_prices.py` prices each daily on both sites (or its `sites`) |
| `data/prices/latest.json` | Per game and site: copies listed, lowest and median asking price, typical postage, when checked, the median of a week before (`week`), and the game's level. Numbers only |
| `data/prices/YYYY-MM.json` | The same numbers over time: a row whenever they change, and at least one a day |
| `data/prices/index.json` | The PS2 price index per site, and `PAL` (every game on every non-US site together, once two such sites have finished days) (100 on its first day), worked out from every month's history on each run that writes `latest.json`: a chained geometric mean of each game's daily change. Also `rare`: each Rarest list's index and market cap (median × the copies `rare_games.json` estimates). Days and numbers only |
| `data/prices/searches.json`, `tools/search_report.py` | eBay searches spent per UTC day (14 kept): by level and site, and by game (the dearest 400). Our own game names and counts, never a listing. Written by `ebay_prices.py` each run; the tool prints it. Added 2026-10-19 |
| `data/prices/series.json` | Each game's daily median and copies per site over the last 90 days, for its price chart; read by the dashboard only when a chart opens |
| `tests/test_ebay_prices.py` | Offline tests for `ebay_prices.py` and its workflow, including that the key never leaks |
| `worker/`, `tests/worker_check.mjs`, `tests/test_worker.py` | The opt-in crowd data service (anonymous accounts, collection counts, purchase reports, figures published only from 5+ accounts): a Cloudflare Worker with a D1 database, deployed by hand. Written 2026-10-17; the dashboard side (account gate, Account and Report a purchase tabs, game-page figures) is built. Details in [docs/CROWD.md](docs/CROWD.md) |
| `.github/workflows/ebay.yml` | Runs `ebay_prices.py` hourly (started by the scraper's loop), after a scraper run ends, and by hand; commits `data/prices/`, and publishes that run's listings to the `ebay-data` branch |

## Commands

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v   # offline; includes the dashboard checks when node exists
python tools/regression_check.py          # old vs new scraper on identical real feeds (network, ~3 min)
python tools/try_sources.py forum 4chan   # what the live forums and boards give right now; writes nothing
python -m py_compile scraper.py
FULL_RUN=1 python scraper.py              # real run; writes data/ (run it in a copy, don't commit it)
python -m http.server 8000                # dashboard at http://localhost:8000 (check the port is free first)
python ebay_prices.py --plan              # which games would be priced now and why; needs no key, asks nobody
```

## Rules

1. **Never delete existing sources.** Switch them off with `"enabled": false` and a `note`.
   The tests pin the original 18 news feeds and 26 subreddits; removing one needs the
   maintainer's explicit decision and an update of that list in the same commit.
2. **Keep news/Reddit behaviour unchanged unless that is the task.** That means the same URLs,
   subreddits combined per `group` into one multireddit request, and the 429 wait-and-retry for
   core feeds only. Forum, board, YouTube and podcast failures must never abort a run. After touching
   `scraper.py`, `tools/regression_check.py` must print `IDENTICAL`.
3. **Logic that exists twice stays in sync** (a test checks every pair agrees):
   - `validate_config()` (scraper.py) and `validateConfig()` (index.html)
   - `source_key()` and `sourceKey()`
   - `FEED_URL_PATTERN` and `FEED_URL_RE`
   - the name `search_terms()` gives a title (ebay_prices.py) and `priceKey()` (index.html)
   - `RARE_SITES` (ebay_prices.py) and `RARE_SITE` (index.html): which eBay site prices which list
   - `MARKETS` (ebay_prices.py) and `PRICE_SITES`, `PRICE_SEARCH`, `SITE_STALE_HOURS` (index.html): the sites
     the page shows, each one's search link, and a slower site's `min_every_hours` against its dim time
4. **Keep `feeds.json` canonical**: `json.dumps(config, indent=2, ensure_ascii=False) + "\n"`,
   with whole numbers written without `.0`. The dashboard's save reproduces the file byte for
   byte (tested).
5. **Verify sources before adding them, and never invent numbers.**
   - YouTube: prefer the channel ID (`UC` + 22 characters) and check that
     `https://www.youtube.com/feeds/videos.xml?channel_id=<id>` returns entries. `channel_url`
     (`https://www.youtube.com/@handle`, `/c/name` or `/user/name`) is for dashboard users and
     is resolved by the scraper.
   - Podcasts: fetch and parse the RSS URL.
   - Put measured numbers in `stats`, with the `checked` date.
6. **`feed_status.json` only holds values that change when something happens.** No "last
   checked" timestamps, or every round of the loop commits noise.
7. **UI changes update `guide.html`** so non-technical users keep accurate instructions.
8. **No API keys or secrets in the scraper**: everything `scraper.py` reads is a public feed.
   The one script that uses a key is `ebay_prices.py`. It reads the eBay key from the
   `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` Actions secrets. The key is never committed,
   printed, written to a file or sent to the dashboard. It uses only Python's standard
   library, so the job that holds the key installs nothing: keep it that way. `ebay.yml`
   runs after the scraper workflow, when the scraper's loop asks for it each hour
   (`workflow_dispatch`), and by hand; it must never run on pull requests, must
   always check out `main` (never the code of the run that triggered it), and the scraper
   workflow it follows must never gain a pull-request trigger either. No other script may
   use a key without the maintainer's explicit decision. The one decision so far (2026-10-17): the opt-in crowd service in `worker/` (Cloudflare
   Worker + D1, [docs/CROWD.md](docs/CROWD.md)) holds one secret, `SALT`, set from the maintainer's own computer with `wrangler`; it is deployed by hand, has no
   workflow and no Cloudflare token in the repository, and never touches `data/` or `main`.
9. **Commits use a GitHub no-reply email.** Never put personal email addresses in commits,
   messages or files.
10. **Don't push, fork or open pull requests without the maintainer's explicit OK.** Pushing
    changes under `.github/workflows/` needs a token with the `workflow` scope.
11. **QA without a browser:** unittest, `python -m py_compile scraper.py`, `node --check` on the
    inline scripts, and a curl smoke test of the static files. Use browser automation only when
    a human asks for it.
12. **Nothing a 4chan poster wrote is ever kept** (the maintainer's decision of 2026-10-07).
    The boards are read for the names of PS2 games and nothing else, in opening posts and in replies
    (the catalog's `last_replies` and, for flagged threads, the thread file: `read_replies()`; what is kept per
    thread is the titles, the reply count and `Last-Modified`, never a reply). No subject, comment,
    poster name, file name or anything derived from them may be written to `data/`, shown on
    the dashboard or printed in a log, except which library titles were matched and how
    (subject or comment, and by which rule of the matcher); the row's headline is written
    by the scraper. The rows are not scored for sentiment (`null`) and never count towards
    it. 4chan's API terms apply: at most one request a second, `If-Modified-Since` on each
    (the board server's own `Last-Modified` date, kept as `modified` in `feed_status.json`; thread files
    count against the same one-a-second gap),
    4chan named as the source with a link, and its name or logo never used to promote the
    site. A test checks that no poster text reaches the snapshot.
13. **Never contact anyone** (the maintainer's decision of 2026-10-14). No emails, messages,
    contact-form entries, support tickets, licence or permission requests, or API-access
    applications to eBay, PriceCharting, shops, marketplaces, site owners or anyone else, and
    no sign-ups for accounts or keys on the maintainer's behalf. Research reads public pages
    only. If outreach would help, write it up as a suggestion for the maintainer, who decides
    and sends it themselves.

## Making a change: the skeptical checklist

Before you call something done, prove it; don't assume it.

- [ ] List every behaviour of existing features your diff could change, and check each one:
  - `git diff origin/main -- scraper.py index.html` line by line
  - an AST comparison of the functions you did not mean to touch (snippet in docs/VERIFICATION.md)
- [ ] `python -m unittest discover -s tests -v`: all green, including the Node checks.
- [ ] Scraper touched: `python tools/regression_check.py` prints `IDENTICAL`. Then do a real
      `FULL_RUN=1` run in a scratch copy and read the FAILED/SKIPPED lines.
- [ ] Dashboard touched: extend `tests/dashboard_check.mjs` for the new behaviour. Keep the
      validator parity test passing and update `guide.html`.
- [ ] Sources added: each one fetched and parsed live, with numbers measured and dated. For
      a forum or board that means from GitHub's servers: open a pull request and read what
      *Live checks* reports, because a feed that answers your machine may refuse GitHub's.
- [ ] Docs match the code: README, SOURCES.md, docs/*, guide.html. Numbers in docs come from
      the files, not from memory.
- [ ] Get an independent review (a second agent or person) that must back every finding with a
      concrete failure scenario. Fix or answer each finding and record it in
      docs/VERIFICATION.md.

## Gotchas we already hit

- **YouTube**
  - In some regions channel pages redirect to a cookie-consent page (`consent.youtube.com`)
    unless the `SOCS=CAI` cookie is sent. The scraper sends it when resolving channel links.
  - YouTube pages don't allow cross-origin requests, so the browser can't resolve an `@handle`.
    That's why the scraper resolves `channel_url`.
  - Feeds hold the latest 15 uploads including Shorts, and some big channels are Shorts-only.
  - Handles often point at namesakes, so check the resolved channel's name and size.
- **Podcasts**
  - Apple's lookup API (`https://itunes.apple.com/lookup?id=<id>&entity=podcast`) allows
    browser requests; the dashboard uses it to turn Apple links into RSS feeds.
  - Feeds can be 5–15 MB because they carry every episode, which is why podcasts poll every 6
    hours.
  - Some feeds list the oldest episode first, which is why entries are sorted.
  - Many feeds have no episode page links; the audio enclosure is used instead.
- **Forums**
  - Most big forums (XenForo sites such as NeoGAF, GBAtemp and PSX-Place) sit behind
    Cloudflare and answer GitHub's runners with HTTP 403, under any User-Agent, although the
    same feed link works from a home connection. On 2026-10-07 four of six candidates failed
    that way; the two Lemmy communities answered.
  - A forum is an extra: it is read like a channel's or a show's feed, and its failure
    never stops a run.
  - Lemmy puts the article a post shares in `<link>` and the post itself in `<comments>`
    and `<guid>` (8 of the 20 posts in *Lemmy games* on 2026-10-07 were link posts). Items
    are told apart by their link, so a forum thread uses its own page (`thread_link()`);
    with the article's address it replaced the article's own row from the news feed. A
    forum row that still has another source's link is left out of the run.
- **4chan**
  - A thread's own file (all its replies) is read when its opening post names a game, and also when it says PS2 / PlayStation 2 / PCSX2 but names none (`opens_about_ps2()`, 2026-10-17: "PS2 general" threads), at most `BOARD_THREAD_READS` a board per round. A thread about nothing in particular is not read.
  - The catalog holds only the post that opens each thread. Most threads on /v/ and /vr/
    have no subject, so most names are found in the comment (`matched_in: "body"`).
  - Headline matching is too loose for posts: the first dry run counted 68 mentions of 50
    games in the live threads, many of them plainly another game or an ordinary phrase
    (Dragon Rage, Legend of Herkules, The Thing, Happy Feet). `games_in_post()` asks for
    the whole name in the library's spelling, written as a name, and not followed by
    another entry's number; that left 33 mentions of 23 games (28 of 20 in threads young
    enough to enter the feed). Don't relax it without a new dry run.
  - `tools/try_sources.py` prints, per board, the near misses by reason (`post_near_misses()`: spelt differently / runs into a number / not written as a name / inside a longer title), library names and counts only. Read that in a pull request's *Live checks* before loosening a rule, and compare mentions of the same game that are wrong (the first dry run's Dragon Rage) with those that are real.
  - Nobody working on the rules for posts could read the boards: they were judged from the
    game names and counts `try_sources.py` prints, and from made-up posts in the tests.
  - `normalise()` turns Roman numerals into digits, so the pronoun "I" reads as 1 and the
    letter "X" as 10. For headlines that has not mattered; in posts it made "can i ninja
    edit" name *I-Ninja*, which is why a lone I, V or X is not taken as a number there.
  - Threads on the slow boards stay live for months or years (the oldest on /vmg/ was from
    2023), so a thread is dated by its start and left out when that is before the 14 days.
  - A thread's row has the same headline as every other thread about that game on that
    board. Anything that tells mentions apart by headline needs the start time as well
    (`archive.py` does this).
  - Thread links die when 4chan prunes the thread; the row outlives the link.
  - Archives (probe of 2026-10-16 from GitHub's runners, asked once for /vr/ and /tg/, 6 API requests): **desuarchive.org** answers its API (HTTP 200, FoolFuuka JSON, thread numbers are 4chan's own) but its `robots.txt` says `Disallow: /_/api` and `/_/search` for everyone, and its board pages answer with a Cloudflare challenge (403). **archive.4plebs.org** answers every page and API path with a Cloudflare challenge (403). So neither is read, like RFGeneration (the one-off probe went to the disallowed API paths, which was a mistake not to repeat; it was deleted). The archives mirror 4chan's own threads under the same thread numbers: 24 of the 25 newest openers on each board were in the live catalog at that moment, so an archive would add only threads that died between two polls. A thread seen on an archive but not on the tracker is more likely a matcher miss than a missed poll (for example a series name such as `.hack` in a subject, which names no single library title).
  - The job logs cannot be downloaded through the API from every network. `try_sources.py`
    therefore also attaches its report to the run as notices (`check-runs/<job id>/annotations`).
- **Newer games with a PS2 name**
  - A PS2 title is often the first words of a newer game's name (God of War, 2026-10-15: "God of War Ragnarök" filled the feed). `NEWER_GAME_FOLLOWERS` in `scraper.py` names the words that, right after the title, make a text about the newer game; add the series there when one floods the feed (a new entry needs a test in `tests/test_matcher_fixtures.py`). Old rows are cleaned from their headline by `without_newer_games()`.
  - False matches (2026-10-26): `LOOKALIKES` (a famous game one letter from a PS2 title, such as Dragon Age / Dragon Rage), `ORDINARY_TITLES` (titles that are ordinary words need PS2 in the text itself, not just in the source; `CAPITALISED_NAMES` for Bully) and `NEWER_GAME_FOLLOWERS` stop them. Replay the feed's headlines through old and new code before adding to them (see docs/CHANGELOG.md, 2026-10-26); the maintainer's fixtures count remakes and sequels such as Persona 4 Revival as PS2 news, so do not list those.
- **Reddit**
  - Unauthenticated access allows about one request a minute; quick test loops get 429s.
  - The multireddit uses the "hot" listing, so small subreddits can look quiet.
- **Existing feeds (as of 2026-09-30)**
  - Time Extension is behind a Cloudflare check that blocks some networks but not GitHub's
    runners.
  - VG247's feed hasn't changed since 2026-06-02.
  - r/Steelbook and r/xboxone contribute only old posts.
- **GitHub**
  - Fine-grained tokens can't be used by a collaborator on another user's personal repository;
    that case needs a classic token with `public_repo`.
  - The contents API needs the file's current `sha`.
  - Web-editor commits use the account's email settings.
  - Scheduled workflow runs are often delayed or skipped: in the first week of October 2026,
    24 of about 130 hourly runs fired. That is why `scrape_loop.py` keeps one run going and
    hands over to its successor instead of relying on the schedule. Never rely on fixed UTC
    hours; `poll_state.json` tracks elapsed time.
  - A workflow's own token can start another workflow only through `workflow_dispatch` (the
    loop's successor, the hourly eBay job); its pushes start nothing. A run waiting in a
    concurrency group is replaced by a newer waiting run of the same group.
  - A run that waited in the concurrency queue must check out the branch head
    (`ref: ${{ github.ref }}`), or its data commit conflicts with the previous run's.
  - GitHub Pages lags a few minutes behind a commit. The dashboard reads `feeds.json` from the
    API when it differs, and checks it again before saving.
  - *Live checks* and *Tests* are the only workflows that run on pull requests. Neither holds
    a key or may write; keep it that way (rule 8).
  - Five workflows commit to `main` on their own (scraper, archive, demand, eBay prices, euro rates). Each
    one must `git pull --rebase` and retry before giving up, or it fails whenever another got
    there first, and each stages only the files it wrote. The fixtures workflow commits too,
    but only when started by hand.
- **Links**
  - Browsers' URL parser "repairs" links like `https:/site.com/feed` that Python rejects. The
    dashboard stores the repaired link, and both sides check it with the same pattern.
  - A link one side accepts and the other rejects would stop every scraper run.
  - Podcast episodes can share one `<link>` (the show's homepage), have none, or have a bare guid.
    Links identify items, so those episodes use their audio file.
- **eBay**
  - The data comes under eBay's API License Agreement. What is kept, by the maintainer's
    decision of 2026-10-06:
    - Listings (titles, links) are kept only for the latest run: `ebay.yml` replaces the
      `ebay-data` branch with one fresh commit every time. Never write listing titles, links
      or anything about a seller to `data/` or to `main`. (GitHub can still serve a replaced
      commit for a while to someone who knows its ID.)
    - Numbers derived from them (copies listed, lowest, median, typical postage) are kept
      permanently under `data/prices/`. A test checks nothing else gets in.
    - Prices are never printed in a workflow log: the log is public and is not ours to prune.
  - How often a game is checked (the settings are at the top of `ebay_prices.py`): `surging`
    (a game the feed rarely names, named in headlines by 2+ sources within 24 hours) on every
    run for 48 hours; `normal` and `staple` (named on 5+ of the last 14 days, never surging)
    every 12 hours (6 until 2026-10-18), except a *steady* game on one site (see below), which waits 48 hours; `collection` (a game in someone's My collection that nothing else tracks: `load_wanted()` reads the crowd service's `GET /api/wanted`, names only, no key sent; any failure adds nothing) daily on the US and UK, so a game people own has a price; `dormant` (mentioned once, quiet for 14 days) daily. A run uses at most 500
    searches and stops for the day at 4,950 (raised from 4,900 on 2026-10-26). Games held **sealed** in a collection (`sealed` in `/api/wanted`, 2026-10-20) get one extra search for new copies a day per US/UK site while the day has used under 4,050 searches (`mark_sealed()`; `new` / `new_checked` in `latest.json`).
  - Quiet sites (2026-10-15): on the euro sites only, a non-pinned, non-surging, non-Rarest game and site whose last check found no copies (or `unmatched`) is looked up every 48 hours (`QUIET_EVERY_HOURS`) and carries `steady: true`, so the dashboard's 56-hour allowance applies; the US and UK are never slowed this way. Euro clocks (2026-10-19, slowed from 72 / 48 / 24 / 24 to save searches): Spain 96 h, France 72 h, Germany and Italy 48 h (`min_every_hours`; `SITE_STALE_HOURS` in index.html is 104, 80, 54, 54 to match).
  - Rarest and Underrated (2026-10-15): the Rarest page's games are checked every 12 hours (`CHECK_EVERY_HOURS["rare"]`; consoles and editions stay daily, `RARE_SLOW_KINDS`). The Underrated page's games that the feed does not track are priced daily on the US and UK as level `underrated` (`add_underrated_games()`; a title not in the library, or with an ordinary one-word name, is left out and named in the log). A game on either page named in the feed after its last check is looked up again within the hour on the US and UK (`mark_watched()`, `WATCH_RECHECK_MINUTES`). The sort puts `underrated` and `rare` pairs last when the run's allowance is short. About 4,700 of the 4,950 searches a day by estimate, not measurement: read `searches` in `latest.json` after a day.
  - Accuracy (2026-10-15): game searches send `sort=price` (cheapest first, 200 listings, never a second page), so a `truncated` game's figures are for the cheapest 200; `SORT_BY_PRICE` drops the sort for the run if eBay answers 400 before any sorted search worked. Condition "acceptable" (6000) is left out. A listing that says it is incomplete is left out (`incomplete` in the skipped counts); `complete` in `latest.json` is the median of 3 or more listings that say they are complete. The sort was written from eBay's documentation and has not been run against the API: start *eBay asking prices* with **check_game** and read the "cheapest first: yes/NO" line before relying on it. Until a game has a week of history, `week_before()` uses its oldest row that is 3 or more days old (`CHANGE_MIN_DAYS`). The day's allowance was 94% used on 2026-10-15, so more frequent checks need savings elsewhere first.
  - Steady games (2026-10-14): a `normal` or `staple`, unpinned game on one site is looked up every 48
    hours (`STEADY_EVERY_HOURS`) while, in the last 6 days of history, it had 50+ copies at every check,
    its median stayed within 10% and its copy count within 30% of their middles, with 3+ rows spanning
    4+ days (`is_steady()`). It is worked out per game and site from the history rows, so there is no new
    level; a figure on that clock carries `steady: true` in `latest.json` and the dashboard allows it 56 hours
    before dimming it; the first check that breaks the pattern puts it back on 6
    hours. Chosen by replaying the first nine days of history: 0.4% of flagged moments saw a move
    over 10% within two days. Re-run that replay before loosening the limits.
  - About half of the "surging" flags in the first week were matcher mistakes (the wrong game
    matched), so treat the level as "worth a look", not as news. It gets better only as the
    matcher does.
  - The search words for a game come from its library title, and listings must contain the
    whole name. That is strict on purpose: better no figure than another game's prices. A
    title with a Roman numeral is searched both ways ("kingdom hearts ii" and "kingdom hearts
    2"). A listing that names a different library game containing this one's name ("Ultimate
    Spider-Man" for "Spider-Man") is left out; `other_games()` decides which names those are.
  - Some games were released in Europe under another name (Fatal Frame is Project Zero, Bully
    is Canis Canem Edit). Searched under the US name, eBay UK finds no PAL copy (Fatal Frame 2
    showed 0 copies on 2026-10-08 while eBay US had 16). `regional_names` in
    `ebay_watchlist.json` renames the start of a game's name per site; the UK search, the name
    check and the list of other games (`siblings`) all use the renamed words. Add a rule there,
    with the PAL box title, when a UK figure is missing for a game that sold in Europe.
  - A listing is checked against a game's name with every "the" removed from both (`the_less()`, 2026-10-14):
    sellers write "Prince of Persia: The Sands of Time" for the library's "Sands of Time", which used to leave
    out about 170 of 200 listings. Different library entries for one game ("FIFA 2003" / "FIFA Football 2003")
    are still counted apart; fix those with `regional_names` or a pin, not by loosening the check.
  - When eBay returns listings and none of them names the game, the game is marked
    `unmatched` in `latest.json` and gets no history row: that means "these search words do
    not find it", not "no copies for sale". Fix it by pinning the game with its own `search`.
    The listings file on the `ebay-data` branch shows what was returned and why it was left out.
  - `data/prices/` files are never rebuilt from nothing: if `latest.json` or the month's
    history cannot be read, the run stops before asking eBay. Restore the file from its git
    history rather than deleting it.
  - One-word titles are priced only if they are in `ONE_WORD_TITLES` (names nothing else
    uses, such as Kuon or Okami) or pinned. "Black", "Cars" and "Gun" would match every
    listing that uses the word.
  - Nobody has been able to test `ebay_prices.py` against the real API from a development
    machine: the request format follows eBay's documentation. When a run looks wrong, start
    it with the search check ticked and read the counts it prints. When one game shows no copies where a
    person can see some (Kuon on eBay UK, 2026-10-15), start *eBay asking prices* by hand with the game's
    title in **check_game** (`EBAY_CHECK_GAME`): it counts what eBay reports for the UK and US with the
    condition, the country, the format and the category relaxed one at a time, and attaches the counts to the
    run as a notice (`check-runs/<job id>/annotations`). Counts only; it looks up and writes nothing.
  - The Rarest page's games (`rare_games.json`) are priced once a day on their own list's site
    only. A game the feed already tracks is reused when it is searched there under the entry's
    words or its name; otherwise the entry is looked up on its own (King's Field IV is, because
    the tracked game's words do not match how PAL sellers name it). An entry whose search is one
    ordinary word is not priced at all (Obscure, Buccaneer), like such games in the feed. Its figures are
    asking prices of rare games, so "none listed" and medians of one copy are common. The list
    order is a dated research snapshot (PriceCharting complete-copy values of 2026-10-08), not
    something any job updates; RFGeneration and consolevariations.com ask robots to stay out
    and are not read.
  - The market cap's copies are estimates, not print runs: publishers almost never gave PS2
    print runs for Europe or America (research of 2026-10-13: Kuon about 12,000 US and 8,000
    PAL, from VGChartz-level figures). Most entries are reference-class guesses; change an
    entry's `copies` only with a source. Mainstream games on the lists dominate any total,
    which is why there is a `core` cap without them.
  - The charts load TradingView's Lightweight Charts from jsDelivr at a pinned version. The
    page must work without it (the Node tests have no library): keep the SVG fallback.
  - Consoles (`rare_consoles.json`) are searched differently from games: in eBay's consoles
    category (or every category for the PSX and the Bravia TV), any condition but for parts,
    from sellers anywhere, and a listing must have the entry's `require` words and one of its
    `require_any` words (the model or the colour's name). Bundles count; shells, skins, custom
    paint, mods and broken consoles never do (`CONSOLE_JUNK`). They are `kind: "console"` in
    `latest.json` and stay off the eBay prices page.
  - The Rarest page's games also get a second search for new and sealed copies on their list's site (`check_new_copies()`, `new` in `latest.json`, shown as "new from £X (n)"), because the used-condition search showed Kuon as "none listed" on eBay UK while 3 new copies were for sale (2026-10-15, found with `check_game`). It covers every Rarest entry, including a game the feed also tracks (Kuon was skipped until 2026-10-15). `check_game` prints which condition ids came back; all of Kuon's 3 UK listings were id 1000. Never mix it into `copies`, `median`, the history or the index. Copies listed from another country (27 for Kuon on eBay UK) are still left out of the used figures on purpose; since 2026-10-16, when a Rarest game has no used copy at home, one more search (`check_abroad_copies()`, `abroad` in `latest.json`, shown as "median from abroad") counts used copies from any country under the same name checks and the site's `foreign` words, so an NTSC disc on eBay UK still never counts. Never mix it into `copies`, `median`, the history or the index.
  - The API returns listings that are still for sale. They are asking prices, not sold prices,
    and US (NTSC) and UK (PAL) figures are never combined.
  - The dashboard shows a game's medians wherever its name appears, so it has to tie the
    feed's spelling to the price file's. It does that with `priceKey()`, which must give
    every title the same name as `search_terms()`; change one and change the other.
  - eBay's default allowance is 5,000 searches a day. One lookup is one search, or two when
    no listing carries the PS2 item specific and it asks again by keyword; a failed search
    is tried up to three times. eBay returns at most 200 listings per search, and a game
    with more is marked `truncated`.
  - Other eBay sites (decision of 2026-10-14: Germany, France, Italy and Spain are on; Poland was
    left off after the probe). `ebay_prices.py` only *counts* listings there, never prices them: start *eBay
    asking prices* by hand with **probe** ticked (`EBAY_PROBE`). It asks each site in
    `PROBE_MARKETS` (with Britain as the control) how many listings it reports for 20 famous
    games and 20 rare PAL ones (about 300 searches, not added to the day's count), prints counts
    and our own game names only, and attaches one notice per site to the run
    (`check-runs/<job id>/annotations`) because the job log cannot be downloaded from every
    network. It reads no state and writes no file. A site is added to `MARKETS` only after those
    counts, and the code that loops over `MARKETS` (and the dashboard's site labels) must be
    checked first: adding a market there prices every tracked game on it.
  - Germany (`EBAY_DE`), France (`EBAY_FR`), Italy (`EBAY_IT`) and Spain (`EBAY_ES`), all switched on 2026-10-14; Poland is
    left off: an `extra` site in `MARKETS`. It is priced in euros, every 48 hours since 2026-10-19 (`min_every_hours`, once 24; its
    own clock, so it cannot slow the first two), after every lookup on the US and UK, and a run is
    judged on the US and UK alone, so a failing German site cannot discard their answers. It is searched
    by keyword only (`keyword_only`: the probe counted listings by "ps2" and the category, and nobody
    could check what the Platform item specific is called in German), borrows the UK's `regional_names`
    (`names_like`), and has its own `junk` and `incomplete` words, written from knowledge of how German
    sellers list games and not yet checked against live ones: read the first run's skip counts on the
    `ebay-data` branch and fix the lists. Consoles stay off it unless they name it. To add the next site:
    a `MARKETS` entry like Germany's, one `PRICE_LOOKUPS` link and the three constants in index.html, the
    guide, and `FranceTests`-style tests; the Node check compares the two lists.
  - A production keyset stays disabled until eBay's marketplace account deletion notifications
    are subscribed to or opted out of in the developer portal.
- **Speed**
  - Build an `Intl` formatter once (`cachedFormat()`), never per price: per-price formatters cost ~380 ms of a page load
    (2026-10-14). The long lists of pages not on screen are drawn when the tab opens (`drawForView()`); a new long list on a
    hidden page should do the same. Profile with a CPU profile in headless Chromium before and after (long tasks, element count).
  - Lists show a game as name (`gameLinkHtml()`) + `compactPriceHtml()` only (US, UK, cheapest euro median). The lookup buttons stay under every name (`listPricesHtml()`); per-site
    detail, chart and eBay links belong on the game page (`gamePriceDetailHtml()`); don't put them back in a list row.
- **Euros**
  - The EUR button converts at display time with one rate (`fxData`), through `money()` and
    `moneyShort()` only. A price shown some other way will not convert: route new prices through
    those two. PriceCharting guide figures pass `convert = false` and stay in dollars.
  - Converted figures are marked `≈`. The week's change converts the amount, not the percentage.
  - `data/fx.json` holds no time of day, so a day with the same ECB rates commits nothing.
- **Windows**
  - Set `PYTHONIOENCODING=utf-8` before printing titles.
  - `core.autocrlf=true` gives CRLF working files, so the tests normalise line endings.
  - `http.server` can bind a port another process already listens on, so check with `netstat`
    first.
