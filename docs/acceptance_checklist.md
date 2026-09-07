# Acceptance checklist (TB Data Acceptance Criteria V1.3 → evidence)

Legend: ✅ satisfied and machine-checked here · 📝 satisfied by construction, reviewed by hand · ⏳ requires the supplier's model runs (not possible in this environment).

## Basic acceptance criteria

| Criterion | How this dataset meets it | Evidence |
|---|---|---|
| Environment runs and completes the tests; specific Docker image provided | Every task builds from `python:3.11-slim` with pinned pip dependencies; images are tagged `tbval/<task>:validate` by the validator. Base image digest recorded in README. | ✅ `reports/validation/summary.json` (`docker-build` checks) |
| solve.sh passes the tests (oracle) and nop fails; consistent with the instruction | Pre-apply (nop) reward 0 and post-apply (oracle) reward 1 in separate clean containers, plus Harbor `-a nop` / `-a oracle` runs. Reviewers checked instruction/test alignment. | ✅ `reports/validation/summary.md`, `reports/acceptance_report.md` |
| Not purely synthetic; manually constructed by domain experts with a real multi-file codebase, structured metadata and clear scoring | Each task is a purpose-built multi-file Python codebase with an in-workspace evidence trail (ticket, spec, legacy source or logs), `task.toml` metadata and pytest scoring. | 📝 `tasks/<task>/README.md`, `environment/app/docs/` |
| Every task requires code tools | Each task depends on real libraries (see per-task README) and the agent must run/modify code, not answer a question. | 📝 per-task README, Dockerfile |
| Solution interacts with the environment / reads multiple files | Solutions read data files, databases, logs or legacy sources in the workspace and change several modules. | ✅ `files_changed >= 3` check |
| Not an algorithm puzzle / knowledge quiz | Tasks are engineering changes on a codebase in the required categories. | 📝 reviewer lens "difficulty-realism" |
| Tests not overfit; equally valid patches pass; tests add no extra requirements | Behaviour-based pytest suites; for every task an independent reviewer implemented a structurally different solution from `instruction.md` and the workspace alone and ran the hidden tests against it (claims 65/65, BundleVault 74/74, COBOL port 29/29, recon 32/32 after fixes); instruction/test misalignments found by reviewers were fixed. | 📝 `reports/review/README.md` |
| Required categories | Each task declares one required category in `task.toml [metadata]`: operations, security hardening, cross-language migration, performance optimisation. Incident remediation, data migration and STEM are not covered in this version (see `reports/design/ranked_designs.md`). | ✅ README table |
| P25 of lines changed by solve.sh > 100; changes span multiple files | Measured by diffing `/app` before/after solve.sh in the post-apply container. | ✅ `loc_changed_p25` in `summary.json` |
| Hard for qwen3.8 max, solvable by C-17/C-11, gap thresholds | Designed for a capability gap (cross-module root causes, spec subtleties). Actual avg@8 / pass@8 must be measured by the supplier. | ⏳ Step 3 in `reports/acceptance_report.md` |
| Primary language Python | All codebases and solutions are Python. | ✅ |

## Task structure and format

| Criterion | Evidence |
|---|---|
| Harbor dataset format; one directory per task; names only `[A-Za-z0-9._-]` | ✅ `dir-name-charset`, `dataset.toml` |
| Six required files present | ✅ `file-present:*` |
| instruction.md: clear, solvable from workspace, no network / changing APIs / time-sensitive info, no leaks | ✅ `instruction-*` checks + 📝 leak/overfit review |
| task.toml parses; image/timeout/cpu/memory/disk match runtime and are numeric; no tokens | ✅ `toml-*` checks (validator runs containers with the declared cpu/memory limits); Harbor `TaskConfig` schema validation |
| solve.sh: `bash -n`, runs unattended, does not touch test.sh / reward.txt | ✅ `bash-n`, `solve.sh-does-not-touch-verifier`, `post-apply:solve.sh-did-not-write-reward` |
| test.sh: `bash -n`, real evaluation, explicit reward 1/0, no "no tests collected" anomalies | ✅ `test.sh-*`, `*:tests-collected*` |
| Dockerfile builds with `docker build -f environment/Dockerfile .`; no tests/solution/answers copied; `.dockerignore` excludes tests/ and solution/ when `COPY .` is used | ✅ `docker-build(task-root-context)`, `docker-build(environment-context)`, `dockerfile-*`, `dockerignore-*`, `image-has-no-tests-or-solution` |

## Oracle pre-/post-apply validation

| Check | Passing criterion | Evidence |
|---|---|---|
| Pre-apply test.sh exit code | non-zero | ✅ `pre-apply:test.sh-exit-nonzero` |
| Pre-apply reward.txt | exactly `0` | ✅ `pre-apply:reward==0` |
| Pre-apply outcome | ≥ 1 failing test | ✅ `pre-apply:at-least-one-test-fails` |
| Post-apply solve.sh | exit 0 within agent timeout | ✅ `post-apply:solve.sh-*` |
| Post-apply test.sh | exit 0, reward exactly `1`, all tests pass | ✅ `post-apply:*` |
| Separate clean environments | validator uses two fresh containers; Harbor runs use fresh compose stacks | ✅ by construction (`scripts/validate_task.py`) |

## Scaffold baseline validation

⏳ Requires Claude Code / mini-swe-agent runs with Fable 5 or Opus 5 and qwen3.8 max (8 attempts each). Command template and analysis checklist are in `reports/acceptance_report.md`.
