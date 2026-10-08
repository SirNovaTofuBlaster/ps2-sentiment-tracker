"""Offline tests for scrape_loop.py and the scraper workflow that runs it.

The loop is driven by a fake clock that only moves when the loop sleeps or a round runs; git,
scraper.py and GitHub are stood in for, so nothing here touches the network or the repository."""

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scrape_loop  # noqa: E402
import scraper  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "scraper.yml"
START = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
CLOCKS = {"news": 0.5, "reddit": 1, "forum": 0.5, "4chan": 0.25, "youtube": 1, "podcast": 6}


def config(clocks=CLOCKS, kinds=scraper.SOURCE_TYPES, enabled=True):
    return {"poll_every_hours": dict(clocks),
            "sources": [{"type": kind, "enabled": enabled} for kind in kinds]}


class NextRoundTests(unittest.TestCase):
    def test_a_type_never_fetched_is_due_now_and_otherwise_the_earliest_clock_wins(self):
        polls = {kind: "2026-10-08 09:00 UTC" for kind in scraper.SOURCE_TYPES}
        now = START + timedelta(minutes=1)
        self.assertEqual(scrape_loop.next_round(config(), polls, now), START + timedelta(minutes=14, seconds=15))
        self.assertEqual(scrape_loop.next_round(config(), {k: v for k, v in polls.items() if k != "podcast"}, now), now)

    def test_only_types_with_a_source_switched_on_count(self):
        polls = {"news": "2026-10-08 09:00 UTC"}
        self.assertEqual(scrape_loop.next_round(config(kinds=["news"]), polls, START), START + timedelta(minutes=28, seconds=30))
        mixed = config(kinds=["news"])
        mixed["sources"].append({"type": "4chan", "enabled": False})
        self.assertEqual(scrape_loop.active_types(mixed), ["news"], "a board that is switched off is never due")
        self.assertIsNone(scrape_loop.next_round(config(enabled=False), {}, START))


