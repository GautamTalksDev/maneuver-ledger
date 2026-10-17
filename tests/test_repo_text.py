"""House rules for every text file in the repository."""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP_DIRS = {".git", ".venv", "cache", "__pycache__"}
DASHES = "[" + chr(0x2013) + chr(0x2014) + "]"
TEXT = (".py", ".md", ".txt", ".csv", ".json", ".html", ".cff", ".toml", ".cfg", ".yml", ".yaml", "")


def files():
    for d, dirs, names in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            if os.path.splitext(n)[1] in TEXT:
                yield os.path.join(d, n)


class RepoText(unittest.TestCase):
    def test_no_em_or_en_dashes(self):
        bad = []
        for path in files():
            with open(path, encoding="utf-8", errors="replace") as f:
                if re.search(DASHES, f.read()):
                    bad.append(os.path.relpath(path, ROOT))
        self.assertEqual(bad, [])

    def test_withdrawn_claims_stay_out(self):
        # gate 17 Oct round 1: no claim that SpaceX ephemerides contain planned thrust (open question only),
        # and Space-Track is described by what its agreement restricts (redistribution), not "forbids sharing analysis"
        bad = []
        for path in files():
            if path.endswith(os.path.join("tests", "test_repo_text.py")):
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read().lower()
            if "already contain planned thrust" in text or "fits smooth planned thrust" in text \
                    or "forbids sharing analysis" in text:
                bad.append(os.path.relpath(path, ROOT))
        self.assertEqual(bad, [])

    def test_no_secrets(self):
        pattern = re.compile(r"(BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[bp]-)")
        bad = []
        for path in files():
            with open(path, encoding="utf-8", errors="replace") as f:
                if pattern.search(f.read()):
                    bad.append(os.path.relpath(path, ROOT))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
