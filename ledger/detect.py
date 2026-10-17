"""Finding manoeuvres in a satellite's history of element sets.

The idea in one paragraph. Every element set gives the satellite's mean semi-major
axis a (the size of its orbit) at that set's epoch. Between thruster firings, a
changes slowly and smoothly (drag, or a long low-thrust campaign). A firing that is
short compared with the spacing between element sets shows up as a STEP in a. For
each gap between two consecutive sets we estimate that step from the sets on either
side, and call it a manoeuvre when it is bigger than what fit noise produces.

Why not simply subtract consecutive sets: public GP sets sometimes contain one bad
fit, off by 0.4 to 2 km, with good sets on both sides (seen many times in DODGE's
recordings; see docs/METHODS.md). A one-set outlier makes two big differences of
opposite sign. Using the MEDIAN of up to five sets on each side of the gap ignores
one bad set, so a step must persist to count.

Why not propagate the older set with SGP4's drag term: SGP4 models drag only. A
satellite under continuous electric thrust (raising or lowering by about a
kilometre a day) is fitted with a strange drag term that extrapolates badly, which
again looks like a step. The local slope used here is measured from the data (the
median slope between consecutive sets within 3 days), so a steady ramp is not a
step.

A step counts when it is (a) a local maximum, (b) at least the calibrated threshold
in metres (set on passive debris, see pipeline.py) and (c) at least SNR_MIN times the
standard error implied by the scatter of its own supporting sets.

Output per detected step: when (between which two epochs), how big (metres of
semi-major axis), the equivalent along-track delta-v, and the local noise.
"""
import math
from dataclasses import dataclass

import numpy as np

from . import elements as E

WINDOW_DAYS = 1.5        # how far either side of a gap we look for supporting sets
MAX_SIDE = 5             # at most this many sets per side
MIN_SIDE = 3             # a step needs at least 3 sets on each side (outlier-proof median)
MAX_GAP_DAYS = 2.0       # a gap longer than this is not tested (too much can happen)
MERGE_SECONDS = 3600.0   # two sets less than an hour apart: keep only the newer fit


@dataclass
class Series:
    """One satellite's history from one kind of source ("gp", "supgp" or "control")."""
    kind: str
    norad: int
    name: str
    t: np.ndarray      # epochs, days since 2026-01-01 00:00 UTC
    a: np.ndarray      # mean semi-major axis at each epoch, km
    inc: np.ndarray    # mean inclination, degrees
    ecc: np.ndarray


T0 = 1767225600.0  # 2026-01-01T00:00:00Z as a Unix time


def to_days(dt):
    return (dt.timestamp() - T0) / 86400.0


def build_series(kind, norad, rows):
    """Series from raw rows: SGP4 mean elements at each set's own epoch."""
    pts = []
    for r in sorted(rows, key=lambda r: r["EPOCH"]):
        try:
            t = E.parse_epoch(r["EPOCH"])
            m = E.mean_at(E.satrec(r), *E.to_jd(t))
        except (ValueError, KeyError, TypeError):
            continue
        if m is None:
            continue
        pts.append((t.timestamp(), m[0], math.degrees(m[2]), m[5]))
    merged = []
    for p in pts:
        if merged and p[0] - merged[-1][0] < MERGE_SECONDS:
            merged[-1] = p          # the newer fit replaces an almost simultaneous older one
        else:
            merged.append(p)
    if not merged:
        return None
    arr = np.array(merged)
    name = str(rows[-1].get("OBJECT_NAME") or "") if rows else ""
    return Series(kind, int(norad), name, (arr[:, 0] - T0) / 86400.0, arr[:, 1], arr[:, 2], arr[:, 3])


SLOPE_SPAN_DAYS = 3.0    # the local trend comes from consecutive pairs within this distance of a gap
MIN_PAIR_HOURS = 2.0     # consecutive sets closer than this give a slope too noisy to use
SNR_MIN = 5.0            # a step must also be at least 5 local noise sigmas
CONSENSUS_SIGMA = 4.0    # a supporting set agrees with its side's level within 4 sigma...
CONSENSUS_FLOOR_KM = 0.02  # ...or 20 m, whichever is larger
CONSENSUS_SHARE = 0.6    # and at least 60% of each side's sets must agree


