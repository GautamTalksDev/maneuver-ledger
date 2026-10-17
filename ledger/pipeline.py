"""Run the whole ledger: data in, events and reconciliation out.

    python -m ledger.pipeline sync    download new DODGE day files (+ one cached SupGP fetch)
    python -m ledger.pipeline run     detect, classify, calibrate, reconcile; writes out/
    python -m ledger.pipeline page    build site/index.html from out/summary.json
    python -m ledger.pipeline all     run + page (no network)

Everything after "sync" is offline and deterministic (fixed random seeds), so two
people with the same day files get byte-identical outputs.

The pre-registered rules (written before looking at the Starlink result):
- Threshold: the smallest step, on a 25 m grid from 50 m, at which the passive
  control group's false-alarm rate (95% upper bound) is at most 5% of the FCC rate.
- Headline population: on-station Starlink satellites whose median altitude is
  inside the control band (400 to 600 km), from public GP sets.
- Agreement line (from the 17 Oct plan): GP and SupGP agree on at least 70% of
  steps above the threshold, after subtracting chance agreement measured by
  time slides.
"""
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import numpy as np

from . import classify as C
from . import detect as D
from . import elements as E
from . import fleet as F
from . import reconcile as R
from . import sources as S
from . import synth as Y

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
DODGE_CACHE = os.path.join(CACHE, "dodge")
CT_CACHE = os.path.join(CACHE, "celestrak")
OUT = os.path.join(ROOT, "out")
FIRST_DAY = "2026-10-06"           # DODGE's first recording day

CONTROL_ALT = (400.0, 600.0)        # km, passive objects used to measure false alarms
CONTROL_MAX_ECC = 0.005
GRID_M = list(range(50, 501, 25))   # thresholds tried, metres of semi-major axis
FAR_SHARE = 0.05                    # false alarms may be at most 5% of the FCC rate
SEED = 2026
INJECT_DV_CM_S = [2, 4, 6, 8, 10, 12, 14, 16, 20, 25, 30, 40, 60]
INJECT_PER_DV = 600
SLIDES_DAYS = (-4.0, -3.0, 3.0, 4.0)
HIGH_BAND = (530.0, 600.0)          # km, the low-drag band used for the headline bound
BOUND_DV_CM_S = (10, 16, 20, 30, 40)
AGREE_WINDOW_DAYS = 0.5


def utc(days):
    return datetime.fromtimestamp(D.T0 + days * 86400.0, timezone.utc)


def iso(days):
    return utc(days).strftime("%Y-%m-%dT%H:%MZ")


# ---------------------------------------------------------------- loading

def load_series():
    extra = sorted(glob.glob(os.path.join(CT_CACHE, "starlink-supgp-*.json")))
    rows = S.read_rows(DODGE_CACHE, extra_supgp=extra)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["kind"], r["NORAD_CAT_ID"])].append(r)
    series = {}
    for (kind, nid), rs in groups.items():
        s = D.build_series(kind, nid, rs)
        if s is None or len(s.t) < 2 * D.MIN_SIDE:
            continue
        if kind == "control":
            alt = float(np.median(s.a)) - E.RE_KM
            if not (CONTROL_ALT[0] < alt < CONTROL_ALT[1]) or float(np.median(s.ecc)) > CONTROL_MAX_ECC:
                continue
            if C.net_change_km(s) < -C.REGIME_KM:
                continue        # fast-decaying debris: not comparable with satellites holding altitude
        series[(kind, nid)] = s
    rows_by_kind = Counter(r["kind"] for r in rows)
    return series, rows_by_kind, extra


def candidates(s):
    """All local-maximum steps of a series (no threshold yet), plus its tested gaps."""
    steps = D.gap_steps(s)
    cands = []
    for g in D.events_from_steps(s, steps, 0.0):
        a_km = float(s.a[g["k"]])
        ev = dict(g)
        ev.update(kind=s.kind, norad=s.norad, name=s.name, a_km=a_km, alt_km=a_km - E.RE_KM,
                  inc_deg=float(s.inc[g["k"]]), dv_m_s=E.dv_from_da(g["step_km"], a_km))
        cands.append(ev)
    exposure = sum(g["t_after"] - g["t_before"] for g in steps)
    return cands, steps, exposure


