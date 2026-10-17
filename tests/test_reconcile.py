"""The FCC arithmetic and the statistics behind every error bar."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ledger import fleet as F  # noqa: E402
from ledger import reconcile as R  # noqa: E402


class Filing(unittest.TestCase):
    def test_totals_and_period(self):
        self.assertEqual(F.fcc_total(), 207152)
        self.assertEqual(F.FCC["gen1_maneuvers"] + F.FCC["gen2_maneuvers"], 207152)
        self.assertEqual(F.period_days(), 182)     # 1 Dec 2025 to 31 May 2026 inclusive

    def test_quotes_carry_the_numbers(self):
        for n in ("65,137", "142,015", "36", "46"):
            self.assertIn(n, F.FCC["quote_counts"])
        self.assertIn("3e-7", F.FCC["quote_threshold"])
        self.assertIn("1e-4", F.FCC["quote_threshold"])

    def test_implied_fleet(self):
        # 65,137 / (36 x 182 / 365.25) = 3,631 and 142,015 / (46 x 182 / 365.25) = 6,196.
        self.assertAlmostEqual(F.implied_fleet(65137, 36), 3631.15, places=1)
        self.assertAlmostEqual(F.implied_fleet(142015, 46), 6195.77, places=1)
        lo, hi = F.implied_fleet_range(65137, 36)
        self.assertLess(lo, 3631.15)
        self.assertGreater(hi, 3631.15)

    def test_combined_rate_brackets_the_two_stated_rates(self):
        fleet = F.implied_fleet(65137, 36) + F.implied_fleet(142015, 46)
        r = F.fcc_combined_rate(fleet)
        self.assertGreater(r, 36)
        self.assertLess(r, 46)


class Statistics(unittest.TestCase):
    def test_poisson_known_values(self):
        # Garwood 95% intervals: k=0 -> (0, 3.689); k=1 -> (0.0253, 5.572); k=10 -> (4.795, 18.39)
        lo, hi = R.poisson_interval(0)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 3.689, places=2)
        lo, hi = R.poisson_interval(1)
        self.assertAlmostEqual(lo, 0.0253, places=3)
        self.assertAlmostEqual(hi, 5.572, places=2)
        lo, hi = R.poisson_interval(10)
        self.assertAlmostEqual(lo, 4.795, places=2)
        self.assertAlmostEqual(hi, 18.39, places=1)

    def test_poisson_large_counts_do_not_underflow(self):
        lo, hi = R.poisson_interval(2335)
        self.assertLess(lo, 2335)
        self.assertGreater(hi, 2335)
        self.assertAlmostEqual(hi - lo, 2 * 1.96 * 2335 ** 0.5, delta=5)

    def test_wilson(self):
        p, lo, hi = R.wilson(98, 100)
        self.assertAlmostEqual(p, 0.98)
        self.assertLess(lo, 0.98)
        self.assertGreater(hi, 0.98)
        self.assertLessEqual(hi, 1.0)

    def test_bootstrap_covers_the_truth(self):
        rng = np.random.default_rng(11)
        covered = 0
        for _ in range(40):
            expo = rng.uniform(5, 12, 400)
            counts = rng.poisson(30.0 * expo / 365.25)
            lo, hi = R.bootstrap_rate(counts, expo, rng, n_boot=500)
            covered += lo <= 30.0 <= hi
        self.assertGreaterEqual(covered, 34)       # about 95% of 40, with room for chance

    def test_false_alarm_upper_bound(self):
        rate, up = R.false_alarm(0, 365.25)
        self.assertEqual(rate, 0.0)
        self.assertAlmostEqual(up, 3.689, places=2)


if __name__ == "__main__":
    unittest.main()
