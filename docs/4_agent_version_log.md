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
- **Acceptance-gate measurement, first pass** (50 full 720-step episodes
  vs. `starter`, seeds 2000–2049):

  | Metric | Result |
  | --- | --- |
  | `DONE` both players | 50/50 |
  | Invalid/non-finite episodes | 0 |
  | Distinct tiles worked/episode | median 25, p10 24, range [22, 25] — all 25 NW tiles, most episodes |
  | Action-kind coverage | `PLANT`=3213, `WATER`=24211, `HARVEST`=1578, `DIG`=1643 |
  | `HIRE` orders/episode | min 54, max 122, avg 112.2 (re-evaluated every turn, per the design) |
  | Max hands active/episode | min 7, max 8, avg 7.0 |

- **Local tournament, first pass** (`scripts/run_tournament.py`, 8 seed
  pairs / 16 games per opponent, full 720-step episodes, base seed 0):

  | Opponent | Win rate | Mean money margin |
  | --- | ---: | ---: |
  | `pass` | 1.000 | +30238.1 |
  | `random` | 1.000 | +33128.4 |
  | `starter` | 1.000 | +27214.1 |
  | **`task_teacher_v1` (direct)** | **0.875** | **+2779.6** |
  | **`roi_teacher_v3` (direct)** | **0.875** | **+22839.4** |

- **Premature champion claim, self-identified error (2026-08-02):** this
  entry originally declared `task_teacher_v2` "provisionally the new local
  champion" from the numbers above. That conflicts with the authoritative
  design doc §6's own rule — game outcomes/win rate drive promotion, money
  margin is diagnostic only — and the evidence base (8 pairs, 2 losses, no
  confidence interval) was well short of the promotion gate (50 pairs / 100
  games with a paired bootstrap interval wholly above/below 0.50). Codex's
  2026-08-02 implementation review (see
  `2026-08-01-task-teacher-v2-design.md` §10) caught both the process
  violation and, more importantly, a confirmed implementation bug:
  `agents/task_teacher_v2/main.py`'s `should_hire(...)` call never passed
  `existing_hands=len(me["hands"])`, so the hiring-value fix below (item 1)
  was correct in `tasking.py` and in its direct unit tests, but never
  actually took effect in the running agent — every turn evaluated
  workload as if only the farmer existed. This is the real explanation for
  the 54–122 `HIRE` orders/episode and 7–8 simultaneously active hands
  measured above: the fix hadn't taken effect, and the acceptance-gate
  numbers were incorrectly rationalized as "economically correct given a
  large load" rather than investigated as a persisting symptom of an
  already-"fixed" bug.
- **Fix (2026-08-02):** added
  `tests/test_task_teacher_v2.py::test_does_not_hire_again_when_existing_hand_already_covers_the_load`
  (RED: failed by hiring again with a hand already covering the load; GREEN
  after the fix), then added the missing `existing_hands=len(me["hands"])`
  argument at the call site. Also fixed a related test-rigor gap Codex
  flagged: the synthetic observation fixtures in `test_task_teacher_v1.py`,
  `test_task_teacher_v2.py`, and `test_agents.py` defaulted to `money=3000`,
  inconsistent with the pinned `1.29.3` environment's actual `$2000`
  default (`docs/2_environment_notes.md`) — corrected to `$2000` throughout.
