# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-01)

`roi_teacher_v2` is the local champion (beats `roi_teacher_v1` head-to-head
1.000 win rate, +2222.8 mean money margin — see `docs/4_agent_version_log.md`).
Packaging (`scripts/package_agent.py`) is generic across agent versions, so
v2 is submission-ready the same way v1 was. **User chose to keep iterating
locally before spending a submission** (2026-08-01 decision) — revisit
submitting once the next candidate below is evaluated, since ladder rating
needs game volume to converge and each week without a submission is a week
of rating not accumulating.

## Immediate Next Tasks

1. ~~Packaging step~~ — done 2026-08-01.
2. ~~v2 candidate — add Melon~~ — done 2026-08-01, confirmed as a large
   win (see `docs/4_agent_version_log.md`).
3. **v3 candidate — ongoing crops/animals ROI ranking**: `docs/3_agent_strategy.md`
   still has tomato/strawberry/goose/cow/sheep un-ranked against the
   one-time crops above (needs a season-length assumption + feed-cost
   model, since they don't have a fixed lifespan the way wheat/carrot/melon
   do). Rank them the same static-ROI way before deciding whether adding
   any of them beats another one-time-crop tweak.
4. **Multi-tile pathing** — v1/v2 still only ever use 1 of 25 available NW
   tiles. Larger lever than crop choice; evaluate as its own one-variable
   change once v3's result is in, not bundled with it.
5. **Confirm submission-slot / ladder-tracking rules** (open item since
   `docs/1_competition_instructions.md`): check `kaggle competitions
   submissions kaggriculture` behavior and the Rules page once a submission
   exists.
6. **Confirm actual ladder episode configuration** (open item since
   `docs/2_environment_notes.md`): whether scored games vary `boardSize`/
   `episodeSteps`/etc. from defaults — relevant to whether the design doc's
   conditional C5 robustness stage is worth its GPU budget later.
7. **Week-1 throughput benchmarking** (per the design doc §9's Codex
   resolution): env-only steps/sec is measured (~1000–1100/sec, see
   `docs/2_environment_notes.md`); policy-inference and training steps/sec
   at multiple parallel-env counts, and checkpoint write/load time, are not
   yet measured — needed before any BC/PPO evaluation-size commitment.
