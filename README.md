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

| task | category | lines changed / files changed by solve.sh | pre-apply | post-apply | resources (task.toml) | verifier / agent timeout |
|---|---|---|---|---|---|---|
| `claims-adjudication-audit-recalc` | Operations (claims processing, prompt-pay compliance) | 447 / 10 | 50 of 65 fail → reward 0 | 65 of 65 pass → reward 1 | 2 CPU / 2048 MB / 4096 MB disk | 600 s / 2700 s |
| `bundlevault-pentest-remediation` | Security hardening / reverse-engineering patch | 426 / 10 | 53 of 74 fail → reward 0 | 74 of 74 pass → reward 1 | 2 CPU / 2048 MB / 4096 MB disk | 600 s / 2400 s |
| `cobol-loan-accrual-port-parity` | Rewriting / cross-language migration (COBOL to Python) | 213 / 9 | 23 of 29 fail → reward 0 | 29 of 29 pass → reward 1 | 2 CPU / 2048 MB / 4096 MB disk | 600 s / 2700 s |
| `recon-nightly-timeout-2291` | Performance / algorithm optimisation (incident-driven) | 826 / 15 | 28 of 32 fail → reward 0 | 32 of 32 pass → reward 1 | 2 CPU / 2048 MB / 4096 MB disk | 900 s / 3600 s |

- **`claims-adjudication-audit-recalc`** — tessera-claims: stdlib + sqlite claims adjudication engine; an internal audit ticket, the auditor's recomputed figures, the production batch log and a product-rules manual are in the workspace. Seven cross-module root causes (policy-version selection, per-occurrence deductible and sublimits, depreciation, Decimal rounding, per-state prompt-pay clocks, business-day calendar, occurrence-scoped ledger).
- **`bundlevault-pentest-remediation`** — BundleVault: stdlib http.server + sqlite firmware-bundle registry for a proprietary binary TLV format; a pentest report with six findings, five captured malicious .fwb samples, the access log and a forged audit excerpt are in the workspace. Parser/verifier differential, path traversal, manifest/file bijection, identity binding, rollback/revocation and log injection must all be fixed per the format spec.
- **`cobol-loan-accrual-port-parity`** — pyledger: in-progress Python port of the mainframe batch LNACCR01; the read-only COBOL source and copybooks, the shadow-run reconciliation log, the blocker ticket and a dismissed PR review are in the workspace. Seven COBOL-semantics defects (ROUNDED vs truncation, two-step accrual, zoned overpunch signs, century window, 30/360 clamp, days-late/grace, copybook v3 waive flag, status ladder) must be fixed to byte parity with the mainframe output.
- **`recon-nightly-timeout-2291`** — recon: stdlib + sqlite payments reconciliation engine whose nightly run no longer finishes after a large tenant was onboarded; the incident ticket, nightly log, cProfile listing, hotfix review and matching specification are in the workspace. Several independent root causes (per-candidate SQL, unbounded fuzzy matching, per-row connections, customer-master reloads, a batch-rule cap) must be fixed without changing what the specification says must match.

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

How the Harbor runs were executed here: this sandbox can only reach PyPI through a
local proxy, so `scripts/harbor_validate.sh --prebuilt` builds each image with
`docker build --network=host --build-arg HTTPS_PROXY=...` and points a *scratch copy*
of the task at that image via `environment.docker_image`; the committed `task.toml`
files carry no `docker_image` and Harbor builds the Dockerfile itself on a normal host.
The Dockerfile build (from both the task-root and the `environment/` context) is
verified separately by `scripts/validate_task.py`. Set
`TB_BUILD_FLAGS="--network=host --build-arg=HTTPS_PROXY=http://127.0.0.1:34087"` and
pass `--build-flag=...` to the validator only when reproducing inside such a sandbox.

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

All four tasks pass every check in `scripts/validate_task.py` (43 checks per task) and the Harbor `nop` / `oracle` runs (`scripts/harbor_validate.sh`).

- Pre-apply failures (required): 4 / 4 tasks (reward `0`, at least one failing test, tests collected).
- Post-apply successes (required): 4 / 4 tasks (reward `1`, all tests pass, solve.sh well within the agent timeout).
- Lines changed by the reference solutions: 447, 426, 213, 826; **P25 = 373** (criterion > 100).
- Every task changes at least 9 files; every task is Python, pip-only, offline and deterministic.
- Adversarial review: for each task an independent reviewer wrote a structurally different solution from `instruction.md` and the workspace alone and ran the hidden suite against it; all pass (claims 65/65, BundleVault 74/74, COBOL port 29/29, recon 32/32). Findings and fixes are recorded in `reports/review/README.md`.
- Design provenance: 14 candidate designs, two per required category, scored by three judges; ranking and rationale in `reports/design/ranked_designs.md`.
- Full per-check evidence: `reports/validation/summary.json`, `reports/validation/summary.md`, `reports/acceptance_report.md`.

Categories covered: operations, security hardening / reverse-engineering, rewriting / cross-language migration, performance / algorithm optimisation. The incident-remediation, data-migration and STEM designs were not built in this version (see the design ranking for the judges' reasons).

## What is not covered here

- The scaffold baseline (Step 3: avg@8 / pass@8 with Claude Code on Fable 5 / Opus 5 and
  qwen3.8 max, 8 attempts per task) requires model API access and is run by the supplier.
  Difficulty was therefore designed for, not measured: each task needs several
  cross-module root causes fixed behind an all-or-nothing reward, and the reviewers'
  notes on what a mid-tier model is likely to miss are in `reports/design/` and
  `reports/review/`. If a pilot shows a task with qwen avg@8 = 0, the design files list
  the specific difficulty knobs (which evidence hints to remove or which defect to drop).
- Three of the seven required categories (incident remediation, data/database migration,
  STEM) are not represented in this version; the judges' objections to those designs are
  recorded in `reports/design/ranked_designs.md`.
- The tasks are manually constructed by domain experts with an in-workspace evidence trail
  (tickets, specs, logs, legacy source) rather than mined from public repositories.
