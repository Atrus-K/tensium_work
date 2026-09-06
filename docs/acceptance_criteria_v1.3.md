# TB Data Acceptance Criteria V1.3 (redacted, English)

> Reference copy of the acceptance document this dataset is built against (converted from the supplied .docx). Use `docs/acceptance_checklist.md` for the criterion-to-evidence mapping.


## TB Data Acceptance Criteria


## Data Acceptance


### Basic Acceptance Criteria

- Confirm that the environment runs successfully and completes the tests, and provide the specific Docker image;
  - solve.sh must pass the tests (oracle&nop) and be consistent with the instruction.
- Tasks may be based on a real software-engineering repository and its context, or may be manually constructed by domain experts. The purpose of this requirement is to avoid purely synthetic tasks, such as tasks generated directly in bulk by a model.
  - ✅ May come from a public repository;
  - ✅ May come from real user feedback, a bug report, PR review, or release regression;
  - ✅ May be derived from internal engineering records, but must include the original evidence trail;
  - ✅ May be manually constructed by domain experts: build a real multi-file codebase specifically for each task and include structured metadata and a clear scoring design (unit tests/verification scripts);
  - ✅ Every task must require code tools (for example, pyOpenMS, pyensembl, or petsc4py);
  - ✅ The solution code for every task must interact with the environment or read multiple files (for example, FASTA files);
  - ❌ The task is merely an algorithm problem repackaged as an engineering task, or tests only factual domain knowledge.
- Consistency Between the Problem and Tests
  - Avoid tests that are too narrow or overfit to the reference solution. A patch that differs from the reference answer but is equally valid must pass. The problem statement and tests must remain aligned; the tests must not introduce extra requirements that make it nearly impossible for the model to generate a correct solution.
- Required data categories:
  - Operations: implementation of real business rules such as financial risk control, logistics scheduling, claims processing, and regulatory filings.
  - System debugging / production-incident remediation: identify and fix the root cause of real failures; production container orchestration.
  - Data / database migration and recovery: online switchover, WAL recovery, data masking, and graph queries.
  - Security hardening / reverse-engineering patches: vulnerability remediation, backdoor investigation, and reverse patches for formats/binaries.
  - Rewriting / cross-language migration: port a legacy language to a new language or change frameworks while implementing equivalent functionality.
  - Performance / algorithm optimization: improve latency, cycle count, solution quality, and similar metrics.
  - Coding for STEM: the scope is broad; the following are examples only: MS2 glycan-structure analysis, polymorph spectral fitting, framework topology, variant annotation + CRISPR design, GSEA, protein-feature inference, lake-temperature-profile LSTM, biped contact dynamics, inverse photonic design, radiation metrology, and Coq/Lean4 theorem proving.
- Data difficulty requirements:
  - Each task must require code changes across multiple files, and the implementation produced by the reference solution, solve.sh, must itself have corresponding scale and complexity. Lines of code changed are measured from the actual changes made by the reference solve.sh (this criterion is intended to ensure task difficulty). Specifically, across tasks in the dataset, the P25 (25th percentile) of lines of code changed must be > 100.
  - The dataset must be significantly challenging for qwen3.8 max while remaining solvable by C-17 or C-11, with a clear capability gap.
  - Metric definitions: both difficulty and gap thresholds are calculated using avg@8. avg@8 is the average score across 8 independent runs for each task (reward is 0 or 1 for each run). Solvability is calculated using pass@8 and requires at least 1 successful run out of 8 for every task. The capability gap is calculated per task as the difference between the two models' avg@8 values on the same task (C-17 or C-11 avg@8 − qwen3.8 max avg@8, denoted gap), and acceptance uses cumulative thresholds.
    - qwen3.8 max:
      - avg@8 ≤ 50% (passes at most half)
      - Of which:
        - At least 75% of tasks must have avg@8 ≥ 25%
        - At most 25% of tasks may have avg@8 = 0%
    - Fable 5 or Opus 5
      - pass@8 > 0 (solvability: every task must have at least 1 successful run out of 8)
    - C-17 or C-11 avg@8 − qwen3.8 max avg@8 (clear capability gap): acceptance is based on cumulative per-task gap thresholds:
    - 100% of tasks: gap ≥ 12.5%;
    - At least 20% of tasks: gap ≥ 25%;
    - Tasks with gap < 12.5% will not be accepted.
  - Language requirements:
    - Primary focus: Python

### Task Structure and Format Acceptance


Harbor dataset format is required.

Reference: https://www.harborframework.com/docs/tasks

At the dataset root, data must be organized by task, with each task in its own directory. Each task directory name must be unique and may contain only letters, numbers, underscores, hyphens, or periods. It must not contain spaces, Chinese characters, path separators, or shell special characters.

Each task directory must contain the following six files:
```
<task-dir>/
  instruction.md          # Task description
  task.toml               # Task configuration
  environment/
    Dockerfile            # Environment definition
  solution/
    solve.sh              # Reference solution
  tests/
    test.sh               # Evaluation script
```

