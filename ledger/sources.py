"""Where the orbit data comes from, and the rules for getting it.

1. DODGE's recorder (github.com/GautamTalksDev/dodge) downloads CelesTrak's public
   element sets every 4 hours and keeps one gzipped NDJSON file per UTC day,
   published as the release asset gp-YYYY-MM-DD.ndjson.gz. CelesTrak keeps only the
   latest set per object, so these files ARE the history; this project reads them
   and never runs a second recorder. We also read the day's catalogue
   (satcat-YYYY-MM-DD.csv.gz) and DODGE's close-approach screen (events-YYYY-MM-DD.json.gz).
2. Each finished day is sealed by DODGE with manifest-YYYY-MM-DD.json (SHA-256 of
   every file). We check the gp, satcat and events files against it, so a reader can
   tell that our inputs are byte-for-byte what DODGE published.
3. For the newest hours, one cached download of CelesTrak's Starlink SupGP file is
   allowed per run, under CelesTrak's usage rules (at most one download per update,
   never more often than every 2 hours, a 403 means "not changed" and is not retried).

Two kinds of Starlink element sets are used, never mixed in one time series:
    "gp"    the public GP sets (CelesTrak sources "active" and "last-30-days"),
            which CelesTrak describes as derived from US Space Surveillance Network
            radar and optical observations;
    "supgp" CelesTrak's Supplemental GP fits, "derived from latest Starlink
            ephemeris data from SpaceX's public data repository".
Debris and rocket bodies near Starlink's altitudes are read as a passive control
group: they cannot manoeuvre, so every "event" found in them is a false alarm.
"""
import gzip
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

DODGE_RELEASE = "https://github.com/GautamTalksDev/dodge/releases/download/day-{day}/{name}"
SUPGP_STARLINK = "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=json"
UA = "maneuver-ledger (research; reads DODGE releases; one CelesTrak download per update at most)"
MAX_BODY = 256 * 1024 * 1024
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

GP_SOURCES = ("active", "last-30-days")
SUPGP_SOURCES = ("starlink-supgp",)
CONTROL_SOURCES = ("debris", "rocket-bodies")


# ---------------------------------------------------------------- downloading

