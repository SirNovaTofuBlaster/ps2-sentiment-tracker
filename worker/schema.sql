-- Crowd data (docs/CROWD.md). Run once in the D1 console, or: npx wrangler d1 execute spindle --remote --file=schema.sql
-- No email, no address, no name. An account is a random id and the hash of a random key.
CREATE TABLE IF NOT EXISTS accounts (
  id       TEXT PRIMARY KEY,
  key_hash TEXT NOT NULL,
  created  INTEGER NOT NULL            -- day number (days since 1970-01-01)
);
CREATE TABLE IF NOT EXISTS copies (
  account  TEXT NOT NULL,
  game     TEXT NOT NULL,              -- the dashboard's priceKey()
  sealed   INTEGER NOT NULL,
  complete INTEGER NOT NULL,
  loose    INTEGER NOT NULL,
  updated  INTEGER NOT NULL,
  PRIMARY KEY (account, game)
);
CREATE TABLE IF NOT EXISTS reports (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  account   TEXT NOT NULL,
  game      TEXT NOT NULL,
  region    TEXT NOT NULL,             -- US or PAL
  condition TEXT NOT NULL,             -- sealed, complete or loose
  currency  TEXT NOT NULL,
  price     REAL NOT NULL,
  month     TEXT NOT NULL,             -- when it was bought: YYYY-MM
  source    TEXT NOT NULL DEFAULT 'other',   -- no longer asked for or sent (2026-10-17); kept so older databases still fit
  created   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS reports_group ON reports (game, region, condition, currency);
CREATE INDEX IF NOT EXISTS reports_account ON reports (account, created);
-- Counters for rate limits: the bucket is a hash that rotates daily, never an address.
CREATE TABLE IF NOT EXISTS limits (
  bucket TEXT NOT NULL,
  day    INTEGER NOT NULL,
  n      INTEGER NOT NULL,
  PRIMARY KEY (bucket, day)
);
