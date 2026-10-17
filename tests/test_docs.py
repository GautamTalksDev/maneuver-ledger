"""Documentation rules: numbers written in prose match out/summary.json, and every local link resolves."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
SUMMARY = os.path.join(ROOT, "out", "summary.json")
DOCS = ["README.md", "SECURITY.md", "CHANGELOG.md"] + [os.path.join("docs", n) for n in
                                                      ("METHODS.md", "ARCHITECTURE.md", "DATA.md", "FAQ.md")]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(os.path.exists(SUMMARY), "run the pipeline first")
class ProseNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SUMMARY) as f:
            cls.s = json.load(f)
        cls.row16 = next(r for r in cls.s["bound"]["rows"] if r["dv_cm_s"] == 16)

    def test_readme_one_line_result(self):
        line = next(x for x in read("README.md").splitlines() if x.startswith("**Result in one line:**"))
        line += " " + read("README.md").split(line, 1)[1].splitlines()[1]
        self.assertIn(f"{self.s['fcc']['total']:,}", line)
        self.assertIn(f"{self.row16['dv_cm_s']} cm/s or more are at most {self.row16['max_rate']:.1f} per", line)
        self.assertIn(f"{self.row16['max_share_of_gen1'] * 100:.0f}% of the lower filed rate", line)

    def test_faq_numbers(self):
        faq = read(os.path.join("docs", "FAQ.md"))
        s = self.s
        inj = {r["dv_cm_s"]: r for r in s["bound"]["injection"]}
        for text in (f"about {s['synthetic']['sigma_m']:.0f} m around",
                     f"about {s['noise']['outlier_share'] * 100:.1f}% of sets",
                     f"{s['threshold']['m']} m [`threshold.m`]",
                     f"about {s['threshold']['dv_cm_s_at_470km']:.1f} cm/s at 470 km",
                     f"{s['bound']['threshold_dv_cm_s']:.1f} cm/s in the low-drag band",
                     f"{inj[16]['recall'] * 100:.0f}% of the time at 16 cm/s and {inj[10]['recall'] * 100:.0f}% at 10 cm/s",
                     f"about {s['fcc']['gen1_rate_stated']} per satellite per year for Gen 1 and about "
                     f"{s['fcc']['gen2_rate_stated']} for Gen 2",
                     f"pre-registered {s['agreement']['pre_registered_line'] * 100:.0f}% beyond chance"):
            self.assertIn(text, re.sub(r"\s+", " ", faq), text)
        observed = s["bound"]["steps"] / s["bound"]["exposure_years"]
        self.assertTrue(0.4 < observed / s["bound"]["steps_upper95_per_year"] < 0.6, "FAQ says 'about half'")

    def test_gauss_rule_of_thumb(self):
        # "about 18 m of semi-major axis per cm/s" at Starlink altitudes
        from ledger import elements as E
        for alt in (470.0, 550.0, 570.0):
            m = E.da_from_dv(0.01, E.RE_KM + alt) * 1000
            self.assertAlmostEqual(m, 18.0, delta=0.5)


class Links(unittest.TestCase):
    def test_local_links_resolve(self):
        bad = []
        for rel in DOCS:
            if not os.path.exists(os.path.join(ROOT, rel)):
                bad.append(f"missing {rel}")
                continue
            base = os.path.dirname(os.path.join(ROOT, rel))
            for target in re.findall(r"\]\(([^)\s]+)\)", read(rel)):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path = target.split("#", 1)[0]
                if not os.path.exists(os.path.normpath(os.path.join(base, path))):
                    bad.append(f"{rel}: {target}")
        self.assertEqual(bad, [])

    def test_security_files_present(self):
        for rel in ("LICENSE", "LICENSE-DATA", "SECURITY.md", "CITATION.cff", ".github/CODEOWNERS",
                    ".github/dependabot.yml", ".github/workflows/ci.yml"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)

    def test_workflow_rules(self):
        wf = read(os.path.join(".github", "workflows", "ci.yml"))
        self.assertIn("permissions:\n  contents: read", wf)
        self.assertNotRegex(wf, r"\$\{\{\s*secrets\.")
        self.assertNotIn("pull_request_target", wf)
        for ref in re.findall(r"uses:\s*(\S+)", wf):
            self.assertRegex(ref, r"@[0-9a-f]{40}$", f"action not pinned to a full commit SHA: {ref}")

    def test_gitignore_keeps_secrets_and_caches_out(self):
        gi = read(".gitignore").splitlines()
        for pat in ("cache/", ".env", "*.key", "*.pem"):
            self.assertIn(pat, gi)


if __name__ == "__main__":
    unittest.main()
