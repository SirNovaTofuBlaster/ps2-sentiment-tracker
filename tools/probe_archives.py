"""Asks public 4chan archives (desuarchive.org, archive.4plebs.org) how they answer, from this
machine, and how their threads line up with the live 4chan catalog. Nothing is written.

    python tools/probe_archives.py

Prints status codes, headers that show whether a firewall is in the way, the archive's own
robots.txt, the NAMES of the fields in an answer, counts, and dates. Never prints anything a
poster wrote (AGENTS.md rule 12): no subject, comment or name is read into the report, only
whether a field is empty. At most one request every 2 seconds. On GitHub Actions the report is also attached to the run as notices."""

import json
import os
import re
import sys
import time

import requests

AGENT = "ps2-sentiment-tracker/1.1 (+https://github.com/SirNovaTofuBlaster/ps2-sentiment-tracker)"
GAP = 2.0
ON_GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"
ARCHIVES = [("desuarchive.org", "vr"), ("desuarchive.org", "tg"), ("archive.4plebs.org", "tg")]
report = []
_last = [0.0]


def say(heading, line):
    print(f"[{heading}] {line}")
    for name, lines in report:
        if name == heading:
            lines.append(line)
            return
    report.append((heading, [line]))


def get(url, **kw):
    time.sleep(max(0.0, GAP - (time.monotonic() - _last[0])))
    _last[0] = time.monotonic()
    return requests.get(url, headers={"User-Agent": AGENT}, timeout=30, **kw)


def describe(heading, response):
    say(heading, f"HTTP {response.status_code}, {len(response.content)} bytes, type {response.headers.get('content-type', '?')}, "
                 f"server {response.headers.get('server', '?')}, cf-mitigated {response.headers.get('cf-mitigated', '-')}, "
                 f"retry-after {response.headers.get('retry-after', '-')}, "
                 f"x-ratelimit {response.headers.get('x-ratelimit-limit', '-')}/{response.headers.get('x-ratelimit-remaining', '-')}")


def shape(value, depth=0):
    """Field names and kinds only; values are never kept."""
    if isinstance(value, dict):
        if depth >= 3:
            return "{...}"
        return "{" + ", ".join(f"{k}:{shape(v, depth + 1)}" for k, v in list(value.items())[:40]) + "}"
    if isinstance(value, list):
        return f"[{len(value)}x " + (shape(value[0], depth + 1) if value else "") + "]"
    if isinstance(value, str):
        return "str" if value else "str(empty)"
    return type(value).__name__


def threads_of(payload):
    """Thread numbers and opening-post timestamps from a FoolFuuka index/search answer, whatever its exact shape."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            num = node.get("thread_num") or (node.get("num") if node.get("op") in ("1", 1, True) else None)
            if num and str(num).isdigit():
                stamp = node.get("timestamp") or node.get("time") or 0
                found[int(num)] = int(stamp) if str(stamp).isdigit() else 0
            for key, child in node.items():
                if key.isdigit() and isinstance(child, dict) and "op" in child and isinstance(child["op"], dict):
                    walk(child["op"])
                else:
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(payload)
    return found


def day(stamp):
    return time.strftime("%Y-%m-%d", time.gmtime(stamp)) if stamp else "?"


def probe(host, board, live):
    heading = f"{host} /{board}/"
    base = f"https://{host}"
    try:
        robots = get(f"{base}/robots.txt")
        describe(heading, robots)
        if robots.status_code == 200:
            say(heading, "robots.txt: " + " | ".join(line.strip() for line in robots.text.splitlines() if line.strip())[:900])
        page = get(f"{base}/{board}/")
        describe(heading, page)
        html = page.text
        say(heading, f"board page: {len(set(re.findall(r'/' + board + r'/thread/(\d+)', html)))} distinct thread links, "
                     f"{len(re.findall(r'/page/(\d+)', html))} page links, api mentioned: {'/_/api' in html}")
        for label, path in (("index page 1", f"/_/api/chan/index/?board={board}&page=1"),
                            ("index page 2", f"/_/api/chan/index/?board={board}&page=2"),
                            ("search, openers only, newest first", f"/_/api/chan/search/?boards={board}&type=op&order=desc")):
            answer = get(base + path)
            describe(heading + f" {label}", answer)
            if answer.status_code != 200:
                continue
            try:
                payload = answer.json()
            except ValueError:
                say(heading + f" {label}", "not JSON")
                continue
            say(heading + f" {label}", "shape: " + shape(payload)[:700])
            found = threads_of(payload)
            if found:
                stamps = [s for s in found.values() if s]
                say(heading + f" {label}", f"{len(found)} threads, openers dated {day(min(stamps)) if stamps else '?'} to {day(max(stamps)) if stamps else '?'}, "
                                           f"{len(set(found) & live)} of them are in 4chan's live catalog right now")
    except requests.RequestException as error:
        say(heading, f"FAILED: {type(error).__name__}")


def main():
    live = {}
    for board in sorted({b for _, b in ARCHIVES}):
        try:
            catalog = get(f"https://a.4cdn.org/{board}/catalog.json").json()
            live[board] = {thread["no"] for page in catalog for thread in page["threads"]}
            say("4chan", f"/{board}/ catalog: {len(live[board])} live threads")
        except (requests.RequestException, ValueError, KeyError) as error:
            live[board] = set()
            say("4chan", f"/{board}/ catalog FAILED: {type(error).__name__}")
    for host, board in ARCHIVES:
        probe(host, board, live[board])
    if ON_GITHUB:
        escape = lambda text: text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")  # noqa: E731
        merged = {}
        for name, lines in report:
            merged.setdefault(name.split(" index")[0].split(" search")[0], []).extend(f"{name}: {line}" for line in lines)
        for name, lines in list(merged.items())[:10]:
            print(f"::notice title={escape(name).replace(',', '%2C').replace(':', '%3A')}::{escape(chr(10).join(lines))}")


if __name__ == "__main__":
    main()
