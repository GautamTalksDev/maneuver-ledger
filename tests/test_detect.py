"""The detector's exam: synthetic histories with burns we injected, so the truth is known.

The headline numbers here are precision and recall at known delta-v. The noise level
(14 m) and bad-set share (0.3%) are close to what pipeline.noise_model measures on the
real public GP histories; the exam is repeated with three times more bad sets to show
the median makes single bad sets harmless.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ledger import detect as D  # noqa: E402
from ledger import elements as E  # noqa: E402
from ledger import synth as Y  # noqa: E402

THRESHOLD_KM = 0.175
SIGMA_KM = 0.014


def exam(dv_m_s, n=300, seed=1, p_outlier=0.003, sigma_km=SIGMA_KM):
    rng = np.random.default_rng(seed)
    tp = fp = fn = 0
    for i in range(n):
        burns, t = [], rng.uniform(1.6, 3.0)
        while t < 9.4:
            burns.append((t, dv_m_s * (1 if rng.random() < 0.5 else -1)))
            t += rng.uniform(3.2, 4.5)
        s, truth = Y.synthetic_series(rng, sigma_km=sigma_km, p_outlier=p_outlier, burns=burns,
                                      slope_km_day=rng.uniform(-0.03, 0.0), norad=i)
        ev, _ = D.detect_series(s, THRESHOLD_KM)
        a, b, c = Y.match(ev, truth)
        tp, fp, fn = tp + a, fp + b, fn + c
    return tp / max(1, tp + fp), tp / max(1, tp + fn), fp


class KnownBurns(unittest.TestCase):
    def test_burns_well_above_the_limit_are_found(self):
        for dv in (0.16, 0.30, 0.60):
            prec, rec, _ = exam(dv)
            self.assertGreaterEqual(prec, 0.98, f"precision at {dv} m/s")
            self.assertGreaterEqual(rec, 0.97, f"recall at {dv} m/s")

    def test_burns_below_the_limit_are_not_claimed(self):
        # 4 cm/s is about 72 m of semi-major axis, well under the 175 m threshold: nothing should be found,
        # and anything found would be a false alarm.
        _, rec, fp = exam(0.04)
        self.assertLess(rec, 0.02)
        self.assertLessEqual(fp, 3)

    def test_bad_sets_do_not_become_burns(self):
        # Ten times the measured bad-set rate, no burns at all.
        rng = np.random.default_rng(7)
        false = 0
        for i in range(300):
            s, _ = Y.synthetic_series(rng, sigma_km=SIGMA_KM, p_outlier=0.03, norad=i)
            false += len(D.detect_series(s, THRESHOLD_KM)[0])
        self.assertLessEqual(false, 6, "more than 2% of burn-free histories produced a detection")

    def test_one_bad_set_next_to_good_ones(self):
        rng = np.random.default_rng(3)
        s, _ = Y.synthetic_series(rng, sigma_km=0.005)
        s.a[len(s.a) // 2] += 1.5          # a single set off by 1.5 km
        self.assertEqual(D.detect_series(s, THRESHOLD_KM)[0], [])

    def test_a_steady_ramp_is_not_a_step(self):
        rng = np.random.default_rng(4)
        s, _ = Y.synthetic_series(rng, sigma_km=0.01, slope_km_day=1.2)   # continuous electric raising
        self.assertEqual(D.detect_series(s, THRESHOLD_KM)[0], [])

    def test_drag_sawtooth_slope_is_the_decay(self):
        # Decay of 60 m/day with a 180 m boost every 3 days: the local slope must be the decay, not a blend.
        t = np.arange(0, 12, 0.55)
        a = 6850.0 - 0.06 * t + 0.18 * np.floor(t / 3.0)
        s = D.Series("gp", 1, "SAW", t, a, np.full(len(t), 53.0), np.full(len(t), 1e-4))
        events, _ = D.detect_series(s, 0.1)
        self.assertGreaterEqual(len(events), 3)
        for e in events:
            self.assertGreater(e["step_km"], 0, "a sawtooth must not produce negative steps")
            self.assertAlmostEqual(e["slope_km_day"], -0.06, delta=0.01)

    def test_location_is_the_true_gap(self):
        # With medians the estimate is flat across neighbouring gaps; refine() must pick the real one.
        rng = np.random.default_rng(5)
        hits = 0
        for i in range(200):
            s, truth = Y.synthetic_series(rng, sigma_km=SIGMA_KM, burns=[(5.0 + rng.uniform(-0.3, 0.3), 0.3)], norad=i)
            ev, _ = D.detect_series(s, THRESHOLD_KM)
            tb = truth[0][0]
            hits += any(e["t_before"] <= tb <= e["t_after"] for e in ev)
        self.assertGreaterEqual(hits, 196)

    def test_noisy_series_need_a_bigger_step(self):
        # 150 m of scatter per set: a 200 m step is under 5 sigma and must not count.
        rng = np.random.default_rng(6)
        s, _ = Y.synthetic_series(rng, sigma_km=0.15, burns=[(5.0, E.dv_from_da(0.2, 6850.0))])
        self.assertEqual(D.detect_series(s, THRESHOLD_KM)[0], [])

    def test_long_gaps_are_not_tested(self):
        t = np.array([0, 0.5, 1.0, 1.5, 4.5, 5.0, 5.5, 6.0])   # a 3 day hole
        a = np.where(t > 3, 6850.5, 6850.0)
        s = D.Series("gp", 1, "GAP", t, a, np.full(len(t), 53.0), np.full(len(t), 1e-4))
        self.assertEqual(D.detect_series(s, 0.1)[0], [])
        self.assertEqual(sum(1 for g in D.gap_steps(s) if g["t_before"] == 1.5), 0)


if __name__ == "__main__":
    unittest.main()
