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

### Ongoing crops / animals (production schedule)

| Crop/Animal | Cost | Product | Production days (age since planted/placed) | Unit price @ base |
| --- | ---: | --- | --- | ---: |
| Tomato | 50 | — | [8, 9, 10, 11] | 60 |
| Strawberry | 100 | — | [10, 12, 14, 16] | 120 |
| Goose | 300 | Egg | [4, 5, 6, 7] | 50 |
| Cow | 400 | Milk | [8, 10, 12, 14, 16, 18] | 160 |
| Sheep | 500 | Wool | [6, 9, 12, 15, 18, 21] | 200 |

**Tomato/Strawberry are now day-aware ROI-ranked** via
`tasking._score_ongoing_crop` (lifespan = last reachable tick offset + 1,
mirroring one-time `max_yield_day + 1` — see
`2026-08-02-task-teacher-v3-design.md` §8). At base prices with a full
season ahead: Melon ~109 ≫ Strawberry ~22 ≈ Carrot 21 > Wheat 18 >
Tomato ~16 — so the corrected ranking rarely (if ever) selects an
ongoing crop when Melon is still feasible. Animals are still not
ROI-ranked (need feed-cost accounting) and remain out of scope until a
`task_teacher_v4` design covers land/animals.

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
promotion rule (win rate/outcomes decide, margin is diagnostic only). A
second Codex review round then caught two further issues: an end-of-day
hiring-timing bug (a hire queued on the day's last hour recovers zero
future actions before hands clear at the day boundary) and a percentile
bootstrap confidence interval that gave false zero-width certainty on
all-win samples. After fixing both, the full paired evaluation with a
corrected Hoeffding confidence interval (`docs/4_agent_version_log.md`)
gave a 50-pair promotion-gate CI of `[0.730, 1.000]` vs. `task_teacher_v1`
— wholly above 0.50 — plus clean 20-pair regression sweeps vs.
`roi_teacher_v3` and `starter`. A third review round then found one
further narrow defect in the same end-of-day fix's helper (a seedless
`PLANT` counted as completing when it wouldn't actually resolve); fixed,
and refreshed telemetry showed no material change, so the 50-pair
evidence above stands. This is a legitimate, rigorously-established
promotion, not a margin-based guess.

## `task_teacher_v3` Scope (`agents/task_teacher_v3`) — built, not promoted

Extends v2's candidate set with Tomato/Strawberry and the shared
ongoing-crop dispatch in `economy.py`/`tasking.py` (feasibility,
day-aware scoring, `yield_units`-gated HARVEST). After the §8 lifespan
fix, re-evaluation vs. `task_teacher_v2` is exact identity under the
promotion seeds — Melon still wins the ranking whenever feasible — so
v3 does **not** displace v2 as Current Champion. Full numbers in
`docs/4_agent_version_log.md`.

## `task_teacher_v4` Scope (`agents/task_teacher_v4`) — built, not promoted

Extends v2 with ROI-gated NE land and a Goose loop. After buy-cap + sat=12
fixes, land fires but Goose FEED labor still loses every pair to v2.
Ablation: land-only ≈0.75 WR vs v2; full Goose path ≈0.05. Left as the
land+Goose experiment. Full numbers in `docs/4_agent_version_log.md`.

## `task_teacher_v5` Scope (`agents/task_teacher_v5`) — promoted

v2 + NE `BUY_LAND` only (`MAX_GEESE=0`). 2026-08-11: 50-pair vs v2
`win_rate=0.780`, Hoeffding CI `[0.540, 1.000]` — new local champion.
See `docs/4_agent_version_log.md`.

## `task_teacher_v6` Scope (`agents/task_teacher_v6`) — built, not promoted

v5 + a higher land `budget_reserve` (`LAND_BUDGET_RESERVE_V6=2000` vs. the
shared-library default 400) so `BUY_LAND` waits for cost+$2000 post-hire
instead of firing day 0/1, per `docs/superpowers/specs/2026-08-11-task-teacher-v6-design.md`
(motivated by the v5 ladder replay's day-1 cash-starvation losses).
2026-08-11: acceptance clean (100/100, `BUY_LAND=100`, median first-buy
day 15 vs. v5's day 0/1), regression-clean vs. v2/`starter`, but 50-pair
vs. `task_teacher_v5` is an exact `win_rate=0.500` tie, Hoeffding CI
`[0.260, 0.740]` — straddles 0.50, so **not promoted**; `task_teacher_v5`
remains `competitive_champion`. See `docs/4_agent_version_log.md`.

## Strategy Approach (unchanged from the design doc)

Per `docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md`'s
converged RL discussion: this heuristic serves as (a) a working ladder
submission, (b) the scripted teacher for behavioral cloning, (c) a
benchmark/fallback opponent for every later policy. It is not the intended
final champion architecture.