class LoopTests(unittest.TestCase):
    """main() against a fake clock. A round 'fetches' whatever scraper.due_types() says is due."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.polls_path = Path(folder.name) / "poll_state.json"
        self.clock = [START]
        self.rounds, self.started, self.slept = [], [], []
        self.config = config()
        self.round_code = 0
        self.round_minutes = 1

        def sleep(seconds):
            self.slept.append(seconds)
            self.clock[0] += timedelta(seconds=seconds)

        def run_round(full, first=False):
            now = self.clock[0]
            polls = scraper.load_json_dict(self.polls_path)
            with mock.patch.dict(os.environ, {"FULL_RUN": "1" if full else ""}):
                due = scraper.due_types(self.config, now, polls)
            due &= set(scrape_loop.active_types(self.config))
            self.rounds.append((now, full, sorted(due)))
            if self.round_code == 0:
                polls.update({kind: now.strftime(scraper.TIMESTAMP_FORMAT) for kind in due})
                self.polls_path.write_text(json.dumps(polls), encoding="utf-8")
            self.clock[0] += timedelta(minutes=self.round_minutes)
            return self.round_code

        def start(workflow, **inputs):
            self.started.append((self.clock[0], workflow, inputs))
            return True

        def load_config():
            if isinstance(self.config, BaseException):
                raise self.config
            return self.config

        self.saves = []

        def save(force=False):
            self.saves.append((self.clock[0], force))
            return True

        for name, value in (("utc_now", lambda: self.clock[0]), ("sync", lambda: True), ("save", save),
                            ("run_round", run_round), ("start", start)):
            patcher = mock.patch.object(scrape_loop, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (mock.patch.object(scrape_loop.time, "sleep", sleep),
                        mock.patch.object(scraper, "load_config", load_config),
                        mock.patch.object(scraper, "POLL_STATE_PATH", self.polls_path),
                        mock.patch.object(scrape_loop, "say", lambda text: None),
                        mock.patch.dict(os.environ, {"GITHUB_REF_NAME": "main"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_loop(self, full=False):
        with mock.patch.dict(os.environ, {"FULL_FIRST": "1" if full else ""}):
            return scrape_loop.main()

    def at(self, moment):
        return round((moment - START).total_seconds() / 60, 1)

    def test_each_type_is_fetched_on_its_own_clock_for_five_and_a_half_hours(self):
        self.assertEqual(self.run_loop(), 0)
        first = self.rounds[0]
        self.assertEqual((self.at(first[0]), first[1], first[2]), (0, False, sorted(scraper.SOURCE_TYPES)),
                         "nothing remembered: everything is due at once")
        boards = [self.at(when) for when, _, due in self.rounds if "4chan" in due]
        gaps = [round(b - a, 1) for a, b in zip(boards, boards[1:])]
        self.assertTrue(all(14 <= gap <= 16 for gap in gaps), gaps)
        self.assertGreaterEqual(len(boards), 20, "about four rounds of the boards an hour")
        news = [self.at(when) for when, _, due in self.rounds if "news" in due]
        self.assertTrue(all(27 <= b - a <= 32 for a, b in zip(news, news[1:])), news)
        podcasts = [self.at(when) for when, _, due in self.rounds if "podcast" in due]
        self.assertEqual(len(podcasts), 1, "every six hours: once in this run")
        last = self.rounds[-1][0]
        self.assertLessEqual(last, START + timedelta(minutes=scrape_loop.LOOP_MINUTES) - scrape_loop.ROUND_RESERVE)
        self.assertGreater(last, START + timedelta(minutes=300))

    def test_rounds_keep_a_gap_and_the_eBay_job_is_asked_for_once_an_hour(self):
        self.run_loop()
        times = [when for when, _, _ in self.rounds]
        self.assertTrue(all((b - a).total_seconds() >= scrape_loop.MIN_GAP for a, b in zip(times, times[1:])))
        ebay = [when for when, workflow, _ in self.started if workflow == scrape_loop.EBAY_WORKFLOW]
        self.assertEqual(self.at(ebay[0]), 1.0, "after the first round")
        self.assertTrue(all(timedelta(hours=1) <= b - a < timedelta(hours=1, minutes=20) for a, b in zip(ebay, ebay[1:])))
        self.assertIn(len(ebay), (5, 6))
        self.assertTrue(all(inputs == {} for when, workflow, inputs in self.started if workflow == scrape_loop.EBAY_WORKFLOW))

    def test_at_the_end_it_saves_everything_and_starts_its_successor_to_carry_on(self):
        self.run_loop()
        when, workflow, inputs = self.started[-1]
        self.assertEqual((workflow, inputs), (scrape_loop.SCRAPER_WORKFLOW, {"mode": "continue"}))
        self.assertLessEqual(when, START + timedelta(minutes=scrape_loop.LOOP_MINUTES))
        self.assertEqual(sum(1 for _, workflow, _ in self.started if workflow == scrape_loop.SCRAPER_WORKFLOW), 1)
        self.assertEqual(self.saves[-1], (when, True), "the bookkeeping goes up with the hand-over")
        self.assertEqual([force for _, force in self.saves[:-1]], [False] * (len(self.saves) - 1))

    def test_the_last_round_is_not_followed_by_a_pointless_wait(self):
        self.run_loop()
        last_round_end = self.rounds[-1][0] + timedelta(minutes=self.round_minutes)
        self.assertLess(self.started[-1][0] - last_round_end, timedelta(seconds=scrape_loop.MIN_GAP))

    def test_after_an_error_the_chain_still_goes_on_but_not_after_a_cancel(self):
        def broken(*args, **kwargs):
            raise RuntimeError("something went wrong")
        with mock.patch.object(scrape_loop, "run_round", broken), self.assertRaises(RuntimeError):
            self.run_loop()
        self.assertEqual(self.started[-1][1:], (scrape_loop.SCRAPER_WORKFLOW, {"mode": "continue"}))
        self.started.clear()

        def cancelled(*args, **kwargs):
            raise KeyboardInterrupt
        with mock.patch.object(scrape_loop, "run_round", cancelled):
            self.assertEqual(self.run_loop(), 130)
        self.assertEqual(self.started, [], "a cancelled run was replaced or stopped on purpose: no successor")

    def test_a_run_on_another_branch_starts_neither_the_eBay_job_nor_a_successor(self):
        with mock.patch.dict(os.environ, {"GITHUB_REF_NAME": "test-branch"}):
            self.run_loop()
        self.assertTrue(self.rounds)
        self.assertEqual(self.started, [])

    def test_run_now_fetches_everything_first_whatever_was_fetched_lately(self):
        recent = START.strftime(scraper.TIMESTAMP_FORMAT)
        self.polls_path.write_text(json.dumps({kind: recent for kind in scraper.SOURCE_TYPES}), encoding="utf-8")
        self.run_loop(full=True)
        self.assertEqual(self.rounds[0][:2], (START, True))
        self.assertEqual([full for _, full, _ in self.rounds].count(True), 1, "only the first round")
        self.assertNotIn("podcast", self.rounds[1][2])

    def test_a_loop_that_carries_on_waits_for_what_is_due(self):
        then = (START - timedelta(minutes=5)).strftime(scraper.TIMESTAMP_FORMAT)
        self.polls_path.write_text(json.dumps({kind: then for kind in scraper.SOURCE_TYPES}), encoding="utf-8")
        self.run_loop()
        self.assertEqual((self.at(self.rounds[0][0]), self.rounds[0][2]), (9.2, ["4chan"]))

    def test_a_failed_round_is_waited_out_not_repeated_at_once(self):
        self.round_code = 1
        self.run_loop()
        times = [when for when, _, _ in self.rounds]
        self.assertTrue(all((b - a).total_seconds() >= scrape_loop.FAILED_WAIT for a, b in zip(times, times[1:])))
        self.assertLessEqual(len(times), 22, "about one try every quarter of an hour, not a storm")

    def test_an_invalid_feeds_json_is_waited_out(self):
        self.config = SystemExit("feeds.json is invalid")
        self.run_loop()
        self.assertEqual(self.rounds, [])
        self.assertTrue(all(seconds == scrape_loop.FAILED_WAIT for seconds in self.slept))
        self.assertEqual(self.started[-1][1:], (scrape_loop.SCRAPER_WORKFLOW, {"mode": "continue"}))

    def test_a_long_wait_is_taken_in_quarter_hours_so_a_saved_feeds_json_is_seen(self):
        self.config = config(kinds=["podcast"])
        self.polls_path.write_text(json.dumps({"podcast": START.strftime(scraper.TIMESTAMP_FORMAT)}), encoding="utf-8")
        self.run_loop()
        self.assertTrue(self.slept and max(self.slept) <= scrape_loop.MAX_WAIT, max(self.slept))
        self.assertEqual(self.rounds, [], "due after this run's last round may start: the successor fetches it")

    def test_with_every_source_switched_off_nothing_runs(self):
        self.config = config(enabled=False)
        self.run_loop()
        self.assertEqual(self.rounds, [])

    def test_a_slow_round_does_not_run_past_the_job_limit(self):
        self.round_minutes = 12
        self.run_loop()
        end = self.rounds[-1][0] + timedelta(minutes=12)
        self.assertLessEqual(end, START + timedelta(minutes=scrape_loop.LOOP_MINUTES))
        self.assertLess(scrape_loop.LOOP_MINUTES + 15, 355, "the workflow's time limit leaves room to hand over")


class StartTests(unittest.TestCase):
    def test_without_a_token_nothing_is_started(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": ""}), mock.patch.object(scrape_loop.subprocess, "run") as run, \
                mock.patch.object(scrape_loop, "say"):
            self.assertFalse(scrape_loop.start("ebay.yml"))
        run.assert_not_called()

    def test_the_successor_is_asked_for_on_this_branch_with_its_mode(self):
        done = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.dict(os.environ, {"GH_TOKEN": "t", "GITHUB_REF_NAME": "main"}), \
                mock.patch.object(scrape_loop.subprocess, "run", return_value=done) as run, mock.patch.object(scrape_loop, "say"):
            self.assertTrue(scrape_loop.start("scraper.yml", mode="continue"))
        self.assertEqual(run.call_args.args[0], ["gh", "workflow", "run", "scraper.yml", "--ref", "main", "-f", "mode=continue"])

    def test_a_round_is_scraper_py_in_a_process_of_its_own_with_a_time_limit(self):
        with mock.patch.object(scrape_loop.subprocess, "run", return_value=mock.Mock(returncode=3)) as run:
            self.assertEqual(scrape_loop.run_round(True, first=True), 3)
            env = run.call_args.kwargs["env"]
            self.assertEqual((env["FULL_RUN"], env["TITLES_FROM_CACHE"]), ("1", ""), "the first round downloads the title index")
            scrape_loop.run_round(False, first=False)
            env = run.call_args.kwargs["env"]
            self.assertEqual((env["FULL_RUN"], env["TITLES_FROM_CACHE"]), ("", "1"))
        self.assertEqual(run.call_args.args[0][1:], ["scraper.py"])
        self.assertEqual(run.call_args.kwargs["timeout"], scrape_loop.ROUND_TIMEOUT)
        expired = scrape_loop.subprocess.TimeoutExpired("scraper.py", 1)
        with mock.patch.object(scrape_loop.subprocess, "run", side_effect=expired), mock.patch.object(scrape_loop, "say"):
            self.assertEqual(scrape_loop.run_round(False, first=False), 124)
        # The last round starts with ROUND_RESERVE left and may run ROUND_TIMEOUT: with five
        # minutes to hand over, that stays inside the workflow's 355-minute limit.
        latest_end = (timedelta(minutes=scrape_loop.LOOP_MINUTES) - scrape_loop.ROUND_RESERVE
                      + timedelta(seconds=scrape_loop.ROUND_TIMEOUT) + timedelta(minutes=5))
        self.assertLessEqual(latest_end, timedelta(minutes=355))


class GitTests(unittest.TestCase):
    """sync() and save() against a fake git that answers each command as told."""

    def setUp(self):
        self.calls, self.answers = [], {}

        def git(*args):
            self.calls.append(args)
            code, out = self.answers.get(args[0], (0, ""))
            if callable(code):
                code = code()
            return mock.Mock(returncode=code, stdout=out, stderr="")

        for patcher in (mock.patch.object(scrape_loop, "git", git), mock.patch.object(scrape_loop, "say"),
                        mock.patch.object(scrape_loop.time, "sleep"), mock.patch.object(scrape_loop, "_last_commit", None),
                        mock.patch.dict(os.environ, {"GITHUB_REF_NAME": "main"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def commands(self):
        return [" ".join(call) for call in self.calls]

    def test_sync_rebases_with_the_round_set_aside_and_gives_up_cleanly(self):
        self.assertTrue(scrape_loop.sync())
        self.assertEqual(self.commands(), ["pull --rebase --autostash --quiet origin main"])
        self.calls.clear()
        self.answers["pull"] = (1, "")
        self.assertFalse(scrape_loop.sync())
        self.assertEqual(self.commands(), ["pull --rebase --autostash --quiet origin main", "rebase --abort"])

    def test_new_items_are_committed_from_data_only_and_pushed_on_top_of_main(self):
        self.answers["diff"] = (0, "data/sentiment_feed.json\ndata/poll_state.json\n")
        self.assertTrue(scrape_loop.save())
        self.assertEqual(self.commands(), [
            "add data/", "diff --staged --name-only", f"commit --quiet -m {scrape_loop.COMMIT_MESSAGE}",
            "pull --rebase --quiet origin main", "push --quiet origin HEAD:main"])

    def test_a_push_that_loses_a_race_is_rebased_and_tried_again(self):
        self.answers["diff"] = (0, "data/sentiment_feed.json\n")
        pushes = iter([1, 0])
        self.answers["push"] = (lambda: next(pushes), "")
        self.assertTrue(scrape_loop.save())
        self.assertEqual(self.commands()[3:], ["pull --rebase --quiet origin main", "push --quiet origin HEAD:main", "rebase --abort",
                                               "pull --rebase --quiet origin main", "push --quiet origin HEAD:main"])

    def test_bookkeeping_alone_goes_up_once_an_hour(self):
        self.answers["diff"] = (0, "data/poll_state.json\ndata/feed_status.json\n")
        clock = [START]
        with mock.patch.object(scrape_loop, "utc_now", lambda: clock[0]):
            self.assertTrue(scrape_loop.save(), "nothing committed yet in this run: it goes up")
            clock[0] += timedelta(minutes=15)
            self.calls.clear()
            self.assertFalse(scrape_loop.save())
            self.assertEqual(self.commands(), ["add data/", "diff --staged --name-only", "reset --quiet"],
                             "left in the working tree for the next commit")
            self.assertTrue(scrape_loop.save(force=True), "the hand-over takes it along")
            clock[0] += timedelta(minutes=59)
            self.assertFalse(scrape_loop.save())
            clock[0] += timedelta(minutes=2)
            self.assertTrue(scrape_loop.save())
        self.answers["diff"] = (0, "")
        self.assertFalse(scrape_loop.save())

    def test_branch_is_the_one_the_run_is_on(self):
        with mock.patch.dict(os.environ, {"GITHUB_REF_NAME": "test"}):
            self.assertEqual(scrape_loop.branch(), "test")
        with mock.patch.dict(os.environ, {"GITHUB_REF_NAME": ""}):
            self.assertEqual(scrape_loop.branch(), "main")


class ToolTests(unittest.TestCase):
    def test_the_tools_space_reddit_requests_and_never_touch_the_repositorys_data(self):
        tryer = (ROOT / "tools" / "try_sources.py").read_text(encoding="utf-8")
        self.assertIn("time.sleep(max(0.0, scraper.REDDIT_REQUEST_GAP - (time.monotonic() - last_reddit)))", tryer)
        check = (ROOT / "tools" / "regression_check.py").read_text(encoding="utf-8")
        self.assertIn('for name in ("STATUS_PATH", "YOUTUBE_IDS_PATH", "POLL_STATE_PATH"):  # never the repository\'s data/', check)
        self.assertIn("REDDIT_SPACING = 65", check)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.code = "\n".join(line for line in self.text.split("\n") if not line.strip().startswith("#"))

    def test_triggers_never_include_a_pull_request(self):
        triggers = re.findall(r"^  (\w+):", self.code.split("\non:\n")[1].split("\n\n")[0], flags=re.MULTILINE)
        self.assertEqual(triggers, ["schedule", "workflow_dispatch", "push"])
        for word in ("pull_request", "pull_request_target", "issue_comment", "workflow_run"):
            self.assertNotIn(word, self.code)
        self.assertIn("      - scrape_loop.py", self.code, "a change to the loop restarts it")

    def test_a_push_or_run_now_replaces_the_loop_and_the_schedule_and_successor_wait(self):
        self.assertIn("  group: scraper-${{ github.ref_name }}\n  cancel-in-progress: ${{ github.event_name == 'push' || "
                      "(github.event_name == 'workflow_dispatch' && inputs.mode != 'continue') }}", self.code)
        self.assertIn("FULL_FIRST: ${{ (github.event_name == 'push' || (github.event_name == 'workflow_dispatch' "
                      "&& inputs.mode != 'continue')) && '1' || '' }}", self.code)
        self.assertIn("        options: [now, continue]\n        default: now", self.code)

    def test_it_runs_the_loop_with_only_the_rights_it_needs_and_no_secrets(self):
        self.assertRegex(self.code, r"\npermissions:\n  contents: write\n  actions: write +#[^\n]*\n\n")
        self.assertIn("    timeout-minutes: 355", self.code)
        self.assertIn("python scrape_loop.py", self.code)
        self.assertIn("          ref: ${{ github.ref }}", self.code, "a run that waited starts from the latest data commit")
        self.assertNotIn("persist-credentials: false", self.code, "the loop pushes with the checkout's credentials")
        self.assertIn("  push:\n    branches: [main]", self.code)
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.code)
        self.assertNotIn("secrets.", self.code)
        self.assertIn("users.noreply.github.com", self.code)

    def test_the_successor_mode_the_loop_asks_for_is_one_the_workflow_offers(self):
        self.assertIn("options: [now, continue]", self.code)
        self.assertIn('mode="continue"', (ROOT / "scrape_loop.py").read_text(encoding="utf-8"))
        self.assertIn("inputs: { mode: 'now' }", (ROOT / "index.html").read_text(encoding="utf-8"),
                      "the dashboard's Run scraper now asks for a fresh start")


if __name__ == "__main__":
    unittest.main()
