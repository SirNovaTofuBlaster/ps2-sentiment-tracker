# Changelog

## 2026-10-17: every spelling of a game shows its price

- Found with the "Yazuka" copy (the library has the typo beside "Yakuza"; nobody lists a game under a typo, so it had no price, and `same_game` (#121) could not help because it needed a row for both names). A check of `covers.json` `same` against `latest.json` found about 115 games, 137 spellings, in that state (Alien Homind / Hominid, Soulcalibur 2, FIFA 13, the .hack parts, ...).
- `shareFigures()` (used for `same_game` and for the library's groups) gives a name with no row a copy of the first row that has one, and a name whose site has no figure the other name's. `shareSpellingPrices()` applies it to every group in `covers.json` `same` when prices arrive and again when the covers file does. `priceOwn` keeps the figures before sharing: the Library still picks the spelling that is priced in the chosen region (`medianOf(title, label, true)`).
- `covers.json` / `tools/build_covers.py`: EyeToy: Groove and In the Groove are different games and were one group; `NOT_SAME` keeps them apart on a rebuild.

## 2026-10-17: browsers on one account stay together

- Found by the maintainer: two games added in one browser did not appear in the other. A browser only loaded the account's list when its button was pressed, and every send replaced the saved list, so a stale browser could also wipe a newer one.
- `crowdSync()` runs when the page opens and when its tab is shown again (at most every 5 minutes; the service allows 60 reads a day): it reads the account's list, merges it game by game (title, region, condition) against `ps2-sentiment-tracker.crowdbase` (the list that browser last saw on the account), then sends when the result differs. A count only this browser changed stays, one only the account changed is taken, both changed takes the larger, a removal travels; with no base (a new browser) it only adds and raises. `crowdSend()` now reads and merges first, and sends nothing when the account cannot be read. Prices stay in the browser that typed them. No Worker change.
- `tests/dashboard_check.mjs`: a two-browser simulation (add, removal, stale browser, offline, no saved list, throttle).

## 2026-10-17: "Yazuka" shares Yakuza's price

- The library (`data/ps2_database.json`) holds misspelled entries (Yazuka, Yazuka 2, Yazuka Fury) beside the real ones, and nobody lists a game under the typo, so a copy added to My games as "Yazuka" had no price. `same_game` in `ebay_watchlist.json` now ties each to its correct spelling, so the page shows the Yakuza figure. Only `Yakuza` is priced so far; Yakuza 2 and Yakuza Fury have no figure until the feed names them (or they are pinned).

## 2026-10-17: a lost closing brace in retro.css

- Merging the form restyle dropped one `}` that closed a phone-width `@media` block, so every rule after it (the whole Portfolio section, the chart height) sat inside that block and applied only on phones; on a desktop the Portfolio tiles stacked and the chart had no height. Brace added; a test now checks `retro.css` has as many `}` as `{`. `?v=` on the stylesheet link bumped to `20261017c`.

## 2026-10-17: versioned stylesheet link

- `index.html` and `guide.html` link `retro.css?v=20261017c`. The maintainer saw the new form's markup with the old stylesheet (white boxes, loose £ sign) because GitHub Pages lets browsers keep a file for 10 minutes and the two files were fetched at different times. **Change the `v=` value in both files whenever `retro.css` changes** (a test checks the link has one).

## 2026-10-17: glowing boxes for the add-game form

- The search, region, condition, quantity and "Paid each" boxes on My collection and the Library's bottom bar, and the Add button, follow the maintainer's mock: a dark box that glows on hover/focus (search teal, region gold, condition rose, quantity and price silver), a blue Add button in the REFRESH style, and a custom blue checkbox for "Show cover images". Classes `spin-field`, `spin-teal|gold|rose|silver`, `spin-select`, `spin-paid`, `spin-check` in `retro.css`; the glow colours are `--glow-*` tokens in `:root`.
- The £/$ sign in front of "Paid each" follows the region (`paintPaidSymbols()`). The Library bar is two rows: the fields and Add, then Remove / Game page and the message. No behaviour changed.

## 2026-10-17: Portfolio chart on My games

- Between the My games tabs and the My Collection card (`#portfolioSection`, `renderPortfolio()`, `portfolioModel()`): the value of the list per day, from `data/prices/series.json` (read when My games opens with a list) and `collectionValue()`, so the last point equals the summary's estimate. Today's list valued from each game's first priced day; sealed article prices and editions are constant; US and UK added in GBP (EUR with the button) at the `fx.json` rate, and no chart without the rates when two currencies are mixed.
- Tiles: value now, latest day, change over the range (1W / 1M / 3M / All), you paid. A solid yellow line at the total paid and a **Profit / loss** style (green above, red below, a Lightweight Charts baseline series); both only when some copy has a price paid. Without the library the plain SVG line is drawn.
- `drawChart()` takes `paid` and the `pnl` style; `setChart('portfolio', ...)`. Yellow is also used for the "What you paid" key (`portfolio-paid`). The TradingView credit sits under it. Preview approved by the maintainer; the real-browser look was not checked here.

## 2026-10-17: the account carries your list to another browser

- Found by the maintainer: a key used in a second browser signed in but showed no games, because only counts (no regions, no titles) were kept server-side.
- The Worker saves the account's list (title, region, condition, count; no price) in a new `lists` table and returns it on `GET /api/collection`; `cleanList()` bounds it. The table is optional: without it counts still save. Needs the one-line table in the D1 console and the new bundle pasted into Cloudflare (steps in `docs/CROWD.md`).
- Signing in with a key now asks the service for the list, which also proves the key is real (an unknown key is refused instead of signing in). The list is merged into the browser (adds missing games, raises a count, never removes, keeps prices typed here). Account tab: **Load my list from the account**. Each browser's sends replace the saved list.
- `tests/worker_check.mjs` (15) and the accounts test cover the list, the merge, an unknown key and the service being unreachable.

## 2026-10-17: more articles behind the Rarest list (Rule of Rose, Manhunt 2)

- `rare_reference_prices.json`: two new sources (Time Extension's CeX Retro Watch, 2023-11-17, and AnimeClick.it, 2024-09-11) and three Rule of Rose PAL points: CeX shop price GBP 570, and the article's average of about $600 before and about $320 after sealed copies turned up in Italy (September 2024). Reference points only; nothing ranks by them.
- `rare_games.json`: PAL Rule of Rose note gains the Italian sealed stock; PAL Manhunt 2 note gains the BBFC refusals of 2007 (with sources).
- Not added, because no PriceCharting value could be read to rank or value them: Manhunt (Australia RC 2004), Reservoir Dogs, BMX XXX, Leisure Suit Larry: Magna Cum Laude, Shellshock: Nam '67, The Getaway. They are candidates for the next research pass.

## 2026-10-17: Library: Remove, a way back to the top, a bigger x

- The Library's add bar has **Remove** (`libraryRemovePicked()`), shown whenever the collection holds the copy the bar's region and condition point at ("Remove one (you have N)" with several); it takes away one copy, un-ticks the tile at none, and refreshes My collection. The add message now says it is there.
- A round up-arrow button (`#libraryTop`, `updateLibraryTop()`, shown after 700 px of scrolling, above the add bar when that is open, `inert` while hidden, smooth scroll unless the visitor asked for less motion).
- The x on a My collection cover is 1.9 rem (was 1.5) and 2.6 rem square on a phone: the phone rule `body main button { min-height: 2.75rem }` had been making it a thin pill 1.5 rem wide.
- Not looked at on a real phone or browser.

## 2026-10-17: Library: optional price paid

- The Library's add bar has a **Paid each** box (optional, in the chosen region's currency, `libraryAddPaid`). Empty adds the game without a price, as before; a number is kept as the copy's `paid`; text that is not a price stops the add with a message. The box empties after each add. Kept on the device like the My collection form's price.

## 2026-10-17: an anonymous account is needed to add games

- **My collection** shows "Create an account to start your collection" until there is an account. Pressing **Add** on the Library or Underrated page (or the form on My collection) opens a "Create an account to add games" dialog (`requireAccount()`), and the game that was being added is added once the account is live.
- Creating the account shows the key first (Copy, Save as a text file, "I've saved my key") before the collection opens; a visitor who closes the page in between sees the key screen again.
- Having an account means the counts of sealed, complete and loose copies are sent automatically (there is no tick any more). A game list saved on the device before comes along. Signing out hides the games until the key is pasted again; the list stays on the device.
- New tabs once signed in: **Report a purchase** and **Account** (Copy my key, Send my counts now, Sign out on this device, Delete my account and data).
- Copy follows the approved preview: "Create", not "Make", and plainer sentences. Yellow is also used for the account screens' small heading, notice and message (`account-eyebrow`, `account-warn`, `account-msg`).
- `guide.html`: "Accounts and sharing"; AGENTS.md map and `docs/CROWD.md` say the same. `tests/dashboard_check.mjs`: the page checks run signed in; one test covers the gate, the dialog, the key screen, sign in, sign out and delete.

## 2026-10-17: Share data (opt-in crowd data) on the dashboard

- My collection has a third tab, **Share data**: an anonymous account (random id and key, shown for copying; no email), a tick to send per-game counts of sealed, complete and loose copies, a **Report a purchase** form, sign out, and delete my account and data. Nothing is sent until an account exists and sharing is ticked (`crowdCounts()` sends counts only; one send after a burst of changes).
- A game's page shows what collectors say they paid and how many share it, from `GET /api/stats` (the service publishes only from 5+ accounts); empty when there are none. Opening a game page or the tab asks the service for that file once per page load.
- `guide.html` has a Share data section and its "where it is kept" line says the list stays here unless sharing is turned on; AGENTS.md's map says the same.
- `tests/dashboard_check.mjs`: a test with a fake service (no account means no network, counts only, header, report body, figures, delete).

## 2026-10-17: crowd data service (backend only)

- `worker/`: a Cloudflare Worker and D1 schema for opt-in, anonymous crowd data: random accounts (only the key's hash kept), collection counts per game (sealed, complete, loose) and purchase reports. Figures are published only from 5+ accounts, and a price far from the middle is held back, not deleted. See `docs/CROWD.md`.
- `tests/worker_check.mjs` (run by `tests/test_worker.py`): 13 offline checks of the rules.
- Nothing on the dashboard changed and nothing is sent from the page yet. Deploying is the maintainer's step (steps in `docs/CROWD.md`).

## 2026-10-17: Underrated buttons on every card, and a Back that returns to the page you came from

- Every card in the Underrated grid has Open game page, Add to collection and Find reviews (`underratedButtons()`), not only the game of the day.
- A game's page remembers the tab it was opened from (`gameBackTo`, `BACK_LABELS`, `goBack()`): from Underrated the button reads "Back to Underrated"; from any other tab it names that tab; from the search box or a reloaded address it is still "Back to Highlights".

## 2026-10-17: 4chan rows no longer repeat the game name

- The table row's headline cell is empty for a 4chan row (`rowHeadline()` gives `''`, the cell carries `data-empty` and is hidden on a phone) because the Game column already names the games; a game page's list leaves the line out too. Display only.

## 2026-10-16: boxed game names, yellow sources, plain 4chan rows

- A game's name sits in a blue box wherever it is a link (`.game-link`, and the 24-hour list's `.recent-game`).
- A source's name (subreddit, YouTube channel, site; table, game page and the 24-hour list's sources line) is the palette yellow, `--money` (`.src-name`).
- A 4chan row shows only the game name(s), not "Thread on /v/ naming ..." (`rowHeadline()`, display only: the scraper still writes that headline, so archive keys are unchanged).

## 2026-10-16: "Show fewer" no longer shows on Highlights

- `body .brand-btn { display: inline-flex }` beat Tailwind's `.hidden`, so a fold button the script had hidden (Highlights shows cards, not the list) stayed on screen, as "Show fewer" when the list had been left open. `body .list-toggle.hidden { display: none; }` fixes it for every list's button; a Node check reads the rule and the state.

## 2026-10-16: phone polish for the new rows

- At 640 px and below the three order buttons share one full row (they used to run off the edge), the "Named in the last 24 hours" box has less padding, the Shops pill is 2.25 rem tall, the opened shop buttons wrap inside their panel instead of swiping out of it, Highlights cards are tighter, and cards no longer lift on touch screens. Written from the stylesheet; not looked at on a real phone.

## 2026-10-16: Highlights moved into "Named in the last 24 hours"

- Highlights is no longer a tab. It is the third button beside Most expensive and Most rare in the 24-hour window (`setRecentSort('highlights')`; the window opens on it) and shows its cards in `#highlightsGrid` in place of the list. The Tracker is the front page again; `#highlights` still opens the Tracker on that button.

## 2026-10-16: Highlights, folded shops, bigger names, more YouTube channels

- New first tab **Highlights** (`pickHighlights()`): 12 games a day, 3 named in the news, 3 rare, 2 staples, 2 underrated, 2 movers, alternating by kind and seeded by the UTC day; missing kinds are filled by the others. The Tracker is no longer home.
- Shop buttons fold under a **Shops** button on each row (grid 0fr to 1fr, `inert` while shut, no motion with `prefers-reduced-motion`); game pages show them open.
- The "in the text only" tag, the footer line and the paragraph under "Named in the last 24 hours" are gone (the paragraph stays for screen readers). Smaller chips; game names in Newsreader, larger.
- Charts: sized explicitly and refitted when the box gets its size (the first open used to draw nothing); a game's latest.json figure is appended, so a game has a chart from its first price. Not tested in a real browser.
- feeds.json: 13 YouTube channels from the maintainer's list (retro reviews and history). Their IDs resolve at the scraper's first run; check `feed_status.json`.

## 2026-10-16: 4chan archives looked at, not added

- desuarchive.org's `robots.txt` disallows its API and search, and 4plebs answers GitHub's runners with a Cloudflare challenge, so neither is read. Details in AGENTS.md under *4chan*. No code changed.

## 2026-10-16: new tagline

- The line under the name reads "Price Guides, Collection Trackers & Tools for Collectors" (it was "PS2 news, mentions and prices"), set in Plus Jakarta Sans in normal case instead of small spaced capitals. The search box says "Search any PS2 game" with no example.

## 2026-10-16: colour-coded buttons

- Header buttons each take a colour of the logo (How it works red, Sources teal, REFRESH blue, My collection gold, EUR blue) and the labels use Plus Jakarta Sans.
- The shop buttons under every game take their shop's look: Price Charting teal with a chart mark, eBay as its four-colour name with the country in a badge and a four-colour edge, CeX red (`price-link--pc|ebay|cex`, chosen in `priceLookupHtml()` from the lookup's `id`). The "scarce" tag is a red pill with a dot.
- The new colours are tokens (`--k-*`) at the top of `retro.css`. Yellow is no longer the colour of the search buttons; the guide says "shop buttons". Design by the maintainer and a friend; not checked on a phone.

## 2026-10-16: the hidden Gacha tab really is hidden

- The first change added `hidden` to the Gacha and My gacha prizes tab buttons, but `body .view-tab { display: inline-flex }` in `retro.css` overrode it, so both stayed visible. `body .view-tab.hidden { display: none; }` fixes it; a Node check reads the rule.

## 2026-10-16: the EUR button moves next to My collection

- The `€ EUR` button now sits in the header beside **My collection** (it was in its own row under the page tabs). It still appears only when `data/fx.json` could be read. The line saying which rate is used is now the button's hover text and a screen-reader note instead of visible text. Not checked in a browser; look at it on a phone.

## 2026-10-16: charts open on the last week

- The Rarest charts and a game's price chart now open on **1W** instead of All (`rareChart.range` and `gameChart.range` in `index.html`). The other ranges are one tap away.

## 2026-10-16: Gacha page hidden for now

- The Gacha tab, the My gacha prizes tab and the `#gacha` address are switched off (`GACHA_SHOWN = false` in `index.html`; `#gacha` opens the Tracker). Nothing is deleted: `gacha.json`, the page code and the visitor's saved coins and prizes in `localStorage` stay. To bring it back, set the constant to `true` and take `hidden` off the two tab buttons.

## 2026-10-16: Rarest games get a short release note

- 103 Rarest entries (of 143 that had none) gained a one-sentence `note` in `rare_games.json`: release dates and order by region, a region that never got the game, or a limited run, each read from a public page (mostly Wikipedia) and stated only as that page states it. The page is kept in a new `note_sources` list and shown as **Release facts** links after the entry's price sources. `note_sources` is separate from `evidence`, which the `one_source` flag counts. 40 entries stay without a note because no readable page backed one. `tests/test_rare_notes.py` and a dashboard check cover it.

## 2026-10-16: Library: US exclusives and PAL exclusives

- Two buttons beside the sort buttons (and **All regions**) show only games with a box in one region. It is worked out in the page from `covers.json` (the Libretro box-art collection's file list): an NTSC-U/Canada box and no Europe/UK/Australia/World box is a US exclusive, the reverse a PAL exclusive. It is a guide: a game released in both regions looks exclusive when the collection lacks one box, and Japan-only games are in neither. Against the library on 2026-10-16: 435 US, 706 PAL, 1,341 in both or Japan-only, 192 with no cover entry. `covers.json` is fetched when a region is chosen even if pictures are switched off (the file only names files; no picture is requested).

## 2026-10-16: Rarest games with no copy at home show a median from abroad

- Kuon on eBay UK had no used copy located in the UK (3 new ones, 27 used ones from other countries on 2026-10-15), so its UK figure read "none listed". When a Rarest game has none at home, `ebay_prices.py` now makes one more search without the seller-location filter and keeps the median and lowest of the used copies it names (`abroad`), shown as "median from abroad · n copies listed in other countries". American discs on eBay UK are still left out. It never touches the UK median, the history or the index, and it costs one search per Rarest game with an empty site per check.

## 2026-10-15: gems are priced, Rarest every 12 hours, mentions bring a recheck forward

- The Underrated page's games that the feed does not track (59 of 100 on 2026-10-15; 9 more are left out: Mega Man X8 and Bujingai are not in the library, and Oni, Obscure, Summoner, Extermination, Primal, Fahrenheit and The Thing are ordinary words) are priced once a day on eBay US and UK as level `underrated`, so a gem has a figure the day it is shown. The Rarest page's games are checked every 12 hours instead of 24 (consoles and editions stay daily). A game on either page that the feed names after its last check is looked up again within the hour on the US and UK. Estimated from the plan (186 lookups due on the first run): about 4,700 of the 4,900 searches a day; the first day's `searches` figure in `latest.json` is the measurement.

## 2026-10-15: cheapest listings first, complete copies only, euro sites asked less often

- eBay searches for games now ask for `sort=price`, so the 200 listings a search can return are the 200 cheapest (a game with more than that is marked `+` and its hover says so). If eBay refuses the sort the run asks again without it. The check run (`check_game`) prints "cheapest first: yes/NO" and the field names of a listing, no prices.
- "Acceptable" condition is no longer asked for (the web links match). Listings that say disc only, loose, no manual, no case and so on are now left out of the copies, lowest and median (they show in the skipped counts as `incomplete`); the "complete" figure is the median of three or more listings that say CIB, complete, with manual or boxed. Existing history is not rewritten, so some medians step on the next check.
- Euro sites: Spain every 72 hours, France 48, Germany and Italy 24, and an empty pair on those sites 48. The first version of this change also slowed empty US and UK pairs; that was taken out. Rarest and US/UK clocks are unchanged.

## 2026-10-15: price movements appear after three days, and empty sites are asked less often

- Today's allowance was 4,612 of 4,900 searches by 23:00, so asking more often was not an option. Two changes instead, using no extra searches: (1) `week_before()` falls back, when a game has no row from 7-9 days back, to its oldest row that is at least `CHANGE_MIN_DAYS` (3) old, so the 307 figures with less than a week of history show a change now; the hover says "3 days before" and so on, the bracket is unchanged. (2) A game and site that had no copies, or whose words found none, at the last check (476 of them in `latest.json`: 18+34 US, 28+40 UK, 46+30 DE, 68+17 FR, 63+13 IT, 95+24 ES) is asked every `QUIET_EVERY_HOURS` (48) instead of every 24, on the euro sites only (see the entry above: the US and UK are not slowed), and marked `steady` so the dashboard allows it 56 hours. Pinned, surging and Rarest entries are not slowed.

## 2026-10-15: texts about a newer game with a PS2 game's name no longer count

- "God of War Ragnarök saves should work..." was filed under the PS2 *God of War*, because the PS2 title is the start of the newer one's name. `NEWER_GAME_FOLLOWERS` in `scraper.py` lists, per PS2 title, the words that mean a newer game when they come right after the name (for God of War: Ragnarök, 2018, Laufey, the last from a live Lemmy headline about the next game's collector box). A text is not about the PS2 game when every place its name stands alone is followed by one of them; "God of War II" and a place where the PS2 title stands alone still count. Rows already in the snapshot are cleaned on the next run that writes it (`without_newer_games()`, headline only; 4chan rows are never reread). The next God of War's name is not known yet: add it to the list when it is.

## 2026-10-15: Underrated shows developer, attention and a reviews link

- Each game has a `developer` in `underrated.json` (95 of 100, written from general knowledge, null where unsure). The game of the day shows an Attention bar built from the feed's own counts (items naming the game in the last 14 days, and its rank among games named), and a "Find reviews" link (Metacritic search). Review scores (Metacritic, Eurogamer, magazines) and the praise-versus-attention bar of the first preview are not shown: they were placeholders and no score has been checked against a source yet.

## 2026-10-15: Underrated grows to 100 games, one revealed a day

- `underrated.json` now holds 100 games in reveal order (40 from the three public lists, 60 added from general knowledge, marked `via`), with `launch: 2026-10-15`. The game at position k is the pick of day launch + k, so Rygar is today's, and a game is not shown before its day. The grid shows only games revealed so far; "Last 7 days" counts only days since launch. After the hundredth day the rounds repeat in a seeded shuffle.

## 2026-10-15: Underrated tab

- New page after Gacha: one underrated PS2 game a day, from `underrated.json` (40 games, made by hand). The titles were collected from three public lists (Den of Geek, TheGamer, Super Phillip Central); the reason lines are original and no rank or score is kept, because none was verified. Metacritic and Wikipedia could not be read from the build environment, so they are not used.
- The pick is random but set by the UTC date, so everyone sees the same game; each round is a seeded shuffle, so no game repeats until all have shown. The page also lists the last 7 picks and all games, with genre and "under £15" (UK median) filters, live prices, add to collection, `#underrated` link. Famous classics (see `never` in the file) are excluded.
- Tests: file shape, every title in the library, the never list, the no-repeat round, and the page.

## 2026-10-15: steady figures are marked on every run

- 195 US and UK figures (121 US, 74 UK, normal and staple games) looked overdue on the page, 32 hours old against an 8-hour limit. None was late: all 195 are games on the 48-hour *steady* clock, which `due_lookups()` leaves alone. The page could not tell, because `steady: true` was written only when a figure was looked up, and these were written before the rule began (2026-10-14) and not looked up since. `update_records()` now brings the mark up to date on every run for a figure it did not look up this run (adds it when the game is steady on that site, drops it when it no longer is). Checked against the live files: every overdue-looking figure is a steady one. The hourly job's 500-search cap was not the cause (the lookups left over each run are the daily euro sites, after US and UK).

## 2026-10-15: no grey prices beside names

- A price beside a game's name in the lists was dimmed to half strength when its check was overdue (over 8 hours for a staple), which read as a broken or different price next to a full-strength euro figure. Those figures now keep their colour; their hover line says `Last checked 9h ago: later than usual.` The detail on a game's own page and the eBay prices page still dims an overdue figure and prints its age beside it. The overdue figures came from the hourly job's 500-search cap: when more than 500 lookups are due, the rest wait for the next run.

## 2026-10-15: one game, two names, one set of prices

- King's Field IV (the European name) showed no US price on the shelf: in the US the game is King's Field: The Ancient City, which has its own entry and its own US figure ($119.99, 15 copies on eBay US), while the European name's US search finds none. `ebay_watchlist.json` has a new `same_game` list (names of one game the library files apart), and `setPrices()` lets a name take another's figure for any site where its own has none, so both names read the same. Nothing is searched differently and each name keeps its own row and history. Listed: King's Field (three names), Project Zero / Fatal Frame (1, 2 and 3), Kaido Racer / Tokyo Xtreme Racer: Drift (1 and 2), Mr. Moskeeto / Mister Mosquito, Persona 4 / Shin Megami Tensei: Persona 4. Names in the list are never labelled region-only. Add a group when a game shows a price under one name and none under the other.

## 2026-10-15: shelf prices line up

- On the Tracker's shelf a one-line game name left its price rows higher than a neighbour's two-line name. The name now always reserves two lines (`min-height: 2.4em` on `.shelf-name`), so the US, UK and EU rows start at the same height in every box, on a desktop and a phone (checked in headless Chromium: every row at the same top).

## 2026-10-15: times on the 24-hour clock

- "Last sync" and every other time the page shows (feed rows, the Demand Index's date) now use the 24-hour clock, `13:46` instead of `01:46 pm` (`hourCycle: 'h23'` in `formatLocalTime()`, so midnight is `00:05`, never `24:05`). The time zone was already the visitor's own, because no zone is forced: the same sync reads `21:46 GMT+9` in Japan and `08:46 EDT` in New York, and the long form names the offset. The check pins both.

## 2026-10-15: "n/a" for a region a game never came out in

- Gregory Horror Show is a PAL release, so its US price will always be a dash. On the shelf the slot now says **n/a** (with a hover line saying why) where the game has box art from the PAL regions (Europe, UK, Australia, World) and none from the USA or Canada (US slot), or the other way round (UK and EU slots), read from the file names in `covers.json` (`regionOnly()`). Games with another name on another site (`regional_names`) or folded into one tile (`same`) are never called exclusive, because their other region's file sits under the other name. It is a label only: prices, history and lookups are unchanged. By the file list that is about 845 PAL-only and 480 US-only titles; it is as good as that list, so a release it lacks reads as exclusive.

## 2026-10-15: a game's other name shows its prices

- Ratchet: Gladiator on the shelf had dashes everywhere. It is the PAL name of Ratchet: Deadlocked, and `ebay_prices.py` prices such a game once, under the name the feed knows it by, searching eBay UK and the euro sites for the other name (`regional_names`) and skipping the second library entry there. So the other entry had no UK or euro figures at all, and its own US search (the PAL name on eBay US) found 0. The page now points the other name at the game's row (`setPrices()`, for every rename in `ebay_watchlist.json`: Project Zero, Dark Chronicle, Ratchet & Clank 2 and 3, Lucifer's Call, the Ace Combat names...), so both names show the same figures. The other dashes on that shelf were checked in the last run's listings and are real: Winning Eleven: PES 2007 has no US copy (the 9 US listings are Japanese discs, other games or cover art), Romancing SaGa has no UK copy, Gregory Horror Show no US one.

## 2026-10-15: app icon fills the circle

- On Android the installed icon sat as a dark square inside a white circle: the manifest only offered icons for "any" use, so the phone padded them. It now also lists `icon-maskable-192.png` and `icon-maskable-512.png` (`purpose: maskable`): the ring mark on full-bleed black, kept inside the central 74% (the safe zone is 80%) so any round or rounded mask leaves only the rings on black. The icons' background is pure black (`#000000`) and the manifest's `background_color` matches. Remove and add the app again to see it.

## 2026-10-15: Library duplicates, phone tab row

- The Library showed some games twice with the same picture (AMF Xtreme Bowling and AMF Xtreme Bowling 2006). The collection's files for the pair are byte-for-byte equal (same git blob). Every tile pair whose files are equal was listed from the collection's file tree and read by eye: 99 more spellings (regional, translated or longer names of one game: LMA Manager / BDFL Manager, Winning Eleven 8 / Pro Evolution Soccer 4, Tenchu 4 / Fatal Shadows, the Star Wars Episode III titles...) are now folded into one tile through `SAME_GAME` in `tools/build_covers.py` (`covers.json` rebuilt; its `covers` and `local` are unchanged). The shown name stays the library file's, closest to the collection's title. Different games that share a file by the collection's mistake (Zombie Hunters and 2, FIFA 2002 and FIFA World Cup 2002, the Club Football teams, the regional SingStar and Buzz editions) are left alone: nothing here shows which of them has the right picture.
- Phone: the seven page tabs overlapped (equal widths, no room). The row is now one line that slides sideways, each tab as wide as its words; the open tab scrolls into view. Shorter rows (My collection, the Gacha machines) still share the width.
- The installed-app icons (`icons/icon-180/192/512.png`: home screen, app list, splash) are now the Spindle mark from the page's banner (red, yellow and blue rings with the teal arc) on the dark background, replacing the blue disc. Phones may keep the old icon until the app is removed and added again.
- The dashboard check for "most rare first" used a fixed date and failed a day later; it now uses the clock.
- The rare-games shelf's dashes were checked against `latest.json`: Wheel of Fortune UK and Hardware Online Arena US have 0 copies listed on eBay (US-only and PAL-only releases); Kuon UK waits for its next check with the new-copies search.

## 2026-10-15: the new-copies search also covers tracked Rarest games

- Kuon on eBay UK still showed no new figure after the new-copies search shipped. The search check showed why it should have: all 3 UK listings are condition New (id 1000) and name the game. The cause was in `add_rare_games()`: the second look was only switched on for Rarest games looked up on their own, and Kuon is also a game the feed tracks, so its used lookup was reused and the second look skipped. It is now switched on for every Rarest entry, on its list's site only. Costs one extra search per tracked Rarest game per check on that site. The *check_game* notice also prints, for the new-only and any-condition searches, the condition ids that came back and how many name the game (counts and eBay's own ids only).

