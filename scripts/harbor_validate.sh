#!/usr/bin/env bash
# Run the acceptance document's Harbor validation for one or more tasks:
#
#   harbor run -p <task-dir> -a nop      # pre-apply  (expects reward 0)
#   harbor run -p <task-dir> -a oracle   # post-apply (expects reward 1)
#
# Each run uses a fresh container, so post-apply artifacts cannot contaminate
# the pre-apply result.
#
# Usage:
#   scripts/harbor_validate.sh [--prebuilt] [--jobs-dir DIR] <task-dir> [<task-dir> ...]
#
# --prebuilt   Build the image locally first (honouring $TB_BUILD_FLAGS, e.g.
#              "--network=host --build-arg=HTTPS_PROXY=http://127.0.0.1:34087"
#              in a sandbox whose containers can only reach PyPI via a host
#              proxy) and point a SCRATCH COPY of the task at that image via
#              environment.docker_image. The task directory itself is never
#              modified. Without --prebuilt, Harbor builds the Dockerfile itself
#              exactly as an acceptance reviewer would.
set -euo pipefail

PREBUILT=0
JOBS_DIR="reports/harbor-jobs"
TASKS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --prebuilt) PREBUILT=1; shift ;;
    --jobs-dir) JOBS_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) TASKS+=("$1"); shift ;;
  esac
done
[ ${#TASKS[@]} -gt 0 ] || { echo "no task directories given" >&2; exit 2; }
command -v harbor >/dev/null || { echo "harbor CLI not found (pip/uv install harbor, needs Python>=3.12)" >&2; exit 2; }

mkdir -p "$JOBS_DIR"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
overall=0

for task in "${TASKS[@]}"; do
  task="${task%/}"
  name="$(basename "$task")"
  run_dir="$task"
  if [ "$PREBUILT" = 1 ]; then
    tag="tbval/${name,,}:harbor"
    # shellcheck disable=SC2086
    docker build -f "$task/environment/Dockerfile" -t "$tag" ${TB_BUILD_FLAGS:-} "$task" >"$JOBS_DIR/$name.build.log" 2>&1 \
      || { echo "[$name] docker build FAILED (see $JOBS_DIR/$name.build.log)"; overall=1; continue; }
    cp -r "$task" "$SCRATCH/$name"
    python3 - "$SCRATCH/$name/task.toml" "$tag" <<'PY'
import sys, re
p, tag = sys.argv[1], sys.argv[2]
s = open(p).read()
assert "[environment]" in s, "task.toml has no [environment] table"
s = re.sub(r"^docker_image\s*=.*\n", "", s, flags=re.M)
s = s.replace("[environment]\n", f'[environment]\ndocker_image = "{tag}"\n', 1)
open(p, "w").write(s)
PY
    run_dir="$SCRATCH/$name"
  fi

  for agent in nop oracle; do
    out="$JOBS_DIR/$name.$agent"
    rm -rf "$out"
    if ! harbor run -p "$run_dir" -a "$agent" -o "$out" --no-force-build >"$JOBS_DIR/$name.$agent.log" 2>&1; then
      echo "[$name] harbor run -a $agent FAILED (see $JOBS_DIR/$name.$agent.log)"; overall=1; continue
    fi
    reward="$(cat "$out"/*/*/verifier/reward.txt 2>/dev/null | tr -d '[:space:]' || true)"
    summary="$(grep -E '^=+ .*(passed|failed|error).* =+$' "$out"/*/*/verifier/test-stdout.txt 2>/dev/null | tail -1 || true)"
    want=0; [ "$agent" = oracle ] && want=1
    if [ "$reward" = "$want" ]; then
      echo "[$name] $agent: reward=$reward (expected $want) PASS   $summary"
    else
      echo "[$name] $agent: reward='$reward' (expected $want) FAIL   $summary"; overall=1
    fi
  done
done
exit $overall
