# Changelog

All notable changes. Dates are UTC.

## 0.1.0, 17 October 2026: public release

Launch plan (ambition pass, 17 Oct 2026):

```
Literal ask:  publish Maneuver Ledger as a secure, documented public repository, a results page under DODGE's
              site, and add SpaceX's raw ephemerides as a second source.
Outcome:      an orbital engineer can check the result in a minute and reproduce it byte for byte -> metric: a
              fresh clone plus the published inputs gives zero changed outputs; every security setting read back
              from the GitHub API; the live page loads with no console errors of its own.
Depth:        1 publish the exact inputs (the 17 October snapshot and the SupGP download no longer exist upstream)
              with SHA-256, so byte-for-byte reproduction is possible for anyone | 2 rawest material: SpaceX's own
              ephemeris files | 3 full-history secret scans (gitleaks, trufflehog), SHA-pinned actions, a ruleset
              on main, a page that passes DODGE's stricter CSP | 4 outside judges: the GitHub API, the first CI run,
              a clean-clone reproduction, headless Chrome on the live URL.
Crew (verbs): keep secrets out -> security engineer: scans and settings readback | prove it reruns -> research
              software engineer: tools/reproduce.sh on a fresh clone | check the page -> web QA: console and headers
              | compare the sources -> orbit analyst: SpaceX ephemerides against SupGP.
Goal:         all of it on 17 October; prior example: DODGE's launch (6 Oct 2026) with pinned actions, signed data
              and an OpenSSF badge; a setting the API refuses is listed for the Settings page, not hidden.
```

### Results (unchanged from release gate round 2, commit 0b1ab8b)

- `ac8d4fe` Maneuver Ledger: Starlink avoidance burns against public orbit data.
- `0b1ab8b` Release gate round 1 fixes (bound wording, planned-thrust claim withdrawn, Space-Track wording, share
  fields, threshold delta-v, fleet check, lede, licence links). Round 2 (fresh reviewer): clean, 49 tests, clean-clone
  reproduction byte-identical.

### Added for the public release

- README: one-line result, three Mermaid diagrams (pipeline, detection logic, reconciliation), quickstart,
  byte-for-byte reproduction, limits, citation, licences. The generated results block is unchanged.
- `docs/ARCHITECTURE.md` (components, data flow, a run in sequence, trust boundaries), `docs/DATA.md` (sources,
  terms, CelesTrak's usage policy and how it is kept, licences, reproduction, the one outside dependency),
  `docs/FAQ.md` (including why public data cannot see small burns).
- `LICENSE-DATA` (CC BY 4.0 for the derived data, as DODGE does), `CITATION.cff`, `SECURITY.md` (private reporting).
- `.github/workflows/ci.yml` (read-only token, actions pinned to full SHAs, hash-pinned install, no secrets),
  `.github/dependabot.yml`, `.github/CODEOWNERS`; `.gitignore` covers caches, `.env`, keys and certificates.
- `data/inputs-2026-10-17.sha256` and `tools/reproduce.sh`.
- `tests/test_docs.py`: prose numbers in the README and FAQ match `out/summary.json`; local links resolve; workflow
  rules (read-only, SHA-pinned, no secrets).
- Wording: the README and METHODS no longer describe SpaceX's ephemerides as needing an internal approval; they say
  the files are not used in this version.
