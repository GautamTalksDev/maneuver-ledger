"""The static results page: one HTML file, inline SVG charts, no scripts.

Rules this file enforces (and tests/test_page.py checks):
- every number in the page's prose and tables is read from out/summary.json through
  Page.num(), Page.derived(), Page.text() or Page.date(), which record it, so a
  test can trace each one back (numbers inside the SVG charts are axis ticks);
- no scripts, no external images, fonts or styles; one <style> block whose SHA-256 is
  pinned in the page's Content-Security-Policy;
- no em or en dashes anywhere;
- presentation attributes only inside SVG (no style="" attributes, which the CSP
  would block).
It is written to drop into DODGE's site later (same signal colour, dark theme).
"""
import base64
import hashlib
import html
import json
import math

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")
ACCENT = "#f4733b"       # DODGE's signal colour
BLUE = "#7aa2c7"
GREY = "#8a8f98"
INK = "#e8e6e3"

CSS = """
:root{color-scheme:dark}
body{margin:0;background:#0b0d10;color:#e8e6e3;font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:34px;line-height:1.15;margin:0 0 6px;letter-spacing:.5px}
h2{font-size:22px;margin:48px 0 10px}
h3{font-size:17px;margin:24px 0 8px}
p,li{color:#cfd2d6}
a{color:#f4733b}
.kicker{color:#8a8f98;font-size:13px;letter-spacing:2px;text-transform:uppercase}
.lede{font-size:19px;color:#e8e6e3}
.box{border:1px solid #2a2f36;border-radius:10px;padding:18px 20px;background:#11151a;margin:18px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
.cell{border:1px solid #2a2f36;border-radius:10px;padding:14px 16px;background:#11151a}
.cell b{display:block;font-size:28px;color:#e8e6e3}
.cell span{color:#8a8f98;font-size:14px}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}
th,td{border-bottom:1px solid #2a2f36;padding:7px 8px;text-align:left;vertical-align:top}
th{color:#8a8f98;font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.pass{color:#6fcf97}.fail{color:#f4733b}
svg{width:100%;height:auto;display:block;margin:6px 0 2px}
.cap{color:#8a8f98;font-size:13px;margin:0 0 10px}
code{background:#1a1f26;padding:1px 5px;border-radius:4px;font-size:14px}
footer{margin-top:60px;color:#8a8f98;font-size:13px}
.chart{overflow-x:auto}
@media (max-width:600px){h1{font-size:26px}.cell b{font-size:24px}table{font-size:13px}.chart svg{min-width:720px}}
"""


def esc(s):
    return html.escape(str(s), quote=True)


class Page:
    """Collects HTML parts and records every number it prints, with where it came from."""

    def __init__(self, summary):
        self.s = summary
        self.used = []          # (rendered text, source path)
        self.parts = []

    def get(self, path):
        cur = self.s
        for key in path.split("."):
            cur = cur[int(key)] if isinstance(cur, list) else cur[key]
        return cur

    @staticmethod
    def _fmt(v, fmt):
        if fmt == "int":
            return f"{int(round(v)):,}"
        if fmt == "pct":
            return f"{v * 100:.0f}%"
        if fmt == "pct1":
            return f"{v * 100:.1f}%"
        return format(v, fmt)

    def num(self, path, fmt=".1f"):
        text = self._fmt(self.get(path), fmt)
        self.used.append((text, path))
        return text

    def derived(self, value, fmt, how):
        text = self._fmt(value, fmt)
        self.used.append((text, "derived: " + how))
        return text

    def text(self, path):
        """A string from the summary (a band name, a satellite name), escaped and recorded."""
        raw = str(self.get(path))
        self.used.append((raw, path))
        return esc(raw)

    def date(self, path):
        """An ISO date from the summary written as '1 December 2025', recorded."""
        raw = str(self.get(path))[:10]
        y, m, d = int(raw[:4]), int(raw[5:7]), int(raw[8:10])
        text = f"{d} {MONTHS[m - 1]} {y}"
        self.used.append((text, path))
        return text

    def add(self, s):
        self.parts.append(s)


# ---------------------------------------------------------------- charts