## 2026-10-15: the Gacha console

- The Gacha machine is now an animated console (button **Insert coin**): it powers on, the disc tray slides out with a disc in the prize's rarity colour, a ring pulses, and the prize card appears; the tray stays out until the next coin. One lit square per capsule left. Covers are much smaller (30px thumbnails in the contents, a 62px prize card, 88px tiles under My gacha prizes), and the odds have a bar. Switched off under `prefers-reduced-motion`. Checks cover the sequence, the squares and the classes.

## 2026-10-15: the Gacha

- New **Gacha** tab (`#gacha`): four capsule machines (Survival Horror, Action, Open World, RPG) from `gacha.json`, 20 capsules each (5 common games x3, 1 uncommon x4, 1 super rare x1). Three free coins a day; a turn takes a random capsule from what is left, with the live odds shown, and the machine refills when empty. Each game shows its eBay US median.
- Prizes are kept in the browser (`localStorage`) and listed under a new **My gacha prizes** tab inside My collection, apart from My games and its value. Nothing is sent anywhere. Guide, AGENTS.md and ARCHITECTURE updated; a Node check covers the file, the draw, coins, restocking, saved-state cleaning and the two tabs.

## 2026-10-15: PriceCharting links on the Rarest page

- Every Rarest game row now has a **PriceCharting** link under its prices (`rarePriceChartingHtml()`): a search on PriceCharting's PAL page for the PAL list and its US page for the US list, so a game with no eBay figure can be checked by hand. It reuses the `pc-pal` / `pc-ntsc` lookups. The new/sealed search already covers every game on the lists; the seller-country and category filters were not relaxed, because that would put non-UK copies into the UK figures.