def local_slope(t, a, k, span=SLOPE_SPAN_DAYS):
    """The satellite's local trend around gap k, in km per day.

    It is the MEDIAN of the slopes between consecutive sets within `span` days of the
    gap, leaving out the pair that spans the gap itself. Why consecutive pairs: on a
    satellite that decays for two days and is then boosted (a drag make-up sawtooth),
    most consecutive pairs show the decay and only the few that straddle a boost do
    not, so the median is the decay rate. Slopes taken across a whole side window
    (Theil-Sen inside 3 to 5 sets) were tried first and are corrupted by a boost
    inside the window, which then invents steps of the opposite sign.
    """
    tm = 0.5 * (t[k - 1] + t[k])
    slopes = []
    for i in range(1, len(t)):
        if i == k:
            continue
        dt = t[i] - t[i - 1]
        if dt * 24.0 < MIN_PAIR_HOURS or abs(0.5 * (t[i] + t[i - 1]) - tm) > span:
            continue
        slopes.append((a[i] - a[i - 1]) / dt)
    return float(np.median(slopes)) if len(slopes) >= 3 else 0.0


def series_noise_km(s):
    """Robust scatter of one set in this satellite's history (km).

    Each interior set is compared with the straight line through its two neighbours.
    For white noise of standard deviation sigma that residual has standard deviation
    sigma * sqrt(1 + w1^2 + w2^2) (about 1.22 sigma for even spacing), so sigma is
    1.4826 * median(|residual|) / that factor. A step or a bad set disturbs only one or
    two residuals, which the median ignores. Returns None with fewer than 5 sets.
    """
    t, a = s.t, s.a
    res, fac = [], []
    for i in range(1, len(t) - 1):
        span = t[i + 1] - t[i - 1]
        if span <= 0:
            continue
        w2 = (t[i] - t[i - 1]) / span
        w1 = 1.0 - w2
        res.append(abs(a[i] - (w1 * a[i - 1] + w2 * a[i + 1])))
        fac.append(math.sqrt(1.0 + w1 * w1 + w2 * w2))
    if len(res) < 3:
        return None
    return 1.4826 * float(np.median(res)) / float(np.median(fac))


def gap_steps(s):
    """The estimated step at every testable gap of a series.

    Returns a list of dicts with: k (index of the first set after the gap), t_before,
    t_after, t_mid (days), step_km, slope_km_day, n_left, n_right, spread_km (the
    median absolute residual of the supporting sets about their side's level) and
    sigma_km (the standard error of the step: the satellite's own per-set noise, from
    series_noise_km, times 1.2533 for a median, times sqrt(1/n_left + 1/n_right)).
    """
    out = []
    t, a = s.t, s.a
    n = len(t)
    noise = series_noise_km(s)
    for k in range(1, n):
        if t[k] - t[k - 1] > MAX_GAP_DAYS:
            continue
        left = [i for i in range(k - 1, -1, -1) if t[k - 1] - t[i] <= WINDOW_DAYS][:MAX_SIDE]
        right = [i for i in range(k, n) if t[i] - t[k] <= WINDOW_DAYS][:MAX_SIDE]
        if len(left) < MIN_SIDE or len(right) < MIN_SIDE:
            continue
        left.reverse()
        tl, al, tr, ar = t[left], a[left], t[right], a[right]
        slope = local_slope(t, a, k)
        tm = 0.5 * (t[k - 1] + t[k])
        lv = al + slope * (tm - tl)        # each left set, carried forward to the gap
        rv = ar - slope * (tr - tm)        # each right set, carried back to the gap
        L, R = float(np.median(lv)), float(np.median(rv))
        spread = float(np.median(np.abs(np.concatenate([lv - L, rv - R]))))
        # a median of n values has about 1.2533 times the error of a mean of n values
        per_set = noise if noise is not None else 1.4826 * spread
        sigma = per_set * 1.2533 * math.sqrt(1.0 / len(left) + 1.0 / len(right))
        # consensus: each side's level must be backed by most of its own sets; two bad sets
        # among four would otherwise drag an even-count median halfway to them
        tol = max(CONSENSUS_SIGMA * per_set, CONSENSUS_FLOOR_KM)
        if (np.sum(np.abs(lv - L) <= tol) < math.ceil(CONSENSUS_SHARE * len(lv))
                or np.sum(np.abs(rv - R) <= tol) < math.ceil(CONSENSUS_SHARE * len(rv))):
            continue
        out.append(dict(k=k, t_before=float(t[k - 1]), t_after=float(t[k]), t_mid=float(tm),
                        step_km=R - L, slope_km_day=slope, n_left=len(left), n_right=len(right),
                        spread_km=spread, sigma_km=sigma))
    return out


