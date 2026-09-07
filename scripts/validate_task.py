#!/usr/bin/env python3
"""Acceptance validator for Harbor-format tasks.

Implements the checks from "TB Data Acceptance Criteria V1.3":

  1. Task structure / format checks (directory name, six required files,
     task.toml parses with numeric resource fields, bash -n on scripts,
     Dockerfile does not copy tests/ or solution/, .dockerignore present when
     `COPY . .` is used, no hard-coded reward, no leaked test paths in
     instruction.md, no hard-coded API keys).
  2. Oracle pre-apply validation in a CLEAN container: run tests/test.sh only.
     Expect non-zero exit, /logs/verifier/reward.txt == "0", >= 1 failing test.
  3. Oracle post-apply validation in a SEPARATE clean container: run
     solution/solve.sh (within the task.toml agent timeout), then tests/test.sh.
     Expect exit 0, reward.txt == "1", all tests pass, tests were collected.
  4. Measures lines of code changed by solve.sh inside /app (added + removed
     lines, text files only) and the number of files changed, and reports the
     dataset P25 of changed lines (criterion: P25 > 100).
  5. Scans the built image for leaked tests/, solution/ or verifier artifacts.

Usage:
  python3 scripts/validate_task.py [--tasks-dir tasks] [--task NAME ...]
      [--report-dir reports] [--build-flag FLAG ...] [--skip-docker] [--keep-images]

  --build-flag is passed verbatim to `docker build` (repeatable); e.g. in a
  sandbox that only reaches PyPI through a local proxy:
      --build-flag=--network=host --build-flag=--build-arg=HTTPS_PROXY=http://127.0.0.1:34087

Exit status is 0 only when every selected task passes every check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

REQUIRED_FILES = [
    "instruction.md",
    "task.toml",
    "environment/Dockerfile",
    "solution/solve.sh",
    "tests/test.sh",
]
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|"
    r"github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AIza[0-9A-Za-z_-]{30,})"
)
PYTEST_SUMMARY_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class TaskReport:
    task: str
    checks: list[Check] = field(default_factory=list)
    image: str = ""
    pre_apply: dict = field(default_factory=dict)
    post_apply: dict = field(default_factory=dict)
    loc_changed: int | None = None
    files_changed: int | None = None
    solve_seconds: float | None = None

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(name, bool(passed), detail))


def sh(cmd: list[str], timeout: float | None = None, check: bool = False, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check, input=input_text)


def parse_pytest_counts(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    # Use the last summary line that pytest prints (== N passed, M failed in Xs ==)
    for line in output.splitlines():
        if re.search(r"^=+ .*(passed|failed|error|no tests ran).* =+\s*$", line):
            counts = {}
            for n, kind in PYTEST_SUMMARY_RE.findall(line):
                kind = {"error": "errors", "warning": "warnings"}.get(kind, kind)
                counts[kind] = counts.get(kind, 0) + int(n)
            if "no tests ran" in line:
                counts["no_tests_ran"] = 1
    m = re.search(r"collected (\d+) items?", output)
    if m:
        counts["collected"] = int(m.group(1))
    return counts


# --------------------------------------------------------------------------- #
# Format checks
# --------------------------------------------------------------------------- #

def format_checks(task_dir: Path, rep: TaskReport) -> dict:
    name = task_dir.name
    rep.add("dir-name-charset", bool(NAME_RE.match(name)), name)

    for rel in REQUIRED_FILES:
        rep.add(f"file-present:{rel}", (task_dir / rel).is_file(), rel)

    cfg: dict = {}
    toml_path = task_dir / "task.toml"
    if toml_path.is_file():
        try:
            cfg = tomllib.loads(toml_path.read_text())
            rep.add("toml-parses", True)
        except Exception as e:  # noqa: BLE001
            rep.add("toml-parses", False, str(e))
        env = cfg.get("environment", {}) if isinstance(cfg, dict) else {}
        for key in ("cpus", "memory_mb", "storage_mb", "build_timeout_sec"):
            v = env.get(key)
            rep.add(f"toml-numeric:environment.{key}", isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0, repr(v))
        for section in ("verifier", "agent"):
            v = cfg.get(section, {}).get("timeout_sec")
            rep.add(f"toml-numeric:{section}.timeout_sec", isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0, repr(v))
        rep.add("toml-no-secrets", not SECRET_RE.search(toml_path.read_text()))

    # optional: validate with the real Harbor schema when a harbor python is available
    harbor_py = harbor_python()
    if harbor_py and cfg:
        code = (
            "import sys, tomllib\n"
            "from harbor.models.task.config import TaskConfig\n"
            "TaskConfig.model_validate(tomllib.load(open(sys.argv[1],'rb')))\n"
            "print('ok')\n"
        )
        r = sh([harbor_py, "-c", code, str(toml_path)], timeout=120)
        rep.add("toml-harbor-schema", r.returncode == 0 and "ok" in r.stdout, (r.stderr or r.stdout).strip()[-400:])

    for rel in ("solution/solve.sh", "tests/test.sh"):
        p = task_dir / rel
        if p.is_file():
            r = sh(["bash", "-n", str(p)])
            rep.add(f"bash-n:{rel}", r.returncode == 0, r.stderr.strip()[-300:])

    test_sh = task_dir / "tests" / "test.sh"
    if test_sh.is_file():
        t = test_sh.read_text()
        rep.add("test.sh-writes-reward", "/logs/verifier/reward.txt" in t)
        writes_one = re.search(r"echo\s+1\s*>\s*\S*reward\.txt", t) is not None or "reward.txt" in t
        writes_zero = re.search(r"echo\s+0\s*>\s*\S*reward\.txt", t) is not None or re.search(r"REWARD|reward=", t) is not None
        rep.add("test.sh-reward-not-hardcoded", writes_one and writes_zero, "must write 1 on success and 0 on failure conditionally")
        rep.add("test.sh-runs-real-tests", re.search(r"pytest|unittest|python[3]?\s+-m", t) is not None)

    solve_sh = task_dir / "solution" / "solve.sh"
    if solve_sh.is_file():
        s = solve_sh.read_text()
        rep.add("solve.sh-does-not-touch-verifier", not re.search(r"/tests/|test\.sh|/logs/verifier|reward\.txt", s))

    instr = task_dir / "instruction.md"
    if instr.is_file():
        text = instr.read_text()
        rep.add("instruction-nonempty", len(text.strip()) > 200, f"{len(text)} chars")
        leaks = [w for w in ("/tests", "test.sh", "solve.sh", "reward.txt", "/solution") if w in text]
        test_files = [p.name for p in (task_dir / "tests").glob("*.py")] if (task_dir / "tests").is_dir() else []
        leaks += [f for f in test_files if f in text]
        rep.add("instruction-no-verifier-leak", not leaks, ", ".join(leaks))
        urls = re.findall(r"https?://\S+", text)
        rep.add("instruction-no-network-deps", not urls, f"urls: {urls[:3]}")

    # leakage: verifier paths / hidden-test names must not appear in anything the agent can see
    app_dir = task_dir / "environment"
    visible_files = [p for p in list(app_dir.rglob("*")) + [task_dir / "instruction.md"] if p.is_file() and p.suffix.lower() not in (".db", ".dat", ".bin", ".fwb", ".sqlite", ".png", ".gz", ".zip", ".pyc")]
    verifier_re = re.compile(r"(/tests\b|tests/test_|\btest\.sh\b|\bsolve\.sh\b|reward\.txt|/logs/verifier|hidden tests?\b)", re.I)
    hits = []
    for p in visible_files:
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for m in verifier_re.finditer(text):
            hits.append(f"{p.relative_to(task_dir)}: {m.group(0)}")
            break
    rep.add("workspace-no-verifier-references", not hits, "; ".join(hits[:5]))
    hidden_names = set()
    app_names = {p.name for p in app_dir.rglob("*") if p.is_file()}
    for sub in ("tests", "solution"):
        for p in (task_dir / sub).rglob("*"):
            if p.is_file() and p.name not in app_names and p.name not in ("test.sh", "solve.sh", "conftest.py", "__init__.py") and len(p.stem) >= 6:
                hidden_names.add(p.stem)
    name_hits = []
    if hidden_names:
        name_re = re.compile(r"\b(" + "|".join(sorted(re.escape(n) for n in hidden_names)) + r")\b")
        for p in visible_files:
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            m = name_re.search(text)
            if m:
                name_hits.append(f"{p.relative_to(task_dir)}: {m.group(0)}")
    rep.add("workspace-no-hidden-fixture-names", not name_hits, "; ".join(name_hits[:5]))

    dockerfile = task_dir / "environment" / "Dockerfile"
    if dockerfile.is_file():
        d = dockerfile.read_text()
        bad = [ln for ln in d.splitlines() if re.match(r"\s*(COPY|ADD)\s", ln) and re.search(r"(^|\s|/)(tests|solution)(/|\s)", ln)]
        rep.add("dockerfile-no-tests-solution-copy", not bad, "; ".join(bad))
        copies_all = any(re.match(r"\s*(COPY|ADD)\s+(--\S+\s+)*\.\s", ln + " ") or re.match(r"\s*(COPY|ADD)\s+(--\S+\s+)*\./?\s", ln) for ln in d.splitlines())
        if copies_all:
            di = task_dir / ".dockerignore"
            ok = False
            if di.is_file():
                lines = [ln.strip() for ln in di.read_text().splitlines()]
                ok = any(ln.rstrip("/") in ("tests", "**/tests") for ln in lines) and any(ln.rstrip("/") in ("solution", "**/solution") for ln in lines)
            rep.add("dockerignore-excludes-tests-solution", ok, "COPY . used; .dockerignore must list tests/ and solution/")
    return cfg


def harbor_python() -> str | None:
    cands = [
        Path.home() / ".local/share/uv/tools/harbor/bin/python",
        Path("/root/.local/share/uv/tools/harbor/bin/python"),
    ]
    for c in cands:
        if c.exists():
            return str(c)
    return None


# --------------------------------------------------------------------------- #
# Docker helpers
# --------------------------------------------------------------------------- #

class Container:
    def __init__(self, image: str, cpus: float | None, memory_mb: int | None, workdir: str = "/app"):
        self.name = f"tbval-{uuid.uuid4().hex[:10]}"
        cmd = ["docker", "run", "-d", "--name", self.name, "-w", workdir]
        if cpus:
            cmd += ["--cpus", str(cpus)]
        if memory_mb:
            cmd += ["--memory", f"{int(memory_mb)}m"]
        cmd += [image, "sleep", "infinity"]
        sh(cmd, check=True, timeout=120)

    def exec(self, command: str, timeout: float | None = None, workdir: str = "/app") -> tuple[int, str, float]:
        t0 = time.time()
        try:
            r = sh(["docker", "exec", "-w", workdir, self.name, "bash", "-lc", command], timeout=timeout)
            return r.returncode, r.stdout + r.stderr, time.time() - t0
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or "") if isinstance(e.stdout, str) else ""
            return 124, out + f"\n[validator] TIMEOUT after {timeout}s", time.time() - t0

    def cp_in(self, src: Path, dst: str) -> None:
        sh(["docker", "exec", self.name, "mkdir", "-p", dst], check=True)
        sh(["docker", "cp", f"{src}/.", f"{self.name}:{dst}"], check=True, timeout=120)

    def read(self, path: str) -> str | None:
        r = sh(["docker", "exec", self.name, "cat", path])
        return r.stdout if r.returncode == 0 else None

    def close(self) -> None:
        sh(["docker", "rm", "-f", self.name])


def build_image(task_dir: Path, tag: str, build_flags: list[str], context: str, log_path: Path) -> tuple[bool, str]:
    ctx = str(task_dir) if context == "root" else str(task_dir / "environment")
    cmd = ["docker", "build", "-f", str(task_dir / "environment" / "Dockerfile"), "-t", tag, *build_flags, ctx]
    t0 = time.time()
    r = sh(cmd, timeout=3600)
    log_path.write_text(" ".join(shlex.quote(c) for c in cmd) + "\n\n" + r.stdout + r.stderr)
    return r.returncode == 0, f"{time.time() - t0:.0f}s; log: {log_path}"


def run_test_sh(c: Container, tests_dir: Path, timeout: float) -> dict:
    c.exec("mkdir -p /logs/verifier && rm -f /logs/verifier/reward.txt")
    c.cp_in(tests_dir, "/tests")
    code, out, secs = c.exec("chmod +x /tests/test.sh; bash /tests/test.sh", timeout=timeout)
    reward = c.read("/logs/verifier/reward.txt")
    return {
        "exit_code": code,
        "seconds": round(secs, 1),
        "reward": reward.strip() if reward is not None else None,
        "pytest": parse_pytest_counts(out),
        "output_tail": out[-6000:],
    }


def stray_files_scan(image: str, task_dir: Path) -> tuple[bool, str]:
    """Files outside /app that the base image does not have (build leftovers, verifier dirs, caches)."""
    base = None
    for ln in (task_dir / "environment" / "Dockerfile").read_text().splitlines():
        if ln.strip().upper().startswith("FROM "):
            base = ln.split()[1]
            break
    find_cmd = ("find / -xdev \\( -path /proc -o -path /sys -o -path /dev -o -path /app -o -path /usr -o -path /etc -o -path /var/lib -o -path /var/cache -o -path /var/log -o -path /bin -o -path /sbin -o -path /lib -o -path /lib64 \\) -prune -o -type f -print 2>/dev/null")
    r = sh(["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", find_cmd], timeout=600)
    files = {ln for ln in r.stdout.splitlines() if ln.startswith("/") and ln != "/.dockerenv"}
    if base:
        rb = sh(["docker", "run", "--rm", "--entrypoint", "sh", base, "-c", find_cmd], timeout=600)
        if rb.returncode == 0:
            files -= {ln for ln in rb.stdout.splitlines()}
    return not files, ("stray files: " + ", ".join(sorted(files)[:6])) if files else ""


def leak_scan(image: str, task_dir: Path) -> tuple[bool, str]:
    """Look for tests/solution/verifier artifacts baked into the image."""
    find_cmd = (
        "find / -xdev \\( -path /proc -o -path /sys -o -path /usr/lib -o -path /usr/local/lib -o -path /usr/share -o -path /root/.cache \\) -prune -o "
        "-type f \\( -path '/tests/*' -o -path '/solution/*' -o -path '/logs/*' -o -name 'test.sh' -o -name 'solve.sh' -o -name 'reward.txt' \\) -print 2>/dev/null; "
        "cd /app 2>/dev/null && find . -type f -not -path '*/__pycache__/*' -exec sha256sum {} + 2>/dev/null"
    )
    r = sh(["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", find_cmd], timeout=600)
    suspicious = [ln for ln in r.stdout.splitlines() if ln.startswith("/")]
    image_hashes = {ln.split()[0] for ln in r.stdout.splitlines() if re.match(r"^[0-9a-f]{64} ", ln)}
    hidden_hashes = {}
    for sub in ("tests", "solution"):
        for p in (task_dir / sub).rglob("*"):
            if p.is_file():
                hidden_hashes[hashlib.sha256(p.read_bytes()).hexdigest()] = str(p.relative_to(task_dir))
    dup = sorted(v for k, v in hidden_hashes.items() if k in image_hashes)
    ok = not suspicious and not dup
    return ok, (("paths: " + ", ".join(suspicious[:5])) if suspicious else "") + (("; identical hidden files in /app: " + ", ".join(dup)) if dup else "")


# --------------------------------------------------------------------------- #
# Oracle validation
# --------------------------------------------------------------------------- #

def validate_task(task_dir: Path, report_dir: Path, build_flags: list[str], skip_docker: bool, keep_images: bool) -> TaskReport:
    rep = TaskReport(task=task_dir.name)
    cfg = format_checks(task_dir, rep)
    if skip_docker or not rep.ok:
        if not rep.ok:
            rep.add("docker-skipped-due-to-format-failures", False)
        return rep

    env = cfg.get("environment", {})
    cpus = env.get("cpus")
    memory_mb = env.get("memory_mb")
    verifier_timeout = float(cfg.get("verifier", {}).get("timeout_sec", 600))
    agent_timeout = float(cfg.get("agent", {}).get("timeout_sec", 1800))

    tag = f"tbval/{task_dir.name.lower()}:validate"
    ok, detail = build_image(task_dir, tag, build_flags, "root", report_dir / f"{task_dir.name}.build-root.log")
    rep.add("docker-build(task-root-context)", ok, detail)
    if not ok:
        return rep
    rep.image = tag
    ok_env, detail_env = build_image(task_dir, tag + "-envctx", build_flags, "environment", report_dir / f"{task_dir.name}.build-env.log")
    rep.add("docker-build(environment-context, as Harbor builds it)", ok_env, detail_env)

    ok, detail = leak_scan(tag, task_dir)
    rep.add("image-has-no-tests-or-solution", ok, detail)
    ok, detail = stray_files_scan(tag, task_dir)
    rep.add("image-no-stray-files-outside-app", ok, detail)

    # ---- pre-apply: fresh container, tests only ----
    c = Container(tag, cpus, memory_mb)
    try:
        pre = run_test_sh(c, task_dir / "tests", verifier_timeout)
    finally:
        c.close()
    rep.pre_apply = pre
    (report_dir / f"{task_dir.name}.pre-apply.log").write_text(pre["output_tail"])
    rep.add("pre-apply:test.sh-exit-nonzero", pre["exit_code"] != 0, str(pre["exit_code"]))
    rep.add("pre-apply:reward==0", pre["reward"] == "0", repr(pre["reward"]))
    pc = pre["pytest"]
    rep.add("pre-apply:at-least-one-test-fails", (pc.get("failed", 0) + pc.get("errors", 0)) >= 1, json.dumps(pc))
    rep.add("pre-apply:tests-collected", pc.get("collected", 0) > 0 and not pc.get("no_tests_ran"), json.dumps(pc))

    # ---- post-apply: separate fresh container ----
    c = Container(tag, cpus, memory_mb)
    try:
        c.exec("mkdir -p /logs/verifier && cp -a /app /tmp/.app_before")
        c.cp_in(task_dir / "solution", "/solution")
        code, out, secs = c.exec("chmod +x /solution/solve.sh; bash /solution/solve.sh", timeout=agent_timeout)
        (report_dir / f"{task_dir.name}.solve.log").write_text(out[-20000:])
        rep.solve_seconds = round(secs, 1)
        rep.add("post-apply:solve.sh-exit-zero", code == 0, f"exit={code} in {secs:.0f}s")
        rep.add("post-apply:solve.sh-within-agent-timeout", secs < agent_timeout, f"{secs:.0f}s < {agent_timeout:.0f}s")
        fabricated = c.read("/logs/verifier/reward.txt")
        rep.add("post-apply:solve.sh-did-not-write-reward", fabricated is None, repr(fabricated))
        # LOC changed inside /app (text diff, added+removed), excluding caches
        _, diff_out, _ = c.exec(
            "diff -rN -x __pycache__ -x '*.pyc' -x .pytest_cache -x '*.egg-info' /tmp/.app_before /app | grep -cE '^[<>]' ; "
            "echo ---; diff -rqN -x __pycache__ -x '*.pyc' -x .pytest_cache -x '*.egg-info' /tmp/.app_before /app | wc -l; echo ---; "
            "diff -rqN -x __pycache__ -x '*.pyc' -x .pytest_cache -x '*.egg-info' /tmp/.app_before /app | sed 's#/tmp/.app_before/##; s#/app/##' | head -60"
        )
        parts = diff_out.split("---")
        try:
            rep.loc_changed = int(parts[0].strip().splitlines()[-1])
            rep.files_changed = int(parts[1].strip().splitlines()[-1])
        except (ValueError, IndexError):
            rep.loc_changed, rep.files_changed = None, None
        (report_dir / f"{task_dir.name}.changed-files.txt").write_text(parts[2].strip() if len(parts) > 2 else diff_out)
        rep.add("post-apply:changes-span-multiple-files", (rep.files_changed or 0) >= 3, f"files_changed={rep.files_changed}")
        rep.add("post-apply:loc-changed>100", (rep.loc_changed or 0) > 100, f"loc_changed={rep.loc_changed}")
        c.exec("rm -rf /tmp/.app_before")
        post = run_test_sh(c, task_dir / "tests", verifier_timeout)
    finally:
        c.close()
    rep.post_apply = post
    (report_dir / f"{task_dir.name}.post-apply.log").write_text(post["output_tail"])
    rep.add("post-apply:test.sh-exit-zero", post["exit_code"] == 0, str(post["exit_code"]))
    rep.add("post-apply:reward==1", post["reward"] == "1", repr(post["reward"]))
    pc = post["pytest"]
    rep.add("post-apply:all-tests-pass", pc.get("failed", 0) == 0 and pc.get("errors", 0) == 0 and pc.get("passed", 0) >= 1, json.dumps(pc))
    rep.add("post-apply:tests-collected-not-all-skipped", pc.get("collected", 0) > 0 and pc.get("passed", 0) >= 1, json.dumps(pc))
    rep.add("post-apply:test.sh-within-verifier-timeout", post["seconds"] < verifier_timeout, f"{post['seconds']}s")

    if not keep_images:
        sh(["docker", "rmi", "-f", tag + "-envctx"])
    return rep


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q
    f, c = int(k), min(int(k) + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks-dir", default="tasks")
    ap.add_argument("--task", action="append", default=None, help="task directory name (repeatable); default: all")
    ap.add_argument("--report-dir", default="reports/validation")
    ap.add_argument("--build-flag", action="append", default=[], help="extra flag passed verbatim to docker build (repeatable)")
    ap.add_argument("--skip-docker", action="store_true", help="format checks only")
    ap.add_argument("--keep-images", action="store_true")
    args = ap.parse_args()

    tasks_dir = Path(args.tasks_dir)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    names = args.task or sorted(p.name for p in tasks_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
    reports: list[TaskReport] = []
    for name in names:
        print(f"\n=== {name} ===", flush=True)
        rep = validate_task(tasks_dir / name, report_dir, args.build_flag, args.skip_docker, args.keep_images)
        reports.append(rep)
        for chk in rep.checks:
            print(f"  [{'PASS' if chk.passed else 'FAIL'}] {chk.name}" + (f"  ({chk.detail})" if chk.detail and not chk.passed else ""))
        print(f"  => {'PASS' if rep.ok else 'FAIL'}  loc_changed={rep.loc_changed} files_changed={rep.files_changed} solve={rep.solve_seconds}s", flush=True)

    locs = [r.loc_changed for r in reports if r.loc_changed is not None]
    p25 = percentile(locs, 0.25)
    summary = {
        "tasks": [dict(task=r.task, passed=r.ok, image=r.image, loc_changed=r.loc_changed, files_changed=r.files_changed,
                       solve_seconds=r.solve_seconds, pre_apply=r.pre_apply, post_apply=r.post_apply,
                       checks=[asdict(c) for c in r.checks]) for r in reports],
        "n_tasks": len(reports),
        "n_pre_apply_fail_ok": sum(1 for r in reports if r.pre_apply and r.pre_apply.get("reward") == "0" and r.pre_apply.get("exit_code") != 0),
        "n_post_apply_pass_ok": sum(1 for r in reports if r.post_apply and r.post_apply.get("reward") == "1" and r.post_apply.get("exit_code") == 0),
        "anomalous_tasks": [r.task for r in reports if not r.ok],
        "loc_changed_p25": p25,
        "loc_changed_p25_gt_100": (p25 or 0) > 100,
        "all_passed": all(r.ok for r in reports) and bool(reports),
    }
    # strip bulky logs from the JSON summary
    for t in summary["tasks"]:
        for k in ("pre_apply", "post_apply"):
            if t[k]:
                t[k] = {kk: vv for kk, vv in t[k].items() if kk != "output_tail"}
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    md = ["# Validation summary", "", f"Tasks: {summary['n_tasks']}  |  pre-apply failures (required): {summary['n_pre_apply_fail_ok']}  |  post-apply successes (required): {summary['n_post_apply_pass_ok']}",
          f"LOC changed P25: {p25}  (criterion > 100: {'PASS' if summary['loc_changed_p25_gt_100'] else 'FAIL'})", "",
          "| task | result | pre exit | pre reward | pre failed | post exit | post reward | post passed | LOC changed | files changed | solve s |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        pre, post = r.pre_apply or {}, r.post_apply or {}
        md.append(f"| {r.task} | {'PASS' if r.ok else 'FAIL'} | {pre.get('exit_code')} | {pre.get('reward')} | {pre.get('pytest', {}).get('failed')} | "
                  f"{post.get('exit_code')} | {post.get('reward')} | {post.get('pytest', {}).get('passed')} | {r.loc_changed} | {r.files_changed} | {r.solve_seconds} |")
    md.append("")
    for r in reports:
        fails = [c for c in r.checks if not c.passed]
        if fails:
            md.append(f"## {r.task}: failed checks")
            md += [f"- {c.name}: {c.detail}" for c in fails]
            md.append("")
    (report_dir / "summary.md").write_text("\n".join(md))
    print("\n" + "\n".join(md))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
