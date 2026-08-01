# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-01)

Do not submit `roi_teacher_v1` yet — the packaging step to bundle
`src/kaggriculture_lib` alongside `main.py` for actual `kaggle competitions
submit` doesn't exist. Build that next, since Week 2 of the design doc's
milestone table calls for "a valid heuristic ladder submission" and ladder
rating needs game volume to converge (start accumulating early).

## Immediate Next Tasks

1. **Packaging step** (blocks any real submission): a script that either
   inlines `kaggriculture_lib` into a self-contained `main.py`, or bundles
   `main.py` + `src/kaggriculture_lib` into a `.tar.gz` per `AGENTS.md`'s
   multi-file submission format. Needed before `roi_teacher_v1` (or any
   later version) can actually be submitted.
2. **v2 candidate — add Melon**: `docs/3_agent_strategy.md` found Melon's
   ROI/day at base price (~109) is 5–6x wheat/carrot's (~18–21). Add it as a
   third candidate crop in `_best_crop`'s dynamic selection (one-variable
   change from v1) and re-run the local tournament before considering
   anything else.
3. **Confirm submission-slot / ladder-tracking rules** (open item since
   `docs/1_competition_instructions.md`): check `kaggle competitions
   submissions kaggriculture` behavior and the Rules page once a submission
   exists.
4. **Confirm actual ladder episode configuration** (open item since
   `docs/2_environment_notes.md`): whether scored games vary `boardSize`/
   `episodeSteps`/etc. from defaults — relevant to whether the design doc's
   conditional C5 robustness stage is worth its GPU budget later.
5. **Multi-tile pathing** — v1 only ever uses 1 of 25 available NW tiles.
   Larger lever than crop choice, but evaluate it as its own one-variable
   change after v2's crop-selection result, not bundled with it.
6. **Week-1 throughput benchmarking** (per the design doc §9's Codex
   resolution): env-only steps/sec is measured (~1000–1100/sec, see
   `docs/2_environment_notes.md`); policy-inference and training steps/sec
   at multiple parallel-env counts, and checkpoint write/load time, are not
   yet measured — needed before any BC/PPO evaluation-size commitment.
