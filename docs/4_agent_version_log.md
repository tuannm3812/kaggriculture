# 4. Agent Version Log

Per `docs/0_coding_standards.md` §4: one entry per tried version, config
diff from the previous version, local-tournament result, ladder result once
available, and outcome/lesson.

## roi_teacher_v1 (`agents/roi_teacher_v1/main.py`)

- **Date:** 2026-08-01
- **Config:** single farmer, single tile (spawn, no movement), dynamic
  best-of-{WHEAT, CARROT} by static $/day ROI (see `docs/3_agent_strategy.md`),
  always waters, harvests once at `max_yield_day`, sells whatever reaches
  the shed. No hands, no land, no animals, no ongoing crops.
- **Local tournament** (`scripts/run_tournament.py`, 8 seed pairs / 16 games
  per opponent, full 720-step episodes, base seed 0):

  | Opponent | Win rate | Mean money margin | Wall time |
  | --- | ---: | ---: | ---: |
  | `pass` | 1.000 | +955.0 | 9.6s (1195 steps/sec) |
  | `random` | 1.000 | +3993.0 | 10.7s (1079 steps/sec) |
  | `starter` | 1.000 | +461.6 | 9.6s (1198 steps/sec) |

- **Packaging:** `scripts/package_agent.py` generates a self-contained
  `build/roi_teacher_v1/main.py` (inlines `economy.py` as an in-memory
  module so `from kaggriculture_lib import economy` isn't needed). Verified
  2026-08-01: runs correctly in a subprocess with `PYTHONPATH` stripped
  (the actual condition Kaggle's execution environment imposes), and
  reproduces the same tournament results as the un-packaged version
  (1.000 win rate vs. all three built-ins, 5 seed pairs / 10 games each).
- **Ladder result:** not yet submitted — packaging is done and verified;
  submission itself is a separate, explicit action (see
  `docs/6_next_steps.md`).
- **Outcome:** beats all three built-ins convincingly, including a solid
  margin over `starter` (the strongest built-in). Confirms the ROI-ranking
  approach and the tested `economy.py` formulas produce a genuinely
  functional policy, not just a plausible-looking one.
- **Lesson carried forward:** Phase-1 ROI analysis (`docs/3_agent_strategy.md`)
  found Melon's ROI/day at base price (~109) is 5–6x wheat/carrot's (~18–21)
  — v2's highest-value change is adding Melon as a candidate crop, not
  further tuning the wheat/carrot loop. Also still open: this agent only
  ever uses 1 of 25 available NW-quadrant tiles — multi-tile pathing is a
  separate, larger lever than crop choice and should be evaluated as its
  own one-variable change once v2's crop-selection change is measured.
