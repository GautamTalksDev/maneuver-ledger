"""What was each manoeuvre for? Heuristics, stated plainly.

Public element sets say THAT an orbit changed, not WHY. These rules use only what
the data shows and are written so an operator could tell us where they are wrong.

1. The satellite's regime over the whole window, from its own history:
       raising     its semi-major axis rose by more than REGIME_KM (orbit raising
                   after launch, or a move to a higher shell)
       descending  it fell by more than REGIME_KM (deliberate lowering, deorbit, or
                   a satellite that lost control and decays; not told apart)
       on-station  neither: it is holding an altitude
2. Each detected step on a raising satellite that goes up is "raising"; on a
   descending satellite that goes down, "lowering". Opposite-sign steps on those
   satellites are "other".
3. On-station satellites hold altitude against drag. Some do it in visible
   instalments: the orbit decays for a day or two, then a boost restores it. A
   positive step whose local trend is a decay of at least DECAY_M_PER_DAY is
   "drag make-up" (station keeping).
4. Every other on-station step smaller than MAX_AVOID_DV is "avoidance-like":
   a short, small, single change that is not raising, lowering or drag make-up.
   This is an upper bound on avoidance burns above the detection limit: phasing
   and slot adjustments look the same in public data.
"""
import numpy as np

REGIME_KM = 2.0           # net change over the window that makes a satellite raising or descending
DECAY_M_PER_DAY = 30.0    # local decay that marks a positive step as drag make-up
MAX_AVOID_DV = 1.0        # m/s; bigger on-station steps are "large on-station" (assumption, see docs)
MIN_SPAN_DAYS = 2.0

CLASSES = ("avoidance-like", "drag make-up", "raising", "lowering", "large on-station", "other")


def regime(series):
    """"raising", "descending", "on-station", or "short" (under MIN_SPAN_DAYS of history)."""
    if len(series.t) < 6 or series.t[-1] - series.t[0] < MIN_SPAN_DAYS:
        return "short"
    net = float(np.median(series.a[-3:]) - np.median(series.a[:3]))
    if net > REGIME_KM:
        return "raising"
    if net < -REGIME_KM:
        return "descending"
    return "on-station"


def net_change_km(series):
    return float(np.median(series.a[-3:]) - np.median(series.a[:3]))


def classify_event(ev, reg):
    """One of CLASSES for a detected step on a satellite in regime reg."""
    step, slope_m_day = ev["step_km"], ev["slope_km_day"] * 1000.0
    if reg == "raising":
        return "raising" if step > 0 else "other"
    if reg == "descending":
        return "lowering" if step < 0 else "other"
    if reg != "on-station":
        return "other"
    if abs(ev["dv_m_s"]) > MAX_AVOID_DV:
        return "large on-station"
    if step > 0 and slope_m_day <= -DECAY_M_PER_DAY:
        return "drag make-up"
    return "avoidance-like"
