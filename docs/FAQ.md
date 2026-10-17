# Frequently asked questions

Numbers here come from `out/summary.json` (key in brackets); `tests/test_docs.py` checks that they still match.

## Why can't public orbit data see small burns?

Because a small burn moves the orbit less than the public data wobbles.

1. **How much a burn moves the orbit.** An along-track burn of `dv` on a near-circular orbit changes the semi-major
   axis by `da = 2 a dv / v` (Gauss's equation). At Starlink's altitudes that is about 18 m of semi-major axis per
   cm/s. Burns that turn the orbit's plane or change its shape move `a` even less, or not at all.
2. **How much the data wobbles.** A single public element set's mean semi-major axis scatters by about 13 m around
   its neighbours [`synthetic.sigma_m`], and about 0.3% of sets are off by more than 300 m [`noise.outlier_share`].
   Each satellite gets a new set only every several hours. Drag also lowers the orbit by metres to tens of metres a
   day, and in the 460 to 490 km shells the satellites are boosted back every few days, so the history is a
   sawtooth even with no avoidance at all.
3. **What it takes to call a step real.** The detector compares the median of 3 to 5 sets on each side of a gap,
   after removing the local trend. The threshold is set on objects that cannot manoeuvre: passive debris and rocket
   bodies at the same altitudes. The smallest step at which the 95% upper bound of their false alarms is at most 5% of the filed
   rate is 175 m [`threshold.m`], about 9.7 cm/s at 470 km [`threshold.dv_cm_s_at_470km`] and 9.5 cm/s in the low-drag band
   [`bound.threshold_dv_cm_s`].
4. **What that means for recall.** Burns of known size injected into real histories in the low-drag band are found
   98% of the time at 16 cm/s and 65% at 10 cm/s [`bound.injection`]. Below that, most are lost in the noise.

So the public data can count burns of roughly 10 cm/s and up, and it says almost nothing about burns of 1 or 2 cm/s.
If most avoidance burns are that small, which is what the bound implies if the filing-period rate still held, they
are invisible here by construction. SpaceX's own ephemerides are a different kind of data (a predicted position and velocity every 60 s, with
covariance, rather than a fitted element set), which is why METHODS section 10 names them as the strongest next
check.

## Does this say SpaceX's number is wrong?

No. The 207,152 was not reproduced, and the page says why: most avoidance burns would have to be smaller than public
data can see. That is a statement about public data, not about the filing. The comparison also spans different
months (the filing covers December 2025 to May 2026, the data October 2026).

## Why compare with the Gen 1 rate and not the combined rate?

The filing gives about 36 per satellite per year for Gen 1 and about 46 for Gen 2. Public data does not say which
authorisation a satellite flies under, so the page uses the lower one. That makes the share that could be large
burns as big as possible. The share against the combined rate is in `bound.rows[].max_share_of_combined`.

## What is SupGP, and why does it disagree with the public GP sets?

SupGP is CelesTrak's set of SGP4 fits to the ephemerides SpaceX publishes. CelesTrak describes the public GP sets
as derived from US Space Surveillance Network radar and optical observations; whether they also use SpaceX's
ephemerides is not known to us (METHODS section 9). They are separate fit chains of the same satellites. They agree on far fewer
steps than the pre-registered 70% beyond chance [`agreement`]. The reasons are not verified; the candidates are in
METHODS section 8.

## What does "avoidance-like" mean?

A step on a satellite holding altitude that is not a drag make-up boost (a decay followed by a boost) and not a
large move. It is an upper bound on avoidance burns above the threshold: phasing or slot moves look the same. The
headline bound does not depend on the classes, because it counts every step in the low-drag band.

## Why is the bound called conservative?

It divides the upper end of a two-sided 95% Poisson interval for the step count (97.5% one-sided) by the lower end of
a 95% Wilson interval for recall (also 97.5% one-sided). Each end fails at most 2.5% of the time, so the combined
statement holds with at least about 95% confidence. A one-sided 95% Poisson bound would give a smaller number. See
METHODS section 7.

## Will the bound get tighter?

Yes, as DODGE keeps recording. With more satellite-years in the low-drag band, the 95% upper bound moves toward the
observed rate there, which today is about half of the bound. It cannot fall below that unless those steps turn out
to be something other than burns.

## Can I reuse the numbers?

Yes. The code is Apache-2.0 and the derived data is CC BY 4.0. The orbit data underneath keeps CelesTrak's terms.
See [DATA.md](DATA.md).

## Is this for operations?

No. It is screening grade, built from public data, and not affiliated with SpaceX or Starlink.
