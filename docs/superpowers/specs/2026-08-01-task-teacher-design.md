# Kaggriculture Task Teacher — Authoritative Design

Written 2026-08-01. This document defines the scripted teacher family used for
behavioral cloning and as a deterministic fallback. Historical discussion lives
in `2026-08-01-kaggriculture-design-discussion-log.md`.

## 1. Purpose

The task teacher converts each observation into legal, deterministic farm and
market actions through explicit task generation, assignment, routing, resource
reservation, and economic ranking. It must provide both competitive behavior
and broad action/state coverage without teaching deliberately irrational play.

Maintain two roles independently:

- `competitive_champion`: strongest paired-game fallback;
- `coverage_teacher`: policy/corpus satisfying BC representation gates.

One version may hold both roles, but promotion to one does not imply the other.

## 2. Environment Contract

- Develop and test against `kaggle-environments==1.29.3` until stronger ladder
  evidence supersedes it.
- Unit actions execute before market orders; current-turn purchases cannot fund
  current-turn field actions.
- Terrain is obstacle-free inside unlocked quadrants; deterministic Manhattan
  routing is sufficient.
- Manual `DROP` is unavailable/no-op in 1.29.3; inventory reaches the shed at
  end of day.
- Farmer and hands reset to spawn/day state at day boundaries; hands disappear.

## 3. Construction Sequence

1. `task_teacher_v1`: one farmer, initial quadrant, multi-tile one-time crops.
2. `task_teacher_v2`: workload forecast, hiring, multi-unit assignment.
3. `task_teacher_v3`: ongoing crops and fertilizer timing.
4. `task_teacher_v4`: structures and animal lifecycle.
5. `task_teacher_v5`: land purchase and season-phase portfolio planning.
6. `task_teacher_v6`: coordinated market sequencing and opponent pressure.

Each version passes correctness, coverage, packaging, and paired-performance
screens before the next action family is added.

## 4. Shared Architecture

### 4.1 Module ownership

- `economy.py`: mechanics constants, yields, prices, biological timing, season
  feasibility, valuation.
- `tasking.py`: typed tasks, priorities, task generation/ranking, assignments,
  reservations, routing, market-intent shapes.
- `agents/task_teacher_v*/main.py`: version-specific policy and submission
  wrapper.
- Core logic receives explicit `TeacherState`; one state per environment.

### 4.2 Task model

Use typed `TaskKind`, `PriorityTier`, `TaskId`, `ResourceNeed`, and `Task`.
Safety is a strict priority tier, not a float. Deadlines use absolute steps.
Tasks are regenerated every turn; only compact assignment state persists.

Ranking is deterministic:

```text
priority tier
deadline slack after travel
negative net value per required action
assignment switch penalty
stable task ID
```

Filter illegal, locked, resource-infeasible, and negative-slack tasks before
ranking.

### 4.3 State and reservations

- Reset submission state at step zero or when step moves backward.
- Training/parallel evaluation creates one state per environment.
- Preserve valid assignments with hysteresis; emergencies preempt them.
- Reserve exclusive target tasks, resources, and budget during joint assignment.
- Never reserve movement cells.

### 4.4 Service and season feasibility

New production must pass:

1. biological maturity/production horizon;
2. service-capacity horizon;
3. harvest/transport/liquidation horizon;
4. marginal profitability after action, travel, and market impact.

Projected load includes maintenance, planting, harvest, conservative travel,
and end-of-day reserve. Log predicted versus realized load for calibration.

### 4.5 Packaging

Generated standalone agents register a real in-memory `kaggriculture_lib`
package and dependency-ordered submodules in `sys.modules`. Tests cover module
names, dataclasses, deterministic generation, standalone import, and full
simulator execution.

## 5. Data Corpora

- Performance corpus: full default games against controls, prior teachers, and
  approved ladder proxies.
- Coverage corpus: deterministic scenarios targeting rare legal actions.
- Split by episode seed/opponent; never split turns from one episode across
  train and validation.
- Use class-aware sampling/loss weighting during BC.
- Coverage quotas do not justify irrational actions in normal states.

## 6. Full BC Coverage Gate

Initial targets, recalibrated only with recorded evidence:

- 100% completion and zero invalid/conflicting actions across at least 200 full
  episodes;
- median >=12 distinct worked tiles; 10th percentile >=8;
- hands active for >=10% of eligible turns after hands are introduced;
- >=200 examples of each parameterized field action;
- >=100 examples of each rare structure/market family;
- >=500 multi-order market turns and >=500 hand-action turns;
- every action component and mask branch represented in train and validation;
- performance teacher passes the paired incumbent/league gate;
- zero crash, timeout, and state-leak failures.

## 7. Testing

1. Golden scenarios for exact tasks, priorities, assignments, routing, market
   timing, horizon, and day-boundary behavior.
2. Seeded invariant tests for determinism, legality, reservations, budget,
   resource use, and movement-distance reduction.
3. Simulator integration across seeds, seats, opponents, episode resets, and
   packaged artifacts.
4. Trajectory schema and coverage-counter regression tests before collection.

## 8. Current Versions

- `roi_teacher_v3`: immutable single-tile competitive control.
- `task_teacher_v1`: implemented multi-tile crop scheduler; locally verified
  over 100 full episodes with reported median 17 worked tiles and 179 total
  passing tests at implementation time. Superseded as champion by v2.
- `task_teacher_v2`: implemented daily hiring and bounded exhaustive
  multi-unit assignment; locally verified over 50 full episodes (median 25
  worked tiles, avg 7.0 max hands active) with 202 total passing tests at
  implementation time. Beats v1 on average (+2779.6 margin, 0.875 win
  rate) but not a clean sweep — see `2026-08-01-task-teacher-v2-design.md`
  and the project version ledger for the two real bugs (runaway hiring,
  combinatorial performance) found and fixed via full simulator runs.
  Provisional champion.

