"""Synthetic orbits with burns we put there ourselves: the detector's exam.

Two kinds of exam:
1. synthetic_series(): a made-up history of mean semi-major axis with drag, fit
   noise, occasional bad element sets, and burns of known delta-v at known times.
   Because we know the truth, precision and recall are exact.
2. inject(): add a burn of known size to a REAL recorded history. The noise is then
   whatever the real data has, which gives the detection limit on real data.
There is also row_from_a(), which writes a synthetic CelesTrak-style row, so the
full path through SGP4 can be tested, not only the step arithmetic.
"""
import math

import numpy as np

from . import elements as E
from .detect import Series


def synthetic_series(rng, days=11.0, cadence_h=13.0, jitter_h=4.0, a0_km=6850.0, slope_km_day=0.0,
                     sigma_km=0.010, p_outlier=0.0, outlier_km=(0.4, 2.0), burns=(), kind="gp", norad=1):
    """A Series plus the truth: [(t_burn_days, dv_m_s, da_km)].

    burns: iterable of (t_days, dv_m_s). Each burn adds da = 2 a dv / v to every set after it.
    """
    t, times = 0.0, []
    while t < days:
        times.append(t)
        t += max(1.0, cadence_h + rng.uniform(-jitter_h, jitter_h)) / 24.0
    times = np.array(times)
    truth = [(tb, dv, E.da_from_dv(dv, a0_km)) for tb, dv in burns]
    a = a0_km + slope_km_day * times
    for tb, _, da in truth:
        a = a + da * (times > tb)
    a = a + rng.normal(0.0, sigma_km, len(times))
    if p_outlier > 0:
        bad = rng.random(len(times)) < p_outlier
        size = rng.uniform(outlier_km[0], outlier_km[1], len(times)) * rng.choice([-1.0, 1.0], len(times))
        a = a + bad * size
    s = Series(kind, norad, f"SYNTH-{norad}", times, a, np.full(len(times), 53.0), np.full(len(times), 2e-4))
    return s, truth


def inject(series, k, da_km):
    """A copy of a real series with a burn of da_km between set k-1 and set k."""
    a = series.a.copy()
    a[k:] += da_km
    return Series(series.kind, series.norad, series.name, series.t.copy(), a, series.inc, series.ecc)


def match(events, truth, slack_days=0.5):
    """(true positives, false positives, missed burns) by time window and sign."""
    used, tp = set(), 0
    for tb, dv, da in truth:
        for i, ev in enumerate(events):
            if i in used:
                continue
            if ev["t_before"] - slack_days <= tb <= ev["t_after"] + slack_days and np.sign(ev["step_km"]) == np.sign(da):
                used.add(i)
                tp += 1
                break
    return tp, len(events) - len(used), len(truth) - tp


def row_from_a(a_km, epoch_dt, inc_deg=53.0, raan_deg=10.0, u_deg=0.0, bstar=0.0):
    """A CelesTrak-style JSON row for a circular orbit of mean semi-major axis a_km."""
    n_rad_s = math.sqrt(E.MU_KM3_S2 / a_km ** 3)
    return {
        "OBJECT_NAME": "SYNTH", "OBJECT_ID": "2026-001A", "NORAD_CAT_ID": 999999,
        "EPOCH": E.epoch_str(epoch_dt), "MEAN_MOTION": n_rad_s * 86400.0 / (2 * math.pi),
        "ECCENTRICITY": 0.0001, "INCLINATION": inc_deg, "RA_OF_ASC_NODE": raan_deg,
        "ARG_OF_PERICENTER": 0.0, "MEAN_ANOMALY": u_deg, "BSTAR": bstar,
        "MEAN_MOTION_DOT": 0.0, "MEAN_MOTION_DDOT": 0.0,
    }
