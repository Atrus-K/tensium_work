#!/usr/bin/env bash
# Reproduce the LNACCR01 shadow run for a batch and reconcile it against the mainframe output.
#   scripts/run_shadow.sh [YYYYMM] [ASOF]      defaults: 202403 2024-03-31
set -euo pipefail
cd "$(dirname "$0")/.."
BATCH="${1:-202403}"
ASOF="${2:-2024-03-31}"
mkdir -p out logs/recon
python -m pyledger run \
    --master "data/LNMAST_${BATCH}.dat" \
    --trans "data/LNTRAN_${BATCH}.dat" \
    --rates "data/RATETBL_${BATCH}.dat" \
    --holidays data/HOLIDAYS.dat \
    --asof "$ASOF" \
    --out "out/LNOUT_${BATCH}.dat"
python -m pyledger recon \
    --legacy "data/MAINFRAME_LNOUT_${BATCH}.dat" \
    --candidate "out/LNOUT_${BATCH}.dat" \
    --report "logs/recon/recon_LNACCR01_${BATCH}.txt"