- **Acceptance-gate measurement, re-run after the fix** (100 full 720-step
  episodes vs. `starter`, seeds 3000–3099, matching `task_teacher_v1`'s
  100-episode rigor per Codex's request):

  | Metric | Result |
  | --- | --- |
  | `DONE` both players | 100/100 |
  | Invalid/non-finite episodes | 0 |
  | Distinct tiles worked/episode | median 25, p10 25, range [25, 25] |
  | Action-kind coverage | `PLANT`=6047, `WATER`=43395, `HARVEST`=3225, `DIG`=2949 |
  | `HIRE` orders/episode | min 72, max 78, avg 73.4 (down from 54–122, and far tighter variance) |
  | Max hands active/episode | min 5, max 5, avg 5.0 (flat, down from 7–8) |
  | Inference latency (ms/turn) | median 1.73, p95 1.85 |
  | Determinism (same seed, 2 runs) | identical rewards |

  The fix's effect is visible directly: hand count is now a stable 5/5/5
  instead of ranging 7–8, and hire-order count dropped and tightened
  substantially — exactly the symptom the bug produced, now gone for the
  reason expected (existing hands' capacity is finally counted).
- **Paired bootstrap evaluation, per the authoritative design doc §6's
  protocol** (screen at 20 pairs / 40 games, promote at 50 pairs / 100
  games, stop when the paired bootstrap 95% CI is wholly above/below
  0.50): implemented `scripts/run_tournament.py::bootstrap_ci` test-first
  (`tests/test_tournament.py`, 5 new tests) as permanent evaluation
  infrastructure, not a one-off.

  | Comparison | Pairs/Games | Win rate | Mean margin | Bootstrap 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v1` (screen, seed 5000) | 20/40 | 1.000 | +6563.0 | [1.000, 1.000] |
  | vs. `task_teacher_v1` (promotion, seed 6000) | 50/100 | 0.970 | +6336.1 | **[0.930, 1.000]** |
  | vs. `roi_teacher_v3` (regression, seed 7000) | 20/40 | 1.000 | +33175.4 | [1.000, 1.000] |
  | vs. `starter` (regression, seed 7000) | 20/40 | 1.000 | +35994.8 | [1.000, 1.000] |

  The promotion-gate CI `[0.930, 1.000]` is wholly above 0.50 — a decisive,
  rigorously-established result, not a margin-based guess. At 50 pairs the
  fixed v2 loses a small minority of games to v1 (unlike the perfect 20-pair
  screen), but the interval leaves no ambiguity about the direction.
- **Outcome: `task_teacher_v2` is legitimately promoted to
  `competitive_champion`**, satisfying every item in Codex's required
  post-fix evidence gate (100-episode acceptance run, 20-pair screen,
  50-pair promotion gate with paired CI, regression screens vs.
  `roi_teacher_v3` and `starter`). This supersedes the premature claim
  above; `task_teacher_v1` is retained as the immutable benchmark this
  result is measured against, per `docs/0_coding_standards.md` §4.

- **Codex follow-up review, second round (2026-08-02):** even after the
  wiring fix above, Codex's review found two further issues (see
  `2026-08-01-task-teacher-v2-design.md` §12), both independently verified
  before acting on them:
  1. **Confirmed end-of-day hiring bug.** Hiring is a market order,
     resolved after the current turn's unit actions, so a hand hired at
     hour H gets its first action at hour H+1. At the day's last hour
     (`hour == turns_per_day - 1`), a new hire is guaranteed zero future
     actions before every hand is cleared at the day boundary — yet
     `remaining_turns_today = turns_per_day - hour` evaluated to `1` there
     (not `0`), so `should_hire` still approved a guaranteed-worthless
     hire under enough load. Reproduced directly: `should_hire` returned
     `True` at hours 21, 22, and 23 for a loaded farm. Load was also
     counted before the current turn's assigned field actions resolve, so
     a task an already-positioned unit was about to complete this turn
     still counted as outstanding demand.
  2. **Bootstrap CI gave false zero-width certainty.** The percentile
     `bootstrap_ci` resamples only the observed pair scores, so an
     all-identical sample (e.g. every pair a win) produced a degenerate
     `[1.000, 1.000]` interval regardless of sample size — describing
     resampling variation of the *sample*, not uncertainty about the true
     population win rate. A handful of pairs cannot establish a true rate
     of exactly 1.0, and this matters directly because the docs called
     that degenerate interval "rigorous."
- **Fix (2026-08-02):**
  1. Added `future_action_turns = max(0, turns_per_day - hour - 1)` in
     `agents/task_teacher_v2/main.py`, replacing `remaining_turns_today`
     for both the existing-unit and new-hire capacity terms, plus a new
     `_count_immediately_completing_tasks` helper that subtracts tasks an
     already-positioned unit will resolve this turn from the load used to
     size the hiring decision. Built test-first: four new regression
     tests in `tests/test_task_teacher_v2.py` (never hires on the day's
     last hour even when heavily overloaded; still hires one hour
     earlier when genuinely justified — confirming no overcorrection; a
     direct unit test of the new helper; a full-episode regression
     asserting no `HIRE` order ever occurs at the day's last hour).
  2. Replaced `bootstrap_ci` with `hoeffding_ci` — a Hoeffding
     concentration bound for a mean bounded in [0, 1], which stays
     nonzero even on a degenerate all-win/all-loss sample because it
     depends only on sample size and boundedness, not sample variance.
     Alpha is Bonferroni-corrected across `max_looks` (default 8,
     matching the authoritative protocol's 20/50/75/…/200-pair
     checkpoints) so a chain of sequential looks stays simultaneously
     valid. Built test-first: 8 new tests in `tests/test_tournament.py`
     per Codex's exact required list (all-win lower bounds strictly below
     1.0 at both 4 and 20 pairs, all-loss upper bound strictly above 0.0,
     interval brackets the sample mean, width decreases with sample size,
     deterministic given the same inputs, and clear failures on empty
     input / invalid confidence / invalid `max_looks`).
- **Re-measurement after both fixes** (100 full 720-step episodes vs.
  `starter`, seeds 3000–3099):

  | Metric | Result |
  | --- | --- |
  | `DONE` both players | 100/100 |
  | Invalid/non-finite episodes | 0 |
  | Distinct tiles worked/episode | median 25, p10 25, range [24, 25] |
  | Action-kind coverage | `PLANT`=6143, `WATER`=43250, `HARVEST`=3176, `DIG`=3091 |
  | `HIRE` orders/episode | min 64, max 74, avg 70.4 (down from 73.4) |
  | Max hands active/episode | min 4, max 5, avg 4.9 (down from a flat 5.0) |
  | Inference latency (ms/turn) | median 2.05, p95 16.89 (P95 measured under CPU contention from a concurrently-running job — isolated re-checks stayed at ~500+ steps/sec; not a real regression) |
  | Determinism (same seed, 2 runs) | identical rewards |

  Re-ran the full paired evaluation with the corrected `hoeffding_ci`:

  | Comparison | Pairs/Games | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v1` (screen, seed 8000) | 20/40 | 1.000 | +6024.1 | [0.620, 1.000] |
  | vs. `task_teacher_v1` (promotion, seed 10000) | 50/100 | 0.970 | +6526.5 | **[0.730, 1.000]** |
  | vs. `roi_teacher_v3` (regression, seed 11000) | 20/40 | 1.000 | +32669.8 | [0.620, 1.000] |
  | vs. `starter` (regression, seed 11000) | 20/40 | 1.000 | +35613.4 | [0.620, 1.000] |

  The Hoeffding intervals are visibly wider than the old percentile
  bootstrap's degenerate `[1.000, 1.000]`/`[0.930, 1.000]` — correctly so,
  since they're honest about the real uncertainty in a 20-50 pair sample
  — but the promotion-gate lower bound (`0.730`) is still comfortably
  above 0.50, exactly as Codex predicted in §12.2 ("likely still
  decisively above 0.50 under a conservative bounded-score interval").
- **Outcome: `task_teacher_v2`'s promotion to `competitive_champion`
  holds** under the corrected end-of-day hiring behavior and the
  corrected, non-degenerate confidence interval. Per Codex's §12.3
  disposition, promotion was treated as provisional until this
  re-measurement confirmed the lower bound above 0.50 — it does.

- **Codex verification round, third pass (2026-08-02):** Codex
  independently verified the §12 fixes above (confirmed correct) and found
  one further narrow defect (see `2026-08-01-task-teacher-v2-design.md`
  §14), verified before acting on it: `_count_immediately_completing_tasks`
  counted any on-target `PLANT`/`WATER`/`HARVEST` assignment as completing
  this turn, but `resolve_unit_action` only actually plants when a matching
  seed is held — otherwise it emits `PASS` and queues a deferred
  `BUY_SEED`, completing nothing. Reproduced directly: an on-target `PLANT
  MELON` assignment with zero held `MELON` seeds was still counted,
  understating `future_load` by one and able to suppress a marginally
  justified hire.
- **Fix (2026-08-02):** `_count_immediately_completing_tasks` now takes
  `seeds_remaining` and only counts an on-target `PLANT` when its crop's
  count is positive, consuming a local copy in farmer-then-hands order (the
  same order `resolve_unit_action` consumes the real one) so two on-target
  `PLANT` assignments sharing one scarce seed aren't both counted;
  `WATER`/`HARVEST` are unaffected (generated tasks are already
  legality-filtered, no consumable resource involved). Built test-first:
  four direct unit tests (zero seed excludes; one matching seed includes;
  two on-target assignments sharing one seed count once, not twice; seed
  counts are independent per crop) plus one agent-level boundary test
  tuned so incorrectly crediting a seedless `PLANT` would suppress a hire
  that correctly excluding it still justifies. Also hardened `hoeffding_ci`
  per Codex's §14.2 request: rejects non-finite or out-of-[0,1] pair
  scores with a clear `ValueError` (defensive, since `run_pair` currently
  only ever produces `{0, 0.5, 1}` — doesn't change any reported result,
  but the function is shared infrastructure other callers may use later).
- **Refreshed telemetry, per §14.3's disposition** ("escalate to the full
  promotion rerun only if behavior or screen results change materially;
  otherwise record equivalence and retain the existing promotion
  evidence"): 100-episode acceptance gate (100/100 `DONE`/finite,
  deterministic, max hands active/episode min 4, max 5, avg 5.0, and avg
  71.6 `HIRE` orders — both essentially unchanged from the prior round's
  4.9/70.4) and a 20-pair
  screen vs. `task_teacher_v1` (0.950 win rate, Hoeffding CI
  `[0.570, 1.000]` — a one-pair difference from the prior round's 1.000,
  well within ordinary seed-to-seed variance given a different seed was
  used, not a behavior change). Neither is materially different from the
  prior round; **the existing 50-pair promotion evidence
  (CI `[0.730, 1.000]`) is retained rather than re-run**, per Codex's own
  stated criterion.
- **Packaging:** re-verified standalone (`PYTHONPATH` stripped) after the
  performance fix; all four existing agents (`roi_teacher_v1-v3`,
  `task_teacher_v1`) re-packaged and re-verified alongside it.
- **Kaggle runtime verification (2026-08-02):** after the recalibration
  attempt/revert above, packaged the current build and pushed a dedicated
  kernel (`notebooks/01_task_teacher_v2_verification.ipynb`,
  `tuannm3812/kaggriculture-task-teacher-v2-verification`) that runs the
  identical packaged artifact (verified by SHA-256) at a fixed seed on
  Kaggle's actual kernel infrastructure and asserts the rewards match a
  local reference run exactly. Result: `kaggle_environments==1.29.3` on
  Kaggle (matching the local pin) and byte-for-byte identical rewards both
  seats (`seed=99999`, `episodeSteps=240`): seat A
  `[["DONE", 2702.0], ["DONE", 2038.0]]`, seat B
  `[["DONE", 2035.0], ["DONE", 2697.0]]` — "VERIFICATION PASSED". This is
  platform-runtime verification only (mirrors
  `00_platform_smoke_test.ipynb`'s scope), not a competition submission.
- **Competition submission (2026-08-06):** explicitly authorized by the
  user — re-packaged (`scripts/package_agent.py`, fresh standalone
  verification: both players `DONE`, finite rewards), full test suite
  re-run clean (296 passed), then submitted via
  `kaggle competitions submit kaggriculture -f build/task_teacher_v2/main.py`.
  Status `PENDING` as of submission (`kaggle competitions submissions
  kaggriculture`); not yet `scored`. Rationale: with ~8 weeks to the
  deadline and zero submissions banked, real ladder feedback (submission-
  slot/ranking rules, actual opponent pool — both open items in
  `docs/1_competition_instructions.md`) is worth more than continuing to
  wait for `task_teacher_v3` or BC/PPO progress; those continue in
  parallel and may produce later resubmissions. This is a deliberate
  "get on the board now" decision, not a claim that `task_teacher_v2` is
  the final agent.
- **Ladder result:** `PENDING` at submission (2026-08-06), later found to
  be `SubmissionStatus.ERROR` (see incident below). Resubmitted after the
  fix; see the incident entry for current status.

- **Production incident (2026-08-06): submission errored on Kaggle,
  root-caused and fixed.** The `kaggle competitions submissions
  kaggriculture` status changed to `SubmissionStatus.ERROR`. The Kaggle
  submissions UI's summary row gave no detail; the user opened the
  submission's own page and pasted its replay/stderr log, which showed
  the real traceback:

  ```
  File "/kaggle_simulations/agent/main.py", line 34, in <module>
      replay_compat = _register_shared_module('kaggriculture_lib.replay_compat', ...)
  File "kaggriculture_lib/replay_compat.py", line 15, in <module>
  RuntimeError: compatibility evaluation requires kaggle-environments==1.29.3; found 1.32.4
  ```

  Root cause: `scripts/package_agent.py`'s `_discover_shared_modules`
  bundled **every** `.py` file under `src/kaggriculture_lib/`
  unconditionally — `package()` never filtered by what the agent's own
  `main.py` actually imports. That was invisible while the directory
  only held `economy.py`/`tasking.py` (the only two `task_teacher_v2`
  needs), but the separate, later Elite Replay EDA work added
  `replay_provenance.py`, `replay_schema.py`, `replay_compat.py`,
  `replay_metrics.py`, `replay_splits.py` to the same directory.
  `replay_compat.py` hard-fails at import time
  (`if kaggle_environments.__version__ != "1.29.3": raise RuntimeError`)
  — a reasonable guard in its own context (protecting replay evaluation
  from running under an incompatible runtime), but bundling it into an
  agent that never calls it is enough to crash that agent on import,
  before it ever takes a turn, the instant the runtime isn't an exact
  version match. This also surfaced a second fact: Kaggle's actual
  submission-validation runtime is `kaggle_environments==1.32.4` — newer
  than the `1.29.3` the 2026-08-02 notebook-kernel verification
  (`notebooks/01_task_teacher_v2_verification.ipynb`) had confirmed;
  that verification apparently ran on a different Kaggle infra image
  than live submission validation does.

  Fixed test-first (branch `fix/package-agent-scope-shared-modules`):
  added `test_package_only_bundles_modules_the_agent_transitively_imports`
  (a stub module with an import-time `RuntimeError`, asserted absent from
  the packaged output unless referenced) — confirmed it failed for the
  right reason (`assert "unrelated_with_side_effect" not in generated`
  found it present), then restricted `_discover_shared_modules`'s
  returned list to the transitive closure of what `agent_src` references
  via `from kaggriculture_lib import ...`, computed within the existing
  topological order. Circular-dependency detection still runs over the
  *entire* directory regardless of agent (a circular shared-module
  dependency is a library bug on its own), only the final returned list
  is filtered. Full suite: 297 passed (296 + the new regression test).
  Re-packaged and re-verified all four existing agents standalone;
  `build/task_teacher_v2/main.py` now bundles only `economy`+`tasking`.

  **Lesson:** local packaging tests all ran under this repo's pinned
  `.venv` (`kaggle_environments==1.29.3` exactly), so `replay_compat.py`'s
  guard never fired locally — the bug was only reachable on Kaggle's
  actual runtime, which turned out to differ from what the last
  runtime-parity check had measured. A version-pinned safety guard in one
  module can silently weaponize an unrelated packaging bug in a totally
  different subsystem; "no agent imports this" is not the same guarantee
  as "no agent's packaged artifact contains this."

  **Resubmitted** (2026-08-06, `kaggle competitions submissions
  kaggriculture`): the fixed `build/task_teacher_v2/main.py` (SHA-256
  `451ad135bd79c2e24afc566e908c3dc4e74d9ab58783b8c1367f2c84cab82daf`,
  bundles only `economy`+`tasking`) cleared validation and reached
  `SubmissionStatus.COMPLETE`. As of 2026-08-07: 8W-11L over 19 real
  ladder episodes, `publicScore` 488.9 (down from 537.6 at the 12-episode
  mark, declining as sample size grows). Full replay-level analysis of
  three representative episodes in
  [`docs/8_ladder_replay_analysis.md`](8_ladder_replay_analysis.md):
  losses correlate almost entirely with opponents who bought land and
  used animals (neither of which `task_teacher_v2` can do), while the one
  deep-analyzed win was against a similarly land/animal-less opponent —
  see that doc for the full evidence and recommendation to prioritize
  land + animals as the next version's scope.

- **Lesson carried forward:** synthetic unit tests validated every
  individual function correctly, but neither the runaway-hiring bug nor
  the performance bug was visible until a *real, full-length simulator
  run* — full-episode smoke runs before declaring a version done are not
  optional, even with thorough unit test coverage. A second, distinct
  lesson from this same version: a library-level fix with passing unit
  tests is not evidence the fix is *wired in* — when a symptom a fix was
  supposed to eliminate persists unchanged afterward, that persistence is
  itself a signal to investigate, not a data point to rationalize. A
  third: win rate/game outcomes, not money margin, decide promotion —
  positive mean margin over a small, unreplicated sample is not
  promotion evidence on its own. A fourth, from the follow-up round: a
  statistical tool that degenerates to false certainty on convenient
  (all-win) data is itself a bug worth the same scrutiny as application
  code — "the interval is [1.000, 1.000]" felt like strong evidence
  precisely because it was wrong, not because the underlying result was
  actually that certain. And a fifth: an alarming timing regression
  (18 steps/sec vs. an established ~550 steps/sec baseline) turned out to
  be CPU contention from running two full-simulation background jobs
  concurrently, not a code regression — confirmed by re-measuring in
  isolation before investigating the application code, rather than
  assuming the worst from the first number seen. And a sixth, from the
  third review round: a helper that mirrors another function's real
  behavior (`resolve_unit_action`'s seed check) needs to mirror *all* of
  it, not just the part that was top of mind (on-target-ness) — the
  seedless-`PLANT` gap wasn't caught by the tests written for the
  end-of-day fix because none of them happened to involve a `PLANT` task,
  only `WATER`, so the gap in scope went untested rather than
  deliberately excluded.

- **BC-teacher-readiness measurements (2026-08-02)**, per Codex's §16
  items 4-5 (`docs/6_next_steps.md` items 14-15) — not promotion gates,
  but measured before treating v2's output as imitation-learning ground
  truth:
  1. **Assignment-quality gap, exhaustive vs. greedy fallback** (30
     episodes, seeds 20000–20029; `tasking.joint_assign`'s exhaustive
     search factored out into `_exhaustive_assign` so it could be invoked
     directly on real 5+-unit states past `MAX_EXHAUSTIVE_UNITS`, purely
     for this offline measurement — a pure refactor, all 232 tests stayed
     green throughout): 1086 real states captured. The greedy fallback
     matched the exact exhaustive-optimal assignment only 74/1086 (6.8%)
     of the time, but tier-coverage loss and expected-value loss vs.
     optimum were both exactly zero on every single state — the entire
     measured gap is extra travel distance (mean 3.089 tiles/turn, max
     17). Reassuring: BC from v2 would not learn a systematically worse
     *economic* policy from the fallback, only a somewhat less
     travel-efficient one.
  2. **Hiring-constant calibration** (20 episodes, seeds 21000–21019):
     `TRAVEL_ALLOWANCE` (assumed 4) measured mean 7.51 turns/unit/day (max
     19) — corroborated independently by measurement 1's extra-travel
     finding. `END_OF_DAY_RESERVE` (assumed 2) measured mean 1.23
     turns/unit/day (max 21, high variance). `AVERAGE_VALUE_PER_RECOVERED_ACTION`
     (assumed $15.0) measured mean $65.26/field-action (range
     [$57.86, $72.17] across episodes) — real net money change per
     `WATER`/`PLANT`/`HARVEST`/`DIG` action, avoiding any need to
     reconstruct per-order sale pricing. `TRAVEL_ALLOWANCE` and
     `AVERAGE_VALUE_PER_RECOVERED_ACTION` are both substantially
     underestimated (~1.9x and ~4.3x respectively) versus real play.
- **Recalibration attempt and revert (2026-08-02):** the user asked to act
  on the hiring-constant measurement above. Recalibrated test-first
  (`TRAVEL_ALLOWANCE` 4→8, `AVERAGE_VALUE_PER_RECOVERED_ACTION` 15.0→65.0;
  `END_OF_DAY_RESERVE` left unchanged, per the "roughly in range" finding),
  then ran the full fix-test-reevaluate cycle this required:
  - **100-episode acceptance gate:** hiring became substantially more
    aggressive as expected — avg 110.7 `HIRE` orders/episode (up from
    70.4-73.4) and a flat 7 max hands active (up from 4.9-5.0), since the
    higher $/action made hiring look far more attractive against the
    fibonacci-scaled cost.
  - **Paired evaluation vs. `task_teacher_v1`:** this is where it went
    wrong. 20-pair screen: win rate dropped to 0.850 (from a clean 1.000),
    Hoeffding CI `[0.470, 1.000]` — straddling 0.50, not wholly above it.
    Escalated to the 50-pair promotion scale rather than stopping on an
    ambiguous screen: win rate dropped *further* to 0.750, CI
    `[0.510, 0.990]` — barely clearing 0.50, a razor-thin margin versus the
    original constants' `[0.730, 1.000]`. Win rate declining monotonically
    as sample size grew (1.000 → 0.850 → 0.750) is the signature of a real
    effect, not noise.
  - **Root cause:** the $65.26/action figure was measured under the
    *original* (less-aggressive) hiring behavior. Plugging it back in
    didn't just correct a number — it changed the equilibrium: aggressive
    hiring escalates the fibonacci-scaled hire cost fast, pushes unit count
    well past `MAX_EXHAUSTIVE_UNITS` into greedy-fallback territory (whose
    only real cost, per the assignment-quality-gap measurement above, is
    extra travel — now paid by more units, more often), and neither of
    those costs were reflected in a $/action figure measured under a
    calmer hiring regime. A single-shot point measurement doesn't account
    for its own feedback effect on the behavior it's meant to calibrate.
  - **Reverted:** `TRAVEL_ALLOWANCE` back to 4, `AVERAGE_VALUE_PER_RECOVERED_ACTION`
    back to 15.0. Confirmed the revert restores the previously-verified
    behavior with a fresh 20-pair screen (seed 16000): win rate 0.950, mean
    margin +6457.5, CI `[0.570, 1.000]` — consistent with the
    already-established promotion evidence. `task_teacher_v2`'s existing
    promotion (50-pair CI `[0.730, 1.000]` from the original constants)
    was never actually at risk; this was a same-session experiment that
    didn't pan out, caught by the same full-gate discipline that's caught
    every other regression this project has found.
  - **Lesson:** "measure before fixing the number" isn't enough on its own
    when the number being fixed influences the very behavior it was
    measured from — a calibration constant that feeds back into the
    system it calibrates needs to be validated at the *new* operating
    point it induces, not just accepted from a measurement taken at the
    old one. The assignment-quality-gap measurement (item 15) is
    unaffected by any of this — it changed no constants, only added
    read-only measurement tooling (`_exhaustive_assign`), and stands as
    previously recorded.

## task_teacher_v3 (`agents/task_teacher_v3/main.py`)

- **Date:** 2026-08-06
- **Extends `task_teacher_v2` with:** ongoing crops (Tomato, Strawberry),
  per the approved design in
  `docs/superpowers/specs/2026-08-02-task-teacher-v3-design.md`. Same
  hiring and multi-unit assignment as v2 (unchanged); no animals,
  fertilizer, or `PICKUP`/`PLACE`. `agents/task_teacher_v3/main.py` differs
  from `agents/task_teacher_v2/main.py` by exactly the docstring and
  `CANDIDATE_CROPS` (verified via direct diff) — all real logic lives in
  the shared `economy.py`/`tasking.py`, gated on
  `economy.CROPS[crop]["ongoing"]` so `task_teacher_v2`'s own behavior is
  provably unaffected (its `CANDIDATE_CROPS` never includes an ongoing
  crop, so the new dispatch branches never fire for it).
- **Built by Cursor** (first task handed to it under the new
  Cursor-implements/Claude-reviews workflow), test-first, per
  `docs/superpowers/plans/2026-08-02-task-teacher-v3-implementation.md`.
  Reviewed independently: every diff matches the approved plan verbatim
  (no shortcuts, no weakened assertions), `task_teacher_v2`'s own files
  are byte-identical to `main`, and a live 720-step episode confirmed
  ongoing crops are genuinely planted and repeatedly harvested (62
  `HARVEST` actions across ~25 tiles in one episode). Cursor correctly
  stopped before the acceptance/evaluation gate, as instructed, rather
  than self-reporting a promotion claim.
- **Acceptance-gate measurement** (100 full 720-step episodes vs.
  `starter`, seeds 50000–50099):

  | Metric | Result |
  | --- | --- |
  | `DONE` both players | 100/100 |
  | Invalid/non-finite episodes | 0 |
  | Distinct tiles worked/episode | range [23, 25] |
  | Action-kind coverage | `PLANT`=1703, `WATER`=26130, `HARVEST`=3011, `DIG`=1372 |
  | Ongoing-crop `PLANT` actions | 698 |
  | `HARVEST`/ongoing-crop-plant ratio | 4.31 (repeated harvesting confirmed, not one-and-done) |
  | Inference latency (ms/turn) | median 1.74 |
  | Determinism (same seed, 2 runs) | identical rewards |

  Clean pass — the mechanics work exactly as designed.
- **Paired evaluation vs. `task_teacher_v2`** (20-pair screen, seed 60000):
  `win_rate=0.025`, `mean_money_margin=-9216.5`, Hoeffding 95% CI
  `[0.000, 0.405]` — **decisively below 0.50**. Per the authoritative
  protocol, a screen this unambiguous stops here; no escalation to 50
  pairs, no regression screens run against a result already known to be
  wrong.
- **Root cause, confirmed by direct investigation, not assumed:** a real
  scoring bug in `tasking._score_ongoing_crop`'s `lifespan_days`
  denominator — `reachable[-1] - reachable[0] + 1` (the span *between* the
  first and last reachable production tick) instead of the correct
  `reachable[-1] + 1` (days from *planting* through the last reachable
  tick, mirroring `_score_crop`'s `max_yield_day + 1` convention exactly).
  This is a design error in `2026-08-02-task-teacher-v3-design.md` §4, not
  an implementation deviation: Cursor built `_score_ongoing_crop` exactly
  as specified, and the specification was wrong. Measured impact: at
  `current_day=0`,
  Strawberry's buggy score is `54.29` vs. the corrected `22.35` (a ~2.4x
  inflation, and the corrected score sits *below* Melon's `109.23`, not
  above it) — late-season the inflation gets worse (~4.3x at one checked
  boundary case, 2 of 4 ticks reachable). A representative game showed v3
  planting Strawberry 34 times vs. Melon only 22 times, and losing by
  ~$9,700 to `task_teacher_v2` as a direct result. See
  `2026-08-02-task-teacher-v3-design.md` §8 for the full account and the
  required fix.
- **Outcome (2026-08-06 buggy formula): not promoted.** `task_teacher_v2`
  remains `competitive_champion`. Mechanics were sound; only the crop-
  scoring formula needed the §8 one-line fix, followed by a fresh Task 9
  evaluation.
- **§8 lifespan fix (2026-08-07, Cursor):** changed
  `tasking._score_ongoing_crop`'s `lifespan_days` from
  `reachable[-1] - reachable[0] + 1` to `reachable[-1] + 1`. Added
  regression test
  `test_best_feasible_crop_picks_melon_over_strawberry_at_base_prices`;
  updated ongoing-crop unit tests whose expected rankings assumed the
  inflated Tomato score. Full suite: 316 passed.
- **Post-fix re-evaluation (2026-08-07)** — supersedes the 2026-08-06
  screen above; same protocol, fresh seeds per the implementation plan:

  | Metric | Result |
  | --- | --- |
  | Acceptance `DONE` / finite (seeds 50000–50099) | 100/100 / 100/100 |
  | Distinct tiles worked/episode | range [23, 25] |
  | Action-kind coverage | `PLANT`=1676, `WATER`=25242, `HARVEST`=2201, `DIG`=1827 |
  | Ongoing-crop `PLANT` actions | **0** (Melon correctly dominates at competitive prices) |
  | Inference latency (ms/turn) | median 1.73 |
  | Determinism | identical rewards |

  | Matchup | Pairs | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v2` (screen, seed 40000) | 20/40 | 0.500 | +0.0 | [0.120, 0.880] |
  | vs. `task_teacher_v2` (promotion, seed 41000) | 50/100 | 0.500 | +0.0 | [0.260, 0.740] |
  | vs. `roi_teacher_v3` (regression, seed 42000) | 20/40 | 1.000 | +31970.9 | [0.620, 1.000] |
  | vs. `starter` (regression, seed 42000) | 20/40 | 1.000 | +34745.8 | [0.620, 1.000] |

  The vs-v2 result is exact behavioral identity under these seeds
  (`win_rate=0.500`, `mean_money_margin=+0.0` at both 20 and 50 pairs):
  with the corrected denominator, Melon's static score (~109) beats
  Strawberry (~22) and Tomato (~16) whenever Melon is feasible, so v3's
  extended `CANDIDATE_CROPS` never changes the chosen crop relative to
  v2. Promotion requires a Hoeffding CI wholly above 0.50 — not met.
  Regression screens vs. `roi_teacher_v3` / `starter` remain clean and
  in line with v2's own recorded margins against the same opponents.
- **Outcome (post-fix): still not promoted.** `task_teacher_v2` remains
  `competitive_champion` and the submitted ladder agent. v3's mechanics
  and corrected economics are sound, but adding ongoing crops to the
  candidate set does not improve (or change) play against v2 under the
  current day-aware ROI ranking at observed prices.
- **Ladder result:** not applicable (not promoted; `task_teacher_v2`
  remains the submitted agent).
- **Lesson carried forward:** the acceptance gate (100 episodes, all
  green) gave zero signal that anything was wrong under the buggy formula —
  mechanical correctness and economic correctness are different questions,
  and only the paired evaluation against a real opponent surfaced the
  problem. After the fix, the same gate's "ongoing-crop PLANT count"
  signal flipped from 698 → 0 for the right economic reason (Melon wins),
  while the vs-v2 screen flipped from decisive loss to exact tie — both
  are useful signals. Holding evaluation back as an explicit review
  checkpoint is what caught the bug before it shipped as an undiagnosed
  "promotion."

## task_teacher_v4 (`agents/task_teacher_v4/main.py`)

- **Date:** 2026-08-10
- **Extends `task_teacher_v2` with:** ROI-gated NE `BUY_LAND` and a Goose
  loop (`BUILD_COOP` / `BUY_ANIMAL` / `PICKUP` / `PLACE` / `FEED` / `CARE` /
  harvest+sell `EGG`), per
  `docs/superpowers/specs/2026-08-10-task-teacher-v4-design.md`. Shared
  lib adds `shed_access_tiles`, `wheat_reserved_for_feed`, `should_buy_land`,
  and new `TaskKind`s. Existing agent mains untouched.
- **Built** test-first on `feat/task-teacher-v4` (Tasks 1–8); NE coverage
  tests added before Task 9 for design §7.4. Full suite green before eval.
- **Acceptance-gate measurement** (100×720 vs `starter`, seeds 70000–70099):

  | Metric | Result |
  | --- | --- |
  | `DONE` / finite | 100/100 / 100/100 |
  | Determinism (seed 70000 ×2) | identical |
  | Mean agent / starter reward | 114.63 / 2514.02 |
  | Unit coverage | `BUILD_COOP`=100, `PICKUP:GOOSE`=399, `PLACE`=399, `FEED`=15565, `PLANT`=1393, `WATER`=9726, `HARVEST`=974 |
  | Market coverage | `BUY_LAND`=**0**, `BUY_ANIMAL:GOOSE`=3757, `HIRE`=2258, `SELL`=201 |
  | Latency ms/turn (median) | 1.32 |

  Mechanics fire for coop/pickup/place/feed, but land never buys and animal
  purchases are orders of magnitude above `MAX_GEESE=2`.
- **Paired evaluation** (no 50-pair escalation — screen CI wholly below 0.50):

  | Matchup | Pairs | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v2` (screen, seed 71000) | 20/40 | **0.000** | -38807.6 | **[0.000, 0.380]** |
  | vs. `roi_teacher_v3` (regression, seed 73000) | 20/40 | 0.000 | -5223.3 | [0.000, 0.380] |
  | vs. `starter` (regression, seed 73000) | 20/40 | 0.000 | -2400.6 | [0.000, 0.380] |

- **Root cause (confirmed, not assumed):** `geese_count` only counts animals
  already on farm tiles. Env `BUY_ANIMAL` deposits the Goose into
  `private["shed"]`, so after the first buy the agent still sees
  `geese_count=0` and re-emits `BUY_ANIMAL` every turn while cash remains —
  burning the budget that `should_buy_land` and seed ROI need. Secondary
  symptom: `BUY_LAND=0` across 100 acceptance episodes.
- **Outcome: not promoted.** `task_teacher_v2` remains `competitive_champion`
  and the submitted ladder agent. Fix path for a later v4.1 / Task 9 re-run:
  count shed + inventory geese toward `MAX_GEESE` (and stop buying when
  in-flight animals already fill the cap), then re-run the full protocol
  on fresh seeds.

### Post-fix re-evaluation (2026-08-10, buy-cap fix)

- **Fix:** `_owned_goose_count` = placed + shed + inventory; `BUY_ANIMAL` /
  `want_coop` use that cap. Regression tests cover shed-full / placed+shed /
  inventory-fill. Commit `1ce02bb`.
- **Acceptance** (100×720 vs `starter`, seeds **74000–74099**):

  | Metric | Result |
  | --- | --- |
  | `DONE` / finite | 100/100 / 100/100 |
  | Mean agent / starter reward | **27379** / 2514 |
  | `BUY_LAND` | **0** |
  | `BUY_ANIMAL:GOOSE` | 1171 (~11.7/ep; geese turnover, not uncapped spam) |
  | Goose loop | `BUILD_COOP`=100, `PLACE`=1079, `FEED`=25876, `CARE`=10 |
  | Determinism | identical |

- **Paired evaluation** (fresh seeds; no 50-pair — screen CI wholly below 0.50):

  | Matchup | Pairs | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v2` (screen, seed 75000) | 20/40 | **0.000** | -10196.5 | **[0.000, 0.380]** |
  | vs. `roi_teacher_v3` (regression, seed 77000) | 20/40 | 1.000 | +20977.3 | [0.620, 1.000] |
  | vs. `starter` (regression, seed 77000) | 20/40 | 1.000 | +23906.1 | [0.620, 1.000] |

- **Outcome: still not promoted.** Beats starter/roi_v3 cleanly after the
  buy-cap fix, but loses every pair to `task_teacher_v2`. Champion remains
  `task_teacher_v2`.
- **Remaining gap (land):** live probe (seed 74000) shows
  `should_buy_land` blocked every turn by `plant_tile_count <
  NW_SATURATION_PLANTS` (18) — Melon-heavy play never holds 18 concurrent
  PLANT tiles on NW. Goose economics alone are not enough to beat v2 under
  these seeds; land never unlocks. Next iteration should retune the
  saturation predicate (or measure peak concurrent plants under v2/v4) before
  another promotion attempt.

### Post-saturation retune (2026-08-10, NW_SATURATION_PLANTS 18→12)

- **Evidence:** Melon-heavy peaks of 16–20 concurrent plants arrive around
  day 19+, after `LAND_MIN_DAYS_REMAINING=12` already fails. Probe: floor
  12 + unchanged hire_v==0 fires land in 10/10 seeds.
- **Acceptance** (seeds **78000–78099**): 100/100 DONE; mean reward
  **28108** vs starter **2515**; **`BUY_LAND=100`** (1/ep); Goose loop intact.
- **Paired evaluation:**

  | Matchup | Pairs | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v2` (screen, seed 79000) | 20/40 | **0.000** | -9300.4 | **[0.000, 0.380]** |
  | vs. `roi_teacher_v3` (regression, seed 80000) | 20/40 | 1.000 | +21495.9 | [0.620, 1.000] |
  | vs. `starter` (regression, seed 80000) | 20/40 | 1.000 | +24528.8 | [0.620, 1.000] |

- **Outcome: still not promoted.** Land purchase now works in live play,
  but v4 remains strictly worse than v2 under the Hoeffding screen. Do not
  submit. Next: diagnose *why* NE+Goose loses to NW-only Melon/hire (egg
  ROI vs Melon opportunity cost; FEED labor; CARE near-absent) before
  further gate tuning.

## task_teacher_v5 (`agents/task_teacher_v5/main.py`)

- **Date:** 2026-08-11
- **Extends `task_teacher_v2` with:** ROI-gated NE `BUY_LAND` only.
  `MAX_GEESE = 0` — no Goose path. Motivated by the v4 ablation where
  land-only beat v2 (~0.75 WR / 10 pairs) while full land+Goose lost.
  `task_teacher_v4` left immutable (not promoted).
- **Acceptance** (100×720 vs `starter`, seeds 82000–82099):

  | Metric | Result |
  | --- | --- |
  | `DONE` / finite | 100/100 / 100/100 |
  | Mean agent / starter | **40900** / 2513 |
  | `BUY_LAND` | **100** |
  | `BUY_ANIMAL` | **0** |
  | Determinism | identical |

- **Paired evaluation:**

  | Matchup | Pairs | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v2` (screen, seed 83000) | 20/40 | 0.825 | +3465.3 | [0.445, 1.000] (straddle → escalate) |
  | vs. `task_teacher_v2` (promotion, seed 84000) | 50/100 | **0.780** | +3036.2 | **[0.540, 1.000]** |
  | vs. `roi_teacher_v3` (regression, seed 85000) | 20/40 | 1.000 | +35982.9 | [0.620, 1.000] |
  | vs. `starter` (regression, seed 85000) | 20/40 | 1.000 | +39044.6 | [0.620, 1.000] |

- **Outcome: promoted.** CI wholly above 0.50 at the 50-pair gate.
  `task_teacher_v5` is the new `competitive_champion`. Ladder submit is
  authorized by the promotion protocol (user may still choose timing).
- **Ladder result (2026-08-11):** submitted via **notebook** path (not raw
  `main.py` CLI). Kernel
  `tuannm3812/kaggriculture-task-teacher-v5-submission` v1 wrote
  `submission.tar.gz` (packaged SHA-256
  `108bd781bf5a46517995a2902fce2bba29aca5ba86c3a959e0869a7ad8913271`);
  competition submit ref **55425318**, `fileName=submission.tar.gz`,
  status **`COMPLETE`**. Score path: **423.9 → 444.2** at first replay
  check (v2 still tracked ~490). Smoke on Kaggle matched local verify
  rewards for seed `424242` / 96 steps (`1570` vs starter `1940`). Helper:
  `scripts/submit_agent_notebook.sh` +
  `scripts/build_agent_submission_notebook.py`.
- **Ladder replay check (2026-08-11, 17 public):** **8W-9L (47%)**.
  `BUY_LAND` **17/17** (always NE → 2Q), `BUY_ANIMAL` 0. vs land+animals
  **2W-4L (33%)**; vs land-only 3W-3L; two losses to NW-only crop bots from
  **day-1 land cash starvation**. Deep losses still to 3–4Q + cow/sheep
  compounds. Full table:
  `docs/8_ladder_replay_analysis.md` (2026-08-11 refresh).

## task_teacher_v6 (`agents/task_teacher_v6/main.py`)

- **Date:** 2026-08-11
- **Extends `task_teacher_v5` with:** a higher `budget_reserve` passed to
  `should_buy_land` (`LAND_BUDGET_RESERVE_V6 = 2000` vs. the shared-library
  default of 400). Motivated by the ladder replay claim that v5 buys NE on
  **day 0/1** and cash-starves Melon (`docs/8_ladder_replay_analysis.md`).
  Otherwise copy-forward of v5: `MAX_GEESE = 0`, NE-only land, no animals.
  `task_teacher_v5` and earlier left immutable.
- **Acceptance** (100×720 vs `starter`, seeds 86000–86099):

  | Metric | Result |
  | --- | --- |
  | `DONE` / finite | 100/100 / 100/100 |
  | Mean agent / starter | **40886** / 2515 |
  | `BUY_LAND` | **100** |
  | `BUY_ANIMAL` | **0** |
  | Determinism | identical |
  | First `BUY_LAND` day (post-action obs histogram) | day 15×72, day 16×28 |

- **Paired evaluation:**

  | Matchup | Pairs | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v5` (screen, seed 87000) | 20/40 | 0.500 | +0.0 | [0.120, 0.880] (straddle → escalate) |
  | vs. `task_teacher_v5` (promotion, seed 88000) | 50/100 | **0.500** | +0.0 | **[0.260, 0.740]** |
  | vs. `task_teacher_v2` (regression, seed 89000) | 20/40 | 0.850 | +3230.8 | [0.470, 1.000] |
  | vs. `starter` (regression, seed 89000) | 20/40 | 1.000 | +38191.0 | [0.620, 1.000] |

- **Outcome: not promoted.** CI straddles 0.50; honesty rule — no
  force-promote. `task_teacher_v5` remains `competitive_champion` / ladder
  agent. `LAND_BUDGET_RESERVE_V6=2000` needed no 1500 fallback
  (`BUY_LAND>0` on acceptance).
- **Post-eval correction (whole-branch review):** under the **local**
  harness, v6 is **behaviorally identical** to v5. Spot-check seeds
  86000–86002: byte-identical seat-0 action streams, identical rewards,
  same first-buy observation day. When NW saturation (12) + min hands (3)
  first open (~day 14–15), the bank is already well above both the v5
  ($1400) and v6 ($3000) cash bars, so `budget_reserve=2000` never binds.
  The exact `win_rate=0.500` / `margin=+0.0` at 20 **and** 50 pairs is
  **policy identity**, not “later buy converges to the same money.” The
  ladder day-0/1 baseline in docs/8 was incorrectly contrasted with v6’s
  local day-15 histogram — that is not a local v5-vs-v6 delay measurement.
  Next work should reconcile ladder day-1 NE unlock vs local day-~15 buy
  (attribution bug vs env mismatch) before any further reserve sweep —
  see `docs/6_next_steps.md`.

## `task_teacher_v8` (2026-08-13) — hire helpers + gated SW; **not promoted**

- **Extends v5 with:** `max_extra_quadrants=2` (NE then SW @
  `SW_BUDGET_RESERVE_V8=3000`); additive `should_hire(hire_cost_mult=…)` /
  `economy.hire_cost_mult`. Agent keeps **decision** hire mult=10 (ladder
  mult=1 without a daily spend model re-hires to cap every day after
  hand clear → first screen WR 0.000).
- **Acceptance** (ladder-match, 20×720): DONE; NE cause-day 0; SW ~90%
  episodes ~day 15; no animals.
- **Paired (ladder-match):** vs v5 20-pair seed 97400 → **WR 0.300**,
  margin −$1626, CI `[0.000, 0.680]` — stop. Do not submit.
- **Lesson:** third quadrant without animals (or a better labor model)
  does not beat focused NE Melon locally; next research = S2 animals
  under ladder-match, not more land alone.

## Ladder-config reconciliation (2026-08-13)

- Live ladder replays use `startingMoney=3000`, `farmHandCostMult=1` (not
  1.29.3 `make()` defaults of 2000/10). Helper:
  `kaggriculture_lib.env_config`; `run_tournament.py` defaults to
  ladder-match.
- Under ladder-match: v5 land cause-day **0** (matches 29/29 public);
  v6 reserve **binds** (cause-day ~13–14) but **loses** 20-pair vs v5
  (`WR=0.300`, CI `[0.000, 0.680]`, seed 96000) — still not promoted.
- Full write-up: `docs/8_ladder_replay_analysis.md` (2026-08-13 section).

## `task_teacher_v7` (2026-08-13) — Cow/pasture/milk on v5; **not promoted**

- **Date:** 2026-08-13
- **Extends `task_teacher_v5` with:** bounded Cow loop (`MAX_COWS=6`,
  `MAX_FEED_ACTIONS_PER_DAY=6`, NE-gated buy/build, pasture task kinds in
  shared `tasking.py`). Spec:
  `docs/superpowers/specs/2026-08-13-task-teacher-v7-design.md`.
- **Acceptance probe** (20×720 vs `starter`, seed 91000; after NE-gate +
  FEED-tier fixes): DONE 20/20; mean ~29k; `BUY_LAND` 1.0/ep;
  `BUY_ANIMAL:COW` > 0; `FEED/day` ~4; no Goose.
- **Animal screen** (10×720): Melon sells still fire but below v5
  (~140 vs ~165 units/ep); milk sells stayed ~0 in early probes
  (placement/feed/inventory-assignment friction).
- **Paired evaluation:**

  | Matchup | Pairs | Win rate | Mean margin | Hoeffding 95% CI |
  | --- | ---: | ---: | ---: | --- |
  | vs. `task_teacher_v5` (seed 92000, pre-priority fix) | 20/40 | 0.050 | −11224 | [0.000, 0.430] |
  | vs. `task_teacher_v5` (seed 92100, post-priority/slot fix) | 20/40 | **0.000** | −17079 | **[0.000, 0.380]** |

- **Outcome: not promoted.** CI wholly below 0.50. Do **not** notebook-submit.
  Champion / ladder agent remains `task_teacher_v5` (`55425318`).
- **Lesson:** scaled animals need inventory-aware assignment + a working
  wheat→feed→milk revenue path; raising FEED/PLACE priority alone still
  taxes Melon harder than milk pays back under the local harness.
