# tensium/tb-acceptance-v1

Harbor-format agentic-coding tasks built to satisfy **TB Data Acceptance Criteria V1.3**
(reference copy: `docs/acceptance_criteria_v1.3.md`; criterion-to-evidence mapping:
`docs/acceptance_checklist.md`).

## Layout

```
dataset.toml                  # Harbor dataset manifest
tasks/<task-name>/            # one Harbor task per directory (see docs/task_authoring_guide.md)
  instruction.md              # what the agent sees
  task.toml                   # Harbor config (schema 1.4), numeric cpu/memory/disk/timeouts
  .dockerignore               # excludes tests/ and solution/ from the build context
  environment/Dockerfile      # python:3.11-slim + pinned pip deps; copies environment/app -> /app
  environment/app/            # the codebase, data and evidence trail the agent works in
  solution/solve.sh           # reference solution (oracle)
  tests/test.sh, test_*.py    # hidden verifier; writes /logs/verifier/reward.txt (1 or 0)
scripts/validate_task.py      # format checks + pre/post-apply oracle validation in clean containers
scripts/harbor_validate.sh    # the document's `harbor run -a nop` / `-a oracle` validation
scripts/report_acceptance.py  # renders the "Final Acceptance Conclusion" section from the reports
docs/                         # criteria, checklist, authoring guide
reports/                      # validation outputs (summary.json / summary.md / acceptance_report.md)
```

## Tasks

<!-- TASK TABLE -->

## Docker image

Every task builds from the official `python:3.11-slim` image (Debian bookworm) with pinned
pip dependencies and no network access at run time. Built images are tagged
`tbval/<task-name>:validate` by the validator. Base image digest used for validation:
`python@sha256:193fdd0bbcb3d2ae612bd6cc3548d2f7c78d65b549fcaa8af75624c47474444d`.

## Validating

```bash
# 1 + 2: format checks, docker build (both contexts), image leak scan, pre-apply and
#        post-apply oracle runs in separate clean containers, LOC-changed measurement
python3 scripts/validate_task.py --tasks-dir tasks --report-dir reports/validation

# the acceptance document's Harbor commands (Harbor needs Python >= 3.12: `uv tool install harbor`)
scripts/harbor_validate.sh tasks/*

# render the final acceptance conclusion
python3 scripts/report_acceptance.py
```

Direct local validation of one task, as described in the acceptance document:

```bash
cd tasks/<task-name>
docker build -f environment/Dockerfile -t t .
docker run --rm -it t bash            # then inside the container:
#   mkdir -p /logs/verifier && rm -f /logs/verifier/reward.txt
#   (copy tests/ to /tests) && bash /tests/test.sh ; cat /logs/verifier/reward.txt   -> 0
#   (fresh container) (copy solution/ to /solution) && bash /solution/solve.sh
#   (copy tests/ to /tests) && bash /tests/test.sh ; cat /logs/verifier/reward.txt   -> 1
```

## Validation results

<!-- RESULTS -->

## What is not covered here

The scaffold baseline (Step 3: avg@8 / pass@8 with Claude Code on Fable 5 / Opus 5 and
qwen3.8 max) requires model API access and is run by the supplier. The command template
and the per-case review checklist are in `reports/acceptance_report.md`.
