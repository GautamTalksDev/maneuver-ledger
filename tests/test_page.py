"""The results page: every number traces to out/summary.json, and the page is safe to host.

Builds the page from the committed summary into a temporary folder, then checks it.
"""
import base64
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from ledger import page  # noqa: E402

SUMMARY = os.path.join(ROOT, "out", "summary.json")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def visible_text(doc):
    body = doc.split("<main>", 1)[1]
    body = re.sub(r"<svg.*?</svg>", " ", body, flags=re.S)       # chart ticks are scales, not claims
    body = re.sub(r"<[^>]+>", " ", body)
    return html.unescape(body)


@unittest.skipUnless(os.path.exists(SUMMARY), "run the pipeline first")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = os.path.join(cls.tmp.name, "index.html")
        cls.doc = page.build(SUMMARY, out)
        with open(out[:-5] + ".numbers.json") as f:
            cls.used = json.load(f)
        with open(SUMMARY) as f:
            cls.summary = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_number_is_traced(self):
        allowed = set()
        for text, _source in self.used:
            allowed.update(NUMBER.findall(str(text)))
        text = visible_text(self.doc).replace("Gen 1", "Gen").replace("Gen 2", "Gen")
        missing = sorted({n for n in NUMBER.findall(text) if n not in allowed})
        self.assertEqual(missing, [], "numbers on the page that did not come from summary.json")

    def test_recorded_paths_resolve(self):
        p = page.Page(self.summary)
        for text, source in self.used:
            if source.startswith("derived: "):
                continue
            p.get(source)   # raises if the path does not exist

    def test_no_dashes(self):
        for bad in (chr(0x2013), chr(0x2014), "&mdash;", "&ndash;", "&#8211;", "&#8212;"):
            self.assertNotIn(bad, self.doc)
        self.assertNotIn("--", visible_text(self.doc))

    def test_no_scripts_no_third_parties(self):
        self.assertNotIn("<script", self.doc.lower())
        self.assertNotIn(" style=", self.doc)
        self.assertNotRegex(self.doc, r"\bsrc=")
        for href in re.findall(r'href="([^"]+)"', self.doc):
            self.assertTrue(href.startswith("https://"), href)

    def test_csp_pins_the_only_style_block(self):
        styles = re.findall(r"<style>(.*?)</style>", self.doc, flags=re.S)
        self.assertEqual(len(styles), 1)
        digest = base64.b64encode(hashlib.sha256(styles[0].encode()).digest()).decode()
        csp = re.search(r'Content-Security-Policy" content="([^"]+)"', self.doc).group(1)
        self.assertIn(f"'sha256-{digest}'", csp)
        self.assertIn("default-src 'none'", csp)

    def test_headline_arithmetic(self):
        f = self.summary["fcc"]
        self.assertAlmostEqual(f["combined_rate"], f["total"] / (f["satcat_mean_fleet"] * f["period_years"]), places=9)
        b = self.summary["bound"]
        for row in b["rows"]:
            self.assertAlmostEqual(row["max_rate"], b["steps_upper95_per_year"] / row["recall_lo95"], places=9)

    def test_says_it_was_not_reproduced(self):
        self.assertIn("did not reproduce", self.doc)


if __name__ == "__main__":
    unittest.main()
