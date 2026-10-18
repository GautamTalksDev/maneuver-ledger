# Data: sources, terms and reproduction

## Sources used

| Source | What it is | How this project gets it | Terms |
|---|---|---|---|
| CelesTrak public GP sets (groups "active" and "last-30-days") | Starlink element sets that CelesTrak describes as derived from US Space Surveillance Network radar and optical observations | DODGE's recorder downloads them every 4 hours; this project reads DODGE's daily `gp-YYYY-MM-DD.ndjson.gz` release assets | CelesTrak's usage policy (below); republished unchanged with credit by DODGE |
| CelesTrak Supplemental GP (SupGP), Starlink | SGP4 fits "derived from latest Starlink ephemeris data from SpaceX's public data repository" (CelesTrak) | the same DODGE files, plus at most one direct download per run from `https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=json` | CelesTrak's usage policy |
| CelesTrak GP, debris and rocket bodies | the passive control group: objects that cannot manoeuvre | the same DODGE files | CelesTrak's usage policy |
| CelesTrak SATCAT | launch and decay dates, for the fleet size and the held-out launch check | DODGE's daily `satcat-YYYY-MM-DD.csv.gz` | CelesTrak's usage policy |
| DODGE close-approach screens | every predicted pass under 5 km per Starlink satellite per day (screening grade) | DODGE's `events-YYYY-MM-DD.json.gz` | CC BY 4.0, credit "DODGE (dodge.gautamkhosla.com)" |
| FCC filing | SpaceX Gen 1 and Gen 2 Semi-Annual Reports, cover letter dated 1 July 2026, period 1 December 2025 to 31 May 2026 | the PDF at [api-prod.fcc.gov](https://api-prod.fcc.gov/icfs-attachment/exp/api/v1/bff0244acfb947505791bf252f851ce6), SHA-256 `0ad265aedaca93827bd6a273f94e1aaed24e3c71d725fea7e6013787143b658c`, quoted in `ledger/fleet.py`; its lists of satellites removed for disposal parsed once by `tools/parse_fcc.py` into `data/fcc_2026-07-01_lists.json` | a public regulatory filing by SpaceX; quoted, not republished |

Every DODGE day file is checked against DODGE's sealed manifest (`manifest-YYYY-MM-DD.json`, SHA-256 of every file)
before it is used. DODGE explains its own sealing and signing in its
[VERIFYING.md](https://github.com/GautamTalksDev/dodge/blob/main/docs/VERIFYING.md).

## CelesTrak's usage rules, and how they are kept

CelesTrak's [usage policy](https://celestrak.org/usage-policy.php) (Dr T.S. Kelso, updated 22 May 2026) asks users
to "only download the data you need, when you are going to use it, and only download data once per update. For GP
data, updates are once every 2 hours. For SupGP data, which updates on different schedules for different
constellations, please use 2 hours, as well." It also asks machine-to-machine software to "immediately stop querying
when it receives any non-HTTP 200 responses".

How `ledger/sources.py` keeps them:

- History comes from DODGE's recordings, so this project never polls CelesTrak for GP data at all.
- At most one Starlink SupGP download per run, and none if the cached copy is less than 2 hours old.
- Any response other than 200 with a JSON array is not retried; the cached copy is kept.
- A descriptive User-Agent names the project.

## Sources not used, and why

- **Space-Track.** Its user agreement restricts redistributing its data, and this project publishes everything it
  uses, so Space-Track is not used.
- **SpaceX's raw ephemeris files** (`https://api.starlink.com/public-files/ephemerides/`, the files CelesTrak's SupGP
  is fitted to). They are not used for the committed results. They would be a much stronger cross-check (see
  [METHODS.md](METHODS.md), section 10), and are being evaluated as a second source separately.

## Licences

| What | Licence |
|---|---|
| Code in this repository | Apache-2.0 ([LICENSE](../LICENSE)) |
| Derived data this repository produces (`out/summary.json`, `out/events.csv`, `out/noise.csv`, the numbers on the page) | CC BY 4.0 ([LICENSE-DATA](../LICENSE-DATA)); credit "Maneuver Ledger (github.com/GautamTalksDev/maneuver-ledger), Gautam Khosla" |
| CelesTrak data (GP, SupGP, SATCAT), including the copies attached to this repository's `inputs-2026-10-17` release | CelesTrak's terms; republished unchanged with credit, as DODGE does. Credit: CelesTrak, Dr T.S. Kelso |
| DODGE's derived files (close-approach screens) | CC BY 4.0, credit "DODGE (dodge.gautamkhosla.com)" |
| The FCC filing | SpaceX's public filing; quoted with its URL and hash |

The derived-data licence covers only what this repository computes. It grants no rights in the input data.

## Reproducing

The committed results were computed from these inputs (SHA-256 of each in
[`data/inputs-2026-10-17.sha256`](../data/inputs-2026-10-17.sha256)):

| Input | Where to get it |
|---|---|
| DODGE days 2026-10-06 to 2026-10-16 (gp, satcat, events, manifest) | DODGE's releases `day-YYYY-MM-DD`, sealed, unchanged |
| DODGE's 2026-10-17 files (gp, satcat, events) as downloaded between 19:01 and 19:32 UTC on 17 October, before DODGE sealed that day | this repository's release `inputs-2026-10-17` (DODGE kept recording that day after these downloads, so its sealed version gives different numbers) |
| CelesTrak Starlink SupGP downloaded 2026-10-17 19:04 UTC (`starlink-supgp-20261017T1904Z.json`) | this repository's release `inputs-2026-10-17` (CelesTrak serves only the latest file) |

`tools/reproduce.sh` downloads them into `cache/`, checks every hash against the list, runs
`python -m ledger.pipeline all`, and prints `git status`. No changed files means byte-identical outputs.

**One outside dependency.** The `dodge_baseline` block of `out/summary.json` (and its row on the page) runs DODGE's
first manoeuvre stub, `engine/maneuvers.py`, from the DODGE checkout named by `DODGE_DIR`. The committed numbers used
the version with SHA-256 `1486023924e1179bbd9587eebaaaec705635c4d60afe3ef6aa70a59af812d141`, which counts only
objects with at least one comparable pair of sets. DODGE's main branch on 17 October 2026 has an earlier version
(`63dd25ddc814a3c0a6715d62c171507693d4ea43e1580e790e950e563f76162b`) that also counts objects with none. A fresh clone
run with it on 17 October 2026 changed exactly two numbers, both in that block: `objects` (11,162 to 11,165) and
`jumps_per_object_year` (50.397 to 50.383); the page, which rounds the rate to 50, did not change. Nothing else depends on DODGE's code. Without DODGE, the block reads
`"available": false` and the row is left out.
