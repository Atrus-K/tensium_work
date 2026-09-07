# Adversarial review record

Each task went through: (1) an implementer that iterated until `scripts/validate_task.py` passed; (2) four independent reviewers with distinct lenses — leakage/overfit, an **independent alternative solution written from `instruction.md` and the workspace alone and then run against the hidden tests**, difficulty/root-cause depth/realism/determinism, and line-by-line acceptance compliance; (3) a fix round that verified every finding and either applied or rejected it with a reason; (4) a re-review of the two lenses most likely to regress. Where a re-review agent was lost to an API session limit, the orchestrator re-ran the reviewers' alternative solutions against the final hidden suites directly (results in the README).

Severity legend: blocker / major / minor as assigned by the reviewer. Every blocker and major was either fixed or shown to be resolved by the dataset commit (the recurring 'git HEAD holds the solved state' finding referred to an interim WIP snapshot; the committed task directories now hold the pre-fix workspace).

## claims-adjudication-audit-recalc

- Build report: validator passed = True, tests = 62, pre-apply failing = 48, lines changed = 447 across 10 files.
- Known weaknesses recorded by the implementer:
  - Rules document, ticket, oracle and reference implementation were all written by the same author; independence of the oracle is stylistic (Fraction-based, separate code) rather than organisational. Mitigation: 29 goldens carry hand derivations in comments and the rules document's worked examples were cross-checked against engine output
  - The deterministic processing-order rule (loss_date, received_date, claim_id) is not independently testable with realistic data because within an occurrence received-date order and claim-id order coincide; any order that processes an original before its supplemental passes
  - Float vs Decimal rounding of INTEREST is not detectable on this data (ablation using float interest rounding passes); banker's rounding is detected only through the two exact half-cent ACV lines in CLM-24-0621, so an agent using floats for ACV would fail but one using floats only for interest would not
  - The test suite pins the exact export column order and the payments-table column names as stated in the instruction; a correct implementation that renames columns would fail (by design, since the instruction fixes the contract)
  - Idempotency test compares ledger rows across two runs excluding payment_id only; an implementation that stores category_acv JSON with non-deterministic key order would fail even though numerically correct (json.dumps with sorted keys or insertion order both pass in practice)
  - Tests build and adjudicate via subprocess against Path.cwd() (overridable with TESSERA_APP_DIR); test.sh runs from /app as required, but running pytest from another directory without the env var would fail to locate the app
  - Difficulty was not empirically calibrated against qwen3.8-max / frontier models; the estimated gap rests on the seven cross-module root causes and the alt dataset, not on measured pass rates
- Review passes: 6; fix rounds: 1.

| review pass | verdict | blocker | major | minor | alternative solution vs hidden tests |
|---|---|---|---|---|---|
| INDEPENDENT ALTERNATIVE SOLUTION | accept | 0 | 0 | 2 | 62 passed / 0 failed |
| LEAKAGE AND OVERFIT | accept | 0 | 0 | 3 | 62 passed / 0 failed |
| DIFFICULTY, ROOT-CAUSE DEPTH, REALISM, DETERMINISM | accept | 0 | 0 | 3 | 62 passed / 0 failed |
| LINE-BY-LINE ACCEPTANCE COMPLIANCE | accept | 0 | 0 | 4 | n/a |
| INDEPENDENT ALTERNATIVE SOLUTION | accept | 0 | 0 | 4 | 65 passed / 0 failed |
| LEAKAGE AND OVERFIT | accept | 0 | 0 | 3 | 65 passed / 0 failed |

