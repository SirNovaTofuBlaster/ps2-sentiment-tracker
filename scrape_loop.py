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
ROUND_RESERVE = timedelta(minutes=20)    # ...and only with this much left
ROUND_TIMEOUT = 1500                     # seconds a round may take (a Reddit round takes about ten minutes)
MIN_GAP = 120                            # seconds between two rounds, whatever is due
MAX_WAIT = 900                           # seconds asleep at most before looking again
FAILED_WAIT = 900                        # seconds to wait after a round that failed
EBAY_EVERY = timedelta(hours=1)          # how often the eBay prices job is asked for
# Files a round rewrites even when nothing new was found (when each type was fetched, a board's
# Last-Modified date). Alone they are committed at most once an hour, so that rounds that only
# looked do not each rebuild the website (GitHub Pages: a soft limit of ten builds an hour).
BOOKKEEPING = {"data/poll_state.json", "data/feed_status.json"}
BOOKKEEPING_EVERY = timedelta(hours=1)
MAIN = "main"                            # only a loop on main starts the eBay job and its successor
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


_last_commit = None


def save(force=False):
    """Commits and pushes data/ when a round changed it: at once when anything but the
    bookkeeping changed, otherwise at most once an hour (or when forced, at the end of a run).
    True when something was pushed."""
    global _last_commit
    git("add", "data/")
    changed = set(git("diff", "--staged", "--name-only").stdout.split())
    if not changed:
        return False
    if changed <= BOOKKEEPING and not force and _last_commit is not None and utc_now() - _last_commit < BOOKKEEPING_EVERY:
        git("reset", "--quiet")   # left in the working tree; the next commit takes them along
        return False
    if git("commit", "--quiet", "-m", COMMIT_MESSAGE).returncode != 0:
        say("Could not commit the new data.")
        return False
    _last_commit = utc_now()
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


def run_round(full, first):
    """scraper.py in a process of its own, for at most ROUND_TIMEOUT. The PS2 title index is
    downloaded in a loop's first round only; later rounds use the copy that round saved."""
    env = {**os.environ, "FULL_RUN": "1" if full else "", "TITLES_FROM_CACHE": "" if first else "1"}
    try:
        return subprocess.run([sys.executable, "scraper.py"], cwd=ROOT, env=env, timeout=ROUND_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        say(f"The round took longer than {ROUND_TIMEOUT // 60} minutes and was stopped.")
        return 124


def start(workflow, **inputs):
    """Starts a workflow on this repository (GitHub lets a workflow's own token do this)."""
    if not os.environ.get("GH_TOKEN"):
        say(f"No GH_TOKEN: not starting {workflow}.")
        return False
    fields = [part for key, value in inputs.items() for part in ("-f", f"{key}={value}")]
    try:
        done = subprocess.run(["gh", "workflow", "run", workflow, "--ref", branch(), *fields],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as problem:
        say(f"Could not start {workflow}: {type(problem).__name__}")
        return False
    if done.returncode != 0:
        say(f"Could not start {workflow}: {(done.stderr or done.stdout).strip()[:200]}")
        return False
    say(f"Started {workflow}.")
    return True


def main():
    """The loop, and at the end the hand-over to the next run: also after an error, so that the
    chain goes on, but not when the run was cancelled (a fresh loop has replaced it, or somebody
    wants it stopped)."""
    try:
        code = loop()
    except KeyboardInterrupt:   # GitHub cancels a run by interrupting it
        say("Cancelled: no successor.")
        return 130
    except Exception:
        hand_over()
        raise
    hand_over()
    return code


def hand_over():
    save(force=True)
    if branch() == MAIN:
        start(SCRAPER_WORKFLOW, mode="continue")
    else:
        say(f"A run on {branch()} does not start a successor; the loop on {MAIN} carries on.")


def loop():
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
        code = run_round(full, first=rounds == 1)
        full = False
        saved = save()
        say(f"Round {rounds}: {'finished' if code == 0 else f'failed (exit {code})'}"
            f"{', data pushed' if saved else ', nothing to push yet'}.")
        if branch() == MAIN and (last_ebay is None or utc_now() - last_ebay >= EBAY_EVERY):
            start(EBAY_WORKFLOW)
            last_ebay = utc_now()
        pause = FAILED_WAIT if code != 0 else MIN_GAP
        if utc_now() + timedelta(seconds=pause) + ROUND_RESERVE > stop_at:
            break   # no round would follow the wait: hand over now
        time.sleep(pause)
    say(f"{rounds} rounds done; handing over to the next run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
