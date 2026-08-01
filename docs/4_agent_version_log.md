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

- **Ladder result:** not yet submitted. Open item before submitting: no
  packaging step exists yet to bundle `src/kaggriculture_lib` alongside
  `main.py` for actual `kaggle competitions submit` (main.py currently
  assumes `kaggriculture_lib` is importable via `PYTHONPATH=src`, which only
  works in local testing). Needed before this becomes a real submission.
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
