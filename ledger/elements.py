"""SGP4 mean elements: the quantities the detector compares.

Why mean elements and not positions: an osculating semi-major axis swings by about
10 km every orbit at Starlink's altitudes because of Earth's oblateness (J2). SGP4
keeps a smooth "mean" orbit internally and adds those swings on top. After every
call, python-sgp4 exposes that mean orbit (am, nm, im, Om, om, mm), with drag
already applied by SGP4's own drag model. Comparing two element sets of the same
satellite at the same instant through these mean elements removes the J2 swings
and leaves what a thruster changes: the size of the orbit (semi-major axis) and
where along the orbit the satellite is (mean argument of latitude).

Constants are WGS72, the gravity model SGP4 element sets are fitted with.
"""
import math
from datetime import datetime, timezone

from sgp4 import omm
from sgp4.api import Satrec

RE_KM = 6378.135          # WGS72 equatorial radius; SGP4's am is in these units
MU_KM3_S2 = 398600.8      # WGS72 gravitational parameter
FIELDS = ("EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
          "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT")


def parse_epoch(s):
    """CelesTrak epochs are UTC ISO strings, sometimes without fractional seconds."""
    if "." not in s:
        s = s + ".000000"
    return datetime.strptime(s[:26], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)


def epoch_str(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


def to_jd(dt):
    """Julian date split into a whole and a fractional part (keeps sub-ms precision)."""
    jd = dt.timestamp() / 86400.0 + 2440587.5
    whole = math.floor(jd)
    return whole, jd - whole


def satrec(row):
    """An SGP4 satellite record from one CelesTrak OMM/JSON row.

    The catalogue number is set to 0 for propagation: it does not affect the orbit,
    and 6-digit numbers (CelesTrak ran out of 5-digit ones on 2026-07-11) can exceed
    what the Alpha-5 field inside SGP4 accepts.
    """
    f = {k: str(row[k]) for k in FIELDS if row.get(k) is not None}
    f.setdefault("MEAN_MOTION_DDOT", "0")
    f.setdefault("MEAN_MOTION_DOT", "0")
    f.setdefault("BSTAR", "0")
    f["EPOCH"] = epoch_str(parse_epoch(f["EPOCH"]))
    f.update(NORAD_CAT_ID="0", OBJECT_ID="2000-000A", CLASSIFICATION_TYPE="U",
             EPHEMERIS_TYPE="0", ELEMENT_SET_NO="0", REV_AT_EPOCH="0")
    s = Satrec()
    omm.initialize(s, f)
    return s


def mean_at(sat, jd_whole, jd_frac):
    """SGP4 mean elements at a time, or None if SGP4 reports an error (decayed etc.).

    Returns (a_km, n_rad_s, inc_rad, raan_rad, u_rad, ecc), where u is the mean
    argument of latitude (argument of perigee plus mean anomaly).
    """
    err, _, _ = sat.sgp4(jd_whole, jd_frac)
    if err != 0 or not (sat.am > 0):
        return None
    n_rad_s = sat.nm / 60.0            # nm is rad/min
    return (sat.am * RE_KM, n_rad_s, sat.im, sat.Om, sat.om + sat.mm, sat.em)


def wrap_pi(x):
    return (x + math.pi) % (2.0 * math.pi) - math.pi


def circular_speed_km_s(a_km):
    return math.sqrt(MU_KM3_S2 / a_km)


def dv_from_da(da_km, a_km):
    """Along-track delta-v (m/s) that changes a near-circular orbit's size by da.

    Gauss's equation for a tangential impulse on a circular orbit: da = 2 a dv / v,
    so dv = v da / (2 a). Positive raises the orbit.
    """
    return circular_speed_km_s(a_km) * da_km / (2.0 * a_km) * 1000.0


def da_from_dv(dv_m_s, a_km):
    return 2.0 * a_km * (dv_m_s / 1000.0) / circular_speed_km_s(a_km)


def pair_residual(sat_a, sat_b, jd_whole, jd_frac):
    """What changed between element set A (older) and B (newer), measured at B's epoch.

    A is propagated forward to B's epoch, so drag between the two is applied by SGP4
    from A's own drag term. Returns (da_km, ds_km, a_km, inc_rad) or None:
        da_km  B's mean semi-major axis minus A's prediction of it
        ds_km  how far ahead (+) or behind (-) along the orbit B is, against A's prediction
    """
    ma = mean_at(sat_a, jd_whole, jd_frac)
    mb = mean_at(sat_b, jd_whole, jd_frac)
    if ma is None or mb is None:
        return None
    a_a, _, inc_a, raan_a, u_a, _ = ma
    a_b, _, _, raan_b, u_b, _ = mb
    du = wrap_pi((u_b - u_a) + math.cos(inc_a) * wrap_pi(raan_b - raan_a))
    return a_b - a_a, du * a_a, a_b, inc_a
