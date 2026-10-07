"""Tries enabled sources against the live sites and prints what the scraper would make of
them. Nothing is written.

    python tools/try_sources.py forum 4chan     # every enabled source of these types
    python tools/try_sources.py                  # every enabled source that is not news or Reddit

Use it before adding a source, and when one looks wrong: it shows whether the site answers
from this machine (GitHub's runners are not treated like a home connection), how many
entries come back and which PS2 games they name. For 4chan boards it prints counts and game
names only, never anything a poster wrote. Exits non-zero when a source could not be read.

On GitHub Actions the same report is also added to the run's summary page and attached to
the run as notices, so it can be read without opening the log."""

import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import scraper  # noqa: E402

GAMES_SHOWN = 40
entering = Counter()  # games named by board threads young enough to enter the feed
READER_NAME = "ps2-sentiment-tracker/1.1 (RSS reader; +https://github.com/SirNovaTofuBlaster/ps2-sentiment-tracker)"
ON_GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"
report = []  # (heading, lines) for each source tried


def say(line=""):
    print(line)
    if report:
        report[-1][1].append(line.strip())


def publish():
    """The report again, where GitHub shows it without the log: one notice per source (a
    step may attach ten, so the forums share one) and a section each on the summary page."""
    if not ON_GITHUB or not report:
        return
    escape = lambda text: text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")  # noqa: E731
    forums = [f"{heading}: {' | '.join(lines)}" for heading, lines in report if "[4chan]" not in heading and "[all]" not in heading]
    notices = ([("Forums", "\n".join(forums))] if forums else []) + [
        (heading, "\n".join(lines)) for heading, lines in report if "[4chan]" in heading or "[all]" in heading]
    for heading, body in notices[:10]:
        print(f"::notice title={escape(heading).replace(',', '%2C').replace(':', '%3A')}::{escape(body)}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            for heading, lines in report:
                out.write(f"### {heading}\n\n" + "\n".join(f"- {line}" for line in lines if line) + "\n\n")


def try_feed(session, job, matcher, ps2_keys):
    feed = scraper.fetch_feed(session, job["url"], retry_rate_limit=False)
    if feed.get("bozo") and not feed.entries:
        raise ValueError("unreadable feed")
    entries = scraper.select_entries(feed, job["type"])
    items = [scraper.analyze_entry(e, feed, job, matcher, {}, ps2_keys, scraper.shared_links(feed, job["type"]))
             for e in entries]
    stamps = sorted(item["timestamp"] for item in items)
    say(f"  {len(items)} entries, {sum(1 for i in items if i['matched_game'])} naming a PS2 game"
        + (f", from {stamps[0]} to {stamps[-1]}" if stamps else ""))
    for item in items:
        if item["matched_game"]:
            say(f"    {item['matched_game']} ({item['matched_in']}, {item['match_method']} {item['match_score']:.0f})"
                f" <- {item['headline'][:90]}")
    return Counter(item["matched_game"] for item in items if item["matched_game"])


def try_board(session, job, matcher, ps2_keys):
    threads, _ = scraper.fetch_board(session, job["url"])
    live = [t for t in threads if scraper.thread_timestamp(t)]
    items = [item for item in (scraper.analyze_thread(t, job, matcher, ps2_keys) for t in threads) if item]
    stamps = sorted(filter(None, map(scraper.thread_timestamp, threads)))
    # How much each way of reading a thread finds, to judge the rules by. Counts only.
    with_subject = [t for t in live if scraper.board_text(t.get("sub"))]
    strict = 0  # what the rule for RSS bodies would keep: the text must also say "PS2"
    for thread in live:
        text = f"{scraper.board_text(thread.get('sub'))} {scraper.board_text(thread.get('com'))}"
        if scraper.PS2_CONTEXT_PATTERN.search(text) and matcher.match_all(" ".join(text.split()[:scraper.MAX_BODY_TOKENS])):
            strict += 1
    # A thread counts on the day it was started, so only those inside the feed's window are kept.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=scraper.RETENTION_DAYS)).strftime(scraper.TIMESTAMP_FORMAT)
    recent = [item for item in items if item["timestamp"] >= cutoff]
    say(f"  {len(live)} live threads ({len(with_subject)} with a subject), started from "
        f"{stamps[0] if stamps else '?'} to {stamps[-1] if stamps else '?'}; "
        f"{sum(1 for stamp in stamps if stamp >= cutoff)} of them in the last {scraper.RETENTION_DAYS} days")
    say(f"  {len(items)} name a PS2 game: {sum(1 for i in items if i['matched_in'] == 'title')} in the subject, "
        f"{sum(1 for i in items if i['matched_in'] == 'body')} in the comment; {strict} also say PS2")
    say(f"  {len(recent)} of those were started in the last {scraper.RETENTION_DAYS} days and would enter the feed: "
        + (", ".join(f"{title} x{count}" if count > 1 else title for title, count in
                     Counter(game for item in recent for game in item["matched_games"]).most_common(GAMES_SHOWN)) or "none"))
    # What the two rules for posts leave out (see scraper.games_in_post): names only.
    loose = Counter()
    for thread in live:
        subject = scraper.board_text(thread.get("sub"))
        comment = " ".join(scraper.board_text(thread.get("com")).split()[:scraper.MAX_BODY_TOKENS])
        found = (matcher.match_all(subject) if subject else []) or (matcher.match_all(comment) if comment else [])
        loose.update(title for title, _, _ in found)
    kept = Counter(game for item in items for game in item["matched_games"])
    dropped = loose - kept
    say(f"  left out by the rules for posts ({sum(dropped.values())} mentions): "
        + (", ".join(f"{title} x{count}" if count > 1 else title for title, count in dropped.most_common(GAMES_SHOWN)) or "nothing"))
    methods = Counter(f"{i['match_method']}" for i in items)
    say(f"  how they matched: {dict(methods)}; threads naming more than one game: "
        f"{sum(1 for i in items if len(i['matched_games']) > 1)}")
    entering.update(game for item in recent for game in item["matched_games"])
    return Counter(game for item in items for game in item["matched_games"])


def main():
    wanted = set(sys.argv[1:]) or set(scraper.SOURCE_TYPES) - scraper.CORE_TYPES
    unknown = wanted - set(scraper.SOURCE_TYPES)
    if unknown:
        raise SystemExit(f"Unknown source type: {', '.join(sorted(unknown))}. Known: {', '.join(scraper.SOURCE_TYPES)}")
    config = scraper.load_config()
    ps2_keys = {scraper.source_key(s) for s in config["sources"] if s["enabled"] and s["role"] == scraper.PS2_ROLE}
    failed, games, last_board = [], Counter(), None
    with requests.Session() as session:
        session.headers["User-Agent"] = scraper.USER_AGENT
        matcher = scraper.TitleMatcher(scraper.load_ps2_titles(session))
        jobs = [job for job in scraper.build_jobs(config) if job["type"] in wanted]
        print(f"Trying {len(jobs)} sources ({', '.join(sorted(wanted))}) against PS2 titles ({matcher.summary()})")
        for job in jobs:
            print()
            report.append((f"{job['sources'][0]['name']} [{job['type']}]", []))
            print(f"{job['sources'][0]['name']}  [{job['type']}]  {job['url']}")
            try:
                if job["type"] == scraper.BOARD_TYPE:
                    if last_board is not None:
                        time.sleep(max(0.0, scraper.BOARD_REQUEST_GAP - (time.monotonic() - last_board)))
                    last_board = time.monotonic()
                    found = try_board(session, job, matcher, ps2_keys)
                else:
                    found = try_feed(session, job, matcher, ps2_keys)
            except (requests.RequestException, ValueError) as error:
                failed.append(job["sources"][0]["name"])
                say(f"  FAILED: {scraper.feed_error(error)}")
                if job["type"] != scraper.BOARD_TYPE and scraper.feed_error(error) == "HTTP 403":
                    # Is it this machine that is refused, or the name the scraper gives? One more
                    # request under a plain feed-reader name tells the two apart.
                    try:
                        again = requests.get(job["url"], timeout=scraper.REQUEST_TIMEOUT, headers={"User-Agent": READER_NAME})
                        say(f"  as a feed reader: HTTP {again.status_code}, {len(again.content)} bytes, "
                            f"server {again.headers.get('server', '?')}, cf-mitigated {again.headers.get('cf-mitigated', '-')}")
                    except requests.RequestException as second:
                        say(f"  as a feed reader: {scraper.feed_error(second)}")
                continue
            if job["type"] == scraper.BOARD_TYPE:
                games.update(found)
                say("  games: " + ", ".join(f"{title} x{count}" if count > 1 else title
                                            for title, count in found.most_common(GAMES_SHOWN))
                    + (f" and {len(found) - GAMES_SHOWN} more" if len(found) > GAMES_SHOWN else ""))
    if games:
        print()
        report.append(("Across the boards [all]", []))
        say(f"{sum(games.values())} mentions of {len(games)} games. Most named: "
            + ", ".join(f"{title} x{count}" for title, count in games.most_common(60)))
        say(f"In threads started in the last {scraper.RETENTION_DAYS} days, which is what enters the feed: "
            f"{sum(entering.values())} mentions of {len(entering)} games"
            + (": " + ", ".join(f"{title} x{count}" for title, count in entering.most_common(60)) if entering else ""))
    publish()
    if failed:
        raise SystemExit(f"\n{len(failed)} of {len(jobs)} sources could not be read: {', '.join(failed)}")
    print(f"\nAll {len(jobs)} sources answered.")


if __name__ == "__main__":
    main()
