# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-02)

`task_teacher_v2` is the new local champion — adds daily hiring and
bounded exhaustive multi-unit assignment on top of `task_teacher_v1`. This
supersedes an earlier, self-identified process error: the first pass
declared v2 "provisionally" champion from an 8-pair local tournament
(0.875 win rate, positive margin) without a confidence interval, which
Codex's 2026-08-02 review correctly flagged as both short of the
authoritative promotion gate (design doc §6) and built on top of a real
bug — a hiring-value fix that was correct in `tasking.py` but never
actually wired into `agents/task_teacher_v2/main.py`'s call site.

After fixing the wiring bug (test-first regression test, then the one-line
call-site fix) and re-running the acceptance gate (100 episodes, 100%
`DONE`/finite, all 25 tiles worked every episode, hand count now a flat
5/5/5 instead of ranging 7-8), the full paired-bootstrap protocol was run:
20-pair screen vs. `task_teacher_v1` (1.000 win rate, CI `[1.000, 1.000]`),
then the 50-pair promotion gate (0.970 win rate, CI `[0.930, 1.000]` —
wholly above 0.50), plus 20-pair regression screens vs. `roi_teacher_v3`
and `starter` (both 1.000, CI `[1.000, 1.000]`). See
`docs/4_agent_version_log.md` for full numbers.

Still not submitted to the ladder — re-ask before submitting or continuing
to delay, per the standing rule from earlier (design doc §9's execution-
status audit).

## Immediate Next Tasks

1. ~~Packaging step~~ — done 2026-08-01.
2. ~~v2 (roi) — add Melon~~ — done 2026-08-01.
3. ~~v3 (roi) — season-horizon gate~~ — done 2026-08-01.
4. ~~Kaggle platform smoke test~~ — done 2026-08-01.
5. ~~Version-gap check (`1.29.3` vs `1.32.2`)~~ — done 2026-08-01.
6. ~~Multi-tile task/route teacher (`task_teacher_v1`)~~ — done 2026-08-01.
7. ~~`task_teacher_v2` (hiring + multi-unit assignment)~~ — done 2026-08-02.
   See `docs/4_agent_version_log.md`.
8. ~~Investigate `task_teacher_v2`'s occasional losses to `task_teacher_v1`~~
   — done 2026-08-02: the losses were caused by the confirmed hiring-wiring
   bug (existing hands' capacity never reached `should_hire`), not
   irreducible variance. Fixed; the 50-pair promotion gate afterward gave
   CI `[0.930, 1.000]`, still not a perfect sweep but decisively above 0.50.
   The remaining ~3% loss rate at 50 pairs could still be profiled further
   (same hiring-risk-vs-fallback-inefficiency question) if it matters before
   BC teacher selection, but is no longer a promotion blocker.
9. **`task_teacher_v3`** (per the construction sequence: ongoing crops —
   Tomato/Strawberry — and fertilizer timing): the next version. Needs the
   ongoing-crop ROI ranking deferred in `docs/3_agent_strategy.md` (season-
   length + feed-cost model) resolved first, or as part of this version.
10. **Critical-path test coverage** — done for economy math, agent decision
    logic (`roi_teacher_*`, `task_teacher_v1`, `task_teacher_v2`), the
    tournament harness, and packaging. Extend to `task_teacher_v3`'s
    ongoing-crop/fertilizer logic once it exists.
11. **Confirm submission-slot / ladder-tracking rules** (open item since
    `docs/1_competition_instructions.md`): check `kaggle competitions
    submissions kaggriculture` behavior and the Rules page once a submission
    exists.
12. **Confirm actual ladder episode configuration** (open item since
    `docs/2_environment_notes.md`): whether scored games vary `boardSize`/
    `episodeSteps`/etc. from defaults — relevant to whether the design doc's
    conditional C5 robustness stage is worth its GPU budget later.
13. **Week-1 throughput benchmarking** (per the design doc's Codex
    resolution): env-only steps/sec is measured (~1000–1100/sec, see
    `docs/2_environment_notes.md`); policy-inference and training steps/sec
    at multiple parallel-env counts, and checkpoint write/load time, are not
    yet measured — needed before any BC/PPO evaluation-size commitment.
14. **Recalibrate `tasking.py`'s constants from real data**:
    `TRAVEL_ALLOWANCE`/`END_OF_DAY_RESERVE` (service-capacity check),
    `AVERAGE_VALUE_PER_RECOVERED_ACTION` (hiring value estimate) — all
    still initial estimates, per the "measure before fixing the number"
    discipline. `task_teacher_v2` now produces real hiring/load data to
    calibrate against.
15. **`MAX_EXHAUSTIVE_UNITS` (currently 4) and the greedy fallback's
    quality gap** — the fallback is fast but not joint-optimal, and v2
    regularly operates in fallback territory (7-8 hands active per the
    acceptance-gate measurement). Worth profiling whether a smarter bounded
    algorithm (not full exhaustive search) could extend joint-optimal
    behavior to more units without the combinatorial cost, if v3+'s
    profile shows this matters.