def _axis_ticks(lo, hi, n=5):
    step = (hi - lo) / n
    return [lo + i * step for i in range(n + 1)]


def line_chart(title, desc, series, x_label, y_label, x_range, y_range, log_y=False, vlines=(), hlines=(),
               width=900, height=360):
    """series: [(label, colour, [(x, y), ...], dashed)]. Returns SVG text.

    The legend sits in its own row above the plot, so it can never cover a curve.
    """
    L, Rm, T, B = 70, 20, 44, 50
    W, H = width - L - Rm, height - T - B
    x0, x1 = x_range
    y0, y1 = y_range
    uid = "c" + hashlib.sha256(title.encode()).hexdigest()[:8]

    def X(x):
        return L + (x - x0) / (x1 - x0) * W

    def Yv(y):
        if log_y:
            y = min(max(y, y0), y1)
            return T + H - (math.log10(y) - math.log10(y0)) / (math.log10(y1) - math.log10(y0)) * H
        return T + H - (y - y0) / (y1 - y0) * H

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="{uid}t {uid}d">',
           f'<title id="{uid}t">{esc(title)}</title><desc id="{uid}d">{esc(desc)}</desc>',
           f'<rect x="{L}" y="{T}" width="{W}" height="{H}" fill="#0f1317" stroke="#2a2f36"/>']
    xt = _axis_ticks(x0, x1)
    yt = ([10.0 ** e for e in range(int(math.floor(math.log10(y0))), int(math.ceil(math.log10(y1))) + 1)]
          if log_y else _axis_ticks(y0, y1))
    for v in xt:
        out.append(f'<line x1="{X(v):.1f}" y1="{T}" x2="{X(v):.1f}" y2="{T + H}" stroke="#1d2228"/>')
        out.append(f'<text x="{X(v):.1f}" y="{T + H + 18}" fill="{GREY}" font-size="12" text-anchor="middle">{v:g}</text>')
    for v in yt:
        if v < y0 or v > y1:
            continue
        out.append(f'<line x1="{L}" y1="{Yv(v):.1f}" x2="{L + W}" y2="{Yv(v):.1f}" stroke="#1d2228"/>')
        out.append(f'<text x="{L - 8}" y="{Yv(v) + 4:.1f}" fill="{GREY}" font-size="12" text-anchor="end">{v:g}</text>')
    for xv, label, colour in vlines:
        out.append(f'<line x1="{X(xv):.1f}" y1="{T}" x2="{X(xv):.1f}" y2="{T + H}" stroke="{colour}" stroke-dasharray="4 4"/>')
        out.append(f'<text x="{X(xv) + 4:.1f}" y="{T + H - 8}" fill="{colour}" font-size="12">{esc(label)}</text>')
    for yv, label, colour in hlines:
        out.append(f'<line x1="{L}" y1="{Yv(yv):.1f}" x2="{L + W}" y2="{Yv(yv):.1f}" stroke="{colour}" stroke-dasharray="6 4"/>')
        out.append(f'<text x="{L + W - 4}" y="{Yv(yv) - 6:.1f}" fill="{colour}" font-size="12" text-anchor="end">{esc(label)}</text>')
    lx = L
    for label, colour, pts, dashed in series:
        pts = [(x, y) for x, y in pts if y is not None and not (isinstance(y, float) and math.isnan(y))]
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(x):.1f},{Yv(y):.1f}" for i, (x, y) in enumerate(pts))
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        out.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="2.2"{dash}/>')
        for x, y in pts:
            out.append(f'<circle cx="{X(x):.1f}" cy="{Yv(y):.1f}" r="2.6" fill="{colour}"/>')
        out.append(f'<rect x="{lx}" y="14" width="14" height="3" fill="{colour}"/>')
        out.append(f'<text x="{lx + 20}" y="19" fill="{INK}" font-size="12">{esc(label)}</text>')
        lx += 20 + 7 * len(label) + 28
    out.append(f'<text x="{L + W / 2:.1f}" y="{height - 10}" fill="{GREY}" font-size="12" text-anchor="middle">{esc(x_label)}</text>')
    out.append(f'<text x="16" y="{T + H / 2:.1f}" fill="{GREY}" font-size="12" text-anchor="middle" '
               f'transform="rotate(-90 16 {T + H / 2:.1f})">{esc(y_label)}</text>')
    out.append("</svg>")
    return "".join(out)


