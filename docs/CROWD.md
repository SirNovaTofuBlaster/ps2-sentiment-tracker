# Crowd data (opt-in): how it works

Decided with the maintainer on 2026-10-17. Status: the service (`worker/`) is written; the dashboard side is not built yet.

## Why
eBay gives asking prices. Visitors who own or buy games can give what they actually paid and what they own. Published only when enough
different people agree, it becomes a second source that does not depend on eBay, and may one day lean on it less.
It will add to eBay for a long time, not replace it: most games will never have five reporters.

## Pieces
| Path | What it is |
|---|---|
| `worker/index.js` | A Cloudflare Worker: register, save collection counts, add a purchase report, delete the account, and read the published figures |
| `worker/lib.js` | The rules, with no Cloudflare calls (what is accepted, how reports become figures). Tested by `tests/worker_check.mjs` |
| `worker/schema.sql` | The D1 tables (database `spindle`) |
| `worker/wrangler.toml` | The Worker's settings. The database id in it is an identifier, not a secret |

## Accounts
No email, no name, no password chosen by the visitor. `POST /api/register` makes a random id and a random 256-bit key and returns them once;
the server keeps only the key's SHA-256 (the key is random and long, so a slow hash is not needed). A lost key is a lost account.
Requests send `Authorization: Bearer <id>.<key>`. The network address is used only to limit sign-ups (5 a day): it is hashed with a secret
`SALT` and the day number, so the stored bucket cannot be turned back into an address and changes every day.

## What is kept
- `copies`: per account and game (the dashboard's `priceKey()`), how many sealed, complete-in-box and loose copies (0-99 each).
- `reports`: per account, game, region (US or PAL), condition, currency (USD, GBP, EUR), price, the month it was bought, and where (eBay, shop,
  convention, private, other). At most 20 a day per account.
- Nothing else: no address, no email, no name, no free text. The Worker logs nothing and never echoes an error.

## What is published (`GET /api/stats`, cached five minutes)
- A price figure for a game, region, condition and currency only with **5 or more different accounts** (`MIN_REPORTERS`). An account counts once,
  by the median of what it reported, so sending many reports gives no extra weight.
- **Held back, not deleted** (`summarise()`): a value more than 3x above or below the median of the accounts is left out of the figure. Nothing is
  removed from the database; every request looks at all the rows again, so a held price counts as soon as most accounts agree with it
  (Kuon and Rule of Rose really do sell for far more than most games). If fewer than five remain, nothing is published.
- No currency conversion: each currency is its own group.
- Owner counts for a game only with 5 or more owners; the totals of sealed, complete and loose copies among those who shared. These are not
  census numbers: the people who sign up are not a random sample of owners, so never present them as copies in existence.
- The figures are never compared with eBay on the server; the dashboard may show the two side by side.

## Not done yet
- Dashboard: an opt-in "Share my collection" setting (off by default), a "Report a purchase" tab, crowd figures beside the eBay ones, a
  privacy notice in the guide (what is sent; deletion with the key). Nothing is sent from the page until that is built.
- Sybil resistance beyond the limits above (account age or agreement weighting).
- A list check on game keys: today any priceKey-shaped text is accepted, and only groups with 5 accounts are published.
- At large volumes `/api/stats` should read a precomputed table instead of scanning every row.

## Setting it up (the maintainer does this: it needs their Cloudflare login)
1. The D1 database `spindle` exists (done 2026-10-17); its id is in `wrangler.toml`.
2. From `worker/`: `npx wrangler login`, then `npx wrangler d1 execute spindle --remote --file=schema.sql`.
3. `npx wrangler secret put SALT` (any long random text; never commit it).
4. `npx wrangler deploy`. The page's address is printed (`https://spindle-crowd.<account>.workers.dev`).
There is no GitHub Actions workflow and no Cloudflare token in the repository, on purpose (AGENTS.md rule 8).

### Without a terminal (Cloudflare dashboard only)
`worker/spindle-crowd.bundle.js` is `index.js` and `lib.js` as one file (made by `node worker/bundle.mjs`; a test fails if it is stale).
1. D1 > `spindle` > **Console**: paste `worker/schema.sql`, run it.
2. Workers & Pages > **Create** > Worker > name `spindle-crowd` > **Deploy** (the Hello World) > **Edit code**: replace everything with the bundle, **Deploy**.
3. The Worker's **Settings > Bindings > Add > D1 database**: variable name `DB`, database `spindle`.
4. **Settings > Variables and Secrets**: add a *Secret* named `SALT` (long random text) and a *Text* variable `ALLOW_ORIGIN` =
   `https://sirnovatofublaster.github.io,http://localhost:8000`. Deploy again if it asks.
5. Open `https://<worker>.<account>.workers.dev/api/stats`: it should answer `{"generated":...,"prices":{},"owners":{}}`.
