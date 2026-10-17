# Methods, assumptions and limits

Every result quoted here lives in `out/summary.json` under the key given in brackets, so this document cannot drift
from the data. Numbers written directly below are either facts from the FCC filing or settings in the code (named).

## 1. The reference number, like for like

SpaceX's Gen 1 and Gen 2 Semi-Annual Reports to the FCC (cover letter 1 July 2026, period 1 December 2025 to
31 May 2026) say:

> Using this very conservative threshold, along with additional miss-distance-based criteria, SpaceX Gen 1 satellites
> performed 65,137 propulsive maneuvers over the reporting period, averaging approximately 36 maneuvers per satellite,
> per year and SpaceX Gen 2 satellites performed 142,015 propulsive maneuvers over the reporting period, averaging
> approximately 46 maneuvers per satellite, per year.

The threshold is a probability of collision of 3e-7 (industry standard 1e-4). URL and SHA-256 of the PDF are in
`ledger/fleet.py`. Three consequences:

- These are **collision-avoidance** manoeuvres. Orbit raising, station keeping and deorbit burns are not in the count,
  so only avoidance-like events may be compared with it.
- The filing has no fleet size. We take the average number of Starlink payloads in orbit over the 182 days from
  CelesTrak's SATCAT launch and decay dates [`fcc.satcat_mean_fleet`]. The filed rounded rates imply Gen 1 and Gen 2
  fleets [`fcc.implied_fleet_gen1`, `fcc.implied_fleet_gen2`]; their sum agrees with SATCAT within the rounding of
  the filed rates. That check cannot resolve better than about 1.4%, because "approximately 36" allows 35.5 to 36.5.
  The combined rate [`fcc.combined_rate`] is 207,152 divided by fleet times 182/365.25 years.
- Our data is from October 2026, not the filing period. We compare rates per satellite per year, never counts.

## 2. Data

| Source | What | How we get it |
|---|---|---|
| CelesTrak public GP sets ("active", "last-30-days") | Starlink element sets that CelesTrak describes as derived from US Space Surveillance Network radar and optical observations | DODGE's recorder, every 4 hours since 6 Oct 2026, one `gp-YYYY-MM-DD.ndjson.gz` per day, sealed with a SHA-256 manifest the next morning |
| CelesTrak Supplemental GP, Starlink | SGP4 fits "derived from latest Starlink ephemeris data from SpaceX's public data repository" | the same DODGE files, plus one cached fetch on the run day (`cache/celestrak/`) |
| CelesTrak debris and rocket bodies | the passive control group (cannot manoeuvre) | the same DODGE files |
| CelesTrak SATCAT | launch and decay dates, for the fleet size and the held-out launch check | DODGE's daily `satcat-*.csv.gz` |
| DODGE close-approach screens | every predicted pass under 5 km per Starlink satellite per day | DODGE's `events-*.json.gz` |
| FCC filing | the reference rate, the satellites named as removed for disposal | the PDF, parsed once by `tools/parse_fcc.py` into `data/` |

`ledger/sources.py` checks every cached day file against DODGE's sealed manifest and stops the run on a mismatch.
Not used: Space-Track (its user agreement restricts redistributing its data) and SpaceX's raw ephemeris files on
api.starlink.com (not used in this version; they would give a much stronger cross-check, see section 10).

## 3. What is measured, and why

For each element set we run SGP4 at the set's own epoch and read SGP4's internal **mean** semi-major axis (`am` in
python-sgp4). The osculating semi-major axis swings by about 10 km every orbit from Earth's oblateness; the mean value
does not, so a thruster's change stands out. One satellite's sets from one source make a time series of mean
semi-major axis.

What the raw recordings showed, and how each finding shaped the detector:

1. **Single bad sets.** Public GP histories contain isolated sets hundreds of metres to about 2 km away from both
   neighbours, which then agree with each other again. Subtracting consecutive sets turns one bad set into two
   "burns". We measure their share on the real data [`noise.outlier_share`] and the detector uses medians.
2. **Continuous thrust.** Raising and lowering satellites change their semi-major axis smoothly by up to kilometres a
   day. Propagating an older set forward with SGP4 (which only models drag) extrapolates these badly, so we never
   compare a set with an older set's prediction; we use the measured local trend instead.
3. **A drag make-up sawtooth.** Many satellites in the 460 to 490 km shells decay for one to three days and are then
   boosted back. These boosts dominate the visible steps.