## 2026-10-15: new and sealed copies on the Rarest page

- Kuon showed "none listed" on eBay UK while a person could see copies at about £800. The search check (`check_game`) found 0 listings with the used-condition filter, 3 with any condition and 27 with the seller-country filter lifted: the
  UK copies are new or sealed ones, which the main search leaves out on purpose. A game on a Rarest list now also gets a second search for new copies (`check_new_copies()`), counted apart (`new` in `latest.json`) and shown as
  "none listed · new from £800 (3)" or after the used figures. It never enters the medians, history, price index or market cap. Copies listed from other countries stay out of the UK figure.

## 2026-10-15: a search check for one game

- *eBay asking prices* has a new box, **check_game**. Kuon showed no UK listings while a person could see copies at about £800 on eBay UK; the box counts what eBay reports for one game with each part of the search
  (condition, seller country, Buy It Now only, category) relaxed in turn, for the UK and US, as a notice on the run. Counts only; nothing is looked up or saved. Lookups are unchanged.

## 2026-10-15: no sentiment on the dashboard

- Removed the **Net sentiment** tile (three tiles are left), the table's **Sentiment** column and its phone-card row, the `×0.5` weight badges, and the weight inputs in the Sources panel (the role weights table and each
  source's Weight box). The Weights & schedule tab is now **Schedule**; the guide's Weights section is now "Roles and schedule", and the page's name drops "Sentiment".
