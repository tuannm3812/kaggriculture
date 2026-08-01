# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-01)

`roi_teacher_v3` is the local champion (beats `roi_teacher_v2` head-to-head
1.000 win rate, +264.5 mean money margin — see `docs/4_agent_version_log.md`)
and is packaging-verified. **The Kaggle platform smoke test passed**
(2026-08-01, see `docs/2_environment_notes.md`): `kaggriculture` imports and
runs correctly on Kaggle's own kernel infrastructure with no explicit
install step, the packaged `roi_teacher_v3` completed a full paired-seat
match `DONE`/`DONE` with finite rewards, and the packaged-agent SHA-256
matched exactly between the local build and the remote kernel. Platform
compatibility is now confirmed, not assumed.

**Next priority is still not another single-tile ROI variant**, per
Codex's 2026-08-01 code review: v1–v3's single-tile trajectory distribution
would make a poor behavioral-cloning teacher — it never demonstrates
movement, route selection, task arbitration, hands, land, animals,
structures, fertilizer, care, or multi-order market coordination. Build
multi-tile task/route coverage before generating any BC dataset.

Still not submitted to the ladder — user chose to keep iterating locally
first (2026-08-01 decision, reaffirmed after v3). Per the execution-status
audit, treat that as a point-in-time note, not standing authorization to
delay indefinitely — re-ask before either submitting or continuing to
delay, now that the platform-compatibility gate is cleared.

## Immediate Next Tasks

1. ~~Packaging step~~ — done 2026-08-01.
2. ~~v2 — add Melon~~ — done 2026-08-01, confirmed a large win.
3. ~~v3 — season-horizon gate~~ — done 2026-08-01, per Codex's code review;
   confirmed a measurable win over v2.
4. ~~Kaggle platform smoke test~~ — done 2026-08-01, passed. See
   `docs/2_environment_notes.md`.
5. **Multi-tile task/route teacher** (reprioritized ahead of ongoing-crop
   ROI ranking, per Codex's Feedback 2): a teacher that uses more than 1 of
   25 available NW-quadrant tiles, and ideally demonstrates every
   structural action family (hands, land, animals/structures, fertilizer,
   care, pickup/place, multi-order market coordination) so a later BC
   dataset isn't built from an overly narrow distribution. This is a
   bigger, separate change from crop-selection tuning — likely its own
   sub-sequence of versions, not a single one-variable diff.
6. **Critical-path test coverage** — done 2026-08-01 for agent decision
   logic (`tests/test_agents.py`), the tournament harness
   (`tests/test_tournament.py`), and packaging (`tests/test_package_agent.py`).
   Extend to the multi-tile teacher's decision logic once it exists.
7. **Ongoing crops/animals ROI ranking** — still deferred (needs a
   season-length + feed-cost model, per `docs/3_agent_strategy.md`), now
   explicitly behind the multi-tile teacher in priority, not ahead of it.
8. **Confirm submission-slot / ladder-tracking rules** (open item since
   `docs/1_competition_instructions.md`): check `kaggle competitions
   submissions kaggriculture` behavior and the Rules page once a submission
   exists.
9. **Confirm actual ladder episode configuration** (open item since
   `docs/2_environment_notes.md`): whether scored games vary `boardSize`/
   `episodeSteps`/etc. from defaults — relevant to whether the design doc's
   conditional C5 robustness stage is worth its GPU budget later.
10. **Week-1 throughput benchmarking** (per the design doc §9's Codex
    resolution): env-only steps/sec is measured (~1000–1100/sec, see
    `docs/2_environment_notes.md`); policy-inference and training steps/sec
    at multiple parallel-env counts, and checkpoint write/load time, are not
    yet measured — needed before any BC/PPO evaluation-size commitment.
11. ~~Version-gap check~~ — done 2026-08-01: diffed `1.29.3` (Kaggle's
    kernel) against `1.32.2` (this project's prior local dev version),
    found real differences (hire cost 10x, `COW` cost, premium-good glut
    sensitivity, several config defaults — full table in
    `docs/2_environment_notes.md`). Re-pinned `requirements.txt` to
    `1.29.3`, corrected `economy.py` and its tests, re-verified v1→v3
    rankings hold (see `docs/4_agent_version_log.md`).
