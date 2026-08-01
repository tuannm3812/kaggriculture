# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-01)

`roi_teacher_v3` is the local champion (beats `roi_teacher_v2` head-to-head
1.000 win rate, +264.5 mean money margin — see `docs/4_agent_version_log.md`)
and is packaging-verified. **Reprioritized per Codex's 2026-08-01 code
review** (see the design doc): the next priority is **not** another
single-tile ROI variant. v1–v3's single-tile trajectory distribution would
make a poor behavioral-cloning teacher — it never demonstrates movement,
route selection, task arbitration, hands, land, animals, structures,
fertilizer, care, or multi-order market coordination. Build multi-tile
task/route coverage before generating any BC dataset.

Still not submitted to the ladder — user chose to keep iterating locally
first (2026-08-01 decision, reaffirmed after v3).

## Immediate Next Tasks

1. ~~Packaging step~~ — done 2026-08-01.
2. ~~v2 — add Melon~~ — done 2026-08-01, confirmed a large win.
3. ~~v3 — season-horizon gate~~ — done 2026-08-01, per Codex's code review;
   confirmed a measurable win over v2.
4. **Multi-tile task/route teacher** (reprioritized ahead of ongoing-crop
   ROI ranking, per Codex's Feedback 2): a teacher that uses more than 1 of
   25 available NW-quadrant tiles, and ideally demonstrates every
   structural action family (hands, land, animals/structures, fertilizer,
   care, pickup/place, multi-order market coordination) so a later BC
   dataset isn't built from an overly narrow distribution. This is a
   bigger, separate change from crop-selection tuning — likely its own
   sub-sequence of versions, not a single one-variable diff.
5. **Critical-path test coverage** — done 2026-08-01 for agent decision
   logic (`tests/test_agents.py`), the tournament harness
   (`tests/test_tournament.py`), and packaging (`tests/test_package_agent.py`).
   Extend to the multi-tile teacher's decision logic once it exists.
6. **Ongoing crops/animals ROI ranking** — still deferred (needs a
   season-length + feed-cost model, per `docs/3_agent_strategy.md`), now
   explicitly behind the multi-tile teacher in priority, not ahead of it.
7. **Confirm submission-slot / ladder-tracking rules** (open item since
   `docs/1_competition_instructions.md`): check `kaggle competitions
   submissions kaggriculture` behavior and the Rules page once a submission
   exists.
8. **Confirm actual ladder episode configuration** (open item since
   `docs/2_environment_notes.md`): whether scored games vary `boardSize`/
   `episodeSteps`/etc. from defaults — relevant to whether the design doc's
   conditional C5 robustness stage is worth its GPU budget later.
9. **Week-1 throughput benchmarking** (per the design doc §9's Codex
   resolution): env-only steps/sec is measured (~1000–1100/sec, see
   `docs/2_environment_notes.md`); policy-inference and training steps/sec
   at multiple parallel-env counts, and checkpoint write/load time, are not
   yet measured — needed before any BC/PPO evaluation-size commitment.