# ---------------------------------------------------------------- the run

def run():
    rng = np.random.default_rng(SEED)
    os.makedirs(OUT, exist_ok=True)
    series, rows_by_kind, extra = load_series()
    day_status = S.verify_against_manifests(DODGE_CACHE)
    if any(v == "sealed-mismatch" for v in day_status.values()):
        raise SystemExit("a cached day file does not match DODGE's sealed manifest; re-run sync")

    # regime per satellite: from public GP when it has enough history, else SupGP
    regime, alt_of, name_of = {}, {}, {}
    for nid in sorted({k[1] for k in series if k[0] != "control"}):
        gp, sup = series.get(("gp", nid)), series.get(("supgp", nid))
        pick = gp if gp is not None and C.regime(gp) != "short" else (sup if sup is not None else gp)
        regime[nid] = C.regime(pick)
        alt_of[nid] = float(np.median(pick.a)) - E.RE_KM
        name_of[nid] = pick.name

    per = {}
    for key, s in series.items():
        per[key] = candidates(s)

    # ---- calibrate the threshold on the passive control group
    ctrl = [k for k in per if k[0] == "control"]
    ctrl_exposure = sum(per[k][2] for k in ctrl)
    fcc_fleet_satcat = None
    satcat_files = sorted(glob.glob(os.path.join(DODGE_CACHE, "satcat-*.csv.gz")))
    satcat_rows = F.starlink_payloads(satcat_files[-1])
    fleet_mean, fleet_first, fleet_last = F.mean_in_orbit(satcat_rows, F.FCC["period_start"], F.FCC["period_end"])
    fcc_fleet_satcat = fleet_mean
    fcc_rate = F.fcc_combined_rate(fleet_mean)
    far_rows = []
    threshold_m = None
    for t in GRID_M:
        n = sum(1 for k in ctrl for ev in per[k][0] if abs(ev["step_km"]) * 1000 >= t)
        rate, up = R.false_alarm(n, ctrl_exposure)
        far_rows.append(dict(threshold_m=t, control_events=n, far_per_year=rate, far_upper95=up))
        if threshold_m is None and up <= FAR_SHARE * fcc_rate:
            threshold_m = t
    if threshold_m is None:
        threshold_m = GRID_M[-1]
    thr_km = threshold_m / 1000.0
    far_at = next(r for r in far_rows if r["threshold_m"] == threshold_m)

    # ---- detect and classify (public GP is the primary source)
    sup_steps = {k[1]: per[k][1] for k in per if k[0] == "supgp"}
    events = []
    for (kind, nid), (cands, steps, exposure) in per.items():
        if kind == "control":
            continue
        reg = regime.get(nid, "short")
        for ev in cands:
            if abs(ev["step_km"]) < thr_km:
                continue
            ev = dict(ev)
            ev["regime"] = reg
            ev["class"] = C.classify_event(ev, reg)
            if kind == "gp":
                ev["supgp_step_km"] = _step_near(sup_steps.get(nid), ev["t_mid"])
            events.append(ev)

    def in_band(nid):
        return nid in alt_of and CONTROL_ALT[0] < alt_of[nid] < CONTROL_ALT[1]

    # ---- rates for the headline population
    head = [nid for (kind, nid) in per if kind == "gp" and regime.get(nid) == "on-station" and in_band(nid)]
    head_set = set(head)
    expo = {nid: per[("gp", nid)][2] for nid in head}
    counts = {c: defaultdict(int) for c in C.CLASSES}
    for ev in events:
        if ev["kind"] == "gp" and ev["norad"] in head_set:
            counts[ev["class"]][ev["norad"]] += 1
    total_expo = sum(expo.values())
    rates = {}
    for c in C.CLASSES:
        k = sum(counts[c].values())
        lo, hi = R.bootstrap_rate([counts[c][n] for n in head], [expo[n] for n in head], rng)
        rates[c] = dict(count=k, rate=R.rate_per_year(k, total_expo), lo95=lo, hi95=hi)
    av = rates["avoidance-like"]
    av_corr = dict(rate=max(0.0, av["rate"] - far_at["far_per_year"]),
                   lo95=max(0.0, av["lo95"] - far_at["far_upper95"]), hi95=av["hi95"])
    sign = Counter("up" if ev["step_km"] > 0 else "down" for ev in events
                   if ev["kind"] == "gp" and ev["norad"] in head_set and ev["class"] == "avoidance-like")
    # the same population seen through SupGP (secondary: fits of SpaceX's predicted ephemerides)
    sup_head = [n for n in head if ("supgp", n) in per]
    sup_expo = sum(per[("supgp", n)][2] for n in sup_head)
    sup_counts = Counter(ev["class"] for ev in events if ev["kind"] == "supgp" and ev["norad"] in head_set)
    supgp_rates = dict(satellites=len(sup_head), exposure_days=sup_expo,
                       **{c: R.rate_per_year(sup_counts.get(c, 0), sup_expo) for c in C.CLASSES})

    # ---- the same rates at every threshold (the detection-limit curve)
    curve = []
    for t in GRID_M:
        row = dict(threshold_m=t, dv_cm_s=round(E.dv_from_da(t / 1000.0, E.RE_KM + 470.0) * 100, 2))
        for c in ("avoidance-like", "drag make-up"):
            k = 0
            for nid in head:
                for ev in per[("gp", nid)][0]:
                    if abs(ev["step_km"]) * 1000 >= t and C.classify_event(ev, "on-station") == c:
                        k += 1
            row[c] = R.rate_per_year(k, total_expo)
        row["control_far"] = next(r["far_per_year"] for r in far_rows if r["threshold_m"] == t)
        curve.append(row)

    # ---- altitude bands, with DODGE's independent close-approach screen as the exposure check
    conj, conj_days = conjunctions(head_set)
    bands = []
    for lo_b, hi_b in ((400, 460), (460, 475), (475, 490), (490, 530), (530, 600)):
        ids = [n for n in head if lo_b <= alt_of[n] < hi_b]
        ex = sum(expo[n] for n in ids)
        row = dict(band=f"{lo_b} to {hi_b} km", satellites=len(ids), exposure_days=ex)
        for c in ("avoidance-like", "drag make-up"):
            k = sum(counts[c][n] for n in ids)
            row[c] = R.rate_per_year(k, ex) if ex else None
            row[c + " count"] = k
            row[c + " upper95"] = R.rate_per_year(R.poisson_interval(k)[1], ex) if ex else None
        if conj_days:
            for lim in ("under_1km", "under_5km"):
                row["passes_" + lim] = sum(conj[lim][n] for n in ids) / (len(ids) * conj_days) * 365.25 if ids else None
        bands.append(row)

    # ---- outside judge 1: injected burns in REAL on-station histories
    inj = injection_recall(series, head, thr_km, rng)

    # ---- the bound: how many avoidance burns of a given size public data could be hiding.
    #      Cleanest band = highest on-station satellites (weakest drag, so fewest drag make-up
    #      boosts). Count EVERY on-station step there (any class), take the upper end of the
    #      two-sided 95% Poisson (Garwood) interval (97.5% one-sided), divide by the lower end of
    #      the 95% recall interval for burns of that size on real histories. Two separate bounds
    #      combined this way make the result conservative: each end fails at most 2.5% of the time
    #      (one-sided), so by Bonferroni the joint coverage is at least about 95% (Wilson is approximate).
    hb_ids = [n for n in head if HIGH_BAND[0] <= alt_of[n] < HIGH_BAND[1]]
    hb_expo = sum(expo[n] for n in hb_ids)
    hb_k = sum(counts[c][n] for n in hb_ids for c in ("avoidance-like", "drag make-up", "large on-station"))
    hb_up = R.rate_per_year(R.poisson_interval(hb_k)[1], hb_expo) if hb_expo else float("nan")

    # ---- outside judge 2: synthetic orbits with known burns (precision and recall),
    #      with the noise level and bad-set share measured on the real headline histories
    noise = noise_model([series[("gp", n)] for n in head], per)
    syn = synthetic_exam(noise["sigma_km"], noise["outlier_share"], thr_km, rng)

    bound_rows = []
    inj_hb = injection_recall(series, hb_ids, thr_km, rng, dvs=BOUND_DV_CM_S) if hb_ids else []
    for r in inj_hb:
        if r["dv_cm_s"] in BOUND_DV_CM_S and r["lo95"] > 0:
            mx = hb_up / r["lo95"]
            bound_rows.append(dict(dv_cm_s=r["dv_cm_s"], recall_lo95=r["lo95"], max_rate=mx,
                                   max_share_of_combined=mx / fcc_rate,
                                   max_share_of_gen1=mx / F.FCC["gen1_rate_stated"]))
    hb_alt = float(np.median([alt_of[n] for n in hb_ids])) if hb_ids else float("nan")
    bound = dict(band=f"{HIGH_BAND[0]:.0f} to {HIGH_BAND[1]:.0f} km", satellites=len(hb_ids), exposure_days=hb_expo,
                 exposure_years=hb_expo / 365.25, steps=hb_k, steps_upper95_per_year=hb_up, rows=bound_rows,
                 injection=inj_hb, median_alt_km=hb_alt,
                 threshold_dv_cm_s=E.dv_from_da(thr_km, E.RE_KM + hb_alt) * 100 if hb_ids else float("nan"),
                 interval="upper end of the two-sided 95% Garwood interval (97.5% one-sided), divided by the "
                          "lower end of the 95% Wilson recall interval (also 97.5% one-sided); conservative, joint "
                          "coverage at least about 95% by Bonferroni")

    # ---- outside judge 3: GP against SupGP (independent processing of the same satellites)
    agree = agreement(events, head_set, sup_steps)

    # ---- held-out checks against public events the detector never saw
    held = held_out(regime, name_of, satcat_rows)

    # ---- the DODGE stub, for comparison
    baseline = dodge_baseline()

    # ---- three example histories for the page (chosen by rule, not by hand)
    launch_of = {}
    for r in satcat_rows:
        try:
            launch_of[int(r["NORAD_CAT_ID"])] = r.get("LAUNCH_DATE") or ""
        except ValueError:
            pass
    examples = pick_examples(series, per, events, head, regime, alt_of, launch_of)

    # ---- coverage
    kinds = Counter(k[0] for k in series)
    t_first = min(float(s.t[0]) for k, s in series.items() if k[0] != "control")
    t_last = max(float(s.t[-1]) for k, s in series.items() if k[0] != "control")
    expected_fcc = fcc_rate * total_expo / 365.25
    summary = dict(
        generated_from=dict(days=day_status, supgp_fetches=[os.path.basename(p) for p in extra],
                            rows=dict(rows_by_kind), series=dict(kinds)),
        coverage=dict(first_epoch=iso(t_first), last_epoch=iso(t_last), span_days=t_last - t_first,
                      headline_satellites=len(head), headline_exposure_days=total_expo,
                      headline_exposure_years=total_expo / 365.25, regimes=dict(Counter(regime.values())),
                      control_objects=len(ctrl), control_exposure_days=ctrl_exposure),
        fcc=dict(total=F.fcc_total(), gen1=F.FCC["gen1_maneuvers"], gen2=F.FCC["gen2_maneuvers"],
                 gen1_rate_stated=F.FCC["gen1_rate_stated"], gen2_rate_stated=F.FCC["gen2_rate_stated"],
                 period_days=F.period_days(), period_years=F.period_years(),
                 implied_fleet_gen1=F.implied_fleet(F.FCC["gen1_maneuvers"], F.FCC["gen1_rate_stated"]),
                 implied_fleet_gen2=F.implied_fleet(F.FCC["gen2_maneuvers"], F.FCC["gen2_rate_stated"]),
                 satcat_mean_fleet=fleet_mean, satcat_fleet_first=fleet_first, satcat_fleet_last=fleet_last,
                 satcat_file=os.path.basename(satcat_files[-1]),
                 combined_rate=fcc_rate, url=F.FCC["url"], pdf_sha256=F.FCC["pdf_sha256"],
                 quote_counts=F.FCC["quote_counts"], quote_threshold=F.FCC["quote_threshold"]),
        threshold=dict(m=threshold_m, dv_cm_s_at_470km=E.dv_from_da(thr_km, E.RE_KM + 470.0) * 100,
                       far_per_year=far_at["far_per_year"], far_upper95=far_at["far_upper95"],
                       control_events=far_at["control_events"], rule=f"smallest grid value with control FAR 95% upper <= {FAR_SHARE:.0%} of the FCC rate"),
        rates=rates, avoidance_corrected=av_corr, avoidance_sign=dict(sign), supgp_rates=supgp_rates,
        conjunction_days=conj_days, bound=bound,
        expected_fcc_events_in_exposure=expected_fcc,
        avoidance_share_of_combined=dict(rate=av_corr["rate"] / fcc_rate, hi95=av_corr["hi95"] / fcc_rate),
        curve=curve, bands=bands, far=far_rows, injection=inj, synthetic=syn, agreement=agree, noise=noise,
        held_out=held, dodge_baseline=baseline, examples=examples,
        constants=dict(control_alt_lo=CONTROL_ALT[0], control_alt_hi=CONTROL_ALT[1], far_share=FAR_SHARE,
                       high_band_lo=HIGH_BAND[0], high_band_hi=HIGH_BAND[1], confidence=0.95,
                       pass_limit_km=1.0, recorder_every_hours=4, window_days=D.WINDOW_DAYS,
                       snr_min=D.SNR_MIN, sizes_m=[GRID_M[0], GRID_M[-1]], dv_reference_alt_km=470.0,
                       one_sided_level=0.975, joint_coverage_min=1.0 - 2 * (1.0 - 0.975)),
    )
    summary["fcc"].update(period_start=F.FCC["period_start"], period_end=F.FCC["period_end"],
                          letter_date="2026-07-01")
    write_outputs(summary, events, series, per, regime, alt_of)
    return summary


