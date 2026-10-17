"""The orbital mechanics the detector relies on, checked against hand calculations."""
import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ledger import detect as D  # noqa: E402
from ledger import elements as E  # noqa: E402
from ledger import synth as Y  # noqa: E402


class GaussEquation(unittest.TestCase):
    def test_round_trip(self):
        for a in (6750.0, 6850.0, 6950.0):
            for dv in (-0.5, -0.01, 0.02, 0.16, 1.0):
                self.assertAlmostEqual(E.dv_from_da(E.da_from_dv(dv, a), a), dv, places=12)

    def test_hand_value(self):
        # a = 6850 km: v = sqrt(398600.8 / 6850) = 7.6283 km/s; da = 2 a dv / v.
        # 10 cm/s gives 2 * 6850 * 0.0001 / 7.6283 = 0.17959 km.
        self.assertAlmostEqual(E.da_from_dv(0.10, 6850.0), 0.17959, places=4)
        self.assertAlmostEqual(E.circular_speed_km_s(6850.0), 7.6283, places=3)

    def test_sign(self):
        self.assertGreater(E.da_from_dv(0.05, 6850.0), 0)
        self.assertLess(E.dv_from_da(-0.1, 6850.0), 0)


class MeanElements(unittest.TestCase):
    def row(self, a, when, **kw):
        return Y.row_from_a(a, when, **kw)

    def test_six_digit_catalogue_numbers_propagate(self):
        r = self.row(6850.0, datetime(2026, 10, 10, tzinfo=timezone.utc))
        r["NORAD_CAT_ID"] = 999999      # above the Alpha-5 limit of 339999
        m = E.mean_at(E.satrec(r), *E.to_jd(datetime(2026, 10, 10, 6, tzinfo=timezone.utc)))
        self.assertIsNotNone(m)

    def test_epoch_without_fraction(self):
        r = self.row(6850.0, datetime(2026, 10, 10, tzinfo=timezone.utc))
        r["EPOCH"] = "2026-10-10T00:00:00"
        self.assertIsNotNone(E.mean_at(E.satrec(r), *E.to_jd(datetime(2026, 10, 10, tzinfo=timezone.utc))))

    def test_mean_sma_matches_mean_motion(self):
        # SGP4's mean semi-major axis is Brouwer's, the input is Kozai's: they differ by a J2 term of a few km
        # at most, and that offset is the same for two orbits of nearly the same size, so steps are preserved.
        t = datetime(2026, 10, 10, tzinfo=timezone.utc)
        a1 = E.mean_at(E.satrec(self.row(6850.0, t)), *E.to_jd(t))[0]
        a2 = E.mean_at(E.satrec(self.row(6850.2, t)), *E.to_jd(t))[0]
        self.assertLess(abs(a1 - 6850.0), 10.0)
        self.assertAlmostEqual(a2 - a1, 0.2, delta=0.002)

    def test_full_path_finds_an_injected_step(self):
        # Synthetic CelesTrak-style rows, through SGP4, into the detector: a 0.25 km raise on day 5.
        t0 = datetime(2026, 10, 6, tzinfo=timezone.utc)
        rows = []
        for i in range(21):
            when = t0 + timedelta(hours=12 * i)
            a = 6850.0 + (0.25 if i >= 10 else 0.0)
            rows.append(self.row(a, when, u_deg=(i * 37.0) % 360))
        s = D.build_series("gp", 1, rows)
        events, _ = D.detect_series(s, 0.1)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]["step_km"], 0.25, delta=0.005)
        self.assertEqual(events[0]["k"], 10)
        self.assertAlmostEqual(events[0]["dv_m_s"], E.dv_from_da(0.25, 6850.0), delta=0.005)

    def test_pair_residual_sees_along_track_offset(self):
        t = datetime(2026, 10, 10, tzinfo=timezone.utc)
        a = E.satrec(self.row(6850.0, t, u_deg=10.0))
        b = E.satrec(self.row(6850.0, t, u_deg=10.01))
        da, ds, _, _ = E.pair_residual(a, b, *E.to_jd(t))
        self.assertAlmostEqual(da, 0.0, places=6)
        self.assertAlmostEqual(ds, 6850.0 * math.radians(0.01), delta=0.1)


if __name__ == "__main__":
    unittest.main()
