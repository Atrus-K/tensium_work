# Task authoring guide

Every task in `tasks/` must satisfy *TB Data Acceptance Criteria V1.3*. This guide
turns those criteria into concrete conventions. `scripts/validate_task.py`
enforces the mechanical parts; the rest is reviewed by hand.

## 1. Layout

```
tasks/<task-name>/
  instruction.md            # what the agent sees (and nothing else)
  task.toml                 # Harbor config (schema_version 1.4)
  .dockerignore             # MUST exclude tests/ and solution/ (task-root build context)
  environment/
    Dockerfile              # builds the workspace image
    app/                    # the codebase + data the agent works in (copied to /app)
  solution/
    solve.sh                # reference solution, non-interactive
  tests/
    test.sh                 # verifier entry point, writes /logs/verifier/reward.txt
    test_*.py               # pytest suites (hidden from the agent)
```

* `<task-name>` uses only `[A-Za-z0-9._-]`.
* Harbor copies `tests/` to `/tests` and `solution/` to `/solution` at run time and
  runs the scripts with `/app` as the working directory. Nothing under `tests/` or
  `solution/` may be baked into the image.

## 2. Dockerfile pattern

Harbor builds with `environment/` as the build context; the acceptance document
builds with the task root (`docker build -f environment/Dockerfile .`). The
pattern below works for both and never copies `tests/` or `solution/`:

```dockerfile
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Pin every dependency. pytest is pre-installed so the verifier never needs the network.
RUN pip install --no-cache-dir pytest==8.4.1 <other pinned deps>
WORKDIR /app
COPY . /tmp/ctx
RUN set -e; \
    if [ -d /tmp/ctx/environment/app ]; then SRC=/tmp/ctx/environment/app; else SRC=/tmp/ctx/app; fi; \
    cp -a "$SRC/." /app/ && rm -rf /tmp/ctx
```

Rules: pip-only (no `apt-get`, the runtime must work offline), pinned versions,
no network access at run time, no `tests/`, `solution/`, answers, or verifier
outputs in the image. The `.dockerignore` at the task root must list
`tests/`, `solution/`, `instruction.md`, `task.toml`.

## 3. task.toml

```toml
schema_version = "1.4"

[task]
name = "<org>/<task-name>"
version = "1.0.0"
description = "one line"
keywords = ["python", "<category>"]

[metadata]
category = "<one of the required categories>"
difficulty = "hard"
source = "manually constructed by domain experts; evidence trail in environment/app/docs"

[verifier]
timeout_sec = 600.0

[agent]
timeout_sec = 1800.0

[environment]
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
```

Resource fields must be numeric and match what the task really needs; the
validator runs containers with exactly these CPU/memory limits. Never put real
tokens or API keys anywhere in the task.

## 4. instruction.md

* Written like a real ticket / spec handed to an engineer: context, what is
  observed or required, where the evidence lives in the workspace, what must be
  true when done (observable behaviour, CLI commands, file names, schemas).
* Self-contained: solvable with the workspace only. No URLs, no external APIs,
  nothing time-sensitive.
* Must not mention `/tests`, test file names, `test.sh`, `solve.sh`,
  `reward.txt`, or describe the assertions.
* Everything the tests check must be stated (or be an unambiguous consequence
  of the spec documents in the workspace); tests must not add requirements.

## 5. solution/solve.sh

* `#!/usr/bin/env bash` + `set -euo pipefail`; `cd /app`; runs unattended.
* Rewrites/creates source files (heredocs are fine) and runs any commands an
  agent would run (migrations, generation scripts). It must not touch `/tests`,
  `test.sh`, or `/logs/verifier/reward.txt`.
* Must change well over 100 lines across at least three files, all necessary.
  The validator measures added+removed lines in `/app` with `diff -r`.

## 6. tests/test.sh and pytest suites

```bash
#!/usr/bin/env bash
cd /app
python -m pytest /tests -rA -p no:cacheprovider
status=$?
mkdir -p /logs/verifier
if [ $status -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit $status
```

Test design rules:

* Test observable behaviour (CLI output, files, DB state, public API results),
  never internal names, code structure, or arbitrary reference choices.
* Any equally valid implementation must pass; use invariants, independent
  oracles, spec-derived golden data, and tolerances where floating point is
  involved.
* Pre-apply at least one test must fail; post-apply all must pass; pytest must
  collect tests (no "no tests ran", nothing all-skipped).
* Deterministic: fixed seeds, no wall clock (inject clocks), no network.

## 7. Grounding, category and difficulty

* Each task is built as a real multi-file codebase for its domain with an
  evidence trail in the workspace (incident ticket, spec excerpt, legacy source,
  regression log) so the work mirrors real engineering, not a puzzle.
* Category must be one of: operations, incident remediation, data/database
  migration & recovery, security hardening / reverse-engineering patch,
  rewriting / cross-language migration, performance / algorithm optimisation,
  coding for STEM.
* Target difficulty: hard for a mid-tier coding model, solvable by a frontier
  model in one session. Cross-cutting changes, subtle spec semantics, and
  root-cause (not symptom) fixes are the levers.

## 8. Validation

```bash
# format + oracle pre/post-apply in separate clean containers + LOC measurement
python3 scripts/validate_task.py --tasks-dir tasks --report-dir reports/validation

# the acceptance document's Harbor commands (nop = pre-apply, oracle = post-apply)
scripts/harbor_validate.sh tasks/<task-name>
```