def pick_examples(series, per, events, head, regime, alt_of, launch_of=None):
    """Three public histories that show the method at work, picked by fixed rules:
    the on-station satellite with the most drag make-up boosts, the on-station
    satellite with the biggest single bad set that produced no detection, and the
    raising satellite launched during the window (catalogue date) with the most sets."""
    ev_by = defaultdict(list)
    for e in events:
        if e["kind"] == "gp":
            ev_by[e["norad"]].append(e)

    def pack(nid, why):
        s = series[("gp", nid)]
        base = float(s.a[0])
        return dict(norad=nid, name=s.name, why=why, alt_km=alt_of.get(nid),
                    t=[iso(x) for x in s.t], t_days=[float(x) for x in s.t],
                    da_m=[round((float(x) - base) * 1000.0, 1) for x in s.a],
                    events=[dict(t_mid=float(e["t_mid"]), step_m=round(e["step_km"] * 1000.0, 1), cls=e["class"])
                            for e in ev_by.get(nid, [])])
    out = []
    drag = sorted(head, key=lambda n: (-sum(1 for e in ev_by.get(n, []) if e["class"] == "drag make-up"), n))
    if drag:
        out.append(pack(drag[0], "most drag make-up boosts"))
    best, best_size = None, 0.0
    for n in head:
        s = series[("gp", n)]
        for i in range(2, len(s.t) - 2):
            nb = [s.a[j] for j in (i - 2, i - 1, i + 1, i + 2)]
            if max(nb) - min(nb) > 0.150:
                continue
            size = abs(s.a[i] - float(np.median(nb)))
            near = any(abs(e["t_mid"] - s.t[i]) < 1.0 for e in ev_by.get(n, []))
            if size > best_size and not near and size < 3.0:
                best, best_size = n, size
    if best is not None:
        out.append(pack(best, "biggest single bad set, correctly ignored"))
    recent = {n for n, d in (launch_of or {}).items() if d >= FIRST_DAY}
    raising = sorted((n for n, r in regime.items() if r == "raising" and ("gp", n) in series and n in recent),
                     key=lambda n: (-len(series[("gp", n)].t), n))
    if raising:
        ex = pack(raising[0], f"orbit raising after its launch on {launch_of[raising[0]]}")
        ex["launch_date"] = launch_of[raising[0]]
        out.append(ex)
    return out


