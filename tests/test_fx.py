"""Offline tests for fx.py and its workflow: the euro rates behind the dashboard's EUR button."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fx  # noqa: E402

ECB = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time='2026-10-13'>
      <Cube currency='USD' rate='1.1188'/>
      <Cube currency='JPY' rate='176.91'/>
      <Cube currency='GBP' rate='0.84460'/>
      <Cube currency='PLN' rate='4.3768'/>
      <Cube currency='CHF' rate='0.9312'/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


class ParseTests(unittest.TestCase):
    def test_the_ecb_file_gives_the_day_and_the_four_rates(self):
        self.assertEqual(fx.parse_rates(ECB), {"date": "2026-10-13",
                                               "rates": {"USD": 1.1188, "GBP": 0.8446, "PLN": 4.3768, "CHF": 0.9312}})

    def test_a_broken_file_is_refused(self):
        for text, why in (("<html>", "not XML"), (ECB.replace("<Cube currency='GBP' rate='0.84460'/>", ""), "no rate for GBP"),
                          (ECB.replace("1.1188", "abc"), "not a number"), (ECB.replace("1.1188", "0"), "not believable"),
                          (ECB.replace("time='2026-10-13'", "time='soon'"), "no date")):
            with self.assertRaises(ValueError, msg=text[:30]) as caught:
                fx.parse_rates(text)
            self.assertIn(why, str(caught.exception))


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "data" / "fx.json"
        self.quiet = None

    def tearDown(self):
        self.dir.cleanup()

    def run_it(self, text):
        def fetcher():
            if isinstance(text, Exception):
                raise text
            return text
        return fx.main(self.path, fetcher)

    def test_the_file_is_canonical_and_holds_only_rates(self):
        self.run_it(ECB)
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual(json.loads(text), {"base": "EUR", "source": "European Central Bank euro foreign exchange reference rates",
                                            "date": "2026-10-13", "rates": {"USD": 1.1188, "GBP": 0.8446, "PLN": 4.3768, "CHF": 0.9312}})
        self.assertTrue(text.endswith("}\n"))
        self.assertNotRegex(text, r"\d{2}:\d{2}", "no time of day, so a quiet day commits nothing")

    def test_the_same_rates_write_nothing_new(self):
        self.run_it(ECB)
        before = self.path.stat().st_mtime_ns
        self.run_it(ECB)
        self.assertEqual(self.path.stat().st_mtime_ns, before)

    def test_a_failed_fetch_or_a_broken_file_keeps_the_old_rates(self):
        self.run_it(ECB)
        old = self.path.read_text(encoding="utf-8")
        for bad in (OSError("offline"), "<html>", ECB.replace("1.1188", "0")):
            self.assertEqual(self.run_it(bad), 0, "an old rate is better than a failed run")
            self.assertEqual(self.path.read_text(encoding="utf-8"), old)

    def test_nothing_is_written_when_there_is_no_first_file_either(self):
        self.run_it(OSError("offline"))
        self.assertFalse(self.path.exists())

    def test_it_needs_nothing_but_python_and_knows_no_key(self):
        source = (ROOT / "fx.py").read_text(encoding="utf-8")
        imported = set(re.findall(r"^(?:import|from) ([a-z_0-9]+)", source, flags=re.MULTILINE))
        self.assertTrue(imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names))
        self.assertNotIn("EBAY", source)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / ".github" / "workflows" / "fx.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.code = "\n".join(line for line in self.text.split("\n") if not line.lstrip().startswith("#"))

    def test_it_runs_on_a_schedule_or_by_hand_never_on_pull_requests_and_holds_no_secret(self):
        for forbidden in ("pull_request", "push:", "secrets.", "pip ", "npm "):
            self.assertNotIn(forbidden, self.code)
        self.assertIn("workflow_dispatch:", self.code)
        self.assertIn("schedule:", self.code)

    def test_it_saves_only_the_rates_file_and_retries_when_another_job_got_there_first(self):
        self.assertEqual(re.findall(r"git add (.+)", self.code), ["data/fx.json"])
        self.assertIn("git pull --rebase", self.code)
        self.assertNotIn("--force", self.code)
        self.assertEqual(self.code.count("41898282+github-actions[bot]@users.noreply.github.com"), 1)


if __name__ == "__main__":
    unittest.main()
