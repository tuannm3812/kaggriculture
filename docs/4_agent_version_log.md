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

## task_teacher_v1 (`agents/task_teacher_v1/main.py`)

- **Date:** 2026-08-01
- **New agent family** (not `roi_teacher_v4`), per the approved design in
  the design doc's "task_teacher_v1: final design" entry — a structurally
  different architecture (multi-tile task generation/ranking/routing) from
  `roi_teacher_v1-v3`'s single-tile ROI loop, built after multiple rounds
  of Codex design review (module boundaries, typed task/state data model,
  deterministic ranking/routing contract, explicit `TeacherState` reset
  semantics, O(1) service-capacity check, market-timing correctness,
  `sys.modules`-based packaging).
- **Scope:** one farmer, initial unlocked (NW) quadrant only, one-time
  crops only (Wheat/Carrot/Melon), multi-tile plant/water/harvest/dig,
  deterministic task generation/ranking/routing, seed acquisition and
  shed selling consistent with `1.29.3`'s turn order. No hands, land,
  animals, fertilizer, `PICKUP`/`PLACE`, or manual `DROP` (a no-op under
  `1.29.3` — modeled correctly: harvested produce reaches the shed via the
  automatic end-of-day drop instead).
- **New shared module:** `src/kaggriculture_lib/tasking.py` (`TaskKind`,
  `PriorityTier`, `TaskId`, `ResourceNeed`, `Task`, `MarketIntent`,
  `TeacherState`, `ReservationLedger`, `generate_tasks`, `rank_tasks`,
  `route_toward`, `project_daily_load`). `economy.py` gained
  `last_day_index`/`can_mature_in_time`, promoted from
  `roi_teacher_v3`'s private per-tile feasibility check.
- **Built test-first** (`superpowers:test-driven-development`): every
  function has a test written and watched fail before implementation —
  `tests/test_tasking.py` (33 tests: data model, task generation, ranking,
  routing, market intent, service-capacity load), `tests/test_task_teacher_v1.py`
  (9 tests: synthetic-obs decision logic, market-timing correctness,
  explicit state-reset-on-`step==0` behavior, a small-sample acceptance-gate
  regression), and `tests/test_package_agent.py` rewritten for the new
  `sys.modules`-registration packaging approach (9 tests, including a
  dataclass-`__module__` correctness check).
