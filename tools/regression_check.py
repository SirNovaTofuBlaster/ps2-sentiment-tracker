"""Regression check for scraper changes.

Runs the scraper from a git ref (default: origin/main) and the scraper in the working tree on
the SAME feed content and compares the two snapshots item by item:

    python tools/regression_check.py                 # compare with origin/main
    python tools/regression_check.py --ref HEAD~1    # any git ref
    python tools/regression_check.py --offline       # reuse feeds downloaded by an earlier run
    python tools/regression_check.py --types news    # only the news feeds (or only reddit)

What is compared: the news and Reddit feeds (the "core" feeds both versions know). If the
reference scraper still has the feed lists hard-coded (NEWS_FEEDS / SUBREDDIT_GROUPS) those are
used for it; otherwise both scrapers read the news/Reddit sources of the working tree's
feeds.json. Feed content is downloaded once (Reddit requests 65 s apart) into a cache folder in
the system temp directory, then both scrapers run offline from it with the same PS2 title list,
an empty previous snapshot and temporary output folders, so the repository's data/ is never
touched. Fields only the newer scraper writes (source_type, feed) are ignored.

Exit code 0 means the snapshots are identical.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
NEW_FIELDS = ("source_type", "feed")
REDDIT_SPACING = 65  # seconds between Reddit requests (about one unauthenticated request a minute)


def notice(title, text):
    """The result again as a notice on the run, where it can be read without the log."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        data = lambda value: value.replace("%", "%25").replace("\r", " ").replace("\n", " ")  # noqa: E731
        prop = lambda value: data(value).replace(":", "%3A").replace(",", "%2C")  # noqa: E731
        print(f"::notice title={prop('Regression check ' + title)}::{data(text)}")


def load_module(name, source, folder):
    path = folder / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def core_config(new, types=("news", "reddit")):
    """The working tree's feeds.json reduced to its enabled news and Reddit sources (or one of the two)."""
    config = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    config["sources"] = [s for s in config["sources"] if s["type"] in types and s["enabled"]]
    # Both runs fetch everything (FULL_RUN), so the clocks don't matter; an older reference may
    # not accept the quarter- and half-hour ones.
    config.pop("poll_every_hours", None)
    problems = new.validate_config(config)
    if problems:
        raise SystemExit("feeds.json is invalid: " + "; ".join(problems[:3]))
    return config


def download(urls, cache, user_agent, offline):
    index_path = cache / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    missing = [url for url in urls if url not in index]
    if missing and offline:
        raise SystemExit(f"--offline: {len(missing)} feeds are not cached yet, e.g. {missing[0]}")
    last_reddit = 0.0
    with requests.Session() as session:
        session.headers["User-Agent"] = user_agent
        for url in missing:
            if "reddit.com" in url:
                wait = REDDIT_SPACING - (time.time() - last_reddit)
                if last_reddit and wait > 0:
                    time.sleep(wait)
                last_reddit = time.time()
            response = session.get(url, timeout=30)
            name = hashlib.sha1(url.encode()).hexdigest() + ".xml"
            (cache / name).write_bytes(response.content)
            index[url] = {"status": response.status_code, "file": name}
            index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
            print(f"  saved {response.status_code} {len(response.content):>8} bytes  {url[:100]}")
    return index