def conjunctions(head_set):
    """Predicted close approaches per Starlink satellite, from DODGE's daily screens.

    DODGE screens every Starlink satellite against the rest of the catalogue once a
    day for the next 24 hours and publishes every pass under 5 km
    (events-YYYY-MM-DD.json.gz). These are screening-grade misses from public orbits,
    not collision probabilities; here they only show whether close-approach exposure
    changes with altitude. Returns ({"under_1km": Counter, "under_5km": Counter}, days).
    """
    import gzip
    files = sorted(glob.glob(os.path.join(DODGE_CACHE, "events-*.json.gz")))
    out = {"under_1km": Counter(), "under_5km": Counter()}
    for p in files:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for e in json.load(f):
                nid = (e.get("starlink") or {}).get("id")
                if nid not in head_set:
                    continue
                out["under_5km"][nid] += 1
                if float(e.get("miss_km", 99)) < 1.0:
                    out["under_1km"][nid] += 1
    return out, len(files)


def _step_near(steps, t_mid, window=AGREE_WINDOW_DAYS):
    """The step another source measured at the gap nearest t_mid, or None."""
    if not steps:
        return None
    best = min(steps, key=lambda g: abs(g["t_mid"] - t_mid))
    return best["step_km"] if abs(best["t_mid"] - t_mid) <= window else None


