#!/usr/bin/env python3
"""Extract the named satellite lists from SpaceX's 1 July 2026 FCC report.

Usage:
    pdftotext -layout report.pdf report.txt
    python tools/parse_fcc.py report.txt > data/fcc_2026-07-01_lists.json

The report (see ledger/fleet.py for its URL and SHA-256) lists, per generation,
the satellites "removed from operation" for disposal during 1 Dec 2025 to 31 May
2026 (section 2) and those that re-entered (section 3). We use section 2 as a
held-out check: a satellite SpaceX says it removed for disposal, and that the
CelesTrak catalogue still shows in orbit in October 2026, should not look like it
is holding an operational altitude.

Sections are found by their headings, not by line numbers.
"""
import json
import re
import sys

HEADINGS = [
    ("removed", r"^\s*2\.\s+.Satellites that, for purposes of disposal"),
    ("reentered", r"^\s*3\.\s+.Satellites that re-entered"),
    ("end", r"^\s*4\.\s+Gen 1:"),
]


def parse(text):
    lines = text.splitlines()
    marks = {}
    for i, line in enumerate(lines):
        for key, rx in HEADINGS:
            if key not in marks and re.search(rx, line):
                marks[key] = i
    if len(marks) != len(HEADINGS):
        raise SystemExit(f"headings not found: {sorted(set(k for k, _ in HEADINGS) - set(marks))}")
    out = {}
    for sec, start, end in (("removed", marks["removed"], marks["reentered"]),
                            ("reentered", marks["reentered"], marks["end"])):
        gen = None
        for line in lines[start:end]:
            if re.match(r"^\s*Gen 1\s*$", line):
                gen = "gen1"
            elif re.match(r"^\s*Gen 2\s*$", line):
                gen = "gen2"
            for m in re.finditer(r"(STARLINK-\d+)\s+(\d{1,2})/(\d{1,2})/(\d{4})", line):
                if gen is None:
                    continue
                mo, dy, yr = int(m.group(2)), int(m.group(3)), int(m.group(4))
                out.setdefault(f"{sec}_{gen}", []).append([m.group(1), f"{yr:04d}-{mo:02d}-{dy:02d}"])
    return out


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        lists = parse(f.read())
    meta = {"source": "SpaceX Gen 1 and Gen 2 Semi-Annual Reports, cover letter 1 July 2026",
            "url": "https://api-prod.fcc.gov/icfs-attachment/exp/api/v1/bff0244acfb947505791bf252f851ce6",
            "pdf_sha256": "0ad265aedaca93827bd6a273f94e1aaed24e3c71d725fea7e6013787143b658c",
            "counts": {k: len(v) for k, v in lists.items()}}
    json.dump({"meta": meta, "lists": lists}, sys.stdout, indent=1)
    sys.stdout.write("\n")
