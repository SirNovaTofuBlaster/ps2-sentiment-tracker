"""Runs the crowd service's offline checks (tests/worker_check.mjs) when Node.js exists."""
import pathlib
import shutil
import subprocess
import unittest

CHECK = pathlib.Path(__file__).with_name("worker_check.mjs")


@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
class WorkerTests(unittest.TestCase):
    def test_worker_rules(self):
        result = subprocess.run(["node", str(CHECK)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("worker checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
