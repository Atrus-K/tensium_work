#!/usr/bin/env python3
"""Produce the "Final Acceptance Conclusion" section required by TB Data
Acceptance Criteria V1.3 from the artifacts written by scripts/validate_task.py
and scripts/harbor_validate.sh.

Usage: python3 scripts/report_acceptance.py [--validation reports/validation/summary.json]
                                           [--harbor-jobs reports/harbor-jobs]
                                           [--dataset dataset.toml] [--out reports/acceptance_report.md]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "uncommitted"


def harbor_rewards(jobs_dir: Path) -> dict[str, dict[str, str]]:
    """{task: {'nop': '0', 'oracle': '1'}} from harbor job directories."""
    out: dict[str, dict[str, str]] = {}
    for reward_file in glob.glob(str(jobs_dir / "*" / "*" / "*" / "verifier" / "reward.txt")):
        parts = Path(reward_file).parts
        run_name = parts[-5]  # <task>.<agent>
        m = re.match(r"(.+)\.(nop|oracle)$", run_name)
        if not m:
            continue
        out.setdefault(m.group(1), {})[m.group(2)] = Path(reward_file).read_text().strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validation", default="reports/validation/summary.json")
    ap.add_argument("--harbor-jobs", default="reports/harbor-jobs")
    ap.add_argument("--dataset", default="dataset.toml")
    ap.add_argument("--out", default="reports/acceptance_report.md")
    a = ap.parse_args()

    summary = json.loads(Path(a.validation).read_text())
    ds = tomllib.loads(Path(a.dataset).read_text()).get("dataset", {})
    harbor = harbor_rewards(Path(a.harbor_jobs))

    tasks = summary["tasks"]
    format_fail = [t["task"] for t in tasks if any((not c["passed"]) and not c["name"].startswith(("pre-apply", "post-apply", "docker-build", "image-has")) for c in t["checks"])]
    pre_ok = [t["task"] for t in tasks if t["pre_apply"] and t["pre_apply"].get("reward") == "0" and t["pre_apply"].get("exit_code") != 0 and (t["pre_apply"].get("pytest", {}).get("failed", 0) + t["pre_apply"].get("pytest", {}).get("errors", 0)) >= 1]
    post_ok = [t["task"] for t in tasks if t["post_apply"] and t["post_apply"].get("reward") == "1" and t["post_apply"].get("exit_code") == 0 and t["post_apply"].get("pytest", {}).get("failed", 0) == 0]
    anomalous = [t["task"] for t in tasks if not t["passed"]]
    locs = sorted(t["loc_changed"] for t in tasks if t["loc_changed"] is not None)
    p25 = summary.get("loc_changed_p25")

    lines = [
        "# Final acceptance conclusion",
        "",
        f"- **Dataset name:** {ds.get('name', 'n/a')}",
        f"- **Number of tasks:** {len(tasks)}",
        f"- **Data version / commit:** {ds.get('version', 'n/a')} / {git_rev()}",
        "",
        "## Step 1: format check",
        "",
        f"**Result: {'Pass' if not format_fail else 'Fail'}**" + (f" (failures: {', '.join(format_fail)})" if format_fail else ""),
        "",
        "Checked per task: directory name charset, six required files, task.toml parses (tomllib and Harbor's TaskConfig schema) with numeric cpu/memory/disk/timeouts and no tokens, `bash -n` on solve.sh and test.sh, test.sh writes reward 1/0 conditionally and runs pytest, solve.sh does not touch the verifier, instruction.md does not leak tests/solution or depend on URLs, Dockerfile builds from both build contexts and copies neither tests/ nor solution/ (.dockerignore enforced), image scanned for leaked hidden files.",
        "",
        "## Step 2: oracle validation (separate clean containers for pre- and post-apply)",
        "",
        f"- Pre-apply failures (required): **{len(pre_ok)} / {len(tasks)}**",
        f"- Post-apply successes (required): **{len(post_ok)} / {len(tasks)}**",
        f"- Anomalous tasks: **{', '.join(anomalous) if anomalous else 'none'}**",
        f"- Lines changed by solve.sh per task: {locs}; P25 = {p25} (criterion > 100: {'Pass' if (p25 or 0) > 100 else 'Fail'})",
        "",
        "| task | pre exit | pre reward | pre failed tests | post exit | post reward | post passed tests | LOC changed | files changed | solve.sh s | harbor nop | harbor oracle |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in tasks:
        pre, post = t["pre_apply"] or {}, t["post_apply"] or {}
        h = harbor.get(t["task"], {})
        lines.append(
            f"| {t['task']} | {pre.get('exit_code')} | {pre.get('reward')} | {pre.get('pytest', {}).get('failed')} | {post.get('exit_code')} | {post.get('reward')} | "
            f"{post.get('pytest', {}).get('passed')} | {t['loc_changed']} | {t['files_changed']} | {t['solve_seconds']} | {h.get('nop', 'not run')} | {h.get('oracle', 'not run')} |"
        )
    lines += [
        "",
        "## Step 3: scaffold baseline (avg@8 / pass@8)",
        "",
        "Not executed in this environment: the acceptance document requires the supplier to run Claude Code (preferred) or mini-swe-agent with Fable 5 / Opus 5 and qwen3.8 max for 8 attempts per task. No model API access was available here. Run, for example:",
        "",
        "```bash",
        "harbor run -p tasks -a claude-code -m <model> -k 8 -n 4 -o reports/baselines/<model>",
        "```",
        "",
        "then compute avg@8, pass@8 and per-task gaps from the result.json files and review failed/passed/fluctuating cases per the document's checklist.",
        "",
        "## Final conclusion",
        "",
        f"**Steps 1-2: {'Pass' if (not format_fail and not anomalous and (p25 or 0) > 100) else 'Fail'}.** Step 3 pending supplier baseline runs.",
    ]
    if format_fail or anomalous:
        lines.append("Reasons: " + "; ".join(sorted(set(format_fail + anomalous))))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
