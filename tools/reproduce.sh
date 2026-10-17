#!/usr/bin/env bash
# Reproduce the committed results byte for byte.
#
#   tools/reproduce.sh
#
# 1. Downloads every input listed in data/inputs-2026-10-17.sha256 that is not already in cache/:
#    DODGE's sealed days from DODGE's public releases, and the three 17 October DODGE files plus
#    the CelesTrak SupGP download from this repository's release inputs-2026-10-17.
# 2. Checks every SHA-256. Stops on any mismatch.
# 3. Runs `python -m ledger.pipeline all` (offline, about 3 minutes) and prints `git status`.
#
# It never deletes anything. If cache/ holds other inputs (for example newer days from
# `pipeline sync`), it stops and asks you to move them aside, because the pipeline reads every
# file in cache/ and extra days would change the numbers.
#
# DODGE_DIR: a DODGE checkout, used only for the dodge_baseline block (see docs/DATA.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LIST="data/inputs-2026-10-17.sha256"
DODGE_REL="https://github.com/GautamTalksDev/dodge/releases/download"
OWN_REL="https://github.com/GautamTalksDev/maneuver-ledger/releases/download/inputs-2026-10-17"

mkdir -p cache/dodge cache/celestrak

# --- 1. refuse to mix in inputs that are not on the list
extra=0
for f in cache/dodge/gp-* cache/dodge/satcat-* cache/dodge/events-* cache/dodge/manifest-* cache/celestrak/starlink-supgp-*.json; do
  [ -e "$f" ] || continue
  rel="${f#cache/}"
  if ! awk '{print $2}' "$LIST" | grep -qxF "$rel"; then
    echo "not on the input list: $f"
    extra=1
  fi
done
if [ "$extra" -ne 0 ]; then
  echo "Move the files above out of cache/ (nothing was deleted), then run this again."
  exit 1
fi

# --- 2. download what is missing, then check every hash
while read -r want rel; do
  path="cache/$rel"
  name="$(basename "$rel")"
  if [ -e "$path" ] && [ "$(sha256sum "$path" | cut -d' ' -f1)" = "$want" ]; then
    continue
  fi
  case "$rel" in
    dodge/*-2026-10-17.*|celestrak/*) url="$OWN_REL/$name" ;;
    dodge/*)
      day="$(echo "$name" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')"
      url="$DODGE_REL/day-$day/$name" ;;
    *) echo "unknown input $rel"; exit 1 ;;
  esac
  echo "downloading $name"
  curl -fsSL --proto '=https' --tlsv1.2 -A "maneuver-ledger reproduce.sh" -o "$path.part" "$url"
  mv "$path.part" "$path"
  sleep 1
done < "$LIST"
(cd cache && sha256sum --quiet -c "../$LIST")
echo "all $(wc -l < "$LIST") inputs match their SHA-256"

# --- 3. run and compare
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --require-hashes --no-deps -r requirements.txt
fi
if [ -z "${DODGE_DIR:-}" ]; then
  echo "note: DODGE_DIR is not set; only the dodge_baseline block can differ (docs/DATA.md)"
fi
.venv/bin/python -m ledger.pipeline all > /dev/null
echo "changed outputs (empty means byte-identical to the commit):"
git status --short -- out site README.md
