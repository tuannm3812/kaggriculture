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

## roi_teacher_v2 (`agents/roi_teacher_v2/main.py`)

- **Date:** 2026-08-01
- **Config diff from v1:** one variable changed — `CANDIDATE_CROPS` extended
  from `("WHEAT", "CARROT")` to `("WHEAT", "CARROT", "MELON")`. No other
  logic changed.
- **Local tournament** (`scripts/run_tournament.py`, 8 seed pairs / 16 games
  per opponent, full 720-step episodes, base seed 0):

  | Opponent | Win rate | Mean money margin |
  | --- | ---: | ---: |
  | `pass` | 1.000 | +3172.0 |
  | `random` | 1.000 | +6147.6 |
  | `starter` | 1.000 | +2674.0 |
  | **`roi_teacher_v1` (direct)** | **1.000** | **+2222.8** |

- **Outcome:** confirms the Phase-1 ROI finding decisively — adding Melon
  as a single extra candidate crop roughly tripled the margin against every
  built-in and beats v1 head-to-head at 100% win rate. **v2 is the new
  local champion**, superseding v1 (v1's folder is kept, per
  `docs/0_coding_standards.md` §4's immutability rule, as the benchmark this
  result is measured against).
- **Ladder result:** not yet submitted — user chose to keep iterating
  locally before spending a submission (2026-08-01 decision).
- **Lesson carried forward:** static ROI analysis before writing code
  (`docs/3_agent_strategy.md`) correctly predicted the single highest-value
  change, ahead of intuition-driven tuning. Next candidates to evaluate the
  same way before implementing: (a) ongoing crops/animals ROI ranking
  (deferred in `docs/3_agent_strategy.md` pending a season-length/feed-cost
  model), (b) multi-tile pathing — still the largest untapped lever (this
  agent uses 1 of 25 available NW tiles) but a bigger, separate change that
  should be evaluated on its own, not bundled with further crop-selection
  tweaks.
- **Code-review finding (2026-08-01, Codex):** neither v1 nor v2 checks
  remaining season length before planting — a late-season purchase can
  spend money that never converts back to bank balance before the episode
  ends. Confirmed as a real, characterized bug (see `roi_teacher_v3` below
  and `tests/test_agents.py::test_v1_v2_have_no_horizon_awareness_by_contrast`).
  v1/v2 are kept as-is (immutable once tried, per `docs/0_coding_standards.md`
  §4) — the fix is a new version, not a retroactive edit.

## roi_teacher_v3 (`agents/roi_teacher_v3/main.py`)

- **Date:** 2026-08-01
- **Config diff from v2:** one variable changed — adds a season-horizon
  gate: only plants a candidate crop if `current_day + max_yield_day <=
  last_day_index` (derived from the real `episodeSteps`/`turnsPerDay` via
  an `(obs, config)` agent signature — `kaggle_environments/agent.py`
  passes `config` when the agent function accepts a second argument, so
  this uses the actual episode config rather than a hardcoded guess). If no
  candidate crop can mature in time, holds (`PASS`) rather than spending on
  a seed that can't come back as money. No other logic changed.
- **Motivation:** fixes the gap Codex's code review found in v1/v2 (see the
  design doc's 2026-08-01 "Codex review of Claude's current implementation"
  entry).
- **Local tournament** (`scripts/run_tournament.py`, 8 seed pairs / 16 games
  per opponent, full 720-step episodes, base seed 0):

  | Opponent | Win rate | Mean money margin |
  | --- | ---: | ---: |
  | `pass` | 1.000 | +3436.5 |
  | `random` | 1.000 | +6388.9 |
  | `starter` | 1.000 | +2938.5 |
  | **`roi_teacher_v2` (direct)** | **1.000** | **+264.5** |

- **Outcome:** measurable improvement over v2 across every opponent
  (margin vs. `pass`/`random`/`starter` all increased), and beats v2
  head-to-head at 100% win rate. Confirms the horizon-gate fix is a real
  improvement, not just theoretically correct. **v3 is the new local
  champion.**
- **Packaging:** verified 2026-08-01 the same way as v1 — runs correctly
  standalone with `PYTHONPATH` stripped (`build/roi_teacher_v3/main.py`),
  including as a full-season (720-step) smoke test in
  `tests/test_package_agent.py`.
- **Ladder result:** not yet submitted.
- **Lesson carried forward:** this was found by external code review, not
  by this project's own local-tournament/replay process — a reminder that
  100% win rate against weak built-ins doesn't surface every correctness
  gap. Per Codex's Feedback 2, the next priority is **not** another
  single-tile ROI variant (e.g., ongoing-crop ROI ranking) but multi-tile
  task/route coverage: v1–v3's single-tile trajectory distribution would
  make a poor behavioral-cloning teacher, since it never demonstrates
  movement, hands, land, animals, structures, or multi-order market
  coordination. See `docs/6_next_steps.md`.

## Correction: All Tournament Numbers Above Were Measured Against `1.32.2`, Not the Ladder-Matching `1.29.3`

- **Date:** 2026-08-01
- **What happened:** Codex's execution-status audit surfaced that Kaggle's
  own kernel infrastructure runs `kaggle-environments==1.29.3`, not the
  `1.32.2` (GitHub `master`) this project had been developing against. A
  direct diff found real balance differences (`COW` cost, hire cost
  multiplier, glut-sensitivity constants for premium goods, several config
  defaults — full table in `docs/2_environment_notes.md`). All tournament
  numbers in the v1/v2/v3 entries above were measured against `1.32.2`.
- **What this does NOT invalidate:** every crop/animal's `base` price is
  identical between versions, so the static ROI ranking
  (`docs/3_agent_strategy.md`) and every *relative* comparison above
  (v3 > v2 > v1 > starter > random > pass) were internally valid — each
  comparison ran both agents inside the same consistently-versioned local
  environment.
- **Fix:** re-pinned `requirements.txt` to `kaggle-environments==1.29.3`,
  corrected `economy.py`'s constants and docstring line-citations, rebuilt
  `.venv`, corrected `tests/test_economy.py`'s expected sample-price
  table, reran the full test suite (129 passing) and re-packaged all
  three agents.
- **Re-verified local tournament** (same protocol: 8 seed pairs / 16 games
  per opponent, full 720-step episodes, base seed 0) — **rankings
  unchanged**, absolute margins shifted somewhat (different
  `startingMoney`/town-consumption defaults change the baseline scale):

  | Agent | vs. `pass` | vs. `random` | vs. `starter` | vs. prior version |
  | --- | ---: | ---: | ---: | ---: |
  | `roi_teacher_v1` | +920.5 | +2944.3 | +407.1 | — |
  | `roi_teacher_v2` | +3259.0 | +5259.0 | +2746.4 | +2343.8 vs. v1 |
  | `roi_teacher_v3` | +3319.0 | +5319.0 | +2806.4 | +60.0 vs. v2 |

  All win rates remained 1.000 (16/16 games) in every matchup above.
- **Lesson carried forward:** verify which environment version a ladder
  actually runs *before* extensive local iteration, not after — this was
  cheap to fix here because v1–v3 never touched the specific constants
  that changed (no hiring, no animals, no glut-sensitive bulk selling), but
  a similar gap discovered later, after building `task_teacher_v1→v6`
  (which will use all of those mechanics), would have been far more
  expensive to unwind.