def history_chart(ex, width=900, height=230):
    """One satellite's mean semi-major axis history with its detected steps marked."""
    t, y = ex["t_days"], ex["da_m"]
    x0, x1 = min(t), max(t)
    lo, hi = min(y), max(y)
    pad = max(50.0, 0.1 * (hi - lo))
    lo, hi = lo - pad, hi + pad
    L, Rm, T, B = 70, 20, 14, 36
    W, H = width - L - Rm, height - T - B

    def X(v):
        return L + (v - x0) / ((x1 - x0) or 1.0) * W

    def Yv(v):
        return T + H - (v - lo) / (hi - lo) * H

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(ex["name"])}: {esc(ex["why"])}">',
           f'<rect x="{L}" y="{T}" width="{W}" height="{H}" fill="#0f1317" stroke="#2a2f36"/>']
    for e in ex["events"]:
        colour = ACCENT if e["cls"] in ("avoidance-like", "large on-station") else BLUE
        out.append(f'<line x1="{X(e["t_mid"]):.1f}" y1="{T}" x2="{X(e["t_mid"]):.1f}" y2="{T + H}" stroke="{colour}" '
                   f'stroke-dasharray="3 3"/>')
        out.append(f'<text x="{X(e["t_mid"]) + 3:.1f}" y="{T + 12}" fill="{colour}" font-size="11">{esc(e["cls"])}</text>')
    d = " ".join(f"{'M' if i == 0 else 'L'}{X(a):.1f},{Yv(b):.1f}" for i, (a, b) in enumerate(zip(t, y)))
    out.append(f'<path d="{d}" fill="none" stroke="{GREY}" stroke-width="1.2"/>')
    for a, b in zip(t, y):
        out.append(f'<circle cx="{X(a):.1f}" cy="{Yv(b):.1f}" r="3" fill="{INK}"/>')
    for v in (lo + pad, hi - pad):
        out.append(f'<text x="{L - 8}" y="{Yv(v) + 4:.1f}" fill="{GREY}" font-size="11" text-anchor="end">{v:+.0f} m</text>')
    out.append(f'<text x="{L}" y="{height - 8}" fill="{GREY}" font-size="11">{esc(ex["t"][0][:10])}</text>')
    out.append(f'<text x="{L + W}" y="{height - 8}" fill="{GREY}" font-size="11" text-anchor="end">{esc(ex["t"][-1][:10])}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- the page

def _index(rows, key, value):
    for i, r in enumerate(rows):
        if r[key] == value:
            return i
    raise KeyError(f"{key}={value} not in summary")


def render(summary):
    p = Page(summary)
    s = summary
    fcc, thr, bound = s["fcc"], s["threshold"], s["bound"]
    i16 = _index(bound["rows"], "dv_cm_s", 16)
    j16 = _index(bound["injection"], "dv_cm_s", 16)
    j10 = _index(bound["injection"], "dv_cm_s", 10)
    k16 = _index(s["synthetic"]["by_dv"], "dv_cm_s", 16)
    gen1_share = bound["rows"][i16]["max_rate"] / fcc["gen1_rate_stated"]
    band = f'{p.num("constants.high_band_lo", ".0f")} to {p.num("constants.high_band_hi", ".0f")} km'
    conf = p.num("constants.confidence", "pct")

    p.add(f'<p class="kicker">Maneuver Ledger &middot; public orbit data &middot; {p.date("coverage.first_epoch")} to '
          f'{p.date("coverage.last_epoch")}</p>')
    p.add("<h1>How many of Starlink's collision-avoidance burns can public orbit data see?</h1>")
    p.add(f'<p class="lede">SpaceX told the FCC its satellites made {p.num("fcc.total", "int")} collision-avoidance '
          f'manoeuvres from {p.date("fcc.period_start")} to {p.date("fcc.period_end")}: about '
          f'{p.num("fcc.combined_rate", ".0f")} per satellite per year. We looked for them in '
          f'{p.num("coverage.span_days", ".0f")} days of public element sets. In the cleanest test, at most '
          f'{p.derived(gen1_share, "pct", "bound.rows[16 cm/s].max_rate / fcc.gen1_rate_stated")} of them can be '
          f'{p.num(f"bound.rows.{i16}.dv_cm_s", ".0f")} cm/s or larger, the size public data reliably sees.</p>')

    # ---- the one-minute check
    p.add('<div class="box"><h3>The one-minute check</h3><div class="grid">')
    p.add(f'<div class="cell"><b>{p.num("fcc.combined_rate", ".1f")}</b><span>avoidance manoeuvres per satellite per year, '
          f'filed by SpaceX ({p.num("fcc.gen1", "int")} Gen 1 plus {p.num("fcc.gen2", "int")} Gen 2, over an average of '
          f'{p.num("fcc.satcat_mean_fleet", "int")} Starlink satellites in orbit)</span></div>')
    p.add(f'<div class="cell"><b>{p.num(f"bound.rows.{i16}.max_rate", ".1f")}</b><span>at most, per satellite per year: burns of '
          f'{p.num(f"bound.rows.{i16}.dv_cm_s", ".0f")} cm/s or more on satellites holding {band} '
          f'({conf} bound from {p.num("bound.steps", "int")} steps of any kind in {p.num("bound.exposure_years", ".1f")} '
          f'satellite-years)</span></div>')
    p.add(f'<div class="cell"><b>{p.derived(gen1_share, "pct", "bound.rows[16 cm/s].max_rate / fcc.gen1_rate_stated")}</b>'
          f'<span>of even the lower filed rate (Gen 1, about {p.num("fcc.gen1_rate_stated", ".0f")} per satellite per year) '
          f'could be burns that large</span></div>')
    p.add("</div>")
    p.add(f'<p>So, if the filing-period rate still held, at least {p.derived(1 - gen1_share, "pct", "1 - share above")} of '
          f'Starlink avoidance manoeuvres change the orbit by less than {p.num(f"bound.rows.{i16}.dv_cm_s", ".0f")} cm/s '
          f'along track, or leave its size unchanged. Public element sets therefore cannot rebuild the '
          f'{p.num("fcc.total", "int")}. <strong>We did not reproduce it; this page shows why it cannot be reproduced this '
          f'way.</strong></p>')
    p.add(f'<p>Detection limit in that band: a burn of {p.num(f"bound.injection.{j16}.dv_cm_s", ".0f")} cm/s added to a real '
          f'recorded history is found {p.num(f"bound.injection.{j16}.recall", "pct")} of the time; '
          f'{p.num(f"bound.injection.{j10}.dv_cm_s", ".0f")} cm/s, {p.num(f"bound.injection.{j10}.recall", "pct")}. '
          f'False alarms on passive debris: {p.num("threshold.far_per_year", ".1f")} per object per year '
          f'({conf} upper {p.num("threshold.far_upper95", ".1f")}).</p></div>')

    # ---- what the steps are
    lo, hi = p.num("constants.control_alt_lo", ".0f"), p.num("constants.control_alt_hi", ".0f")
    p.add("<h2>What the steps in public data are</h2>")
    p.add(f'<p>Across {p.num("coverage.headline_satellites", "int")} satellites holding altitude between {lo} and {hi} km '
          f'({p.num("coverage.headline_exposure_years", ".0f")} satellite-years observed), steps above '
          f'{p.num("threshold.m", ".0f")} m of semi-major axis (about {p.num("threshold.dv_cm_s_at_470km", ".1f")} cm/s) happen '
          f'{p.num("rates.drag make-up.rate", ".1f")} times per satellite per year as drag make-up boosts (a decay, then a boost '
          f'back) and {p.num("rates.avoidance-like.rate", ".1f")} times as other small single changes ({conf} interval '
          f'{p.num("rates.avoidance-like.lo95", ".1f")} to {p.num("rates.avoidance-like.hi95", ".1f")}). Both are far rarer in '
          f'the highest band, where drag is weakest. Close approaches are not: DODGE\'s daily screen of the same satellites '
          f'finds more passes under {p.num("constants.pass_limit_km", ".0f")} km in the highest band than in the busiest one. '
          f'So most visible steps follow drag, not conjunctions.</p>')
    p.add("<table><tr><th>Altitude band</th><th>Satellites</th><th>Drag make-up per sat-year</th>"
          "<th>Other small steps per sat-year</th><th>DODGE passes under "
          f'{p.num("constants.pass_limit_km", ".0f")} km per sat-year</th></tr>')
    for i, _ in enumerate(s["bands"]):
        p.add(f'<tr><td>{p.text(f"bands.{i}.band")}</td><td class="n">{p.num(f"bands.{i}.satellites", "int")}</td>'
              f'<td class="n">{p.num(f"bands.{i}.drag make-up", ".1f")}</td>'
              f'<td class="n">{p.num(f"bands.{i}.avoidance-like", ".1f")}</td>'
              f'<td class="n">{p.num(f"bands.{i}.passes_under_1km", ".1f")}</td></tr>')
    p.add("</table>")
    p.add('<p class="cap">Steps above the calibrated threshold, from public GP sets. "Other small steps" is the avoidance-like '
          'class: an upper bound on avoidance burns above the limit, since phasing moves look the same. Passes are '
          'screening grade (DODGE), not collision probabilities.</p>')

    # ---- chart: detection limit
    inj, syn, hb = s["injection"], s["synthetic"]["by_dv"], bound["injection"]
    p.add("<h2>Detection limit</h2>")
    p.add("<div class=\"chart\">" + line_chart(
        "Recall against burn size",
        "Share of injected burns found, by delta-v, on real histories and on synthetic histories with known burns.",
        [("real histories, all bands", ACCENT, [(r["dv_cm_s"], r["recall"]) for r in inj], False),
         ("real histories, highest band", BLUE, [(r["dv_cm_s"], r["recall"]) for r in hb], False),
         ("synthetic, known burns", GREY, [(r["dv_cm_s"], r["recall"]) for r in syn], True)],
        "delta-v of the injected burn (cm/s)", "share found", (0, 60), (0, 1.0),
        vlines=[(thr["dv_cm_s_at_470km"], "threshold", INK)]) + "</div>")
    trials = [r["trials"] for r in inj]
    p.add(f'<p class="cap">Each point: {p.derived(min(trials), "int", "min injection trials")} to '
          f'{p.derived(max(trials), "int", "max injection trials")} burns injected into randomly chosen real '
          f'on-station histories, or synthetic histories with fit noise of {p.num("synthetic.sigma_m", ".1f")} m and a bad-set '
          f'share of {p.num("synthetic.outlier_share", "pct1")}, both measured on the real data. Synthetic precision at '
          f'{p.num(f"synthetic.by_dv.{k16}.dv_cm_s", ".0f")} cm/s: {p.num(f"synthetic.by_dv.{k16}.precision", "pct1")}.</p>')

    # ---- chart: rate against threshold
    curve = s["curve"]
    p.add("<h2>Rate against threshold</h2>")
    p.add("<div class=\"chart\">" + line_chart(
        "Steps per satellite per year against the size threshold",
        "Drag make-up and avoidance-like steps per satellite-year, false alarms on passive debris, and the filed rate.",
        [("drag make-up", BLUE, [(r["threshold_m"], r["drag make-up"]) for r in curve], False),
         ("avoidance-like", ACCENT, [(r["threshold_m"], r["avoidance-like"]) for r in curve], False),
         ("false alarms on passive debris", GREY, [(r["threshold_m"], max(r["control_far"], 0.05)) for r in curve], True)],
        "step threshold (m of semi-major axis)", "per satellite per year", (50, 500), (0.05, 100), log_y=True,
        vlines=[(thr["m"], "threshold", INK)], hlines=[(fcc["combined_rate"], "filed avoidance rate", ACCENT)]) + "</div>")
    p.add(f'<p class="cap">The threshold is the smallest step on the grid at which the {conf} upper bound of false alarms on '
          f'passive debris near Starlink altitudes is at most {p.num("constants.far_share", "pct")} of the filed rate. The rule '
          f'is fixed in code; the threshold follows from the debris data alone. Zero false alarms are drawn on the bottom '
          f'edge of the log scale.</p>')

    # ---- examples
    p.add("<h2>Three public histories</h2>")
    for i, _ in enumerate(s["examples"]):
        p.add(f'<h3>{p.text(f"examples.{i}.name")}: {p.text(f"examples.{i}.why")}</h3>')
        p.add("<div class=\"chart\">" + history_chart(s["examples"][i]) + "</div>")
        p.add(f'<p class="cap">Mean semi-major axis from each public GP set, relative to the first; median altitude '
              f'{p.num(f"examples.{i}.alt_km", ".0f")} km. Dashed lines: detected steps.</p>')

    # ---- outside judges
    held = s["held_out"]
    age = {r["label"]: j for j, r in enumerate(held["by_launch_age"])}
    jw, jo = age["launched in the window"], age["over a year before"]
    p.add("<h2>Outside judges</h2><table><tr><th>Check</th><th>Result</th></tr>")
    p.add(f'<tr><td>Synthetic orbits, burns of {p.num(f"synthetic.by_dv.{k16}.dv_cm_s", ".0f")} cm/s, fit noise and bad sets '
          f'as measured</td><td class="pass">precision {p.num(f"synthetic.by_dv.{k16}.precision", "pct1")}, recall '
          f'{p.num(f"synthetic.by_dv.{k16}.recall", "pct1")}; {p.num("synthetic.noise_only_false_alarms", "int")} false alarms in '
          f'{p.num("synthetic.noise_only_series", "int")} burn-free histories</td></tr>')
    p.add(f'<tr><td>Passive debris and rocket bodies, {lo} to {hi} km (they cannot manoeuvre)</td><td class="pass">'
          f'{p.num("threshold.control_events", "int")} false steps in {p.num("coverage.control_exposure_days", "int")} '
          f'object-days</td></tr>')
    p.add(f'<tr><td>Held out: satellites launched during the window (catalogue dates, never shown to the detector)</td>'
          f'<td class="pass">{p.num(f"held_out.by_launch_age.{jw}.raising", "int")} labelled raising, '
          f'{p.num(f"held_out.by_launch_age.{jw}.on-station", "int")} on-station</td></tr>')
    p.add(f'<tr><td>Held out: satellites launched over a year earlier</td><td class="pass">'
          f'{p.num(f"held_out.by_launch_age.{jo}.raising", "int")} raising, '
          f'{p.num(f"held_out.by_launch_age.{jo}.on-station", "int")} on-station, '
          f'{p.num(f"held_out.by_launch_age.{jo}.descending", "int")} descending</td></tr>')
    p.add(f'<tr><td>Held out: satellites the FCC report lists as removed from operation, still in orbit</td><td>'
          f'{p.num("held_out.fcc_removed.regimes.descending", "int")} descending, '
          f'{p.num("held_out.fcc_removed.regimes.on-station", "int")} holding altitude, of '
          f'{p.num("held_out.fcc_removed.still_in_orbit", "int")}</td></tr>')
    p.add(f'<tr><td>Public GP against SupGP (fits of SpaceX\'s own ephemerides) on the same steps; pre-registered line: '
          f'{p.num("agreement.pre_registered_line", "pct")} beyond chance</td><td class="fail">'
          f'{p.num("agreement.all.beyond_chance", "pct")} beyond chance ({p.num("agreement.all.agree_share", "pct")} agree, '
          f'{p.num("agreement.all.chance_share", "pct")} by chance in time slides): not met</td></tr>')
    if s["dodge_baseline"].get("available"):
        p.add(f'<tr><td>DODGE\'s first detector (one threshold on consecutive sets)</td><td>'
              f'{p.num("dodge_baseline.jumps_per_object_year", ".0f")} jumps per satellite-year: it counts one bad set as two '
              f'jumps and does not separate drag make-up, so it is replaced here</td></tr>')
    p.add("</table>")

    # ---- limits
    p.add("<h2>Limits, stated first</h2><ul>")
    p.add(f'<li>Different months: the filing covers {p.date("fcc.period_start")} to {p.date("fcc.period_end")}; the data covers '
          f'{p.date("coverage.first_epoch")} to {p.date("coverage.last_epoch")}. Rates are compared, not counts. The '
          f'{p.derived(1 - gen1_share, "pct", "1 - share above")} figure assumes satellites in the highest band dodge about as '
          f'often as the Gen 1 fleet did then; DODGE\'s screen shows them with more close approaches, not fewer. If they '
          f'dodged only a tenth as often, up to '
          f'{p.derived(min(1.0, 10 * gen1_share), "pct", "10 x share above, capped at 100%")} of their burns could be that '
          f'large.</li>')
    p.add("<li>Only the size of the orbit is measured. Two burns that cancel inside one gap between element sets, or burns "
          "that change only the plane or shape, are invisible.</li>")
    p.add("<li>The classes are heuristics. Drag make-up and avoidance cannot be told apart for a single step; the bound uses "
          "every step in the band, whatever its class.</li>")
    p.add("<li>Public GP sets are derived from US Space Surveillance Network radar and optical observations (CelesTrak's "
          "description); whether they also use operator ephemerides is not known to us.</li>")
    p.add(f'<li>The highest band holds {p.num("bound.satellites", "int")} satellites. The bound tightens as DODGE keeps recording '
          f'every {p.num("constants.recorder_every_hours", ".0f")} hours.</li>')
    p.add("</ul>")

    p.add("<h2>What an insider could check in a minute</h2><ol>")
    p.add(f'<li>Is a typical Starlink avoidance burn smaller than {p.num(f"bound.rows.{i16}.dv_cm_s", ".0f")} cm/s along '
          f'track?</li>')
    p.add("<li>Are the regular boosts every few days in the lower shells drag make-up, as classed here?</li>")
    p.add("<li>Do SpaceX's published ephemerides include planned burns? Our GP and SupGP steps agree less often than we "
          "pre-registered.</li>")
    p.add("</ol>")

    p.add("<h2>Data and sources</h2><ul>")
    p.add(f'<li>Filing: <a href="{esc(fcc["url"])}">SpaceX Gen 1 and Gen 2 Semi-Annual Reports</a>, cover letter '
          f'{p.date("fcc.letter_date")}. Quote: "{p.text("fcc.quote_counts")}"</li>')
    p.add('<li>Orbits: public GP sets and the Starlink Supplemental GP set from '
          '<a href="https://celestrak.org/NORAD/elements/supplemental/">CelesTrak</a>, recorded by '
          '<a href="https://github.com/GautamTalksDev/dodge">DODGE</a> because CelesTrak keeps only the latest set.</li>')
    p.add(f'<li>Fleet size: CelesTrak SATCAT, Starlink payloads in orbit averaged over the filing period. The filed rates '
          f'imply {p.num("fcc.implied_fleet_gen1", "int")} plus {p.num("fcc.implied_fleet_gen2", "int")} satellites.</li>')
    p.add("<li>Every detected step: <code>out/events.csv</code>. Every number on this page: <code>out/summary.json</code>. "
          "Method: <code>docs/METHODS.md</code>.</li></ul>")
    p.add("<footer>Independent work from public data. Not affiliated with SpaceX or Starlink. Screening grade, not for "
          "operations.</footer>")
    return p


def build(summary_path, out_path):
    """Write the page and, next to it, the list of every number it printed and its source."""
    with open(summary_path) as f:
        summary = json.load(f)
    p = render(summary)
    css = CSS.strip()
    digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode()
    csp = f"default-src 'none'; style-src 'sha256-{digest}'; img-src 'none'; base-uri 'none'; form-action 'none'"
    doc = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
           f"<meta http-equiv=\"Content-Security-Policy\" content=\"{csp}\">"
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
           "<meta name=\"referrer\" content=\"no-referrer\">"
           "<title>Maneuver Ledger: Starlink avoidance burns in public orbit data</title>"
           f"<style>{css}</style></head><body><main>" + "".join(p.parts) + "</main></body></html>\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    with open(out_path[:-len(".html")] + ".numbers.json", "w") as f:
        json.dump(p.used, f, indent=0)
        f.write("\n")
    return doc