Fix round 1: validator passed = True; 10 fixes applied, 3 findings rejected with reasons; remaining blockers: none.
  - applied: [LEAKAGE #1, minor] days_late for no_coverage claims was test-required but unstated: instruction.md now says 'an empty policy_version_id, days_late 0 and all amounts 0'; CH-7 s1.3 in environment/app/docs/adjudication_rules.md now states no_coverage is reported with zero amounts and days_late 0 (no s
  - applied: [LEAKAGE #2, minor] Dropped the parenthetical module list from instruction.md ('Expect the causes to be spread across several modules; the log's WARN lines are one of the clues.'), leaving discovery to the ticket/CHANGELOG/log evidence trail.
  - applied: [LEAKAGE #3, minor] Added NOTE comments to tests/test_goldens_main.py and tests/test_alt_dataset.py stating the hand-derived goldens must be kept in sync with tests/oracle.py when data changes.
  - applied: [ALT-SOLUTION #1, minor] Unspecified missing clock-start date: CH-7 s6 now states that if the required clock-start date is absent the clock has not started (no deadline, days_late 0, no interest); tests/oracle.py deadline_for() now returns None in that case and compute_batch() yields days_late 0, ma
  - applied: [ALT-SOLUTION #2, minor] CH-7 s2 now defines 'earlier activity' precisely: every payment record on the occurrence counts whatever its batch, except records produced by an earlier run of the batch being re-run, which are replaced (s8). This matches both the oracle and the reference solution.
  - applied: [DIFFICULTY #1 / COMPLIANCE #3, minor] Deleted tests/__pycache__ (7 stale .pyc files); the repo-level .gitignore already ignores __pycache__/ and *.pyc and the task .dockerignore excludes them from the image.
  - applied: [DIFFICULTY #2, minor] Processing order (loss_date, received_date, claim_id) was not test-enforced. Added policy P-9007 / PV-9007-A (CA, flat deductible 1200, jewelry sublimit 1500) and occurrence OCC-24-0715 to tests/fixtures/alt_dataset with two same-loss-date claims received in the reverse of cla
  - applied: [COMPLIANCE #1, minor, partial] Pinned pytest's transitive dependencies explicitly in environment/Dockerfile (pytest==8.4.1 pluggy==1.6.0 iniconfig==2.3.0 packaging==26.3 Pygments==2.21.0); pip freeze in the rebuilt image shows exactly these five packages.
  - applied: [COMPLIANCE #2, minor] Reworded the constraints paragraph in instruction.md: 'do not modify the CSV/JSON source files under data/ (rebuilding data/claims.db with build-db is expected) or anything under docs/ or logs/'.
  - applied: Re-ran the validator: all 43 checks PASS; pre-apply 50 failed / reward 0; post-apply 65 passed / reward 1; loc_changed=447 across 10 files; solve.sh 0.4s. Report: /home/user/tensium_work/reports/validation/claims-adjudication-audit-recalc/summary.json.
  - rejected: [COMPLIANCE #1, digest part] Pin the base image by digest (FROM python:3.11-slim@sha256:...). — The sandbox facts require 'Use ONLY FROM python:3.11-slim': the locally available image is a CA-trusting mirror tagged with that name, so a real Docker Hub digest would not match it and the build would fail here (and a d
  - rejected: [COMPLIANCE #4] Commit the task directory so the acceptance report can cite a commit hash. — Committing is outside this subtask's remit (the environment rules say commit only when the user asks) and is a dataset-packaging step for the orchestrator across all tasks; the task files themselves are complete and untr
  - rejected: [DIFFICULTY #3] Soften the 'Pattern:' paragraph of docs/tickets/AUD-2024-117_findings.md so the prompt-pay mechanism is not spelled out. — The reviewer marked this as no change required pending calibration; the ticket is the realistic evidence trail the acceptance criteria demand (an internal audit finding naturally names what it observed), and difficulty w

## bundlevault-pentest-remediation

- Build report: validator passed = True, tests = 59, pre-apply failing = 42, lines changed = 414 across 10 files.
- Known weaknesses recorded by the implementer:
  - The reference buggy signature range excludes only trailing bytes past payload_len (it still covers the header), a deviation from the design's 'signature excludes header bytes' bug; this was necessary so the committed fixtures verify byte-identically under both the buggy and fixed verifiers. The header-tamper test (flags+CRC fixed) therefore passes in both states rather than being a pre-fix discriminator, but the shadow-manifest (c1) and stage-before-verify traps preserve the intended difficulty.
  - Each hidden test spins up a short-lived `python -m bundlevault serve` subprocess on a dynamically chosen free port with a bounded /healthz wait and terminates it on teardown; the full 59-test suite runs in ~26s in-container, but a heavily loaded runner could in principle slow subprocess startup (mitigated by a 20s bounded poll and the 600s verifier timeout).
  - The captured-sample test runs against an empty-registry server; on that state some samples (e.g. c1) are accepted pre-fix while others are caught by the stage-before-verify snapshot check, so the specific pre-fix failure reason varies by sample though all five correctly pass post-fix.
- Review passes: 4; fix rounds: 1.

| review pass | verdict | blocker | major | minor | alternative solution vs hidden tests |
|---|---|---|---|---|---|
| INDEPENDENT ALTERNATIVE SOLUTION | accept | 0 | 0 | 4 | 59 passed / 0 failed |
| LEAKAGE AND OVERFIT | fix-needed | 0 | 1 | 5 | 59 passed / 0 failed |
| LINE-BY-LINE ACCEPTANCE COMPLIANCE | fix-needed | 0 | 1 | 3 | n/a |
| DIFFICULTY / ROOT-CAUSE DEPTH / REALISM / DETERMINISM review | fix-needed | 0 | 1 | 5 | 59 passed / 0 failed |

Blocker/major findings and their resolution:
- **[major] codebase** (LEAKAGE AND OVERFIT): The only committed revision of the task ships the oracle inside the image path. `git show HEAD:tasks/bundlevault-pentest-remediation/environment/app/bundlevault/{fwb/sections.py,fwb/signature.py,fwb/manifest.py,fwb/reader.py,staging.py,versioning.py,registry.py,keyring.py,audit.py,ingest.py}` is byte-identical to what solution/solve.sh writes (verified with diff for all ten files). The vulnerable 
- **[major] grounding** (LINE-BY-LINE ACCEPTANCE COMPLI): The task as committed to git is inconsistent with the task on disk. HEAD (1810c79 'WIP: snapshot') tracks only environment/app/** (44 files) and NONE of the six required files (instruction.md, task.toml, environment/Dockerfile, solution/solve.sh, tests/test.sh, .dockerignore are all untracked, 30 untracked files total). Worse, the 10 committed bundlevault modules in HEAD are byte-identical to the 
- **[major] grounding** (DIFFICULTY / ROOT-CAUSE DEPTH ): Git state is inconsistent with the on-disk task: HEAD commit 1810c79 ('WIP: snapshot of tasks under construction') contains the POST-solve (already fixed) versions of the 10 app modules, while the vulnerable baseline lives only as uncommitted working-tree modifications, and instruction.md, task.toml, tests/, solution/, environment/Dockerfile, docs/, SECURITY/, evidence/, tests_local/, README.md an

Fix round 1: validator passed = True; 14 fixes applied, 4 findings rejected with reasons; remaining blockers: ["Git repository state (major, 3 reviewers, CONFIRMED): HEAD 1810c79 tracks the 10 bundlevault modules in their solve.sh-fixed form, while the vulnerable baseline exists only as uncommitted working-tree edits and instruction.md, task.toml, Dockerfile, tests/, solution/, docs/, SECURITY/, evidence/ are untracked. The on-disk task is correct (validator: pre-apply 53 failed/21 passed, post-apply 74 passed). I did not commit because committing writes outside my permitted paths and no explicit commit instruction was given; the orchestrator must `git add tasks/bundlevault-pentest-remediation && git commit` the current working tree so the committed baseline is the vulnerable one, and record that commit hash as the task's data version."].
  - applied: instruction.md: removed the author-facing 'do not restate hidden test cases' sentence; replaced with an in-persona line pointing at the pentest acceptance criteria and spec and forbidding edits under fixtures/, keys/, data/
  - applied: instruction.md: trimmed the 1:1 module enumeration and the five-bullet restatement of spec rules to a pointer at docs/FWB_FORMAT.md section numbers (raises difficulty, no requirement lost since the spec is in the workspace)
  - applied: instruction.md and SECURITY/PENTEST-2026-08.md: replaced the `xxd ... | less` hint (xxd/less absent from python:3.11-slim) with `od -A d -t x1z` (verified present in the image)
  - applied: SECURITY/PENTEST-2026-08.md F6 acceptance: now requires enforcing the section-4 field grammar (control/`|` in name/version/vendor_id => rejected bundle); escaping on write is defence in depth, not a substitute
  - applied: docs/FWB_FORMAT.md section 8: same consistency fix (MUST be rejected under section 4; writer should additionally sanitise)
  - applied: docs/API.md POST /v1/bundles: added that only a vendor token whose vendor_id equals the manifest vendor_id may publish and the ops admin token (vendor_id null) cannot
  - applied: environment/app/bundlevault/registry.py and keyring.py: docstrings now describe shipped behaviour instead of pre-announcing the fix (publish-time revocation / active-key-only wording removed)
  - applied: tests/test_audit.py: docstring no longer says escaping alone is acceptable; added test_manifest_grammar_rejects_control_and_pipe (6 parametrised cases: newline injection, pipe in name, pipe in vendor_id, CR, TAB, DEL) asserting 4xx + no side effects
  - applied: tests/test_structure.py: added padding-after-FILE and padding-between-MANIFEST-and-FILE positive tests and a duplicate-SIGNATURE rejection test
  - applied: tests/test_bijection.py: added duplicate FILE section (same path), duplicate manifest path, and uppercase-sha256 rejection tests
  - applied: tests/test_versioning.py: added test_numeric_prerelease_identifier_below_alphanumeric (1.0.0-1 < 1.0.0-alpha accepted, 1.0.0-2 rejected as rollback, 1.0.0 accepted)
  - applied: tests/test_fixtures.py: added CLI `ingest` tests (fixture exits 0 and stages; c2_traversal exits 2 with no files under var/ or anywhere in tmp)
  - applied: tests/conftest.py: _start now retries up to 3 times with a fresh port when the serve child exits early (free_port TOCTOU hardening)
  - applied: Verified the expanded 74-test suite passes against the reference and all three reviewer alternative solutions (alt_solve.py, lazy.diff, alt-bundlevault-pentest-remediation) and fails 53/74 pre-apply; tests_local smoke tests pass in both states
  - rejected: Reference solve.sh LOC (373-414) is inflated by wholesale rewrites; intrinsic fix ~76 lines (minor, difficulty) — Reviewer marked it 'acceptable as is'; validator reports loc_changed=426 across 10 files, well above the >100 threshold. I addressed the spirit by adding tests the 76-line lazy patch must still satisfy (dup SIGNATURE, du
  - rejected: Puzzle-like tells: patterned hex secrets (1111.., a0a0..) and placeholder sha256 values in registry_seed.sql (minor, realism) — Reviewer said 'None required'. keys/ and data/ are frozen contracts the tests read (conftest loads vendor_keys.json and api_tokens.json), the captured samples and fixtures are signed with these secrets, and changing them
  - rejected: fwb/errors.py pre-defines the full exception taxonomy with docstrings naming conditions to reject (minor, codebase) — Reviewer explicitly suggested leaving errors.py as-is because the server's BundleError->4xx mapping is the intended extension point; the exception classes are needed by the shipped code and every condition they name is a
  - rejected: Signature-range bug deviates from design ('excludes header') — build report known weakness — Not a review finding requiring action: the deviation was necessary so committed fixtures verify byte-identically pre- and post-fix; test_tampered_header_flags_rejected still fails pre-apply via the stage-before-verify si

## cobol-loan-accrual-port-parity

- Build report: validator passed = True, tests = 28, pre-apply failing = 22, lines changed = 214 across 8 files.
- Known weaknesses recorded by the implementer:
  - The +1 days-late defect surfaces on every late account (165 of the 386 recon lines), so it is the loudest and easiest of the seven root causes; the recon log is correspondingly long
  - Half-cent accrual rounding does not actually change any March output (the float single-expression path happens to round the planted half-cents up as well); the rounding-mode defect is exercised in the visible batch mainly through LATE_FEE and in the hidden mini-case tests
  - Goldens come from an author-written straight-line oracle transliteration of the COBOL, not a real COBOL compiler; mitigated by an independent second implementation (the port) agreeing byte-for-byte on 689 records and hand verification of 18 planted edge records against the COBOL text
  - test_reference_data_untouched pins sha256 of data/*; any byte edit to the reference data fails even though the instruction states data/ is read-only
  - test_recon_still_detects_a_difference relies on the existing recon tool's report vocabulary (field label BALANCE, RESULT: MISMATCH); the instruction forbids changing recon.py so this is aligned, but a cosmetic reformat of recon output would fail it
  - The hidden May batch is produced by the same generator structure as March, so an implementation overfit to the generator's distribution of edge cases (rather than to March account values) is conceivable, though unlikely to reach byte parity
  - Six of 28 tests pass pre-apply (structural checks, recon-detects-difference, data hash, tier-bound/status-at-90 cases that the defective port happens to get right); pre-apply failure is still robust at 22 tests
- Review passes: 4; fix rounds: 1.

| review pass | verdict | blocker | major | minor | alternative solution vs hidden tests |
|---|---|---|---|---|---|
| INDEPENDENT ALTERNATIVE SOLUTION | accept | 0 | 0 | 3 | 28 passed / 0 failed |
| LEAKAGE AND OVERFIT | accept | 0 | 0 | 2 | 28 passed / 0 failed |
| LINE-BY-LINE ACCEPTANCE COMPLIANCE | fix-needed | 0 | 1 | 4 | 28 passed / 0 failed |
| DIFFICULTY, ROOT-CAUSE DEPTH, REALISM, DETERMINISM | accept | 0 | 1 | 3 | 28 passed / 0 failed |

Blocker/major findings and their resolution:
- **[major] codebase** (LINE-BY-LINE ACCEPTANCE COMPLI): The task is not committed, and what IS committed is the solved state. HEAD (commit 1810c79 'WIP: snapshot of tasks under construction') contains only 11 files for this task: environment/app/pyledger/*.py, and 8 of them (accrual.py, copybook.py, dates.py, fees.py, layouts.py, models.py, numeric.py, status.py) are the FIXED versions (e.g. HEAD accrual.py already has DAILY_RATE_PIC/ACCRUED_PIC two-st
- **[major] codebase** (DIFFICULTY, ROOT-CAUSE DEPTH, ): The git HEAD commit of the repo contains the SOLVED pyledger in environment/app (identical to solve.sh's heredocs); the buggy, validated version exists only as uncommitted working-tree modifications. If the task is shipped/reproduced from the commit identifier, the environment would already pass pre-apply and the task would be invalid. .dockerignore and README.md are also untracked.

Fix round 1: validator passed = True; 6 fixes applied, 5 findings rejected with reasons; remaining blockers: none.
  - applied: MAJOR (both reviewers) — uncommitted task / HEAD held the solved pyledger: committed the full task directory in its validated pre-apply state as 10403fc (buggy environment/app, instruction.md, task.toml, Dockerfile, .dockerignore, README.md, solution/, tests/ incl. fixtures) plus reports/validation/
  - applied: MINOR — May fixture's extra holiday (20240610) fell after the as-of date and never affected output: regenerated the hidden May 2024 batch with the author's scratchpad generator + straight-line COBOL oracle using a state banking holiday on 2024-05-15 (a Wednesday). Oracle runs with and without that h
  - applied: MINOR — no test for COBOL high-order truncation on store: added tests/test_cobol_semantics.py::test_days_late_high_order_digits_are_dropped_on_store (due dates 1034 and 1004 days before as-of -> LO-DAYS-LATE '034'/'004' while WS-DAYS-LATE S9(5) still drives status 'W' and the fee/waive logic). Groun
  - applied: MINOR — fix-naming breadcrumbs in the workspace: reworded the two TODO comments (pyledger/dates.py days_360 and pyledger/numeric.py truncate) to state only the observed symptom ('verified against the October sample'), removed the CHANGELOG parenthetical that named pyledger/layouts.py as stale, and r
  - applied: MINOR — instruction front-loads the defect categories: dropped the parenthetical list '(numeric storage and rounding, signed-field encoding, date handling, layout, business rules)' from deliverable 2; the remaining bullets restate only what the in-workspace ticket/COBOL header already say and are ne
  - applied: MINOR — stale tests/__pycache__: deleted; tests/test.sh now exports PYTHONDONTWRITEBYTECODE=1 (repo .gitignore already excludes __pycache__/ and *.pyc; .dockerignore excludes them from the image).
  - rejected: MINOR — untested COBOL behaviour for negative accrual-day counts (LM-LAST-ACCR-DATE after the as-of date) — A last-accrual date after the as-of date is a data error no real batch contains, and what the COBOL would emit (a negative WS-ACCR-DAYS moved into unsigned LO-ACCR-DAYS 9(3), a negative ROUNDED accrual) is not spelled ou
  - rejected: MINOR — 1300-LOAD-TRANSACTIONS ignores unknown TR-TYPE and 1100-LOAD-HOLIDAYS skips non-numeric lines; the port raises ValueError and this is untested — The instruction scopes parity to 'other batches with the same layouts'; malformed records are outside that scope, both fixtures are well-formed, and a port that rejects an invalid TR-TYPE is a defensible engineering choi
  - rejected: MINOR — reference solve.sh changes 214 lines but the intrinsic minimal fix is ~44 lines — Reviewers themselves state no change is required and that the extra lines are legitimate hardening, not padding; the LOC criterion is measured from solve.sh (now 213 lines across 9 files) and the ablation shows every one
  - rejected: MINOR — Dockerfile FROM should be patch- or digest-pinned (python:3.11.14-slim or @sha256) — The sandbox mandates `FROM python:3.11-slim` exactly (a locally mirrored CA-trusting image is tagged with that name); a digest or patch tag would not resolve here and the authoring guide's Dockerfile pattern uses the pla
  - rejected: MINOR — validator saves only the last 6000 bytes of the pre-apply log, so the artifact lacks the 'collected 28 items' header — This is a limitation of scripts/validate_task.py, which I am not permitted to modify; the reviewer confirmed collection by re-running test.sh in the kept image, and the fresh run's log ends with '23 failed, 6 passed' (pr

## recon-nightly-timeout-2291

- Build report: validator passed = True, tests = 27, pre-apply failing = 17, lines changed = 826 across 15 files.
- Known weaknesses recorded by the implementer:
  - Per-row connect+commit persistence alone (with every other cause fixed) completes in 9.6 s, so a solution that keeps per-row commits still passes; this is consistent with the instruction's 60 s contract but means that one of the design's five 'each cause alone blows the budget' claims does not hold (customer-master reload alone is 144 s, i.e. 2.4x rather than the intended 3x).
  - The wall-clock assertions (60 s full run, 60 s alt run) remain host-dependent; headroom is ~50x on this host under load, and the SQL-statement budget is the hardware-independent backstop, but very slow verifier hosts are not tested.
  - The SQL-statement counter relies on PYTHONPATH injection into the CLI subprocess; a solution that re-execs Python with a scrubbed environment would be counted as 0 statements and pass the budget test trivially (the timing and correctness tests still apply).
  - The profile ships as a 25-line profiled reproduction (file name kept as recon_sample200.cprofile.txt, header and ticket explain the slice); the design described a 200-line profile.
  - The changed-line count (826) includes CHANGES.md (~57 lines); code-only changes are ~770 lines across 14 files, still far above the 100-line criterion.
  - Fixture generator's oracle is validated against the legacy engine on the 200-line sample and the 25-line slice only; full 12,000-line legacy validation is impractical (~19 h).
- Review passes: 6; fix rounds: 1.

| review pass | verdict | blocker | major | minor | alternative solution vs hidden tests |
|---|---|---|---|---|---|
| LEAKAGE AND OVERFIT | accept | 0 | 0 | 4 | 27 passed / 0 failed |
| INDEPENDENT ALTERNATIVE SOLUTION | accept | 0 | 0 | 4 | 27 passed / 0 failed |
| LINE-BY-LINE ACCEPTANCE COMPLIANCE | accept | 0 | 0 | 4 | n/a |
| DIFFICULTY, ROOT-CAUSE DEPTH, REALISM, DETERMINISM | accept | 0 | 0 | 5 | 27 passed / 0 failed |
| independent-alternative-solution | accept | 0 | 0 | 4 | 30 passed / 0 failed |
| LEAKAGE AND OVERFIT | fix-needed | 0 | 2 | 4 | 30 passed / 0 failed (overfit flagged) |

Blocker/major findings and their resolution:
- **[major] tests** (LEAKAGE AND OVERFIT): The hidden suite assumes the shipped ledger /app/data/recon.db is still pristine (never reconciled) when the tests run: conftest.fresh_db() copies DATA/recon.db for every run fixture, and test_db_invoice_status_reflects_matches / _pick_invoice read it as the 'before' state. Nothing in instruction.md tells the agent to leave data/recon.db untouched or to rebuild it before finishing; on the contrary
- **[major] tests** (LEAKAGE AND OVERFIT): test_lookup_accepts_any_formatting_variant and test_lookup_unknown_reference_exits_1 run `lookup` directly on a fresh copy of the schema-v1 ledger with no prior `run`/`migrate`. The instruction (item 4) and README only promise that `run` (or `migrate`) upgrades the ledger automatically; neither says `lookup` must self-migrate. A spec-conforming design in which `lookup` is a read-only finance-desk 

Fix round 1: validator passed = True; 12 fixes applied, 5 findings rejected with reasons; remaining blockers: none.
  - applied: [Leakage minor] lookup stdout on a miss: environment/app/README.md now states under `lookup` that stdout carries only invoice lines, stays empty on a miss, the diagnostic goes to stderr and the exit code is 1 (test_lookup_unknown_reference_exits_1 is now backed by the contract).
  - applied: [Leakage minor] match_results retention across re-runs: environment/app/README.md persistence contract now states `match_results` is append-only (run never deletes/rewrites rows from earlier runs) and that a re-run's matches are appended; the exact-count assertions in test_rerun_on_reconciled_ledger
  - applied: [Alt-solution minor, grounding] docs/matching_rules.md B3 worked example was self-contradictory (payment 400.00 claimed 'no run' although [0..2]=120+80+200=400 within 30 days is a run). Rewrote the bullets: 400.00 -> run [0..2] ([2..4] also sums to 400 but spans 74 days); 320.00 -> genuinely no run 
  - applied: [Alt-solution minor] CHANGES.md untested: added test_changes_md_names_the_work_done (file exists at /app/CHANGES.md, >=200 chars, mentions B3/batch and the ledger access in some form); instruction.md item 6 now names the location `/app/CHANGES.md`.
  - applied: [Alt-solution minor] v1->v2 upgrade path untested when the agent rebuilds data/recon.db: added tests/fixtures/schema_v1.sql (baseline DDL) and test_v1_ledger_is_upgraded_automatically_by_run, which builds a genuine schema-v1 ledger from the CSV exports independently of the app, runs the sample on it
  - applied: [Alt-solution minor] stage logging untested: added test_pipeline_stages_are_logged asserting at least one `stage=<name> ... elapsed=<seconds>s` line on the full run's stderr (README contract, loose regex, no stage names required).
  - applied: [Difficulty minor] instruction.md no longer claims 'every one of them on its own is enough to blow the time budget' (false for per-row commits); now says 'more than one of them is on its own enough'. Added a one-sentence warning that the unfixed engine needs ~5-6 s per line so reproduction should us
  - applied: [Difficulty/Compliance minor] evidence-trail alignment: cProfile header timestamp changed from the task-build date (Mon Sep 7 02:16:24 2026, sample25.prof) to 'Tue Sep 1 10:33:47 2026 recon_sample.prof' matching the ticket timeline and the -o name in the header; INCIDENT-2291.md fin-batch-02 now '2 
  - applied: [Difficulty minor] task.toml [agent] timeout_sec raised 2700 -> 3600 to absorb an agent burning time on a slow reproduction.
  - applied: [All lenses minor] removed the stray tests/fixtures/__pycache__ (and any other __pycache__ under the task); repo .gitignore already ignores __pycache__/ and *.pyc.
  - applied: Task-root README.md (non-shipped metadata) updated: 30 tests, v1-ledger migration check, append-only match_results, stdout-empty lookup miss, stage lines, CHANGES.md check, agent timeout note.
  - applied: Re-ran the validator: PASS (pre-apply exit 1 / reward 0 / 20 failed 3 passed 7 errors of 30 collected; post-apply solve 0.7 s, 30/30 passed, reward 1, 12.3 s; loc_changed 826 across 15 files; image scan clean). Also verified on the host that the reference solution passes all 30 tests (8.3 s).
  - rejected: [Leakage minor] instruction and evidence documents are too prescriptive about the answer path (item 1 'loads or indexes up front', item 4 normalize_reference hi — The reviewer itself marks this 'acceptable as-is for an incident-remediation task' and the difficulty lens concluded 'no change required'. The evidence trail is the realism the acceptance criteria demand (ticket, hotfix 
  - rejected: [Difficulty minor] root-cause discovery is largely handed to the agent; consider removing the hot-function list from INCIDENT-2291.md item 4 if the baseline gap — Reviewer states 'No change required'; this is a calibration note contingent on baseline results that do not exist yet. Kept as-is (see previous rejection).
  - rejected: [Difficulty minor] optionally add a connection-count check (e.g. sql_connects <= 50) to make the single-connection design mandatory. — Not added: the instruction only forbids querying the ledger per candidate invoice and sets a statement budget; a connection cap would be a new requirement and would not prevent the per-row-commit pattern anyway (commits 
  - rejected: [Compliance minor] uncommitted modifications / no stable commit identifier; commit the validated state. — Committing is outside this task-owner round: the instructions say to commit only when asked, and the orchestration (which produced the earlier WIP commit) owns versioning. All changes are on disk under tasks/recon-nightl
  - rejected: [Compliance minor] the validator truncates the pre-apply log tail so the 'collected 27 items' header is missing. — Requires changing scripts/validate_task.py, which task owners must not modify; summary.json already records pre_apply.pytest.collected=30 (now) and the failed/passed/errors counts. No task change applies.

Fix round 2 (agent completed its edits and started the validator but was lost before reporting): the two major leakage findings were fixed on disk — the hidden suite now builds its own pristine schema-v1 ledger from `tests/fixtures/schema_v1.sql` plus the CSV exports instead of copying `/app/data/recon.db`, and `lookup` tests run `migrate` first; a connection budget, stage-logging and CHANGES.md requirements were added to both `instruction.md` and the tests. The orchestrator then re-validated the task and re-ran the reviewer's alternative solution (32/32 passed).