def _get(url, timeout=120):
    """(status, body). Never raises for HTTP errors; caps the body size."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                return 0, b""
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return 0, b""


def sync_dodge(cache_dir, first_day, last_day, pause_s=1.0, getter=_get):
    """Download DODGE day files we do not have yet. Returns {file name: status}.

    Days already sealed and present are never downloaded again. The newest day is
    re-downloaded on every sync because DODGE keeps adding to it until it is sealed.
    """
    os.makedirs(cache_dir, exist_ok=True)
    out = {}
    d = datetime.strptime(first_day, "%Y-%m-%d").date()
    end = datetime.strptime(last_day, "%Y-%m-%d").date()
    while d <= end:
        day = d.isoformat()
        sealed = os.path.exists(os.path.join(cache_dir, f"manifest-{day}.json"))
        for name in (f"manifest-{day}.json", f"gp-{day}.ndjson.gz", f"satcat-{day}.csv.gz", f"events-{day}.json.gz"):
            path = os.path.join(cache_dir, name)
            if sealed and os.path.exists(path):
                continue
            status, body = getter(DODGE_RELEASE.format(day=day, name=name))
            out[name] = status
            if status == 200 and body:
                tmp = path + ".part"
                with open(tmp, "wb") as f:
                    f.write(body)
                os.replace(tmp, path)
            time.sleep(pause_s)
        d += timedelta(days=1)
    return out


def fetch_supgp_once(cache_dir, now=None, min_interval_h=2.0, getter=_get):
    """One cached download of the current Starlink SupGP file, or None.

    Refuses to download if a copy younger than min_interval_h exists (CelesTrak asks
    for no more than one download per update and never faster than every 2 hours).
    A 403 means "not updated since your last download": we keep what we have.
    """
    now = now or datetime.now(timezone.utc)
    os.makedirs(cache_dir, exist_ok=True)
    have = sorted(f for f in os.listdir(cache_dir) if re.match(r"^starlink-supgp-\d{8}T\d{4}Z\.json$", f))
    if have:
        last = datetime.strptime(have[-1][15:29], "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)
        if now - last < timedelta(hours=min_interval_h):
            return os.path.join(cache_dir, have[-1])
    status, body = getter(SUPGP_STARLINK)
    if status != 200 or not body.lstrip().startswith(b"["):
        return os.path.join(cache_dir, have[-1]) if have else None
    path = os.path.join(cache_dir, f"starlink-supgp-{now.strftime('%Y%m%dT%H%MZ')}.json")
    with open(path, "wb") as f:
        f.write(body)
    return path


# ---------------------------------------------------------------- verifying

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_against_manifests(cache_dir):
    """{day: "sealed-ok" | "sealed-mismatch" | "unsealed"} for every gp day file.

    "unsealed" is normal for the current day (DODGE seals a day the morning after).
    """
    result = {}
    for name in sorted(os.listdir(cache_dir)):
        m = re.match(r"^gp-(\d{4}-\d{2}-\d{2})\.ndjson\.gz$", name)
        if not m:
            continue
        day = m.group(1)
        man = os.path.join(cache_dir, f"manifest-{day}.json")
        if not os.path.exists(man):
            result[day] = "unsealed"
            continue
        with open(man) as f:
            files = json.load(f).get("files", {})
        ok = True
        for fname in (name, f"satcat-{day}.csv.gz", f"events-{day}.json.gz"):
            want = files.get(fname, {}).get("sha256")
            path = os.path.join(cache_dir, fname)
            if want is None or not os.path.exists(path):
                continue
            if sha256_file(path) != want:
                ok = False
        result[day] = "sealed-ok" if ok else "sealed-mismatch"
    return result


# ---------------------------------------------------------------- reading

def _kind(src):
    if src in GP_SOURCES:
        return "gp"
    if src in SUPGP_SOURCES:
        return "supgp"
    if src in CONTROL_SOURCES:
        return "control"
    return None


def read_rows(cache_dir, extra_supgp=(), want=("gp", "supgp", "control")):
    """All usable rows, de-duplicated, as dicts with a "kind" key.

    Starlink rows are those whose OBJECT_NAME starts with STARLINK. Control rows are
    debris and rocket bodies (their filters are applied later, by altitude). The
    same element set recorded on two days is kept once, keyed on (kind, id, epoch).
    """
    seen, rows = set(), []

    def add(r, kind):
        name = str(r.get("OBJECT_NAME") or "")
        if kind in ("gp", "supgp") and not name.startswith("STARLINK"):
            return
        if kind == "control" and name.startswith("STARLINK"):
            return
        if not isinstance(r.get("EPOCH"), str) or r.get("MEAN_MOTION") in (None, 0, "0"):
            return
        try:
            nid = int(r["NORAD_CAT_ID"])
        except (KeyError, TypeError, ValueError):
            return
        key = (kind, nid, r["EPOCH"])
        if key in seen:
            return
        seen.add(key)
        r = dict(r)
        r["kind"], r["NORAD_CAT_ID"] = kind, nid
        rows.append(r)

    for name in sorted(os.listdir(cache_dir)):
        if not re.match(r"^gp-\d{4}-\d{2}-\d{2}\.ndjson\.gz$", name):
            continue
        with gzip.open(os.path.join(cache_dir, name), "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                kind = _kind(r.get("src"))
                if kind in want:
                    add(r, kind)
    if "supgp" in want:
        for path in extra_supgp:
            with open(path, encoding="utf-8") as f:
                for r in json.load(f):
                    if isinstance(r, dict):
                        add(r, "supgp")
    return rows