def _agrees(gp_step, sup_step):
    return sup_step is not None and np.sign(sup_step) == np.sign(gp_step) and abs(sup_step) >= 0.5 * abs(gp_step)


def agreement(events, head_set, sup_steps):
    """Share of GP steps that SupGP also shows, against chance (time slides)."""
    evs = [e for e in events if e["kind"] == "gp" and e["norad"] in head_set and e["class"] in ("avoidance-like", "drag make-up")]
    out = {}
    for cls in ("avoidance-like", "drag make-up", "all"):
        sel = [e for e in evs if cls == "all" or e["class"] == cls]
        testable = [e for e in sel if _step_near(sup_steps.get(e["norad"]), e["t_mid"]) is not None]
        hit = sum(1 for e in testable if _agrees(e["step_km"], _step_near(sup_steps.get(e["norad"]), e["t_mid"])))
        slide_hits, slide_n = 0, 0
        for sh in SLIDES_DAYS:
            for e in sel:
                v = _step_near(sup_steps.get(e["norad"]), e["t_mid"] + sh)
                if v is None:
                    continue
                slide_n += 1
                slide_hits += _agrees(e["step_km"], v)
        p = hit / len(testable) if testable else float("nan")
        bg = slide_hits / slide_n if slide_n else float("nan")
        excess = (p - bg) / (1 - bg) if testable and slide_n and bg < 1 else float("nan")
        out[cls] = dict(events=len(sel), testable=len(testable), agree=hit, agree_share=p,
                        chance_share=bg, beyond_chance=excess)
    out["pre_registered_line"] = 0.70
    out["met"] = bool(out["all"]["beyond_chance"] >= 0.70) if out["all"]["testable"] else False
    return out