4. **SupGP behaves differently from GP.** In the on-station SupGP histories we inspected, the drag term (BSTAR) often
   flips sign between consecutive fits, and SupGP and GP agree on far fewer steps than we pre-registered
   (section 8). We do not know why (one open question is in section 10). Public GP is therefore the primary source
   and SupGP the cross-check.

## 4. The detector (`ledger/detect.py`)

For every gap between two consecutive sets (gaps over `MAX_GAP_DAYS` = 2 days are not tested):

1. Take up to `MAX_SIDE` = 5 sets on each side within `WINDOW_DAYS` = 1.5 days; at least `MIN_SIDE` = 3 per side.
2. Local trend: the median slope between consecutive sets within `SLOPE_SPAN_DAYS` = 3 days, leaving out the pair
   across the gap. On a sawtooth the median picks the decay, not the boost. (A Theil-Sen slope inside each side window
   was tried first; a boost inside the window corrupted it and invented steps of the opposite sign. The test
   `test_drag_sawtooth_slope_is_the_decay` keeps it fixed.)
3. Carry each side's sets to the middle of the gap along the trend. Each side's level is the **median**; the step is
   right minus left.
4. Noise: the satellite's own per-set scatter, from each set's distance to the line through its two neighbours
   (robust, so steps and bad sets do not inflate it). The step's standard error is that scatter times 1.2533 (the
   efficiency of a median) times sqrt(1/n_left + 1/n_right).
5. Consensus: at least `CONSENSUS_SHARE` = 60% of each side's sets must sit within 4 sigma (or 20 m) of that side's
   level; otherwise the gap is not tested. Two bad sets among four would otherwise move an even-count median.
6. A gap is a detection if its step is a local maximum within one window, at least the threshold in metres, and at
   least `SNR_MIN` = 5 standard errors.
7. With medians the estimate is almost the same one gap before and after the true one, so the location is refined to
   the neighbouring gap with the smallest L1 misfit of a two-level model (`refine`). Without this, about one in six
   large injected burns was reported one gap early and missed the injection's time window.

**Threshold, pre-registered rule** (`ledger/pipeline.py`): the smallest value on a 25 m grid from 50 m at which the
95% upper bound of false alarms on the passive control group (debris and rocket bodies, median altitude 400 to 600 km,
eccentricity under 0.005, not decaying faster than 2 km over the window) is at most 5% of the filed rate. The result
and its false-alarm rate are in [`threshold`].

**Delta-v.** For a short along-track burn on a near-circular orbit, Gauss's equation gives `da = 2 a dv / v`, so
`dv = v da / (2 a)`. A burn that is not along track changes `a` less for the same delta-v, so reported delta-v is a
lower bound on the real one for non-tangential burns. Along-track position changes (`elements.pair_residual`) are
computed but not used for detection in this version.

## 5. Classes (`ledger/classify.py`)

Regime per satellite over the window, from its GP history (SupGP if GP is too short): **raising** (net rise over
2 km), **descending** (net fall over 2 km: deliberate lowering, deorbit or uncontrolled decay, not told apart), or
**on-station**. Steps on on-station satellites are **drag make-up** if positive with a local decay of at least 30 m per
day, **large on-station** above 1 m/s, and otherwise **avoidance-like**. Avoidance-like is an upper bound on avoidance
burns above the threshold: phasing or slot moves look the same, and some boosts may be misread.

## 6. Rates and error bars (`ledger/reconcile.py`)

Exposure is the total duration of tested gaps, so a satellite seen for 3 days counts for 3 days. Rates are events
per satellite per year of exposure. Intervals are 95%: bootstrap over whole satellites for rates, exact Poisson
(Garwood) for small counts and false alarms, Wilson for recall. Random seeds are fixed.

## 7. The bound

The cleanest test is the band with the weakest drag, on-station satellites at 530 to 600 km [`bound`]:

1. count **every** detected step there, whatever its class (so misclassification cannot hide a burn);
2. take the upper end of the two-sided 95% Poisson (Garwood) interval of that count, per satellite-year
   [`bound.steps_upper95_per_year`]; on its own that end is a 97.5% one-sided bound;
3. inject burns of known size into those same satellites' real histories and measure recall [`bound.injection`];
4. divide (2) by the lower end of the 95% Wilson interval of recall (also 97.5% one-sided): the most burns of at least
   that size per satellite-year that are consistent with what we saw [`bound.rows[].max_rate`].

