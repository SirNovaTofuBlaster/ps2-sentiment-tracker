# ps2-sentiment-tracker
Retro gaming sentiment tracking.

`scraper.py` reads gaming news sites, Reddit, forums, YouTube channels and podcasts (all as
RSS/Atom feeds) and 4chan's game boards (through 4chan's read-only API), every one of them
listed in [`feeds.json`](feeds.json). It fuzzy-matches every headline, thread, video and episode
title against the PS2 library, flags remaster/remake chatter and scores sentiment. From 4chan it
keeps only the names of the PS2 games a thread mentions, never anything a poster wrote. Results go to
`data/sentiment_feed.json`, with per-feed health in `data/feed_status.json`. `index.html` renders
both as a dashboard. A GitHub Actions workflow keeps the scraper running all the time
(`scrape_loop.py`), each kind of source on its own clock, and restarts it straight away when
`feeds.json` or `scraper.py` changes on `main`.

## Sources

| Type | Listed | On by default |
|---|---:|---:|
| News sites | 18 | 18 |
| Subreddits | 26 | 26 |
| Forums | 2 | 2 |
| 4chan boards | 7 | 7 |
| YouTube channels | 159 | 114 |
| Podcasts | 91 | 64 |

- [SOURCES.md](SOURCES.md): the ranked lists (subscribers, total views, Apple ratings and chart
  positions, last activity) and why each source is on or off.
- The dashboard's **Sources & Weights** panel switches sources on and off, adds new ones (paste a
  YouTube channel link, an Apple Podcasts link, a feed link, a subreddit or a 4chan board) and tunes how much
  each kind of source counts. **Save changes** commits `feeds.json` through a guided copy/paste
  into GitHub's editor, or in one click with a GitHub token.
- `guide.html` (the dashboard's **How to use** button) explains all of this step by step for
  non-technical users.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how a run works end to end, how weights are
  applied, and why it is built this way.

## What else runs

Three smaller jobs build on the scraper's snapshot. Each has its own workflow and none of them
touches `scraper.py`.

| Script | Writes | What for |
|---|---|---|
| `archive.py` | `data/archive/` | A permanent record of every PS2 game mention (the snapshot itself only holds about two weeks) |
| `demand.py` | `data/demand.json` | The dashboard's Demand Index: Wikipedia reading figures blended with mentions |
| `ebay_prices.py` | `data/prices/` | eBay asking prices (US and UK) for every library game the feed has mentioned, and for the rarest PAL and US games in `rare_games.json` (the dashboard's Rarest page) |

`ebay_prices.py` is the only part that needs a key: an eBay developer keyset, stored as the
`EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` repository secrets. Without them its workflow fails
and everything else carries on. It keeps numbers only (copies listed, lowest and median asking
price), decides how often to check each game from how it is being mentioned, and is described in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#ebay-asking-prices).

```sh
python ebay_prices.py --plan   # which games would be priced now and why; needs no key and asks nobody
```

## Run locally

```sh
pip install -r requirements.txt
FULL_RUN=1 python scraper.py  # FULL_RUN=1 fetches every enabled source instead of only those due now
python -m http.server         # then open http://localhost:8000
```

## Tests

```sh
python -m unittest discover -s tests -v
```

The tests are offline (fixture feeds, no network). The dashboard checks run too when Node.js is
installed. The *Tests* workflow runs the same suite on GitHub.