def injection_recall(series, head, thr_km, rng, dvs=INJECT_DV_CM_S):
    """Recall when a burn of known delta-v is added to a real on-station GP history."""
    pool = [series[("gp", n)] for n in head]
    rows = []
    for dv_cm in dvs:
        found, n_try = 0, 0
        for _ in range(INJECT_PER_DV):
            s = pool[int(rng.integers(0, len(pool)))]
            gaps = D.gap_steps(s)
            if not gaps:
                continue
            g = gaps[int(rng.integers(0, len(gaps)))]
            sign = 1.0 if rng.random() < 0.5 else -1.0
            da = E.da_from_dv(sign * dv_cm / 100.0, float(s.a[g["k"]]))
            s2 = Y.inject(s, g["k"], da)
            evs, _ = D.detect_series(s2, thr_km)
            n_try += 1
            tb = 0.5 * (g["t_before"] + g["t_after"])
            tp, _, _ = Y.match(evs, [(tb, sign, da)], slack_days=0.0)
            found += tp
        p, lo, hi = R.wilson(found, n_try)
        rows.append(dict(dv_cm_s=dv_cm, trials=n_try, recall=p, lo95=lo, hi95=hi))
    return rows


def noise_model(series_list, per):
    """Fit noise and bad-set share of real histories, to make the synthetic exam realistic.

    sigma: 1.4826 x the median local spread (a robust standard deviation of one set).
    bad sets: a set more than 300 m from the median of its four neighbours while those
    four agree with each other within 150 m (after the local trend is removed). A real
    step does not qualify, because its neighbours then disagree.
    """
    spreads = [g["spread_km"] for s in series_list for g in per[(s.kind, s.norad)][1]]
    bad, tested = 0, 0
    for s in series_list:
        for i in range(2, len(s.t) - 2):
            nb = [i - 2, i - 1, i + 1, i + 2]
            slope = D.local_slope(s.t, s.a, i)
            vals = np.array([s.a[j] + slope * (s.t[i] - s.t[j]) for j in nb])
            if vals.max() - vals.min() > 0.150:
                continue
            tested += 1
            bad += abs(s.a[i] - float(np.median(vals))) > 0.300
    return dict(sigma_km=float(np.median(spreads)) * 1.4826 if spreads else 0.01,
                outlier_share=bad / tested if tested else 0.0, tested_sets=tested, bad_sets=bad)


