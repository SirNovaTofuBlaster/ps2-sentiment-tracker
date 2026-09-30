# Changelog

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
