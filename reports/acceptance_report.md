# Final acceptance conclusion

- **Dataset name:** tensium/tb-acceptance-v1
- **Number of tasks:** 4
- **Data version / commit:** 1.0.0 / 8511b5d

## Step 1: format check

**Result: Pass**

Checked per task: directory name charset, six required files, task.toml parses (tomllib and Harbor's TaskConfig schema) with numeric cpu/memory/disk/timeouts and no tokens, `bash -n` on solve.sh and test.sh, test.sh writes reward 1/0 conditionally and runs pytest, solve.sh does not touch the verifier, instruction.md does not leak tests/solution or depend on URLs, Dockerfile builds from both build contexts and copies neither tests/ nor solution/ (.dockerignore enforced), image scanned for leaked hidden files.

## Step 2: oracle validation (separate clean containers for pre- and post-apply)

- Pre-apply failures (required): **4 / 4**
- Post-apply successes (required): **4 / 4**
- Anomalous tasks: **none**
- Lines changed by solve.sh per task: [213, 426, 447, 826]; P25 = 372.75 (criterion > 100: Pass)

| task | pre exit | pre reward | pre failed tests | post exit | post reward | post passed tests | LOC changed | files changed | solve.sh s | harbor nop | harbor oracle |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bundlevault-pentest-remediation | 1 | 0 | 53 | 0 | 1 | 74 | 426 | 10 | 0.1 | 0 | 1 |
| claims-adjudication-audit-recalc | 1 | 0 | 50 | 0 | 1 | 65 | 447 | 10 | 0.3 | 0 | 1 |
| cobol-loan-accrual-port-parity | 1 | 0 | 23 | 0 | 1 | 29 | 213 | 9 | 0.3 | 0 | 1 |
| recon-nightly-timeout-2291 | 1 | 0 | 21 | 0 | 1 | 32 | 826 | 15 | 0.7 | 0 | 1 |

## Step 3: scaffold baseline (avg@8 / pass@8)

Not executed in this environment: the acceptance document requires the supplier to run Claude Code (preferred) or mini-swe-agent with Fable 5 / Opus 5 and qwen3.8 max for 8 attempts per task. No model API access was available here. Run, for example:

```bash
harbor run -p tasks -a claude-code -m <model> -k 8 -n 4 -o reports/baselines/<model>
```

then compute avg@8, pass@8 and per-task gaps from the result.json files and review failed/passed/fluctuating cases per the document's checklist.

## Final conclusion

**Steps 1-2: Pass.** Step 3 pending supplier baseline runs.
