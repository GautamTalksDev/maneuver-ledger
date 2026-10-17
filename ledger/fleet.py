"""The reference numbers: what SpaceX told the FCC, and how many satellites there were.

Every constant here is copied from a primary source, with the exact words, so the
page can show the quote next to the number. Nothing is rounded here; rounding
happens only when a number is displayed.
"""
import csv
import gzip
from datetime import date, timedelta

FCC = {
    "title": "SpaceX Gen 1 and Gen 2 Semi-Annual Reports (cover letter dated July 1, 2026)",
    "url": "https://api-prod.fcc.gov/icfs-attachment/exp/api/v1/bff0244acfb947505791bf252f851ce6",
    "pdf_sha256": "0ad265aedaca93827bd6a273f94e1aaed24e3c71d725fea7e6013787143b658c",
    "period_start": "2025-12-01",
    "period_end": "2026-05-31",            # inclusive, "December 1, 2025 through May 31, 2026"
    "gen1_maneuvers": 65137,
    "gen2_maneuvers": 142015,
    "gen1_rate_stated": 36,                # "approximately 36 maneuvers per satellite, per year"
    "gen2_rate_stated": 46,                # "approximately 46 maneuvers per satellite, per year"
    "threshold_pc": 3e-7,
    "industry_pc": 1e-4,
    "quote_counts": ("Using this very conservative threshold, along with additional miss-distance-based "
                     "criteria, SpaceX Gen 1 satellites performed 65,137 propulsive maneuvers over the "
                     "reporting period, averaging approximately 36 maneuvers per satellite, per year and "
                     "SpaceX Gen 2 satellites performed 142,015 propulsive maneuvers over the reporting "
                     "period, averaging approximately 46 maneuvers per satellite, per year."),
    "quote_threshold": ("SpaceX satellites will maneuver when the probability of collision is greater than "
                        "3e-7 (3 in 10,000,000 chance of collision), as opposed to the industry standard of "
                        "1e-4 (1 in 10,000 chance of collision)."),
}

SUPGP = {
    "url": "https://celestrak.org/NORAD/elements/supplemental/",
    "quote": "Derived from latest Starlink ephemeris data from SpaceX's public data repository.",
}


def period_days():
    a = date.fromisoformat(FCC["period_start"])
    b = date.fromisoformat(FCC["period_end"])
    return (b - a).days + 1


def period_years():
    return period_days() / 365.25


def fcc_total():
    return FCC["gen1_maneuvers"] + FCC["gen2_maneuvers"]


def implied_fleet(maneuvers, rate_per_sat_year):
    """Satellites implied by a manoeuvre count and a stated per-satellite yearly rate."""
    return maneuvers / (rate_per_sat_year * period_years())


def implied_fleet_range(maneuvers, rate):
    """Range allowed by the rounding of "approximately <rate>" (rate +/- 0.5)."""
    return implied_fleet(maneuvers, rate + 0.5), implied_fleet(maneuvers, rate - 0.5)


def starlink_payloads(satcat_gz_path):
    """Starlink payload rows from a CelesTrak SATCAT CSV (as recorded by DODGE)."""
    out = []
    with gzip.open(satcat_gz_path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("OBJECT_NAME", "").startswith("STARLINK") and r.get("OBJECT_TYPE") == "PAY":
                out.append(r)
    return out


def in_orbit_on(rows, day):
    """Payloads launched on or before day and not decayed by day."""
    n = 0
    for r in rows:
        ld = r.get("LAUNCH_DATE") or ""
        dd = r.get("DECAY_DATE") or ""
        if ld and date.fromisoformat(ld) <= day and (not dd or date.fromisoformat(dd) > day):
            n += 1
    return n


def mean_in_orbit(rows, start, end):
    """Average daily count of Starlink payloads in orbit over [start, end] inclusive."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    days = [a + timedelta(days=i) for i in range((b - a).days + 1)]
    counts = [in_orbit_on(rows, d) for d in days]
    return sum(counts) / len(counts), counts[0], counts[-1]


def fcc_combined_rate(fleet):
    """FCC avoidance manoeuvres per satellite per year for a given average fleet."""
    return fcc_total() / (fleet * period_years())
