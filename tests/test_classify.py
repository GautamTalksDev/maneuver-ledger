"""The classification rules, one case each."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ledger import classify as C  # noqa: E402
from ledger import detect as D  # noqa: E402


def series(a):
    t = np.linspace(0, 10, len(a))
    return D.Series("gp", 1, "X", t, np.array(a, float), np.full(len(a), 53.0), np.full(len(a), 1e-4))


def ev(step_km, slope_m_day, dv=0.1):
    return {"step_km": step_km, "slope_km_day": slope_m_day / 1000.0, "dv_m_s": dv}


class Regimes(unittest.TestCase):
    def test_regimes(self):
        self.assertEqual(C.regime(series([6850.0 + 0.5 * i for i in range(20)])), "raising")
        self.assertEqual(C.regime(series([6850.0 - 0.5 * i for i in range(20)])), "descending")
        self.assertEqual(C.regime(series([6850.0 + 0.01 * (i % 3) for i in range(20)])), "on-station")
        self.assertEqual(C.regime(series([6850.0] * 4)), "short")


class Classes(unittest.TestCase):
    def test_on_station(self):
        self.assertEqual(C.classify_event(ev(0.2, -60), "on-station"), "drag make-up")
        self.assertEqual(C.classify_event(ev(0.2, -5), "on-station"), "avoidance-like")
        self.assertEqual(C.classify_event(ev(-0.2, -60), "on-station"), "avoidance-like")
        self.assertEqual(C.classify_event(ev(-2.0, 0, dv=-1.1), "on-station"), "large on-station")

    def test_campaigns(self):
        self.assertEqual(C.classify_event(ev(0.3, 900), "raising"), "raising")
        self.assertEqual(C.classify_event(ev(-0.3, 900), "raising"), "other")
        self.assertEqual(C.classify_event(ev(-0.3, -500), "descending"), "lowering")
        self.assertEqual(C.classify_event(ev(0.3, 0), "short"), "other")

    def test_every_class_is_listed(self):
        for reg in ("on-station", "raising", "descending", "short"):
            for step in (-0.3, 0.3):
                for slope in (-80, 0, 80):
                    self.assertIn(C.classify_event(ev(step, slope), reg), C.CLASSES)


if __name__ == "__main__":
    unittest.main()