def significant(g, threshold_km):
    """The detection rule: big enough in metres AND well above the local scatter."""
    return abs(g["step_km"]) >= threshold_km and abs(g["step_km"]) >= SNR_MIN * g["sigma_km"]


def local_maxima(steps, window_days=WINDOW_DAYS):
    """Keep a gap only if its |step| is the largest among gaps whose windows overlap it.

    One real step raises the estimate at a few neighbouring gaps too (they share
    supporting sets); this keeps one gap per step. Exact ties go to the earliest
    gap here; refine() then moves the detection to the gap that splits best.
    """
    keep = []
    for i, g in enumerate(steps):
        big = abs(g["step_km"])
        if all(abs(h["step_km"]) <= big for j, h in enumerate(steps)
               if j != i and abs(h["t_mid"] - g["t_mid"]) < window_days):
            if not any(abs(h["step_km"]) == big and h["t_mid"] < g["t_mid"]
                       and abs(h["t_mid"] - g["t_mid"]) < window_days for h in steps):
                keep.append(g)
    return keep


def split_cost(s, k, slope, lo, hi):
    """L1 misfit of a step between sets k-1 and k, over the sets lo..hi-1.

    Each side is a line with the shared slope through that side's median level; the
    cost is the sum of absolute residuals. The best split has the smallest cost.
    """
    t, a = s.t[lo:hi], s.a[lo:hi]
    tm = 0.5 * (s.t[k - 1] + s.t[k])
    left = (np.arange(lo, hi) < k)
    if left.sum() == 0 or (~left).sum() == 0:
        return float("inf")
    carried = a + slope * (tm - t)
    L = np.median(carried[left])
    R_ = np.median(carried[~left])
    return float(np.abs(carried[left] - L).sum() + np.abs(carried[~left] - R_).sum())


def refine(s, steps, g):
    """Move a detection to the neighbouring gap that splits the sets best.

    With medians, the step estimate is nearly the same one gap before and after the
    true one (one misplaced set does not move a median), so the largest |step| does
    not pin the location. Among gaps within one window whose estimate has the same
    sign and at least 80% of the size, pick the one with the smallest split_cost over
    a common set of points. The location (and its slope and supporting counts) comes
    from that gap; the size stays the peak estimate, so thresholds mean one thing.
    """
    near = [h for h in steps if abs(h["t_mid"] - g["t_mid"]) < WINDOW_DAYS
            and np.sign(h["step_km"]) == np.sign(g["step_km"]) and abs(h["step_km"]) >= 0.8 * abs(g["step_km"])]
    if len(near) <= 1:
        return dict(g)
    ks = [h["k"] for h in near]
    lo = max(0, min(ks) - MAX_SIDE)
    hi = min(len(s.t), max(ks) + MAX_SIDE)
    best = min(near, key=lambda h: (split_cost(s, h["k"], g["slope_km_day"], lo, hi), h["t_mid"]))
    out = dict(best)
    out["step_km"] = g["step_km"]
    return out


def events_from_steps(s, steps, threshold_km=0.0):
    """Refined local-maximum steps with |step| >= threshold, one per real change."""
    seen, out = set(), []
    for g in local_maxima(steps):
        if not significant(g, threshold_km):
            continue
        r = refine(s, steps, g)
        if r["k"] in seen:
            continue
        seen.add(r["k"])
        out.append(r)
    return out


def detect_series(s, threshold_km):
    """Detected manoeuvres in one series: local-maximum steps above the threshold."""
    steps = gap_steps(s)
    events = []
    for g in events_from_steps(s, steps, threshold_km):
        a_km = float(s.a[g["k"]])
        ev = dict(g)
        ev.update(kind=s.kind, norad=s.norad, name=s.name, a_km=a_km,
                  alt_km=a_km - E.RE_KM, inc_deg=float(s.inc[g["k"]]),
                  dv_m_s=E.dv_from_da(g["step_km"], a_km))
        events.append(ev)
    return events, steps


def exposure_days(s):
    """Days of this series in which a step could have been detected (tested gaps only)."""
    total = 0.0
    for g in gap_steps(s):
        total += g["t_after"] - g["t_before"]
    return total