def synthetic_exam(sigma_km, outlier_share, thr_km, rng, n_sats=400):
    """Precision and recall on synthetic histories with known burns, per delta-v.

    Burns are 3.2 to 4.5 days apart (isolated, like most real steps), with random
    sign, on top of drag decay of 0 to 30 m per day, fit noise and bad sets.
    """
    out = []
    for dv_cm in INJECT_DV_CM_S:
        tp = fp = fn = 0
        for i in range(n_sats):
            burns = []
            t = rng.uniform(1.6, 3.0)
            while t < 9.4:
                burns.append((t, (1 if rng.random() < 0.5 else -1) * dv_cm / 100.0))
                t += rng.uniform(3.2, 4.5)
            s, truth = Y.synthetic_series(rng, sigma_km=sigma_km, p_outlier=outlier_share, burns=burns,
                                          slope_km_day=rng.uniform(-0.03, 0.0), norad=i)
            evs, _ = D.detect_series(s, thr_km)
            a, b, c = Y.match(evs, truth)
            tp, fp, fn = tp + a, fp + b, fn + c
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        out.append(dict(dv_cm_s=dv_cm, burns=tp + fn, detected=tp + fp, precision=prec, recall=rec))
    noise_only, noise_days = 0, 0.0
    for i in range(n_sats):
        s, _ = Y.synthetic_series(rng, sigma_km=sigma_km, p_outlier=outlier_share, norad=10000 + i)
        noise_only += len(D.detect_series(s, thr_km)[0])
        noise_days += float(s.t[-1] - s.t[0])
    return dict(sigma_m=sigma_km * 1000, outlier_share=outlier_share, by_dv=out, noise_only_series=n_sats,
                noise_only_false_alarms=noise_only, noise_only_days=noise_days)


def held_out(regime, name_of, satcat_rows):
    """Compare regimes with public facts the detector never used."""
    window_start = date.fromisoformat(FIRST_DAY)
    by_name = {r["OBJECT_NAME"]: r for r in satcat_rows}
    nid_of = {}
    for r in satcat_rows:
        try:
            nid_of[r["OBJECT_NAME"]] = int(r["NORAD_CAT_ID"])
        except ValueError:
            pass
    out = {}
    # 1. recently launched satellites should be raising
    bins = [("launched in the window", -20, -1), ("0 to 20 days before", 0, 20), ("21 to 40 days before", 21, 40),
            ("41 to 60 days before", 41, 60), ("over a year before", 366, 10 ** 6)]
    by_age = {b[0]: Counter() for b in bins}
    for r in satcat_rows:
        try:
            nid = int(r["NORAD_CAT_ID"])
        except ValueError:
            continue
        if nid not in regime or not r.get("LAUNCH_DATE"):
            continue
        age = (window_start - date.fromisoformat(r["LAUNCH_DATE"])).days
        for label, lo, hi in bins:
            if lo <= age <= hi:
                by_age[label][regime[nid]] += 1
    out["by_launch_age"] = [dict(label=b[0], **{k: by_age[b[0]].get(k, 0) for k in
                                                ("raising", "on-station", "descending", "short")}) for b in bins]
    # 2. satellites SpaceX told the FCC it removed from operation for disposal
    path = os.path.join(ROOT, "data", "fcc_2026-07-01_lists.json")
    with open(path) as f:
        lists = json.load(f)["lists"]
    removed = {n for key in ("removed_gen1", "removed_gen2") for n, _ in lists.get(key, [])}
    still = [n for n in removed if n in by_name and not by_name[n].get("DECAY_DATE")]
    reg = Counter(regime.get(nid_of.get(n), "not in our data") for n in still)
    out["fcc_removed"] = dict(listed=len(removed), still_in_orbit=len(still), regimes=dict(reg))
    return out


