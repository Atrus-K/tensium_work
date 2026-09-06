#!/usr/bin/env bash
cd /app
export PYTHONDONTWRITEBYTECODE=1
python -m pytest /tests -rA -p no:cacheprovider
status=$?
mkdir -p /logs/verifier
if [ $status -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit $status
