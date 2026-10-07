"""Tries enabled sources against the live sites and prints what the scraper would make of
them. Nothing is written.

    python tools/try_sources.py forum 4chan     # every enabled source of these types
    python tools/try_sources.py                  # every enabled source that is not news or Reddit

Use it before adding a source, and when one looks wrong: it shows whether the site answers
from this machine (GitHub's runners are not treated like a home connection), how many
entries come back and which PS2 games they name. For 4chan boards it prints counts and game
names only, never anything a poster wrote. Exits non-zero when a source could not be read."""

import sys
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import scraper  # noqa: E402

GAMES_SHOWN = 40


def try_feed(session, job, matcher, ps2_keys):
    feed = scraper.fetch_feed(session, job["url"], retry_rate_limit=False)
    if feed.get("bozo") and not feed.entries:
        raise ValueError("unreadable feed")
    entries = scraper.select_entries(feed, job["type"])
    items = [scraper.analyze_entry(e, feed, job, matcher, {}, ps2_keys, scraper.shared_links(feed, job["type"]))
             for e in entries]
    stamps = sorted(item["timestamp"] for item in items)
    print(f"  {len(items)} entries, {sum(1 for i in items if i['matched_game'])} naming a PS2 game"
          + (f", from {stamps[0]} to {stamps[-1]}" if stamps else ""))
    for item in items:
        if item["matched_game"]:
            print(f"    {item['matched_game']} ({item['matched_in']}, {item['match_method']} {item['match_score']:.0f})"
                  f" <- {item['headline'][:90]}")
    return Counter(item["matched_game"] for item in items if item["matched_game"])


def try_board(session, job, matcher, ps2_keys):
    threads = scraper.fetch_board(session, job["url"])
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
    print(f"  {len(live)} live threads ({len(with_subject)} with a subject), started from "
          f"{stamps[0] if stamps else '?'} to {stamps[-1] if stamps else '?'}")
    print(f"  {len(items)} name a PS2 game: {sum(1 for i in items if i['matched_in'] == 'title')} in the subject, "
          f"{sum(1 for i in items if i['matched_in'] == 'body')} in the comment; {strict} also say PS2")
    methods = Counter(f"{i['match_method']}" for i in items)
    print(f"  how they matched: {dict(methods)}; threads naming more than one game: "
          f"{sum(1 for i in items if len(i['matched_games']) > 1)}")
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
            print(f"\n{job['sources'][0]['name']}  [{job['type']}]  {job['url']}")
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
                print(f"  FAILED: {scraper.feed_error(error)}")
                continue
            if job["type"] == scraper.BOARD_TYPE:
                games.update(found)
                print("  games: " + ", ".join(f"{title} x{count}" if count > 1 else title
                                              for title, count in found.most_common(GAMES_SHOWN))
                      + (f" and {len(found) - GAMES_SHOWN} more" if len(found) > GAMES_SHOWN else ""))
    if games:
        print(f"\nAcross the boards: {sum(games.values())} mentions of {len(games)} games. Most named: "
              + ", ".join(f"{title} x{count}" for title, count in games.most_common(60)))
    if failed:
        raise SystemExit(f"\n{len(failed)} of {len(jobs)} sources could not be read: {', '.join(failed)}")
    print(f"\nAll {len(jobs)} sources answered.")


if __name__ == "__main__":
    main()
