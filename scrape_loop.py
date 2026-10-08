"""Keeps the scraper running for most of the six hours a GitHub Actions job may last.

GitHub starts scheduled workflows late or not at all: in this repository's first week about one
hourly run in five happened. So instead of one run an hour, one run of the scraper workflow stays
up for LOOP_MINUTES. It starts scraper.py whenever a source type is due (feeds.json
"poll_every_hours", remembered in data/poll_state.json), commits what that writes to data/, asks
for the eBay prices job once an hour, and at the end starts its own successor. The hourly
schedule in the workflow is only a backstop that starts a loop when none is running.

    python scrape_loop.py              # in GitHub Actions (scraper.yml)
    FULL_FIRST=1 python scrape_loop.py # the first round fetches every source, as "Run scraper now" does

Each round runs scraper.py in a process of its own, so a round that fails (a site refusing us,
feeds.json saved with a mistake) is reported and waited out, and the loop carries on.
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scraper

ROOT = Path(__file__).resolve().parent
LOOP_MINUTES = 330                       # a round starts no later than this after the loop began...
ROUND_RESERVE = timedelta(minutes=15)    # ...and only with this much left (a Reddit round takes ~10)
MIN_GAP = 120                            # seconds between two rounds, whatever is due
MAX_WAIT = 900                           # seconds asleep at most before looking again
FAILED_WAIT = 900                        # seconds to wait after a round that failed
EBAY_EVERY = timedelta(hours=1)          # how often the eBay prices job is asked for
SCRAPER_WORKFLOW = "scraper.yml"
EBAY_WORKFLOW = "ebay.yml"
COMMIT_MESSAGE = "Auto-update sentiment data [skip ci]"
PUSH_ATTEMPTS = 3


def utc_now():
    return datetime.now(timezone.utc)


def say(text):
    print(f"[{utc_now().strftime('%H:%M:%S')}] {text}", flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def branch():
    return os.environ.get("GITHUB_REF_NAME") or "main"


def sync():
    """Brings in what other jobs committed (the archive, eBay prices, a feeds.json saved from the
    dashboard), so that the next round starts from it and its commit goes on top."""
    if git("pull", "--rebase", "--autostash", "--quiet", "origin", branch()).returncode != 0:
        git("rebase", "--abort")
        say("Could not bring in the latest commits; trying again next round.")
        return False
    return True


def save():
    """Commits and pushes data/ when a round changed it. True when something was pushed."""
    git("add", "data/")
    if git("diff", "--staged", "--quiet").returncode == 0:
        return False
    if git("commit", "--quiet", "-m", COMMIT_MESSAGE).returncode != 0:
        say("Could not commit the new data.")
        return False
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        pulled = git("pull", "--rebase", "--quiet", "origin", branch()).returncode == 0
        if pulled and git("push", "--quiet", "origin", f"HEAD:{branch()}").returncode == 0:
            return True
        git("rebase", "--abort")
        say(f"Push attempt {attempt} failed.")
        time.sleep(5)
    say("Push failed; the commit goes up with the next round's.")
    return False


def active_types(config):
    """Source types that have at least one source switched on: only those are ever due."""
    return [kind for kind in scraper.SOURCE_TYPES
            if any(src["enabled"] and src["type"] == kind for src in config["sources"])]


def next_round(config, polls, now):
    """When the next round is due: the earliest moment any active type is due, or now when one
    has never been fetched. None when no source is switched on at all."""
    moments = []
    for kind in active_types(config):
        when = scraper.next_poll(config, kind, polls)
        moments.append(now if when is None else when)
    return min(moments) if moments else None


def run_round(full):
    env = {**os.environ, "FULL_RUN": "1" if full else ""}
    return subprocess.run([sys.executable, "scraper.py"], cwd=ROOT, env=env).returncode


def start(workflow, **inputs):
    """Starts a workflow on this repository (GitHub lets a workflow's own token do this)."""
    if not os.environ.get("GH_TOKEN"):
        say(f"No GH_TOKEN: not starting {workflow}.")
        return False
    fields = [part for key, value in inputs.items() for part in ("-f", f"{key}={value}")]
    done = subprocess.run(["gh", "workflow", "run", workflow, "--ref", branch(), *fields],
                          cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        say(f"Could not start {workflow}: {(done.stderr or done.stdout).strip()[:200]}")
        return False
    say(f"Started {workflow}.")
    return True


def main():
    began = utc_now()
    stop_at = began + timedelta(minutes=LOOP_MINUTES)
    full = os.environ.get("FULL_FIRST") == "1"
    last_ebay = None
    rounds = 0
    say(f"Running until {stop_at.strftime('%H:%M')} UTC" + (", starting with every source." if full else "."))
    while utc_now() + ROUND_RESERVE <= stop_at:
        sync()
        try:
            config = scraper.load_config()
        except SystemExit as problem:   # feeds.json is unreadable or invalid: wait for a fix
            say(f"feeds.json cannot be used: {problem}")
            time.sleep(FAILED_WAIT)
            continue
        now = utc_now()
        due_at = now if full else next_round(config, scraper.load_json_dict(scraper.POLL_STATE_PATH), now)
        if due_at is None:
            say("No source is switched on.")
            time.sleep(MAX_WAIT)
            continue
        if due_at > now:
            time.sleep(min(MAX_WAIT, max(1.0, (due_at - now).total_seconds())))
            continue
        rounds += 1
        code = run_round(full)
        full = False
        saved = save()
        say(f"Round {rounds}: {'finished' if code == 0 else f'failed (exit {code})'}"
            f"{', data pushed' if saved else ', nothing new to push'}.")
        if last_ebay is None or utc_now() - last_ebay >= EBAY_EVERY:
            start(EBAY_WORKFLOW)
            last_ebay = utc_now()
        time.sleep(FAILED_WAIT if code != 0 else MIN_GAP)
    say(f"{rounds} rounds done; handing over to the next run.")
    start(SCRAPER_WORKFLOW, mode="continue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