Two bounds combined this way are conservative. Each end fails at most 2.5% of the time, so by Bonferroni the
combined statement holds with at least about 95% confidence (the Wilson interval is itself approximate). This is what
"conservative 95% bound" means on the page and in the README. A one-sided 95% Poisson bound would give a smaller
number; we keep the larger one.

The detection threshold in metres is the same everywhere, but its delta-v depends on altitude: about
[`threshold.dv_cm_s_at_470km`] cm/s at 470 km and [`bound.threshold_dv_cm_s`] cm/s at the band's median altitude
[`bound.median_alt_km`].

Comparing with the filed rate assumes those satellites dodge about as often as the fleet did in the filing period. We
compare with the lower filed rate (Gen 1): [`bound.rows[].max_share_of_gen1`] is the share shown on the page;
[`bound.rows[].max_share_of_combined`] uses the combined rate instead. DODGE's own screen supports the assumption rather than weakening it: those
satellites have more predicted passes under 1 km per satellite-year than the busiest shells [`bands`].

## 8. Outside judges

| Judge | What it tests | Where |
|---|---|---|
| Synthetic histories with burns of known size, noise and bad-set share measured on the real data | precision and recall per delta-v | [`synthetic`], `tests/test_detect.py` |
| Burns injected into real histories | recall on real noise, per delta-v | [`injection`], [`bound.injection`] |
| Passive debris and rocket bodies | false alarms (they cannot manoeuvre) | [`far`], [`threshold`] |
| Catalogue launch dates, never shown to the detector | satellites launched during the window should be raising; year-old ones should not | [`held_out.by_launch_age`] |
| The FCC report's list of satellites removed from operation | those still in orbit should mostly not be holding altitude | [`held_out.fcc_removed`] |
| SupGP, an independent fit chain from SpaceX's own ephemerides | do both sources see the same step, beyond chance? Chance is measured by sliding SupGP 3 and 4 days either way | [`agreement`] |
| DODGE's first stub (`engine/maneuvers.py`) | what a single threshold on consecutive sets counts | [`dodge_baseline`] |

The pre-registered agreement line (70% beyond chance) was **not met**. Possible reasons, none verified: SupGP sets
are noisier per set than GP; the two sources place the same step in different gaps; the two fit chains differ in ways
we cannot see from public data (section 10, question 3). Agreement is higher for drag make-up than for avoidance-like steps [`agreement`].

## 9. Limits

- **Different months.** Filing: December 2025 to May 2026. Data: October 2026. Solar activity, the debris
  environment and SpaceX's own thresholds may have changed.
- **Only orbit size.** Burns that change only the plane or shape, and pairs of burns that cancel inside one gap, are
  invisible.
- **Short window.** About two weeks of recordings; the low-drag band has a few hundred satellites. The bound is
  limited by exposure and tightens as DODGE records.
- **Classes are heuristics.** The bound does not depend on them; the fleet-wide avoidance-like rate does.
- **GP provenance.** Whether the US Space Force's GP sets for Starlink use SpaceX ephemerides is not known to us.
- **No collision probabilities.** DODGE's passes are screening grade; they are used only to compare exposure between
  altitude bands.
- **Gen 1 and Gen 2 are not separated.** Public data does not say which authorisation a satellite flies under (the
  FCC's own lists show the same naming ranges in both), so the comparison uses the fleet-wide and the lower filed rate.

## 10. What an insider could check

1. Is a typical Starlink avoidance burn smaller than about 16 cm/s along track? If yes, the bound is the expected
   result; if most are larger, something here is wrong and we want to know what.
2. Are the regular boosts every few days in the 460 to 490 km shells drag make-up?
3. Do the ephemerides on api.starlink.com contain planned burns? Comparing successive SpaceX
   ephemeris files directly (rather than CelesTrak's SGP4 fits of them) would be the strongest next cross-check.

## 11. Growing daily

`python -m ledger.pipeline sync` downloads new DODGE days (sealed days are never downloaded twice) and at most one
SupGP file; `python -m ledger.pipeline all` recomputes everything. With more exposure the 95% upper bound in the
low-drag band moves toward the observed rate there ([`bound.steps`] divided by [`bound.exposure_years`]), which today
is about half of the bound; it cannot fall below that unless those steps turn out to be something other than burns.
