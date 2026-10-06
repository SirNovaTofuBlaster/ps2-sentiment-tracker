# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot, ...) and for developers
working on this repository. `CLAUDE.md` loads this file. Non-technical users should read
`guide.html` (the dashboard's **How to use** page) instead.

## What this project is

A PS2 sentiment and remaster tracker. `scraper.py`, run by GitHub Actions every hour, reads every
enabled source in `feeds.json`: news-site RSS, Reddit, YouTube channel feeds and podcast RSS. It
matches each headline, video title and episode title against the PS2 library, flags
remaster/remake news and scores sentiment. It writes:

- `data/sentiment_feed.json`: the snapshot
- `data/feed_status.json`: per-feed health
- `data/youtube_channels.json`: remembered IDs for YouTube channels added by link
- `data/poll_state.json`: when slower source types (e.g. podcasts) were last fetched

The static `index.html` dashboard (GitHub Pages) renders those files and edits `feeds.json`
through its **Sources & Weights** panel.

- How it works and why: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- What changed and when: [docs/CHANGELOG.md](docs/CHANGELOG.md)
- How changes were verified: [docs/VERIFICATION.md](docs/VERIFICATION.md)
- Ranked source lists: [SOURCES.md](SOURCES.md)

## Map

| Path | What it is |
|---|---|
| `feeds.json` | Every source (news / reddit / youtube / podcast), roles and weights, `poll_every_hours` |
| `scraper.py` | Config validation, fetch plan, YouTube link resolution, matching, sentiment, feed health, snapshot merge |
| `index.html` | Dashboard; its inline script mirrors `validate_config()` and `source_key()`. Also reads `data/demand.json` and `data/prices/latest.json`, and hides those sections when the files are missing |
| `guide.html` | Plain-language user guide; must match the UI |
| `data/` | Written only by workflows (the scraper's, the archive, the demand index and eBay prices, each its own files); never edit or commit it by hand |
| `tests/test_scraper.py` | Offline unittest suite; also runs `tests/dashboard_check.mjs` when Node.js exists |
| `tests/dashboard_check.mjs` | Runs the dashboard script in a Node sandbox with a stub DOM |
| `tools/regression_check.py` | Proves a scraper change leaves news/Reddit output identical to a git ref |
| `.github/workflows/scraper.yml` | Hourly scrape, plus immediately on pushes that change `feeds.json`/`scraper.py` |
| `.github/workflows/tests.yml` | The test suite on pushes and pull requests |
| `archive.py`, `.github/workflows/archive.yml` | Appends every PS2 game mention to `data/archive/YYYY-MM.json`, four times a day |
| `demand.py`, `.github/workflows/demand.yml` | Builds `data/demand.json` (the Demand Index) from Wikipedia pageviews and mentions, daily |
| `ebay_prices.py` | eBay asking prices (US and UK) for every library game the feed has mentioned, through eBay's official API; decides how often each game is checked. The only script that uses a key |
| `ebay_watchlist.json` | Games pinned for pricing (always tracked, with their own search words) and titles never to price |
| `data/prices/latest.json` | Per game and site: copies listed, lowest and median asking price, typical postage, when checked, and the game's level. Numbers only |
| `data/prices/YYYY-MM.json` | The same numbers over time: a row whenever they change, and at least one a day |
| `tests/test_ebay_prices.py` | Offline tests for `ebay_prices.py` and its workflow, including that the key never leaks |
| `.github/workflows/ebay.yml` | Runs `ebay_prices.py` after every scraper run (and by hand), commits `data/prices/`, and publishes that run's listings to the `ebay-data` branch |

## Commands

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v   # offline; includes the dashboard checks when node exists
python tools/regression_check.py          # old vs new scraper on identical real feeds (network, ~3 min)
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
   core feeds only. YouTube and podcast failures must never abort a run. After touching
   `scraper.py`, `tools/regression_check.py` must print `IDENTICAL`.
3. **Logic that exists twice stays in sync** (a test checks every pair agrees):
   - `validate_config()` (scraper.py) and `validateConfig()` (index.html)
   - `source_key()` and `sourceKey()`
   - `FEED_URL_PATTERN` and `FEED_URL_RE`
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
   checked" timestamps, or the hourly workflow commits noise.
7. **UI changes update `guide.html`** so non-technical users keep accurate instructions.
8. **No API keys or secrets in the scraper**: everything `scraper.py` reads is a public feed.
   The one script that uses a key is `ebay_prices.py`. It reads the eBay key from the
   `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` Actions secrets. The key is never committed,
   printed, written to a file or sent to the dashboard. It uses only Python's standard
   library, so the job that holds the key installs nothing: keep it that way. `ebay.yml`
   runs after the scraper workflow and by hand; it must never run on pull requests, must
   always check out `main` (never the code of the run that triggered it), and the scraper
   workflow it follows must never gain a pull-request trigger either. No other script may
   use a key without the maintainer's explicit decision.
9. **Commits use a GitHub no-reply email.** Never put personal email addresses in commits,
   messages or files.
10. **Don't push, fork or open pull requests without the maintainer's explicit OK.** Pushing
    changes under `.github/workflows/` needs a token with the `workflow` scope.
11. **QA without a browser:** unittest, `python -m py_compile scraper.py`, `node --check` on the
    inline scripts, and a curl smoke test of the static files. Use browser automation only when
    a human asks for it.

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
- [ ] Sources added: each one fetched and parsed live, with numbers measured and dated.
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
  - Scheduled workflow runs are often delayed or skipped: in this repo's history only 3 of about
    16 hourly runs fired. Never rely on fixed UTC hours; `poll_state.json` tracks elapsed time.
  - A run that waited in the concurrency queue must check out the branch head
    (`ref: ${{ github.ref }}`), or its data commit conflicts with the previous run's.
  - GitHub Pages lags a few minutes behind a commit. The dashboard reads `feeds.json` from the
    API when it differs, and checks it again before saving.
  - Four workflows commit to `main` on their own (scraper, archive, demand, eBay prices). Each
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
    every 6 hours; `dormant` (mentioned once, quiet for 14 days) daily. A run uses at most 500
    searches and stops for the day at 4,500.
  - About half of the "surging" flags in the first week were matcher mistakes (the wrong game
    matched), so treat the level as "worth a look", not as news. It gets better only as the
    matcher does.
  - The search words for a game come from its library title, and listings must contain the
    whole name. That is strict on purpose: better no figure than another game's prices. A
    title with a Roman numeral is searched both ways ("kingdom hearts ii" and "kingdom hearts
    2"). A listing that names a different library game containing this one's name ("Ultimate
    Spider-Man" for "Spider-Man") is left out; `other_games()` decides which names those are.
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
    it with the search check ticked and read the counts it prints.
  - The API returns listings that are still for sale. They are asking prices, not sold prices,
    and US (NTSC) and UK (PAL) figures are never combined.
  - eBay's default allowance is 5,000 searches a day. One lookup is one search, or two when
    no listing carries the PS2 item specific and it asks again by keyword; a failed search
    is tried up to three times. eBay returns at most 200 listings per search, and a game
    with more is marked `truncated`.
  - A production keyset stays disabled until eBay's marketplace account deletion notifications
    are subscribed to or opted out of in the developer portal.
- **Windows**
  - Set `PYTHONIOENCODING=utf-8` before printing titles.
  - `core.autocrlf=true` gives CRLF working files, so the tests normalise line endings.
  - `http.server` can bind a port another process already listens on, so check with `netstat`
    first.
