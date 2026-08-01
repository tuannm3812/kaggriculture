# 3. Agent Strategy

## Static ROI Tables (at base market price, ignoring price-impact of own sells)

Computed via `src/kaggriculture_lib/economy.py` (tested against the real
environment's formulas, see `docs/2_environment_notes.md`). These assume
watering/feeding every day (no weeds/escapes) and harvesting once at the
end of the watering-bonus window to capture maximum accumulated yield —
the same policy `agents/roi_teacher_v1/main.py` implements for one-time
crops.

### One-time crops

| Crop | Seed cost | Bonus window (age, days) | Total units | Lifespan (days) | Revenue @ base | ROI/day @ base |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Wheat | 10 | [2, 4] | 4 | 5 | 100 | 18.00 |
| Carrot | 20 | [2, 3] | 3 | 4 | 105 | 21.25 |
| Melon | 80 | [6, 12] | 6 | 13 | 1500 | **109.23** |

**Finding:** Melon's ROI/day at base price is ~5–6x wheat/carrot's, despite
the higher upfront seed cost — the Object Types table's "Max yield/tile/day"
column undersells it because it measures raw yield, not yield × price.
Melon's market curve barely reacts to scarcity but crashes hard on glut
(`above_func: sq, above_target: 3.60`) — a real risk if several tiles sell
melons simultaneously into a shared market, but not a concern for a single-
tile agent selling a handful of units per ~13-day cycle. **Confirmed** by
`agents/roi_teacher_v2` (adds Melon as a candidate, one variable changed
from v1): beats v1 head-to-head at 1.000 win rate, +2222.8 mean money
margin, and roughly triples the margin against every built-in — see
`docs/4_agent_version_log.md`.

### Ongoing crops / animals (production schedule, not yet ROI-ranked)

| Crop/Animal | Cost | Product | Production days (age since planted/placed) | Unit price @ base |
| --- | ---: | --- | --- | ---: |
| Tomato | 50 | — | [8, 9, 10, 11] | 60 |
| Strawberry | 100 | — | [10, 12, 14, 16] | 120 |
| Goose | 300 | Egg | [4, 5, 6, 7] | 50 |
| Cow | 400 | Milk | [8, 10, 12, 14, 16, 18] | 160 |
| Sheep | 500 | Wool | [6, 9, 12, 15, 18, 21] | 200 |

Not yet ROI-ranked against the one-time crops above — ongoing crops/animals
run for the rest of the season once started (no fixed lifespan the way
one-time crops have), so a fair ROI/day comparison needs a season-length
assumption and feed-cost accounting (wheat consumption for animals), not
just a per-tick unit count. Per `docs/6_next_steps.md`'s 2026-08-01
reprioritization (Codex code review), this is now explicitly behind the
multi-tile teacher-coverage work in priority, not the next thing to build.

## v1/v2/v3 Scope (`agents/roi_teacher_v1`, `_v2`, `_v3`)

Deliberately minimal — single farmer, single tile (the spawn tile, no
movement), dynamic best-of-{wheat, carrot} (v1) or best-of-{wheat, carrot,
melon} (v2, v3) selection, always waters, never buys land/hands/animals.
v3 adds a season-horizon gate (never plants a crop that can't mature before
the episode ends — see `docs/4_agent_version_log.md`, a real gap Codex's
code review found in v1/v2). Rationale for staying single-tile this far:
get a genuinely-tested, ROI-aware baseline running today rather than
spending the first implementation session on multi-tile pathing before any
local-tournament evidence exists. Superseded as champion by
`task_teacher_v1` (below); kept as the immutable benchmark line and BC/
fallback-submission candidate.

## `task_teacher_v1` Scope (`agents/task_teacher_v1`)

New agent family, not a continuation of `roi_teacher_v*`'s numbering —
structurally different (multi-tile task generation/ranking/routing vs. a
single-tile ROI loop). Same crop scope as v2/v3 (Wheat/Carrot/Melon,
one-time crops only) but uses every tile in the initial unlocked (NW)
quadrant simultaneously via a deterministic task scheduler
(`src/kaggriculture_lib/tasking.py`): generates a `PLANT`/`WATER`/
`HARVEST`/`DIG` task per tile every turn, ranks by safety-tier first then
distance/value/hysteresis, and routes the farmer via greedy Manhattan
movement (confirmed no obstacles exist in this game). Result: a step
change, not an incremental one — roughly 10x `roi_teacher_v3`'s margins
(full numbers in `docs/4_agent_version_log.md`), from tile-count scaling
alone, without any smarter per-tile decision-making than v3 already had.

Built after multiple rounds of Codex design review (module boundaries,
typed task/state data model, deterministic ranking/routing contract,
explicit `TeacherState` reset semantics rather than relying on module-
reload behavior, an O(1) service-capacity check, the market-timing
constraint, and `sys.modules`-based packaging) and implemented test-first
end to end. Still narrow by design: one farmer, no hands/land/animals/
fertilizer — `task_teacher_v2→v6` add those incrementally per the agreed
construction sequence (`docs/6_next_steps.md`). Superseded as champion by
`task_teacher_v2`; kept as the immutable benchmark this result is measured
against.

## `task_teacher_v2` Scope (`agents/task_teacher_v2`) — Current Champion (promoted 2026-08-02)

Adds daily hiring and bounded exhaustive multi-unit assignment on top of
v1's task model — `src/kaggriculture_lib/tasking.py`'s `joint_assign`
scores every valid combination of (farmer + hands) × their own top-8
candidate tasks jointly, so an earlier-decided unit can't grab a task
purely by its own ranking when a later unit is actually better positioned
for it. Falls back to a fast deterministic greedy assignment once unit
count exceeds `MAX_EXHAUSTIVE_UNITS` (4) — the design's own anticipated
safety valve, needed in practice: real games commonly reach 7-8 active
hands. Hiring is gated on an explicit marginal-value estimate
(`should_hire`/`estimate_hire_value`) that must exceed the fibonacci-scaled
cost, discounted by capacity existing hands already provide — an earlier
version of this formula didn't discount for existing hands and approved
hire after hire indefinitely, found via a full simulator run (see
`docs/4_agent_version_log.md`).

An early hiring-value fix in `tasking.py` was correct but never actually
reached the running agent (a missing `existing_hands` argument at the call
site, confirmed by Codex's 2026-08-02 review) — this produced an initial,
premature "provisional champion" claim from an 8-pair sample with 2
losses and no confidence interval, which conflicted with the project's own
promotion rule (win rate/outcomes decide, margin is diagnostic only). After
fixing the wiring bug, the full paired-bootstrap protocol
(`docs/4_agent_version_log.md`) gave a 50-pair promotion-gate CI of
`[0.930, 1.000]` vs. `task_teacher_v1` — wholly above 0.50 — plus clean
20-pair regression sweeps vs. `roi_teacher_v3` and `starter`. This is a
legitimate, rigorously-established promotion, not a margin-based guess.

## Strategy Approach (unchanged from the design doc)

Per `docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md`'s
converged RL discussion: this heuristic serves as (a) a working ladder
submission, (b) the scripted teacher for behavioral cloning, (c) a
benchmark/fallback opponent for every later policy. It is not the intended
final champion architecture.