def dodge_baseline():
    """What DODGE's first stub (engine/maneuvers.py) counts on the same public sets."""
    dodge_dir = os.environ.get("DODGE_DIR", os.path.expanduser("~/projects/dodge-shape"))
    path = os.path.join(dodge_dir, "engine", "maneuvers.py")
    if not os.path.exists(path):
        return dict(available=False)
    import importlib.util
    spec = importlib.util.spec_from_file_location("dodge_maneuvers", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = [dict(r, src="active") for r in S.read_rows(DODGE_CACHE, want=("gp",))]
    seen, span = mod.detect(rows)
    jumps = sum(seen.values())
    objs = len(seen)
    return dict(available=True, file="engine/maneuvers.py", threshold_km=mod.THRESHOLD_KM, objects=objs,
                jumps=jumps, span_days=span,
                jumps_per_object_year=(jumps / objs / (span / 365.25)) if objs and span else None)


# ---------------------------------------------------------------- writing

def write_outputs(summary, events, series, per, regime, alt_of):
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True, default=float)
        f.write("\n")
    cols = ["norad", "name", "source", "t_before_utc", "t_after_utc", "step_m", "dv_cm_s", "slope_m_per_day",
            "alt_km", "inc_deg", "regime", "class", "sets_before", "sets_after", "local_spread_m", "supgp_step_m"]
    events = sorted(events, key=lambda e: (e["t_mid"], e["norad"], e["kind"]))
    with open(os.path.join(OUT, "events.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for e in events:
            sup = e.get("supgp_step_km")
            w.writerow([e["norad"], e["name"], e["kind"], iso(e["t_before"]), iso(e["t_after"]),
                        f"{e['step_km'] * 1000:.1f}", f"{e['dv_m_s'] * 100:.2f}", f"{e['slope_km_day'] * 1000:.1f}",
                        f"{e['alt_km']:.1f}", f"{e['inc_deg']:.2f}", e["regime"], e["class"], e["n_left"],
                        e["n_right"], f"{e['spread_km'] * 1000:.1f}", "" if sup is None else f"{sup * 1000:.1f}"])
    with open(os.path.join(OUT, "noise.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["norad", "name", "source", "sets", "span_days", "median_alt_km", "regime", "median_local_spread_m", "tested_gaps"])
        for (kind, nid), s in sorted(series.items()):
            steps = per[(kind, nid)][1]
            spread = float(np.median([g["spread_km"] for g in steps])) * 1000 if steps else float("nan")
            w.writerow([nid, s.name, kind, len(s.t), f"{s.t[-1] - s.t[0]:.2f}",
                        f"{float(np.median(s.a)) - E.RE_KM:.1f}", regime.get(nid, "control" if kind == "control" else "short"),
                        f"{spread:.1f}", len(steps)])


def sync():
    today = datetime.now(timezone.utc).date().isoformat()
    got = S.sync_dodge(DODGE_CACHE, FIRST_DAY, today)
    path = S.fetch_supgp_once(CT_CACHE)
    print(json.dumps(dict(dodge=got, supgp=path), indent=1))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd == "sync":
        sync()
    elif cmd in ("run", "all"):
        s = run()
        print(json.dumps(dict(threshold_m=s["threshold"]["m"], avoidance_like=s["rates"]["avoidance-like"],
                              fcc_rate=s["fcc"]["combined_rate"]), indent=1, default=float))
        if cmd == "all":
            from . import page, readme
            page.build(os.path.join(OUT, "summary.json"), os.path.join(ROOT, "site", "index.html"))
            readme.update(os.path.join(ROOT, "README.md"), s)
    elif cmd == "page":
        from . import page
        page.build(os.path.join(OUT, "summary.json"), os.path.join(ROOT, "site", "index.html"))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