def run_offline(module, index, cache, titles, extra_patches):
    def fake_fetch(session, url, retry_rate_limit=True):
        entry = index[url]
        if entry["status"] != 200:
            response = requests.Response()
            response.status_code = entry["status"]
            raise requests.HTTPError(f"{entry['status']} Client Error: for url: {url}", response=response)
        return feedparser.parse((cache / entry["file"]).read_bytes())

    data = Path(tempfile.mkdtemp(prefix="regression-data-"))
    patches = [mock.patch.object(module, "DATA_DIR", data),
               mock.patch.object(module, "OUTPUT_PATH", data / "sentiment_feed.json"),
               mock.patch.object(module, "fetch_feed", side_effect=fake_fetch),
               mock.patch.object(module, "load_ps2_titles", return_value=titles),
               *extra_patches(data)]
    for name in ("STATUS_PATH", "YOUTUBE_IDS_PATH", "POLL_STATE_PATH"):  # never the repository's data/
        if hasattr(module, name):
            patches.append(mock.patch.object(module, name, data / f"{name.lower()}.json"))
    for name in ("REDDIT_REQUEST_GAP", "BOARD_REQUEST_GAP"):  # the feeds are on disk: no need to wait
        if hasattr(module, name):
            patches.append(mock.patch.object(module, name, 0))
    for patch in patches:
        patch.start()
    try:
        with mock.patch("builtins.print"):
            module.run_scraper()
    finally:
        for patch in reversed(patches):
            patch.stop()
    return json.loads((data / "sentiment_feed.json").read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ref", default="origin/main", help="git ref of the reference scraper (default: origin/main)")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "ps2-regression-feeds",
                        help="folder for downloaded feeds")
    parser.add_argument("--offline", action="store_true", help="only use feeds already in the cache")
    parser.add_argument("--types", default="news,reddit", help="which core feeds to compare: news, reddit or both")
    args = parser.parse_args()
    types = tuple(kind.strip() for kind in args.types.split(",") if kind.strip())
    if not types or set(types) - {"news", "reddit"}:
        raise SystemExit("--types takes news, reddit or news,reddit")

    sys.path.insert(0, str(ROOT))
    import scraper as new  # noqa: E402  (the working tree)

    work = Path(tempfile.mkdtemp(prefix="regression-"))
    source = subprocess.run(["git", "-C", str(ROOT), "show", f"{args.ref}:scraper.py"], capture_output=True,
                            text=True, encoding="utf-8", check=True).stdout
    old = load_module("scraper_reference", source, work)
    config = core_config(new, types)
    config_path = work / "feeds.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    if hasattr(old, "RSS_FEEDS"):  # feed lists hard-coded in the reference scraper
        old_urls = list(old.RSS_FEEDS)
        old_patches = lambda data: []  # noqa: E731
    else:
        old_urls = [job["url"] for job in old.build_jobs(config)]
        old_patches = lambda data: [mock.patch.object(old, "FEEDS_PATH", config_path)]  # noqa: E731
    new_urls = [job["url"] for job in new.build_jobs(config)]
    if old_urls != new_urls:
        print("Fetch plans differ:")
        print("  only in reference:", [u for u in old_urls if u not in new_urls])
        print("  only in working tree:", [u for u in new_urls if u not in old_urls])
        notice(f"{'/'.join(types)}: fetch plans differ", f"{len(old_urls)} requests before, {len(new_urls)} now")
        sys.exit(1)
    print(f"Both versions fetch the same {len(new_urls)} {'/'.join(types)} feeds.")

    args.cache.mkdir(parents=True, exist_ok=True)
    index = download(new_urls, args.cache, new.USER_AGENT, args.offline)
    titles = sorted(new.read_cached_titles() | set(new.FALLBACK_TITLES))

    with mock.patch.dict("os.environ", {"FULL_RUN": "1"}):
        reference = run_offline(old, index, args.cache, titles, old_patches)
        current = run_offline(new, index, args.cache, titles,
                              lambda data: [mock.patch.object(new, "FEEDS_PATH", config_path)])

    stripped = [{k: v for k, v in item.items() if k not in NEW_FIELDS} for item in current["items"]]
    same = stripped == [{k: v for k, v in item.items() if k not in NEW_FIELDS} for item in reference["items"]]
    print(f"reference ({args.ref}): {len(reference['items'])} items, total_tracked_feeds={reference['total_tracked_feeds']}")
    print(f"working tree:          {len(current['items'])} items, total_tracked_feeds={current['total_tracked_feeds']}")
    print(f"PS2 matches:   {sum(1 for i in reference['items'] if i['matched_game'])} vs {sum(1 for i in stripped if i['matched_game'])}")
    print(f"remaster flags: {sum(i['is_remaster_rumor'] for i in reference['items'])} vs {sum(i['is_remaster_rumor'] for i in stripped)}")
    if same and reference["total_tracked_feeds"] == current["total_tracked_feeds"]:
        print("IDENTICAL: same items, same order (ignoring fields only the new version writes).")
        notice(f"{'/'.join(types)}: IDENTICAL", f"{len(current['items'])} items from {len(new_urls)} feeds")
        return
    first = next(((a, b) for a, b in zip(reference["items"], stripped) if a != b), None)
    if first:
        print("FIRST DIFFERENCE\n  reference:", first[0], "\n  working:  ", first[1])
    notice(f"{'/'.join(types)}: DIFFERENT",
           f"{len(reference['items'])} vs {len(current['items'])} items; first difference in: "
           + (", ".join(key for key in first[0] if first[0].get(key) != first[1].get(key)) if first else "the item count"))
    sys.exit(1)


if __name__ == "__main__":
    main()