instruction.md:
- The task objective must be clear and the agent must be able to complete it using the workspace contents.
- Must not depend on an external network, changing APIs, or highly time-sensitive information.
- Must not disclose test assertions, hidden test cases, the oracle solution, or the answer path.

task.toml:
- TOML syntax must parse successfully: python -c "import tomllib; tomllib.load(open('task.toml','rb'))"
- The image, timeout, CPU, memory, and disk fields must match the actual runtime environment.
- Resource fields such as timeout, CPU, memory, and disk must contain valid numeric values.
- Must not hard-code a real token/API key.

solution/solve.sh:
- Must pass the shell syntax check: bash -n solution/solve.sh
- bash solution/solve.sh must run directly without human intervention.
- Must not modify tests/test.sh or fabricate /logs/verifier/reward.txt

tests/test.sh:
- Must pass the shell syntax check: bash -n tests/test.sh
- Must execute real evaluation logic and must not hard-code the reward.
- Must write the result explicitly to /logs/verifier/reward.txt (write 1 on success and 0 on failure).
- The verifier log must not show anomalies such as no tests collected, pytest not run, or all tests skipped.

environment/Dockerfile:
- Must build successfully (docker build -f environment/Dockerfile .)
- Must not copy tests/, solution/, hidden answers, or verifier outputs directly into the image.
- If COPY . . is used, .dockerignore must exclude tests/ and solution/

### Oracle Pre- and Post-Apply State Validation


For each task, validate the pre-apply and post-apply states separately.

The pre-apply and post-apply checks must use separate clean environments so that post-apply artifacts cannot contaminate the pre-apply result.

##### Pre-Apply (run tests/test.sh directly; do not run solution/solve.sh)


| Check | Passing Criterion |
|---|---|
| tests/test.sh exit code | Non-zero |
| /logs/verifier/reward.txt | Exists, with content exactly 0 |
| Test-case outcome | At least one test case fails |


A pre-apply failure is required. If the initial state already passes the tests, the task cannot distinguish whether the agent actually completed the work and therefore fails acceptance.

##### Post-Apply (run solution/solve.sh first, then tests/test.sh)


| Check | Passing Criterion |
|---|---|
| solution/solve.sh exit code | Zero |
| solution/solve.sh execution time | Completes within the timeout defined in task.toml |
| tests/test.sh exit code | Zero |
| /logs/verifier/reward.txt | Exists, with content exactly 1 |
| Test-case outcome | All test cases pass |


Post-apply success is required. If the oracle solution cannot pass consistently, the task itself is unusable and fails acceptance.

##### Validation Commands

```
harbor run -p <task-dir> -a oracle   # Complete post-apply validation
harbor view jobs                     # View verifier logs, test output, and reward
```

For direct local validation, remove any old reward file first:
```
cd <task-dir>

rm -f /logs/verifier/reward.txt
bash tests/test.sh

rm -f /logs/verifier/reward.txt
bash solution/solve.sh
bash tests/test.sh
cat /logs/verifier/reward.txt
```

### Scaffold Baseline Validation


Use Harbor to perform end-to-end baseline validation of the dataset, confirming that the tasks can be executed normally through a standard agent workflow and that the overall difficulty lies within a range that distinguishes model capability.
- scaffold: mini-swe-agent or Claude Code. Claude Code is preferred.
- model: Fable 5/Opus 5 and qwen3.8 max.
- Execution requirements: All baseline models must be able to run the entire dataset. There must be no large-scale task interruptions caused by scaffold, container image, dependency, path, or verifier issues.
- Model execution: All baseline models (Fable 5, Opus 5, and qwen3.8 max) are run by the supplier; we do not provide API access. The specific model versions corresponding to Fable 5 and Opus5 will be confirmed separately.
- Exception handling: if the pass rate falls outside the expected range, sample both failed and passed cases to confirm that the cause is task difficulty rather than an environment, test, or data-leakage issue.

Key points for per-case review:
- Failed case: the failure must not be caused by environment startup failure, missing dependencies, an incorrect path, unreasonable timeout settings, or a verifier error.
- Failed case: the agent log must show a meaningful attempt; it must not be a systemic failure caused by missing task instructions, insufficient context, or an unavailable toolchain.
- Passed case: the pass must not be caused by tests that are too weak, a hard-coded reward, leaked answers, or residual oracle artifacts.
- Fluctuating case: repeated runs of the same task must not show large random fluctuations. If randomness exists, the seed must be fixed or the unavoidable cause must be explained.
- Boundary case: record the reason for tasks that are too easy, too hard, unexpectedly pass, or unexpectedly fail, then decide whether to retain, correct, or remove them.

### Final Acceptance Conclusion


After completing the steps above, provide the following information:
- Dataset name, number of tasks, and data version or commit identifier.
- Step 1 format-check result: Pass / Fail.
- Step 2 oracle-validation result: number of pre-apply failures, number of post-apply successes, and list of anomalous tasks.
- Step 3 scaffold pass rate: model, avg@8, pass@8 (solvability), and explanation of anomalous cases.
- Final conclusion: Pass / Fail, and reasons for failure.
