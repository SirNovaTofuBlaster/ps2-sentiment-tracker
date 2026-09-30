# ps2-sentiment-tracker
Retro gaming sentiment tracking.

`scraper.py` reads gaming news sites, Reddit, YouTube channels and podcasts (all as RSS/Atom feeds
listed in [`feeds.json`](feeds.json)), fuzzy-matches every headline, video and episode title
against the PS2 library, flags remaster/remake chatter and scores sentiment. Results go to
`data/sentiment_feed.json`, with per-feed health in `data/feed_status.json`. `index.html` renders
both as a dashboard. A GitHub Actions workflow reruns the scraper every hour, and straight away
when `feeds.json` or `scraper.py` changes on `main`.

## Sources

| Type | Listed | On by default |
|---|---:|---:|
| News sites | 18 | 18 |
| Subreddits | 26 | 26 |
| YouTube channels | 156 | 111 |
| Podcasts | 91 | 64 |

- [SOURCES.md](SOURCES.md): the ranked lists (subscribers, total views, Apple ratings and chart
  positions, last activity) and why each source is on or off.
- The dashboard's **Sources & Weights** panel switches sources on and off, adds new ones (paste a
  YouTube channel link, an Apple Podcasts link, a feed link or a subreddit) and tunes how much
  each kind of source counts. **Save changes** commits `feeds.json` through a guided copy/paste
  into GitHub's editor, or in one click with a GitHub token.
- `guide.html` (the dashboard's **How to use** button) explains all of this step by step for
  non-technical users.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how a run works end to end, how weights are
  applied, and why it is built this way.

## Run locally

```sh
pip install -r requirements.txt
FULL_RUN=1 python scraper.py  # FULL_RUN=1 fetches every enabled source instead of only those due this hour
python -m http.server         # then open http://localhost:8000
```

## Tests

```sh
python -m unittest discover -s tests -v
```

The tests are offline (fixture feeds, no network). The dashboard checks run too when Node.js is
installed. The *Tests* workflow runs the same suite on GitHub.
