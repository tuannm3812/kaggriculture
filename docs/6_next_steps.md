# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-01)

`task_teacher_v1` is the new local champion — a step change, not an
incremental one: 1.000 win rate and roughly 10x `roi_teacher_v3`'s margins
against every opponent (+25244.9 direct vs. v3; see
`docs/4_agent_version_log.md`), from using ~25 NW-quadrant tiles
simultaneously instead of 1. Passed its full acceptance gate (100 episodes,
100% `DONE`/finite rewards, median 17 distinct tiles worked, every
`TaskKind` well-represented, deterministic). Built test-first end to end
(`superpowers:test-driven-development`) after multiple rounds of Codex
design review — every test passed on first implementation attempt.

The Kaggle platform smoke test passed earlier (`docs/2_environment_notes.md`)
and the `1.29.3`/`1.32.2` version-gap was found and fixed
(`docs/4_agent_version_log.md`'s correction entry) before this build
started, so `task_teacher_v1` was built and tested against the
ladder-matching environment version from the start.

Still not submitted to the ladder — user chose to keep iterating locally
first. Per the execution-status audit, treat that as a point-in-time note,
not standing authorization to delay indefinitely — re-ask before either
submitting or continuing to delay, especially now that `task_teacher_v1`
is a much stronger candidate than anything submittable so far.

## Immediate Next Tasks

1. ~~Packaging step~~ — done 2026-08-01.
2. ~~v2 — add Melon~~ — done 2026-08-01, confirmed a large win.
3. ~~v3 — season-horizon gate~~ — done 2026-08-01, per Codex's code review;
   confirmed a measurable win over v2.
4. ~~Kaggle platform smoke test~~ — done 2026-08-01, passed. See
   `docs/2_environment_notes.md`.
5. ~~Version-gap check~~ — done 2026-08-01: diffed `1.29.3` (Kaggle's
   kernel) against `1.32.2` (this project's prior local dev version),
   found real differences, re-pinned and corrected `economy.py`. See
   `docs/4_agent_version_log.md`.
6. ~~Multi-tile task/route teacher (`task_teacher_v1`)~~ — done 2026-08-01,
   new local champion. Full design discussion and implementation in
   `docs/4_agent_version_log.md` and the design doc §9.
7. **`task_teacher_v2`** (per the agreed construction sequence: workload
   forecast, hiring, multi-unit assignment): the next version in the
   planned `task_teacher_v1→v6` sub-sequence. `task_teacher_v1`'s
   `AssignmentState`/`ReservationLedger` interfaces were deliberately kept
   general enough for this — real minimum-cost matching across multiple
   units was postponed to v2, not retrofitted.
8. **Critical-path test coverage** — done for economy math, agent decision
   logic (both `roi_teacher_*` and `task_teacher_v1`), the tournament
   harness, and packaging. Extend to `task_teacher_v2`'s multi-unit
   assignment logic once it exists.
9. **Ongoing crops/animals ROI ranking** — still deferred (needs a
   season-length + feed-cost model, per `docs/3_agent_strategy.md`);
   `task_teacher_v3` in the construction sequence covers this
   (ongoing crops + fertilizer timing).
10. **Confirm submission-slot / ladder-tracking rules** (open item since
    `docs/1_competition_instructions.md`): check `kaggle competitions
    submissions kaggriculture` behavior and the Rules page once a submission
    exists.
11. **Confirm actual ladder episode configuration** (open item since
    `docs/2_environment_notes.md`): whether scored games vary `boardSize`/
    `episodeSteps`/etc. from defaults — relevant to whether the design doc's
    conditional C5 robustness stage is worth its GPU budget later.
12. **Week-1 throughput benchmarking** (per the design doc §9's Codex
    resolution): env-only steps/sec is measured (~1000–1100/sec, see
    `docs/2_environment_notes.md`); policy-inference and training steps/sec
    at multiple parallel-env counts, and checkpoint write/load time, are not
    yet measured — needed before any BC/PPO evaluation-size commitment.
13. **Recalibrate `project_daily_load`'s constants** (`TRAVEL_ALLOWANCE`,
    `END_OF_DAY_RESERVE` in `src/kaggriculture_lib/tasking.py`) from real
    `task_teacher_v1` data once enough episodes accumulate — currently
    initial estimates, per the design doc's "measure before fixing the
    number" discipline.
