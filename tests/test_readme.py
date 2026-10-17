"""The README's results block must match out/summary.json exactly."""
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from ledger import readme  # noqa: E402

SUMMARY = os.path.join(ROOT, "out", "summary.json")


@unittest.skipUnless(os.path.exists(SUMMARY), "run the pipeline first")
class Readme(unittest.TestCase):
    def test_block_is_current(self):
        with open(SUMMARY) as f:
            s = json.load(f)
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn(readme.block(s), text, "README results are stale: run python -m ledger.pipeline all")

    def test_ambition_pass_is_first(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            head = f.read(3000)
        self.assertIn("AMBITION PASS", head)
        for line in ("Literal ask:", "Outcome:", "Depth:", "Crew (verbs):", "Goal:"):
            self.assertIn(line, head)


if __name__ == "__main__":
    unittest.main()