- Not changed: `scraper.py` still scores and writes `sentiment`, `feeds.json` keeps its weights and the validators still check them, so nothing in `data/` or the validator parity changes. Stripping the scores from the
  scraper and the data is a separate step.

## 2026-10-15: r/PlaystationCollectors

- Added r/PlaystationCollectors to the "Collecting, Retro & Emulation" Reddit group (role `community`), by the maintainer's request. It joins that group's combined multireddit request; not fetched from the sandbox (Reddit is blocked there), so Live checks/the next run show whether it contributes.

## 2026-10-14: 4chan replies are read for game names

- The catalog's `last_replies` now count: a thread that only a reply names enters the feed (`matched_in: "body"`), and a thread that names a game also lists the games its replies name.
- A thread that names a game and has replies the catalog did not show has its file read (`fetch_thread()`, `read_replies()`): busiest first, 12 per board per run, 120 s, one request a second with `If-Modified-Since`,
  and not again until its reply count changes. `feed_status.json` keeps, per such thread, only the titles, reply count and `Last-Modified`. Only PS2 library titles are kept; rule 12 is unchanged in what is stored.

## 2026-10-14: the Library folds regional names, again

- `build_covers.py` finds more of the library's spellings of one game: "FIFA Soccer 07" / "FIFA Football 07" / "FIFA 07", "PES 2008: Pro Evolution Soccer" / "Pro Evolution Soccer 2008", the translated names of FIFA World Cup 2002,
  words run together ("Soul Calibur" / "Soulcalibur"), and 60 pairs read by eye (`SAME_GAME`). 632 spellings are now folded into 3,246 tiles; all 3,878 library names remain (a name is folded onto a tile, never removed:
  search, prices and the collection still use every spelling). `KEEP_APART` lists spellings that look alike and are not (Dark Angel: Vampire Apocalypse / James Cameron's Dark Angel, EyeToy: Play / Play Sports).
- A spelling with no picture takes its game's (`share_covers()`): 283 tiles are left without one, all games the Libretro collection has no box for.

## 2026-10-14: one tile per game in the Library, more covers, the rest of the .hack games

- The Library showed a game once for every spelling the library has (".hack Infection Part 1" and "Hack: Part 1: Infection", "Club Football 2005: Arsenal" and "Arsenal FC: Club Football 2005", "Alien Homind", ...).
  `tools/build_covers.py` now writes `same` into `covers.json`: 533 spellings folded into the 3,342 games left on the page. Two spellings are one game when `loose_key()` (publisher prefixes, "volume"/"vol", word order,
  articles ignored; numbers kept) is equal, or when they share one Libretro file and the same numbers. The shown spelling is the library file's, never a misspelling (a word nothing else uses). Region is chosen
  when adding (PAL / US in the bar; the picture follows), and the copy is filed under the spelling eBay prices on that region's site.
- Covers: about 120 more hand-checked name pairs in `MANUAL`, aliases may now point at other aliases (three passes), and `loose_key()` finds the rest: 701 games without a picture became 326 (a third of those are SingStar
  discs, club-football discs, magazines and preview discs the Libretro collection does not have).
- `.hack//Fragment`, `.hack//G.U. Terminal Disc` and `.hack//G.U. Vol.1 Rebirth Terminal Disc` added to `search_extra_titles.json` (808 names); the seven main parts were already in the library.
- `genres.json` rebuilt: a genre for 4,425 keys.

## 2026-10-14: the Library tab

- New tab, **Library**: every game in the library (`data/ps2_database.json` plus `search_extra_titles.json`, one box per `priceKey()`) as cover art, A to Z with letter jump buttons or grouped by genre, with a
  name filter, a genre menu and "only games with a cover". Pressing a box opens a bar at the foot of the page (region, condition, Add to My collection, Game page). Owned games carry a tick. `#library` opens it.
- `genres.json` (made by `tools/build_genres.py`) gives each game a genre: the Libretro database's own genre where present, else a keyword guess. Approximate; the rest is "Other".

## 2026-10-14: prices under every shelf box

- Each box on the shelf shows three eBay medians: US ($), UK (£) and EU (€), a dash where nothing is priced (`shelfQuotesHtml()`). The euro figure is the cheapest euro site's median; with none, the UK
  (else US) median converted at the ECB rate and marked ≈. The whole box (cover, name, prices) is one link to the game's page.

## 2026-10-14: the shelf is rarest first

- The shelf (now "Rare finds named in the last 24 hours") orders its games with `byRarity()`, the same order as the list's "Most rare" button: the fewest copies for sale first, then
  up to 30, up to 100, more; collectible games first within a group; games not yet checked on eBay last. Everyday games (God of War, Resident Evil 4) move to the far end.

## 2026-10-14: pictures the maintainer supplied

- Eight games with no file in the Libretro collection now have a small (240 px wide, 12-30 KB) picture kept in `covers/`, listed under `local` in `covers.json` (`LOCAL` in `tools/build_covers.py`):
  Final Fantasy X, Pro Evolution Soccer 2014, World Quiz, SingStar Deutsch Rock-Pop, Harry Potter Collection, Grand Theft Auto Complete Collection, Grand Theft Auto: The Trilogy and
  The Silent Hill Collection. `coverUrl()` prefers them to the collection's file for every region, and their tile says "cover kept with this site". Served from the site itself, so the
  privacy note about the collection's server does not apply to them.

## 2026-10-14: more covers

- 21 more names share a cover the collection files under another title (`MANUAL` in `tools/build_covers.py`): Midnight Club (Street Racing), the Godfather editions, Cars, Cowboy Bebop
  (Tsuioku no Serenade), SOCOM (U.S. Navy SEALs), The Hustle, UEFA Champions League (2006-2007), WALL-E, Winning Eleven 6, Ultimate Spider-Man Limited Edition, Kirikou, the four
  .hack parts as PriceCharting spells them, Hanuman, GigaWing Generations and ATV Off-Road (Fury). `add_aliases()` now also reads the Rarest page's titles (`rare_games.json`).
- No file exists in the collection for: The Silent Hill Collection, Grand Theft Auto: The Trilogy and Complete Collection, Harry Potter Collection, Deutsch Rock-Pop, World Quiz, Pro Evolution Soccer 2014.

## 2026-10-14: covers for games the library names differently

- 15 library names the Libretro collection files under a longer or publisher's title now share that game's cover (`MANUAL` in `tools/build_covers.py`): Metal Gear
  Solid 2 (Sons of Liberty), Splinter Cell, Tomb Raider: Anniversary, Cars Race-O-Rama and Mater-National, Spyro: The Eternal Night, the two James Bond 007 games, King's Field IV,
  Over the Hedge, Donald Duck Goin' Quackers, EyeToy, Pimp My Ride, Dead or Alive 2: Hardcore, Arena Football. `covers.json` gained exactly those 15 keys.
- Shin Megami Tensei: Devil Summoner (the Raidou Kuzunoha vs. the Soulless Army box) and Devil Summoner 2 (King Abaddon) were added the same way.
- LifeLine: Voice Action Adventure uses the collection's "Life Line (USA)".
- The Silent Hill Collection (the PS2 box set of 2, 3 and 4) has no file in the collection, so it keeps its initials tile.

## 2026-10-14: Demand tab, a longer shelf

- The Demand Index has its own **Demand** tab (`#demand`) instead of sharing the Tracker's second column, which made the Tracker wrap awkwardly: each row is a rank,
  a cover, the name and score, a bar and the facts on their own wrapped line (they were one unbroken line that ran off the card). Ten rows show, 25 in all.
- The shelf holds up to 24 games and moves sideways with arrows at both ends (disabled at the ends, hidden when everything fits). Its covers were missing because the
  cover list was only fetched when Rarest or Most mentioned opened; the Tracker, the shelf and Demand now ask for it too (all 24 of today's top games have a cover in `covers.json`).

## 2026-10-14: a new look (the maintainer's theme)

- The maintainer's mock-up (`spindle_ps2_sentiment_market_tracker_letterboxd_ui.html`) was reviewed and its look applied to every page, keeping our script:
  Inter for text, Playfair Display for the wordmark and game names, JetBrains Mono for figures (a `<link>` in both pages, no `@import`); rounded cards
  instead of hairline sections; a glow behind the search box and tabs; stat cards with a coloured top edge; capital tabs underlined in the accent colour;
  box art at 2:3 on My collection; the My collection button as a yellow outline instead of the glossy gradient; the banner sticks to the top on wide screens only.
- New: the **shelf** above the tabs on the Tracker page (`renderShelf()`): the six games named most in the last 24 hours as box art, from the same
  list as "Named in the last 24 hours", with the mention count and the eBay median. Real data only; hidden on the other pages.
- Not taken from the mock-up (it was a design sketch, not a drop-in page): its stripped script (no GitHub saving, no weights, no EUR, no charts), its
  invented fallback games and prices, its "Letterboxd" wording, and its CSS-less parts (charts, editions, sources table, phone layout), which keep our rules.
- Tests: the design-pinned checks in `tests/dashboard_check.mjs` were updated (tab underline, yellow's jobs, banner rules, card markup, collection button) and a
  shelf check added. `guide.html` describes the shelf and the new button.

## 2026-10-14: .hack games searched the way sellers name them

- The library spells them "Hack: Part 1: Infection", but eBay sellers write ".hack//INFECTION" or ".hack Infection". `ebay_watchlist.json` now pins the seven
  games with their own search words (`hack infection`, `hack mutation`, `hack outbreak`, `hack quarantine`, `hack g u vol 1`, `vol 2`, `vol 3`: a Vol. 2 listing is not Vol. 1).
  The Vol. 1 Premium Edition in `editions.json` searches `hack g u vol 1` with "premium edition". A test checks the sellers' spellings count and another part does not.

## 2026-10-14: editions cross-checked against the first eBay run

- First run (26 of 32 editions placed): 6 US editions were missing from `latest["editions"]` because their names are already priced games
  (the Rarest page lists them, e.g. Resident Evil 4 Premium Edition: 28 copies, median $199.99). `add_rare_games()` now points such an
  edition at the game that holds the figures (when it is priced on the edition's site) instead of skipping it.
- Six came back `unmatched` (eBay returned listings, none named the game): the search words for `.hack//G.U. Vol. 1 Rebirth Premium Edition`
  (now "hack g u" + "rebirth") and Shin Megami Tensei: Devil Summoner 2 (now its Raidou Kuzunoha vs. King Abaddon name) were wrong and are changed;
  Brothers in Arms pre-order kit, Driver 2, ICO First Edition, Resident Evil 4 Collector's Pack and Robotech Battlecry Collector's Edition are left as
  they are: either nothing is listed under the edition's own words or the entry is too rare to ever be listed.
- "Special Edition" / "Two Disc Set" entries for Call of Duty 3 and God of War II (US) were the ordinary pressing, so their figures are ordinary prices (180 and
  152 copies), not collectors' prices.

## 2026-10-14: edition badge on My collection

- A coloured badge on an edition's tile in My collection says what it comes in (STEELBOOK, TIN, SLIPCASE, SLIPCOVER, DIGIPAK, BOXED SET,
  FIGURE SET, PLUSH SET, otherwise LIMITED), from the entry's `kinds` (`editionBadge()`). The US Resident Evil 4 Premium Edition was
  checked against two more pages (eBay's product page and Gameventory): it is the PS2 steelbook sold in America (steel case, Making of DVD,
  Ada Wong laser cell, Brady Games prologue); the PAL one is the Limited Edition.

## 2026-10-14: covers for editions

- `coverUrl()` gives an edition (`editions.json`) the Libretro box named in its optional `cover` (four have one: Mortal Kombat
  Armageddon Premium Edition, Driver: Parallel Lines Limited Edition, Call of Duty 2: Big Red One and Tony Hawk's American Wasteland
  Collector's Editions, all USA files) and otherwise its game's box in the edition's own region. The collection has no steelbook
  scans, so the Resident Evil 4 steelbooks show the standard RE4 box. An edition with no game page (Driver 2) shows initials.

## 2026-10-14: editions in the search and in My collection

- The search box and My collection's game box also find the 32 editions of `editions.json`, by name and by what they come in
  ("steelbook", "tin", "slipcase", "digipak"; `addEditionKeywords()`). Picking an edition ticks its region, and My collection values it
  at its own eBay price on the site it was sold on (`collectionValue()` -> `editionFigure()`), never at the plain game's price; an
  edition not priced yet shows no value. Sealed copies still use the reference articles only.

## 2026-10-14: limited and collector's editions

- New `editions.json`: 32 known PS2 limited, collector's, premium and steelbook editions (12 PAL, 20 US), made by hand from the
  Collectors Edition game database's PS2 lists (each entry read on 2026-10-14, its source linked). Includes both Resident Evil 4
  steelbooks (PAL Limited Edition, US Premium Edition). Left out: Dragon Ball Z Budokai 3 Collector's Edition (PAL), Silent Hill 2
  Special 2 Disc Set (PAL) and Bully Special Edition (NTSC), whose pages did not load; Japanese editions (only US and UK are priced).
- `ebay_prices.py` reads it with `load_rare(EDITIONS_PATH, kind="edition")` and prices each edition once a day on its list's site
  (PAL on eBay UK, US on eBay US), searching the game's name plus the entry's `require` words, so a plain copy never counts.
  Editions are `kind: "edition"` in `latest.json`, are listed under `latest["editions"]`, and stay out of the PS2 price index,
  the Rarest page and the eBay prices list. Numbers only are kept.
- The game page shows an "Editions of this game" section: contents, release, its own eBay price, an eBay search link and the source.

## 2026-10-14: more covers found

- `tools/build_covers.py` now accepts any region as a last resort (Cart Kings is only filed under India), matches the collection's zero-padded numbers ("Ace Combat 04"), and links near-identical spellings (typos in the library such as "Alien Homind", "Vol." / "Volume", an added "The") when the numbers agree and no one- or two-letter word differs ("DDR Max" is not "DDR X"). Library games with a cover: 76% -> 82% (5,172 keys).

## 2026-10-14: covers on Most mentioned and Rarest

- A 3 rem box (`withCover()`) sits beside each row of both pages, lazy-loaded; the PAL list uses the Europe box, the US list and Most mentioned the USA one; Rarest also tries the PAL title. The covers list is requested when either page is opened, and both lists redraw when it arrives. Covers off: no pictures, no request.

## 2026-10-14: covers from the Libretro thumbnails

- Wikipedia covers did not work in practice (blank tiles), so they are replaced. `covers.json` (made by
  `tools/build_covers.py` from the file list of github.com/libretro-thumbnails/Sony_-_PlayStation_2, 8,502 box arts)
  names the file for each game under its `priceKey()`: 4,642 keys, about 420 KB (94 KB compressed), read once and only when a
  cover is wanted. The picture itself is an ordinary `<img>` from thumbnails.libretro.com in the visitor's browser.
  A PAL entry gets the Europe box, a US entry the USA one. About a quarter of the 3,292 library games (and more of the extra search names) have no file
  (initials shown). Covers also show beside a game page's title. The old Wikipedia lookup and its localStorage cache are gone.
- No key, no sign-up, nothing asked of anyone (rule 13); the collection is public. Its licence is not stated by the project:
  the art belongs to its publishers and is hotlinked small, the way RetroArch itself loads it.

## 2026-10-14: search buttons back in the lists

- The eBay / PriceCharting / shop search buttons (`priceLookupHtml()`) were removed from list rows with the detail; they are back under every game's name (`listPricesHtml()` = short prices + buttons) and also on the game page.

## 2026-10-14: game pages hold the detail, lists show three prices

- Asked for by the maintainer after the eBay prices page felt slow. Lists (Tracker, Demand Index, Most mentioned,
  eBay prices, table) now show a game's name and three prices only: US median, UK median and the cheapest euro
  median (lowest of DE/FR/IT/ES, marked "from XX"; this reading of "cheapest for EUR" is mine). Every name is a link
  to `#game=Title`. The game page shows every site's full figures, week change, chart, eBay search links and the
  lookup chips, drawn only when opened.
- Removed `priceFiguresHtml()` and `gamePricesHtml()`; added `compactPriceHtml()`, `gamePriceDetailHtml()`,
  `gameLinkHtml()`, `openGameLink()`. The Rarest page lists are unchanged.
- Tests: the eBay prices, medians, week-change and table assertions moved to the new shapes (46 checks).

## 2026-10-14: faster page load

- Measured in headless Chromium on the live data (7.6 MB feed, 484 priced games): about 1.4 s of blocked main
  thread, 66,000 page elements, and 380 ms in `money()` building a new `Intl.NumberFormat` for every price.
- `index.html`: `cachedFormat()` makes each number/date formatter once; the long lists of the two pages
  that are not on screen (Most mentioned, eBay prices) are drawn when their tab is opened
  (`drawForView()`, only where `requestIdleCallback` exists, so the Node checks draw them at once). Tab counts
  still set at load. After: about 0.5 s blocked, 18,000 elements; the eBay prices tab takes about 0.4 s the first
  time it is opened.
- Not changed: the 7.6 MB `sentiment_feed.json` (about 12,900 items; the ceiling grows in steps from 30,000)
  is still downloaded and parsed in full at load.

## 2026-10-14: covers fixed, collection button in the header

- Covers were blank because Wikipedia's page-image lookup returns only freely licensed images unless asked
  with `pilicense=any`, and box art is non-free. Added; tiles now say whether a cover was found, not found or failed.
- The My collection button moved from the page tabs to the header beside REFRESH, with a blue-to-teal glossy
  gradient and a slow shine (off for `prefers-reduced-motion`). No yellow (reserved for price links).

## 2026-10-14: collection search and cover tiles

- `index.html`, `retro.css`: the collection's add box uses the main search's dropdown (`suggestGames`, arrow
  keys, Enter, Esc) and the form is laid out properly (it had no styles). The list is now a grid of cover
  tiles (region, quantity, condition, value). Covers are the lead image of the game's Wikipedia article,
  requested by the visitor's browser (`coverRequestUrl()`, `pickCoverPage()`): the article the Demand Index
  checked when there is one, otherwise the top search hit only if its title matches and its short description
  says "video game"; only `upload.wikimedia.org` addresses are used; results are remembered in the browser.
  A `Show cover images` switch stops all requests. Not tested against Wikipedia's live API (the build machine
  cannot reach it): the Node tests and a browser run use stand-in replies.

## 2026-10-14: My collection, installable site, reference prices on Rarest

- `index.html`: a fifth tab, **My collection** (`#collection`). Games are added by region and condition,
  kept in the browser's `localStorage` only (no login, nothing sent), valued with the eBay median of the
  region's site (complete uses the complete median, sealed an article price), with a backup file to save and
  load. The Rarest page shows up to two dated article figures per game (`Articles (not live)`) from
  `rare_reference_prices.json`.
- `manifest.webmanifest`, `sw.js`, `icons/`: the site can be installed on a phone and opens offline with the
  last data it saw. The worker is network first and same-origin only.
- A crypto-wallet "connect" was left out on purpose: it identifies a visitor but stores nothing, so the list
  would still need a server or a file.

## 2026-10-14: reference prices for rare games

- `rare_reference_prices.json` (78 points from five public articles), `tools/compare_reference.py`,
  `tests/test_reference.py`. Compared with `rare_games.json`: the July 2026 articles agree with our
  PriceCharting values within about 20% (Kuon complete $1,575 vs $1,988; Haunting Ground $575 vs $606);
  the 2020-2024 eBay-sold figures are lower ("over $400" for Rule of Rose against $1,100 now). Four of five
  articles copy PriceCharting, so this checks our reading of it rather than adding a second market.

## 2026-10-14: collectible rules v3

- `demand.py`: after reading the 12 articles flagged on the first live run, only Kuon, Gitaroo Man and
  Rule of Rose were real. The rest were noise: a development budget ("most expensive game", GTA: Vice City),
  sales ("sold for", Persona 4, Guitar Hero III, Mortal Kombat: Deception), rare in-game items (Monster
  Hunter, Persona 3, Jak and Daxter), a review quote (The Punisher), a general remark (Shadow of Memories).
  The rules now need rarity of the game's copies/versions, "out of print", small print runs, a second-hand
  price or "expensive to buy second-hand". `RULES_VERSION` 3 makes every cached check be read again.

## 2026-10-14: Demand Index v2, YouTube views, Wikipedia collectible check, Most rare repaired

- `scraper.py`: YouTube items carry `views` (from the feed's `media:statistics`). Other sources are unchanged.
- `demand.py` rewritten (`version: 2`): five signals (mentions rising 30%, sources 15%, YouTube views 20%,
  eBay week change 20%, Wikipedia trend 15%), missing signals left out and the rest re-weighted. Wikipedia
  articles are read in full and must be a PS2 video game; sentences calling it a rare collectible are
  recorded in `data/wiki_checks.json` (150 articles per run, redone after 30 days). Archive.org is gone.
- `index.html`: "Most rare" had collapsed after `listed` was added (almost no figure had it yet, so
  nearly every game fell into the unchecked tail). Supply is now the higher of our count and eBay's
  `listed`, ranked in groups of 10 / 30 / 100 / more, collectibles first inside a group. Collectible tag,
  Demand Index v2 lines. `guide.html` rewritten for all of it.
- Not verified live: YouTube view counts and the collectible wording rules (the build machine cannot reach
  YouTube or Wikipedia); both are checked on the first workflow runs.

## 2026-10-14: eBay name check ignores "the"

- `ebay_prices.py`: a listing is compared with a game's name with every "the" removed on both sides
  (`the_less()`), in the name, sibling and `require` checks. Replayed on the 711 left-out listings
  that last night's run kept as examples: 18 would now count (Prince of Persia: Sands of Time, Zone of
  the Enders, Spyro: The Eternal Night, Genji, Spider-Man: The Movie), all the right game; sequels
  and siblings (Warrior Within, Top Gun: Combat Zones, Simpsons Hit & Run) stay out. Affected games'
  copy counts rise and medians move on their next check; their week-ago bracket compares two different
  searches for a week.
- "Combat Ace" in the Demand Index was not a current matcher error: 7 rows from 1-4 October predate the
  fix in `TitleMatcher` and age out of the feed by 18 October (the one newer row, a Mount & Blade post
  matched fuzzily at 90, is the only current case).

## 2026-10-14: search fixes, demand index fixes, honest "scarce"

- `index.html`: the search lists a game once (spellings tied by `priceKey()`), also finds words in any form
  ("fifa 10" finds "FIFA Soccer 10") and British spellings ("honour"). It reads `search_extra_titles.json`
  (805 NTSC-U/PAL names from PCSX2's game list that the library lacks: FIFA 09 to 14 among them); the
  scraper, matcher and eBay pricing do not read it.
- `ebay_prices.py`: `latest.json` figures carry `listed`, eBay's own count for the same search. The
  dashboard shows "scarce" and ranks "Most rare" only where `listed` is within 2 of `copies` (not
  truncated). Measured on the `ebay-data` branch: 17 of 30 games with 10 or fewer counted copies had
  3 or more listings left out by the name checks (FIFA 2003: 6 counted of 200; Spyro: The Eternal
  Night: 1 of 34). Figures and the scarce tag now open the search they count (used, Buy It Now, in that
  country, Video Games) instead of the general search.
- `wiki_overrides.json` (new), `demand.py`: wrong Wikipedia matches fixed or left out, and two titles on
  one article are counted once. The guide now lays out how the Demand Index is worked out.

## 2026-10-14: the item ceiling raises itself

- `scraper.py`: `item_ceiling()` keeps `MAX_ITEMS` (30,000) until the two weeks hold more than 90% of it,
  then raises it in steps of 5,000 so there is always 10% room, up to `CEILING_HARD_MAX` (80,000, about
  48 MB). Below 27,000 items nothing changes. Checked by an AST comparison with `main` (only
  `within_ceiling` and `run_scraper` changed) and new tests; `tools/regression_check.py` could not
  reach the news sites from the development machine, so *Live checks* on the pull request runs it.

## 2026-10-14: search, game pages, rare sort, logo home

- `index.html`: a search box over the whole library (`data/ps2_database.json`, read by the page), with
  suggestions as you type ("godh" finds God Hand). A pick opens a game page (`#game=Title`) with its
  eBay prices and the newest feed items that name it (matched by `priceKey()`); a game nobody named gets
  an empty page. The Spindle logo is a link home and clears the search.
- The 24-hour list has **Most expensive** (as before) and **Most rare** (fewest eBay UK/US copies first)
  buttons, and a `scarce` tag at 10 copies or fewer (`SCARCE_COPIES`). Nothing new is fetched: rarity is
  the copy count `ebay_prices.py` already saves in `latest.json`. `guide.html` explains all of it.

## 2026-10-14: one index for all PAL sites

- `ebay_prices.py`: `index.json` has a `PAL` line beside each site's own, built from every game on the UK
  and the euro sites as separate items (`add_pal_days()`); it is a percentage, so no currency enters.
  It appears once two PAL sites have a finished day. The Rarest page's PAL market cap still uses eBay
  UK alone, in pounds (decided so, as its copy estimates are for PAL countries as a whole and not per site).
- `index.html`: the index cards are US, all PAL sites, then each PAL site. `guide.html` explains it.
- Search words (the other half of this step): of the 53 games a European site could not find, none
  has a documented European name, so no rename was added (`ebay_watchlist.json` stays as it is). Most
  are games with few listings outside America or listed under spellings of their own; add a rule only
  with the PAL box title, as the existing ones have.

## 2026-10-14: eBay Spain

- `EBAY_ES` in `MARKETS`, like Germany, France and Italy, with Spanish junk and incomplete-copy words
  (not yet checked on live listings). `index.html`, `guide.html` and the tests follow. That is every
  site asked for except Poland, which was left off.

## 2026-10-14: eBay Italy

- `EBAY_IT` in `MARKETS`, the same way as Germany and France: euros, once a day, keyword search
  only, the UK's regional names, Italian junk and incomplete-copy words (not yet checked on live
  listings). `index.html`: IT everywhere beside DE and FR. `guide.html` updated. Tests: the per-site
  tests are now one factory (`european_site_tests`) used for France and Italy, and one test covers
  every extra site together, so the next site adds one line.

## 2026-10-14: eBay France

- Asked: the next European site after Germany. `EBAY_FR` in `MARKETS`: euros, once a day, keyword
  search only, the UK's regional names, French junk and incomplete-copy words (not yet checked on live
  listings). `index.html`: FR beside DE everywhere (price chips link, chart button, dim time, euros).
  `guide.html` updated. Tests: `FranceTests`, and the Node check now covers each extra site's clock.

## 2026-10-14: eBay Germany

- Asked: add the European eBay sites one at a time, starting with Germany (the probe on 2026-10-14
  showed it has plenty of listings for both famous and rare PAL games).
- `ebay_prices.py`: `EBAY_DE` in `MARKETS`: euros, once a day, keyword search only, the UK's regional
  names, German junk and incomplete-copy words. Its lookups come after the US and UK ones, and a run is
  judged on the US and UK alone.
- `index.html`: a DE price beside US and UK everywhere a game's prices show, a link to eBay Germany's
  search among the price chips, a chart button for DE, a DE index card (once the index has one), and DE
  figures dimmed only after 30 hours. `guide.html` explains it.
- Tests: `GermanyTests`, two more in `ExtraSiteGroundworkTests`, and a Node check that the page's
  sites match `MARKETS`. The older eBay tests run with the first two sites only, as they were written.

## 2026-10-14: groundwork for more eBay sites, and a bigger allowance

- Asked: raise the daily search allowance to just under eBay's 5,000, and get ready to add Germany,
  France, Italy and Spain one at a time (Poland left off).
- `ebay_prices.py`: `DAILY_SEARCHES` 4,500 to 4,900. A site in `MARKETS` may now carry `extra: True`
  (the Rarest page's consoles stay off it unless they name it), `min_every_hours` (its own slower
  check clock) and `junk` (words in its language that mark a listing as not a copy). The first
  two sites have none of these, so nothing changes for them. No new site is switched on here.
  `ExtraSiteGroundworkTests` test all of this with a made-up site.

## 2026-10-14: fewer searches for steady games

- Asked: stop re-checking famous games whose price barely moves (GTA San Andreas, about 160 copies
  listed) so the saved searches go to niche games.
- `ebay_prices.py`: `is_steady()` and `steady_index()`. A normal or staple, unpinned game on one site
  with 50+ copies, a median within 10% and copies within 30% over the last 6 days is checked every 48
  hours instead of 6. Any check that breaks the pattern returns it to 6 hours. Surging, dormant, rare
  and pinned games are unchanged.
- Follow-up fix: `latest.json` marks a figure `steady: true` when it was on the 48-hour clock, and the
  dashboard calls it overdue only after 56 hours (otherwise every steady price would have been dimmed
  after 8). Tested in both `test_ebay_prices.py` and `dashboard_check.mjs`.
- Replay on 9 days of real history: about 205 of 581 game-site pairs qualify (about 700 fewer
  lookups a day); 2 of 482 flagged moments saw a move over 10% within two days. See
  docs/VERIFICATION.md. `tests/test_ebay_prices.py` has `SteadyTests`.

## 2026-10-14: EUR button

- Asked: a button so people can flick every price between its own currency and euros.
- `fx.py` and `.github/workflows/fx.yml` (new): each weekday after the European Central Bank
  publishes, save `data/fx.json` with the rates of USD, GBP, PLN and CHF per euro. No key,
  standard library only. A failed read leaves the old file; the file changes only when the ECB's
  rates do.
- `index.html`: a `€ EUR` button under the page tabs (hidden until `data/fx.json` is read). Off by
  default; the choice is kept in the browser. `money()` and `moneyShort()` convert with today's
  rate and mark the result `≈`. Charts and a week's change use the same latest rate. PriceCharting
  guide figures stay in dollars. Index lines are percentages and do not change.
- `guide.html` explains it. Tests: `tests/test_fx.py` and a dashboard check.

## 2026-10-14: counting listings on other eBay sites

- Asked: add Germany, France, Italy, Spain and Poland to the eBay prices, starting with whether
  each site has enough listings to be worth it.
- `ebay_prices.py`: a probe mode (`EBAY_PROBE=true`, the workflow's new **probe** tick box). It
  asks each site in `PROBE_MARKETS` how many listings it reports for 20 famous games and the
  first 20 plain PAL entries of `rare_games.json`, one listing per search (counts only), and
  prints a summary per site plus one run notice per site. Britain is the control. It uses about
  300 searches, reads no state and writes nothing. The normal run, `MARKETS` and the dashboard are
  unchanged: no site is priced yet.
- `.github/workflows/ebay.yml`: the `probe` input and `EBAY_PROBE`. No other step changed.

## 2026-10-14: charts on a phone

- Asked: the charts did not look good on a Pixel 10 Pro (427 x 952 CSS pixels).
- `retro.css` (phones, up to 640 px): the chart tool buttons are one row you swipe sideways
  (they were 11 full-height 44 px buttons stacked into a block 98 px tall; now 44 px) and
  have a smaller height than the general 44 px button rule, which they out-rank; the chart
  is 300 px tall; the day read-out is larger.
- `index.html`: the chart no longer captures one-finger drags (`handleScroll` touch drags
  off, pinch off), so the page scrolls over it; a tap reads off a day (`subscribeClick`).
  On a computer the mouse still drags and zooms.
- `guide.html` describes the above. Checked with phone-size Chromium screenshots using the
  plain-line fallback only: the chart library's address is not reachable from the sandbox, so
  touch behaviour was checked by reading the library's source (4.2.0), not on a device.

## 2026-10-13: rare-list charts, market cap, price history, and a bigger feed

- Asked: are the rare games still priced (yes: daily, PAL on eBay UK, US on eBay US); more
  accurate rare prices; the feed's 12,000-item ceiling raised; TradingView-style charts tracking
  the PAL and US rare lists' price and market cap, with print runs estimated to weigh the cap;
  BitSkins-style price charts per game.
- `scraper.py`: `MAX_ITEMS` 12,000 → 30,000. The busiest days seen (2026-10-08) brought about
  1,550 items, so two weeks need about 21,700; the snapshot grows to about 7 MB (under 1 MB
  compressed). News/Reddit output otherwise unchanged.
- `ebay_prices.py`: graded and factory-sealed copies are left out (`graded_or_sealed`); when
  some copies say they are incomplete, `latest.json` also keeps the median of the others
  (`complete`). The dashboard shows it, and a red "few copies" tag at one or two copies.
- `rare_games.json`: every entry has `copies` (low/mid/high copies sold in its region, with how
  it was estimated); the top-level `copies` holds the method, survival shares, the figures found
  and the reference classes. Kuon: about 12,000 US and 8,000 PAL. Most entries are estimates.
- `index.json` gains `rare`: each list's index and market cap (all, and without games of
  100,000+ copies), from 8 October. The cap starts as Σ median × copies × 65% and then moves
  like a stock index, so games joining or leaving do not move it. New `data/prices/series.json`: 90 days of each game's
  daily median and copies.
- Dashboard: a chart above the PAL and US lists (index or market cap, all or core, 1W/1M/3M/All,
  line or area, log scale, crosshair read-out), and a "chart" button on Rarest and eBay prices
  rows opening the game's price history with copies-for-sale bars. Drawn with TradingView's
  Lightweight Charts 4.2.0, or a plain line when it cannot load. `guide.html` explains both and
  the market cap's assumptions.

## 2026-10-09: Rarest page widened and made simpler

- Asked: more sources for the rarest games, and simpler, readable console tiers.
- `rare_games.json`: a second research pass (cheatcc and unanswered.io 2026 lists, TheGamer,
  lovemoney, Den of Geek, Potteries Auctions, collector databases and forums, eBay asking
  prices, and PriceCharting's whole PAL and US catalogues). Evidence added to 56 entries; 9
  values re-read (Silent Hill 2 PAL down to $133, Coraline PAL $158, The Punisher US $146 and
  others); 21 games the first pass missed, among them the Australian GTA Complete Collection
  ($1,901, now PAL #1), the shovelware World Quiz and Monster Eggs, The Getaway Limited
  Edition, Silent Hill 3 and 4 PAL, the Sega Fun Pack, and the Dragon Ball Z Budokai 3, MGS3
  Subsistence and RE4 Premium limited editions. Lists now 115 PAL and 106 US; nothing dropped.
  "one source" now means fewer than two different sites back the value (an eBay asking price
  never counts): 78 PAL, 60 US. Jello is not priced (one ordinary word). Two Australia-only
  releases carry a new "Australia" tag, as Indian releases carry "India".
- Rarest page: the console tiers are words with colours (Ultra rare, Very rare, Rare,
  Limited) in shades of white rather than the page's red/blue/teal, with a one-line key under the
  list; each console has one short line (model, where, year, how many); the summaries and notes of
  both lists are shorter.
- Independent review: the four words now say what the tiers mean ("5,000 or fewer, or a
  one-off"; "one country only, mostly Japan"; "a limited edition, or a larger run"); Vice City
  Stories leaves out the double pack; eBay asking prices no longer count as a second source.

## 2026-10-08: digital-only news kept for good

- Asked: keep the digital-only news, without spending Reddit requests that PS2 news needs.
- `archive.py` keeps every story flagged `is_digital_only` in `data/archive/digital/YYYY-MM.json`
  with its link, and a small `index.json` (total, per month, per day). It reads the snapshot the
  scraper already wrote, so it adds no request to Reddit or anywhere else, and no subreddit was
  added for it. On the snapshot of 2026-10-08 that is 22 stories, from 27 September.
- The dashboard's Digital-Only News line adds "N archived since …".
- Independent review: a story the rules stop flagging now leaves the archive too; the commit
  message and log say when digital news was archived; the archive tests run when the file is run
  directly; README updated.
- Fixed on the way: a real sentiment of 0 was archived as 50.

## 2026-10-08: Digital-Only News

- Asked: a view of the live feed for news about games going digital-only, to gauge how much
  there is while physical discs are being phased out; any game, from the feeds we have. The
  yardstick: "Phantom Blade Zero Confirmed Digital-Only Despite Promised Physical Release".
- `scraper.py` flags `is_digital_only` from the headline (`is_digital_only()`), and flags the
  whole snapshot again on every write. 22 of the 7,279 items in the snapshot of 2026-10-08,
  among them the yardstick (via r/playstation), Kotaku's "About To Ditch Discs", Lemmy's "No
  Physical Edition Is Coming", game-key card news and the Spanish and Portuguese feeds' versions.
- Dashboard: **Digital-Only News** in the table's menu, with the two-week and seven-day counts,
  and a blue *Digital-only* tag on those rows.
- Independent review: event and sale wording ("all-digital showcase", "digital only sale") was
  counted and "won't get a physical release" was missed; both fixed, with 21 more test headlines.
- News and Reddit fetching, matching, sentiment and remaster flags are unchanged
  (`regression_check.py` ignores the new field).

## 2026-10-08: Rarest page buttons; consoles by region and price

- Asked: split the consoles by region (US, Japan, PAL) and sort them most expensive first; the
  games' buttons to say just PAL and US; colourful, modern buttons.
- The Rarest page's switch is three rounded, coloured buttons: PAL (blue), US (red), Consoles
  (teal), the lit one filled. Under Consoles, US / Japan / PAL buttons pick where the consoles
  were sold; each list is sorted by its eBay median (eBay UK for PAL, eBay US otherwise), then the
  other site's, then the guide value. The tier still shows how rare each is. The theme's rule
  that yellow belongs to price links is kept.

## 2026-10-08: the PS2 Price Index

- Asked: something like the S&P 500 for the PS2 market. A market capitalisation needs to know how
  many copies exist, which nobody does, so this is a price index instead: how asking prices move.
- `ebay_prices.py` writes `data/prices/index.json` on every run that writes prices: per site, 100
  on its first day (6 October 2026), moved each day by the geometric mean of each game's change in
  median since its previous day. Games joining or leaving never move it; medians from fewer than
  three copies, and those that more than doubled or halved, are left out; consoles are not in it.
  Finished UTC days only. On the history so far it stands at about 99.9 on both sites.
- Independent review: a day under way showed false moves (US 97.45 at 02:00, 99.95 by 08:00);
  a console missing from `latest.json` would have entered with its whole history; the moves
  were labelled "on the day before" even across a gap; a kept value read as "no change". All
  fixed; the docs now say a small change of search words can nudge the index.
- Dashboard: the index at the top of the eBay prices page, per site, with the change since the day
  before and over a week and a line of every day.

## 2026-10-08: the Rarest page gets consoles

- Asked: a list of the rarest PS2 consoles, official releases only, using Obsolete Sony and
  consolevariations.com. consolevariations.com asks robots to stay out (robots.txt), so it was
  not read; Wikipedia (English and Japanese), Obsolete Sony, Sony's press releases, PriceCharting
  and articles were.
- `rare_consoles.json` (new): 37 consoles in four tiers, led by the 2001 car-paint colours
  (about 666 of each per region), the Toys"R"Us Japan blue, the development units and the
  Bravia TV with a PS2 inside. Each with model numbers, regions, units where known, value and
  sources.
- `ebay_prices.py`: prices 34 of them once a day on eBay US and UK (or the one site of a
  single-country release), in the consoles category, from sellers anywhere, any condition but
  for parts. A listing must name the model or the colour; bundles count, shells, skins,
  custom paint, mods and broken consoles never do, and neither does a part sold alone (a
  coloured controller, a PSX remote). Game searches are unchanged. About 130 searches a day.
- Independent review: game-named bundles (an ordinary slim with *Final Fantasy XII*), coloured
  controllers, remotes and cables, and the US silver slim's own "satin" listings were all
  mis-sorted; fixed and tested on realistic titles.
- Dashboard: a third switch on the Rarest page, *Consoles*. Consoles stay off the eBay prices
  page.

## 2026-10-08: the Rarest page

- Asked: a tab next to the Tracker with the 100 rarest PAL games and the 100 rarest US games,
  "even if it's shovelware", with their eBay median prices.
- `rare_games.json` (new): both lists, ranked by PriceCharting's complete-copy value of
  2026-10-08, because nobody counts copies and price is how collectors measure rarity. Each
  entry carries its sources (PriceCharting, Racketboy, GIGA, Destructoid, PPE.pl, whynow, Retro
  Dodo), the other region's name, eBay search words, and flags for thin data, single sources,
  editions and Indian releases. PAL is led by Sengoku Anthology, Gun Club and Kuon; US by Kuon,
  Rule of Rose and Haunting Ground. Kept in the list but flagged: Cart Kings, Hanuman and Ra One
  (Indian PAL releases). White Van Racer is left out: its current value is unclear.
- `ebay_prices.py`: prices each list once a day on its own site, PAL on eBay UK and US on eBay
  US, after every other due lookup. A game the feed already tracks is reused when it is searched
  there under the entry's words or name (43 entries today); 133 games are added with the new
  level `rare`, about 150 lookups a day. Editions need their own words in the listing
  (`require`) and may come with an art book or a plush (`allow`). Five entries whose name is
  one ordinary word (Obscure on both lists, Buccaneer, Nightshade, Hanuman) are not priced and
  show "not priced". A broken file is reported and never stops the run.
  `latest.json` gains `rare` (which game holds each entry's figures) and `sites`.
- Independent review: one-word names counted other games' listings ("rare obscure horror
  game"), two entries were looked up a second time under shorter words, editions with a plush
  or art book were all left out, and *FIFA Soccer 13* never matched its US title. All fixed.
- Dashboard: a *Rarest* tab (`#rare`) with a PAL/US switch, 25 rows folded, guide value, flags,
  the eBay median on the list's site with its weekly bracket, and the sources. On the eBay
  prices page those games carry a *rarest* tag and show only their own site.
- Guide: a new section 5, *The rarest games*; one example corrected (Bully keeps its name on
  eBay UK).

## 2026-10-08: eBay UK searched under the European name

- Asked: why *Fatal Frame 2* had no eBay UK price. In Europe the series is *Project Zero*; the
  UK search for "Fatal Frame 2" found no PAL copy (0 copies, against 16 on eBay US).
- `regional_names` in `ebay_watchlist.json` renames the start of a game's name for one site, and
  the price job searches eBay UK under that name: 15 rules, among them Fatal Frame → Project
  Zero, Siren → Forbidden Siren, Dark Cloud 2 → Dark Chronicle, Ratchet: Deadlocked → Ratchet:
  Gladiator, Sly Cooper and the Thievius Raccoonus → Sly Raccoon, Ace Combat 4 and 5 → Distant
  Thunder and Squadron Leader, Shin Megami Tensei: Nocturne → Lucifer's Call. Six games tracked
  today change: Fatal Frame, Fatal Frame 2, Siren, Sly Cooper, Ace Combat 4 and Ace Combat 5.
- Bully keeps its name: only the UK release was Canis Canem Edit, and eBay UK sells both.
- A game the library also files under its European name is looked up on eBay UK once.
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
