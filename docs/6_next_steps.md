# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-01)

`roi_teacher_v1` is packaged (`scripts/package_agent.py` → `build/
roi_teacher_v1/main.py`) and verified to run standalone with no dependency
on this repo's `src/` layout, reproducing the un-packaged version's 1.000
win rate against all three built-ins. **Ready to submit** — actual
`kaggle competitions submit` is a separate, explicit action pending user
go-ahead (it consumes a submission and becomes visible on the ladder under
the user's account). Once submitted, start tracking ladder score in this
doc and confirm the two open items below.

## Immediate Next Tasks

1. ~~Packaging step~~ — done 2026-08-01, see above.
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
