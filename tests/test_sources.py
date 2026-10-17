"""Data rules: DODGE's seals are checked, CelesTrak is rate limited, rows are clean."""
import gzip
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ledger import sources as S  # noqa: E402


def write_day(d, day, rows):
    path = os.path.join(d, f"gp-{day}.ndjson.gz")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


ROW = {"NORAD_CAT_ID": 44714, "OBJECT_NAME": "STARLINK-1008", "EPOCH": "2026-10-06T05:14:07.015200",
       "MEAN_MOTION": 15.66, "ECCENTRICITY": 0.0003, "INCLINATION": 53.1, "RA_OF_ASC_NODE": 250.0,
       "ARG_OF_PERICENTER": 96.0, "MEAN_ANOMALY": 264.0, "BSTAR": 0.0004, "MEAN_MOTION_DOT": 0.0004,
       "MEAN_MOTION_DDOT": 0, "src": "active"}


class Manifests(unittest.TestCase):
    def test_match_mismatch_and_unsealed(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = write_day(d, "2026-10-06", [ROW])
            write_day(d, "2026-10-07", [ROW])
            sha = hashlib.sha256(open(p1, "rb").read()).hexdigest()
            with open(os.path.join(d, "manifest-2026-10-06.json"), "w") as f:
                json.dump({"files": {"gp-2026-10-06.ndjson.gz": {"sha256": sha}}}, f)
            self.assertEqual(S.verify_against_manifests(d), {"2026-10-06": "sealed-ok", "2026-10-07": "unsealed"})
            with gzip.open(p1, "at") as f:
                f.write("\n")                 # one changed byte after sealing
            self.assertEqual(S.verify_against_manifests(d)["2026-10-06"], "sealed-mismatch")


class CelesTrakRules(unittest.TestCase):
    def test_no_second_download_within_two_hours(self):
        calls = []

        def getter(url):
            calls.append(url)
            return 200, b'[{"NORAD_CAT_ID": 1}]'
        with tempfile.TemporaryDirectory() as d:
            t = datetime(2026, 10, 17, 19, 0, tzinfo=timezone.utc)
            first = S.fetch_supgp_once(d, now=t, getter=getter)
            again = S.fetch_supgp_once(d, now=t + timedelta(minutes=119), getter=getter)
            self.assertEqual(first, again)
            self.assertEqual(len(calls), 1)
            S.fetch_supgp_once(d, now=t + timedelta(minutes=121), getter=getter)
            self.assertEqual(len(calls), 2)

    def test_403_keeps_the_cached_copy_and_is_not_retried(self):
        calls = []

        def ok(url):
            return 200, b"[]"

        def forbidden(url):
            calls.append(url)
            return 403, b""
        with tempfile.TemporaryDirectory() as d:
            t = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
            kept = S.fetch_supgp_once(d, now=t, getter=ok)
            self.assertEqual(S.fetch_supgp_once(d, now=t + timedelta(hours=3), getter=forbidden), kept)
            self.assertEqual(len(calls), 1)

    def test_error_text_with_status_200_is_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(S.fetch_supgp_once(d, getter=lambda u: (200, b"Invalid query")))
            self.assertEqual(os.listdir(d), [])

    def test_sealed_days_are_not_downloaded_again(self):
        calls = []

        def getter(url):
            calls.append(url)
            return 404, b""
        with tempfile.TemporaryDirectory() as d:
            for name in ("manifest-2026-10-06.json", "gp-2026-10-06.ndjson.gz", "satcat-2026-10-06.csv.gz",
                         "events-2026-10-06.json.gz"):
                open(os.path.join(d, name), "w").close()
            S.sync_dodge(d, "2026-10-06", "2026-10-06", pause_s=0, getter=getter)
            self.assertEqual(calls, [])


class Rows(unittest.TestCase):
    def test_dedupe_and_filters(self):
        with tempfile.TemporaryDirectory() as d:
            sup = dict(ROW, src="starlink-supgp")
            deb = dict(ROW, OBJECT_NAME="COSMOS 1408 DEB", NORAD_CAT_ID=50000, src="debris")
            other = dict(ROW, OBJECT_NAME="ONEWEB-0012", NORAD_CAT_ID=45000)
            write_day(d, "2026-10-06", [ROW, sup, deb, other])
            write_day(d, "2026-10-07", [ROW, dict(ROW, MEAN_MOTION=0)])   # same set again, and a broken one
            rows = S.read_rows(d)
            kinds = sorted(r["kind"] for r in rows)
            self.assertEqual(kinds, ["control", "gp", "supgp"])


if __name__ == "__main__":
    unittest.main()