- **Acceptance-gate measurement** (100 full 720-step episodes vs. `starter`,
  seeds 1000–1099, per the design doc's numeric gate):

  | Metric | Result | Gate |
  | --- | --- | --- |
  | `DONE` both players | 100/100 | 100% required |
  | Invalid/non-`DONE` episodes | 0 | 0 required |
  | Non-finite-reward episodes | 0 | 0 required |
  | Distinct tiles worked/episode | median 17, p10 15, range [14, 21] | median ≥12, p10 ≥8 |
  | Action-kind coverage (all episodes) | `PLANT`=2697, `WATER`=25356, `HARVEST`=2214, `DIG`=705 | every `TaskKind` present |
  | Determinism (same seed, 2 runs) | identical rewards | required |

  All criteria passed comfortably — natural weed spawning already produced
  705 `DIG` occurrences across the sample, so no seeded weed-scenario
  fixture was needed to hit that threshold.
- **Local tournament** (`scripts/run_tournament.py`, 8 seed pairs / 16 games
  per opponent, full 720-step episodes, base seed 0):

  | Opponent | Win rate | Mean money margin |
  | --- | ---: | ---: |
  | `pass` | 1.000 | +29244.9 |
  | `random` | 1.000 | +31164.9 |
  | `starter` | 1.000 | +28158.4 |
  | **`roi_teacher_v3` (direct)** | **1.000** | **+25244.9** |

  A step change, not an incremental one: margins roughly 10x
  `roi_teacher_v3`'s, consistent with using all ~25 NW-quadrant tiles
  simultaneously instead of 1.
- **Packaging:** `scripts/package_agent.py` rewritten to register real
  modules in `sys.modules` under their true dotted names
  (`kaggriculture_lib`, `kaggriculture_lib.economy`,
  `kaggriculture_lib.tasking`, auto-discovered and topologically sorted —
  no hardcoded module list), rather than the earlier namespace-object-alias
  shim. Verified standalone (`PYTHONPATH` stripped) for `task_teacher_v1`
  and re-verified for `roi_teacher_v1-v3`. Found and fixed a real test-
  isolation bug along the way: executing generated packaged code
  registers modules into the *real* `sys.modules`, which leaked a test
  fixture's stub `kaggriculture_lib` into later tests importing the real
  package — fixed with an autouse `sys.modules` snapshot/restore fixture
  in `tests/test_package_agent.py`.
- **Ladder result:** not yet submitted.
- **Lesson carried forward:** the multi-round Codex design discussion
  (typed enums over raw strings/floats, `deadline_step` over day-
  granularity, the market-timing bug class, and especially the corrected
  "no episode key needed" reasoning — see the design doc §9) produced a
  design with zero rework needed during implementation; every test passed
  on essentially the first attempt after fixing two test-premise bugs
  (a Manhattan-distance tie in a ranking test, and an unrealistic price
  assumption in a synthetic-obs test) — not implementation bugs. Confirms
  the earlier investment in design review before code was worth it.

## task_teacher_v2 (`agents/task_teacher_v2/main.py`)

- **Date:** 2026-08-02
- **Extends `task_teacher_v1` with:** daily hiring and bounded exhaustive
  joint multi-unit assignment, per the approved design in
  `docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md`. Same
  crop scope as v1 (Wheat/Carrot/Melon, one-time crops only); still no
  animals, fertilizer, or land purchases.
- **New shared-module additions:** `joint_assign` (bounded exhaustive
  assignment across farmer + hands, with a deterministic greedy fallback
  for unit counts past a practical exhaustive-search bound —
  `MAX_EXHAUSTIVE_UNITS`), `estimate_hire_value`/`should_hire` (marginal-
  value hiring gate), `reset_hand_assignments_on_day_change` (hand-index
  identity doesn't survive a day boundary), `TeacherState.previous_day`.
- **Two real bugs found via a full simulator run, not caught by unit
  tests alone** — both are exactly the kind of gap `roi_teacher`'s
  100%-win-rate-against-weak-built-ins couldn't have surfaced either:
  1. **Runaway hiring.** The hiring value estimate didn't account for
     capacity already provided by hands hired earlier the same day, so
     `should_hire` kept approving hire after hire — 9 in a row in a
     synthetic worst case, 7–8 in a real game. Fixed by discounting
     `estimate_hire_value` by `remaining_turns_today * (1 + existing_hands)`
     of already-available capacity — hiring hand N+1 only has value if
     load still exceeds what N hands (plus the farmer) already absorb.
  2. **Combinatorial blowup.** 7–8 active units pushed `joint_assign`'s
     exhaustive search (`(candidates+1)^n_units`) into multi-second-per-
     turn territory, making one 720-step episode take ~20s. Measured
     directly: `n=4` costs ~8ms/call, `n=5` ~70ms, `n=6` ~650ms — fixed by
     lowering `MAX_EXHAUSTIVE_UNITS` from 6 to 4 (matching the design's own
     "expected farmer plus 1–3 hands" assumption) and using the
     already-designed deterministic greedy fallback beyond that. Full
     episode time: ~20s → ~1s.
- **Acceptance-gate measurement** (50 full 720-step episodes vs.
  `starter`, seeds 2000–2049):

  | Metric | Result |
  | --- | --- |
  | `DONE` both players | 50/50 |
  | Invalid/non-finite episodes | 0 |
  | Distinct tiles worked/episode | median 25, p10 24, range [22, 25] — all 25 NW tiles, most episodes |
  | Action-kind coverage | `PLANT`=3213, `WATER`=24211, `HARVEST`=1578, `DIG`=1643 |
  | `HIRE` orders/episode | min 54, max 122, avg 112.2 (re-evaluated every turn, per the design) |
  | Max hands active/episode | min 7, max 8, avg 7.0 |

- **Local tournament** (`scripts/run_tournament.py`, 8 seed pairs / 16 games
  per opponent, full 720-step episodes, base seed 0):

  | Opponent | Win rate | Mean money margin |
  | --- | ---: | ---: |
  | `pass` | 1.000 | +30238.1 |
  | `random` | 1.000 | +33128.4 |
  | `starter` | 1.000 | +27214.1 |
  | **`task_teacher_v1` (direct)** | **0.875** | **+2779.6** |
  | **`roi_teacher_v3` (direct)** | **0.875** | **+22839.4** |

- **Outcome:** clear net positive (positive margin and majority win rate
  against every opponent including the prior champion), but **not** a
  clean sweep like v1→v3 or v2(roi)→v3(roi) — 2 of 16 games lost to
  `task_teacher_v1` despite v2's added capabilities. Not investigated
  further this round; the v2 design doc explicitly allows this outcome
  ("v2 may become the coverage teacher without replacing the competitive
  champion if it expands valid action coverage but lacks confident win
  improvement"). **`task_teacher_v2` is provisionally the new local
  champion** given the positive average margin, but the occasional losses
  are worth revisiting before any promotion decision that matters (e.g.
  BC teacher selection or ladder submission).
- **Packaging:** re-verified standalone (`PYTHONPATH` stripped) after the
  performance fix; all four existing agents (`roi_teacher_v1-v3`,
  `task_teacher_v1`) re-packaged and re-verified alongside it.
- **Ladder result:** not yet submitted.
- **Lesson carried forward:** synthetic unit tests validated every
  individual function correctly, but neither bug above was visible until
  a *real, full-length simulator run* — the runaway-hiring bug only
  manifests when load stays high across many consecutive turns in one
  day (not exercised by short synthetic scenarios), and the performance
  bug only manifests at the unit counts that emerge from realistic
  economic conditions over a full season. Full-episode smoke runs before
  declaring a version done are not optional, even with thorough unit
  test coverage.
