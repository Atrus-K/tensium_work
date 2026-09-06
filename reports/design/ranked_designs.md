# Task design panel

Fourteen task designs were proposed independently (two per required category, one incident-driven and one spec-driven) and scored 1-10 by three judges with different lenses (acceptance reviewer, red team, capability analyst) against the acceptance criteria. Full designs are in `designs/`.

| rank | design | category | overall | min | grounding | multi-file | tools/data | test robustness | difficulty gap | feasibility | fatal flaws | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | bundlevault-pentest-remediation | Security hardening / reverse-engineering patc | 8.0 | 8 | 8.3 | 8.3 | 9.0 | 8.0 | 7.7 | 7.0 | 0 | selected (Security hardening) |
| 2 | ltl-tariff-100c-rating-migration | Operations | 7.7 | 7 | 8.3 | 8.3 | 7.7 | 8.0 | 7.0 | 7.0 | 0 | not selected |
| 3 | recon-nightly-timeout-2291 | Performance / algorithm optimization | 7.7 | 7 | 8.0 | 8.3 | 8.3 | 7.0 | 8.0 | 7.0 | 0 | selected (Performance optimisation) |
| 4 | claims-adjudication-audit-recalc | Operations | 7.3 | 7 | 8.0 | 8.3 | 8.0 | 7.0 | 7.0 | 7.0 | 0 | selected (Operations) |
| 5 | cobol-loan-accrual-port-parity | Rewriting / cross-language migration | 7.3 | 7 | 8.3 | 8.0 | 8.0 | 7.3 | 6.3 | 7.0 | 0 | selected (Cross-language migration) |
| 6 | lwal-replica-recovery-and-masking | Data / database migration and recovery | 7.0 | 7 | 7.3 | 8.0 | 8.3 | 7.3 | 6.7 | 6.0 | 0 | not selected |
| 7 | gammaline-hpge-activity-metrology | Coding for STEM (radiation metrology | 7.0 | 6 | 8.0 | 8.3 | 9.0 | 7.3 | 6.3 | 5.7 | 1 | not selected |
| 8 | hatch-inc-2419-rollout-outage | System debugging / production-incident remedi | 6.7 | 6 | 8.0 | 8.3 | 9.0 | 7.0 | 6.3 | 5.7 | 2 | not selected |
| 9 | ledgerbridge-switchover-recovery | Data / database migration and recovery | 6.7 | 6 | 7.7 | 8.0 | 9.0 | 7.7 | 6.7 | 5.3 | 2 | not selected |
| 10 | pkgvault-extract-hardening | Security hardening / reverse-engineering patc | 6.7 | 6 | 7.3 | 7.0 | 7.0 | 8.0 | 5.3 | 8.3 | 0 | not selected |
| 11 | mdx-meter-archive-ingest-speedup | Performance / algorithm optimization | 6.7 | 6 | 8.0 | 8.3 | 8.7 | 7.0 | 6.7 | 5.3 | 0 | not selected |
| 12 | hpge-gamma-assay-nonconformance | Coding for STEM | 6.3 | 6 | 8.0 | 7.7 | 9.0 | 7.0 | 6.3 | 5.7 | 2 | not selected |
| 13 | quaymaster-restart-storm-incident | System debugging / production-incident remedi | 6.0 | 6 | 8.0 | 8.3 | 9.0 | 6.0 | 6.3 | 4.7 | 5 | started, then withdrawn: judges flagged real-subprocess flakiness and scope |
| 14 | utbill02-cobol-billing-port | Rewriting / cross-language migration | 5.0 | 5 | 8.0 | 8.3 | 8.0 | 6.0 | 5.0 | 4.3 | 5 | not selected |

## Selection rationale

- One task per distinct required category, preferring the highest overall score with no fatal flaws.
- `ltl-tariff-100c-rating-migration` (rank 2) shares the Operations category with `claims-adjudication-audit-recalc`; the claims task was chosen for its smaller, tighter rule set (lower spec-ambiguity risk).
- `quaymaster-restart-storm-incident` (incident remediation) was started before judging completed and withdrawn when the judges flagged five fatal issues (real-subprocess/HTTP/`/proc` tests in a 2-CPU container are flaky by nature; ~1800 LOC scope; unresolved recovery semantics). The other incident design (`hatch-inc-2419-rollout-outage`) had similar objections, so the incident category is not represented in this version.
- Judges' improvement notes for the selected designs were attached to each design file (`judge_feedback_to_address`) and given to the implementers.

## Fatal flaws recorded by the judges

### gammaline-hpge-activity-metrology
- Property test 'doubling both times and all counts reduces the combined standard uncertainty and detection limit by ~sqrt(2) (1.25-1.60 band)' is physically wrong for the combined uncertainty: the efficiency, emission-probability and mass relative terms do not scale with counts, so with ~0.5% counting precision the combined ratio will be near 1.0 and a correct implementation fails.

### hatch-inc-2419-rollout-outage
- Instruction pins 'the sqlite schema' as stable while the solution plan adds columns (deployments.last_progress_time, pods.term_deadline) with migration-on-open; as written the reference solution violates its own instruction. Must be changed to 'existing tables/columns must remain; additive changes allowed'.
- Ten spec deviations across nine modules, all required for an all-or-nothing reward, make qwen avg@8 ~0% near-certain; combined with the other orchestrator design this pushes the dataset past the 25% cap on zero-score tasks

### ledgerbridge-switchover-recovery
- Scope: WAL codec+writer+reader, changelog capture, tailer, schema transform, bulk copy, replayer with chaos flag, masking rules/engine, phase coordinator, verify, graph, seeded workload simulator, CLI with 10 subcommands, build-time fixture generator, plus 6 test families (~1850 LOC codebase near the upper bound) is beyond a reliable one-session build for a single implementer.
- Scope: WAL writer/reader, changelog capture, tailer, replayer, transform, masking engine, six-phase coordinator with crash/recover, verify, graph queries and a workload simulator (~1850 lines, at the ceiling) plus deterministic torn-WAL fixtures generated at build and an oracle for all of it is more than one implementer can build and validate reliably in one session; the twelve-ish sub-bugs across six areas also make qwen 0% likely

### hpge-gamma-assay-nonconformance
- Invariant 'combined uncertainty <= smallest used-line uncertainty' contradicts the protocol's own Birge inflation: with Poisson noise, reduced chi-square > 1 occurs randomly and a spec-conformant implementation must inflate the combined uncertainty above the best single line, failing the test on a correct solution.
- The determinism test 'run under a shifted container date/TZ' cannot shift the container date without root or libfaketime inside the verifier; only TZ can be changed. As written the test is unimplementable or trivially weak.

### quaymaster-restart-storm-incident
- Feasibility for a single implementer session is doubtful: ~1,800 LOC orchestrator with real process supervision, deployer state machine, recovery, plus 9 subprocess-driven hidden scenarios; the design itself shows unresolved semantics (the test text debates whether spec_path or the store wins after rollback)
- Build scope: a working single-node orchestrator (~1800 LOC: spawn, real HTTP/exec probes, ports, backoff, rolling deploys, rollback, crash recovery via /proc, graceful shutdown) plus deterministic real-subprocess tests for 9 scenarios is very unlikely to be buildable reliably by one implementer in one session.
- Recovery semantics are unresolved in the design itself ('spec_path still pointing at v2 file? no: ... the store is authoritative'); whether the persisted current_spec or the constructor's spec_path wins on restart is a normative decision that must be pinned in SPEC.md and instruction.md or tests encode an unstated requirement.
- Six interlocking defects spanning scheduler, deployer, supervisor recovery, port allocator, health tracker and process backend (~370 lines, with an 85-line scheduler rework) behind a single all-or-nothing reward on real-subprocess tests: qwen avg@8 will almost certainly be 0% and frontier pass@8 is at real risk because tests demand exact spawn counts, exact in-flight bounds per tick and persisted rollback across a supervisor restart
- Real-subprocess + HTTP-probe + /proc + signal tests in a 2-CPU container are flaky by nature (bounded waits mitigate but do not eliminate), and a single flaky scenario yields reward 0 on an otherwise correct solution, violating the 'fluctuating case' acceptance rule

### utbill02-cobol-billing-port
- Feasibility/difficulty overshoot: the implementer must author a complete ~650-line COBOL program with fully specified paginated report layouts, three copybooks, JCL, an independent oracle and two cycles of byte-exact captured outputs (master, register, exceptions) in one session, and the agent must reproduce paginated control-break reports byte-for-byte from COBOL text alone; qwen is very likely 0% and frontier pass@8 is at risk
- Build scope is unrealistic for one session: authoring a coherent ~650-line COBOL program with copybooks and JCL, a byte-exact independent oracle producing paginated control-break reports and a rewritten binary master, two full cycles of binary fixtures (COMP-3 and overpunch), plus a hidden 130-account cycle, all consistent to the byte.
- Twelve required changes including byte-exact 60-line pagination, edited pictures (floating $, BLANK WHEN ZERO), day-prorated block tariffs and packed-decimal encoding behind an all-or-nothing gate will very likely yield qwen avg@8 = 0 and puts frontier pass@8 at risk.
- Scale and unforgiveness: a half-finished port (COMP-3 raises NotImplementedError, no proration, incomplete report writer) requiring ~12 rule areas and byte-identical reproduction of three files including a 60-line paginated register with control breaks and edited pictures; qwen avg@8 will be 0% and frontier pass@8 is at genuine risk, failing the solvability gate
- Implementer feasibility: authoring ~650 lines of COBOL plus copybooks, an independent oracle, a port, planted edge data for two cycles and byte-exact expected reports is well beyond one session
