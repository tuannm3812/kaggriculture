# Handoff to Cursor — v3 Status Check + Real-Ladder Priority Update

Written 2026-08-07. Purpose: a durable, structured handoff memo — not a
design doc, no approval gate. It records a status check and a priority
directive for the `feat/task-teacher-v3` work (PR #1), backed by
evidence in `docs/8_ladder_replay_analysis.md`.

## 1. Status Check — PR #1 (`task_teacher_v3`)

As of this writing, PR #1 is still at 9 commits — no update since the
review comment requesting the `_score_ongoing_crop` fix:

- Change `lifespan_days` from `reachable[-1] - reachable[0] + 1` to
  `reachable[-1] + 1` (see
  `docs/superpowers/specs/2026-08-02-task-teacher-v3-design.md` §8 for
  the full diagnosis).
- Add a regression test asserting Melon beats Strawberry at
  `current_day=0` under base prices via `_best_feasible_crop`.
- Check the two existing `_score_ongoing_crop` tests
  (`test_score_ongoing_crop_matches_manual_calculation` in particular)
  for expected values that assumed the buggy formula.
- Full test suite green.

No new deadline — this is a check on whether you're still working it or
blocked on something, not a rush.

## 2. New Evidence: Real Ladder Data

`task_teacher_v2` (current champion) is now live on Kaggle's real ladder.
All 19 real episodes it has played were pulled and analyzed via the
Kaggle API directly — full methodology and data in
[`docs/8_ladder_replay_analysis.md`](../../8_ladder_replay_analysis.md).

**Headline finding:** win/loss on the real ladder splits almost entirely
on whether the opponent bought land and/or used animals — mechanics
neither `task_teacher_v2` nor `task_teacher_v3` have.

| Opponent profile | Games | Record |
| --- | ---: | --- |
| Bought land and/or used animals | 16 | 5W-11L (31%) |
| Did neither (still single-quadrant, no animals) | 3 | 3W-0L (**100%**) |

84% of real opponents faced so far (16 of 19) have already expanded past
a single quadrant and/or added animals. Every local evaluation run to
date (acceptance gates, paired Hoeffding-CI screens vs.
`task_teacher_v1`/`roi_teacher_v3`/`starter`) only ever measured against
opponents from our own scope-constrained agent family — none of them buy
land or use animals either — so this gap never had a chance to surface
locally. `docs/3_agent_strategy.md` flagged "ongoing crops / animals ROI
ranking" as an open, unranked question back on 2026-08-01; this is the
first *measured* evidence, not just a standing hypothesis, that closing
it is where the real competitive gap is.

## 3. Decision

1. **Finish and land the `task_teacher_v3` fix above.** The ongoing-crop
   scoring bug is real and independent of this finding; v3 is close to
   done and shouldn't be abandoned mid-flight.
2. **Do not start scoping land or animal mechanics yet.** That's a large
   enough change (new action types — `BUY_LAND`, `BUY_ANIMAL`, `PLACE`,
   `FEED`, `CARE`, `COLLECT_FERTILIZER`, `BUILD_COOP`/`BUILD_PASTURE` —
   plus a new economic subsystem) that it needs the same
   brainstorm → design doc → implementation plan cycle every prior
   version went through, same as
   `docs/superpowers/specs/2026-08-02-task-teacher-v3-design.md` was
   before `task_teacher_v3` got built. That design doc (working title
   `task_teacher_v4`) hasn't been written yet.

## 4. Action Items

- [x] Report status on the `task_teacher_v3` fix — **done** (2026-08-07):
      `lifespan_days = reachable[-1] + 1`, Melon-over-Strawberry regression,
      suite green (316).
- [x] Fresh Task 9 after the fix — **done** (2026-08-07): acceptance clean;
      vs-v2 identity `win_rate=0.500` / margin `+0.0` at 20 and 50 pairs;
      **not promoted**. See `docs/4_agent_version_log.md`.
- [ ] Hold off on any land/animal **implementation** until a
      `task_teacher_v4` design doc and implementation plan are written
      (brainstorm → spec → plan). Ladder refresh 2026-08-10 (56 episodes)
      strengthens the case that animals (not land alone) are the sharper
      edge — see `docs/8_ladder_replay_analysis.md` §Refresh.
