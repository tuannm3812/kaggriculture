# Task Teacher v2 — Proposed Design

Written 2026-08-01. Status: **pending user approval**. This file is intentionally
focused. It inherits the project and teacher constraints from the authoritative
competition and teacher specs.

## 1. Goal

Extend `task_teacher_v1` with daily hiring and deterministic multi-unit task
assignment while preserving v1 crop behavior, legality, explicit state, and
packaging contracts.

No animals, fertilizer, land purchases, or learned policy are added in v2.

## 2. Verified Mechanics

- Hiring cost in environment 1.29.3 is `10 * fib(hires_today)`.
- Hired hands last only for the current day.
- Farmer position resets and hands disappear at every day boundary.
- Hand action order follows `obs["farms"][player]["hands"]`.
- Units may share/traverse tiles, but exclusive field tasks/resources cannot be
  claimed twice.

## 3. Proposed Joint Assignment

Use bounded exhaustive joint assignment rather than Hungarian or farmer-first
greedy assignment:

- Candidate units: farmer plus active hands.
- Candidate actions: each unit's top eight feasible tasks plus `PASS`.
- Evaluate unique-task assignments jointly with deterministic tie-breaking.
- Include priority, deadline slack, value/action cost, travel, and assignment
  switching in the objective.
- Preserve same-day hand assignments through hysteresis.
- If supported unit bounds are exceeded, use a deterministic greedy fallback
  and record the occurrence; do not fail silently.

This avoids a persistent farmer stealing a task that a temporary hand is uniquely
positioned to complete while remaining small enough for the expected 1–3 hands.

## 4. Hiring Policy

- Re-evaluate hiring every turn during the economically useful portion of the
  day, not only at hour zero.
- Queue at most one `HIRE` order per turn.
- Estimate the marginal value of deadline tasks recovered by one additional
  hand over the remaining day.
- Hire only when marginal value exceeds the next Fibonacci-scaled cost plus a
  configurable safety margin and sufficient turns remain for repayment.
- Reserve hire cost before seed or other market intents are emitted.
- Do not hire merely to create training action diversity.

Initial constants are calibration parameters; logs must compare forecast and
realized recovered value/workload.

## 5. Day-Boundary State

Track `previous_day` explicitly.

- On day change, clear all hand assignments.
- Regenerate the farmer's route cost from its reset spawn position.
- Retain the farmer's task only if the freshly regenerated task remains valid;
  otherwise clear it.
- Preserve hand hysteresis within the same day, keyed by the current hand list
  index.
- Submission wrapper still resets all state at episode start/backward step.

## 6. Reservation Flow

Solve the joint assignment first; then construct/validate the reservation ledger
from the winning assignment.

- No duplicate exclusive tile/task claims.
- Resource and budget totals cannot exceed observed availability.
- Movement cells are not exclusive.
- Farmer persistence is a switching penalty, not absolute assignment priority.
- Produce exactly one hand action per observed hand, in observed order.

## 7. Acceptance Tests

- Joint assignment beats a deliberately bad farmer-first allocation.
- No duplicate task/resource assignment.
- Same-day hand hysteresis is deterministic.
- Hand assignments clear across day boundaries.
- Farmer task is revalidated after overnight position reset.
- Hire/no-hire behavior passes exact marginal-value boundary tests.
- No late-day hire when repayment is impossible.
- At most one hire order is emitted per turn.
- Hand action list length/order matches the observation.
- Budget remains valid across hires, seeds, and other market intents.
- Tied assignments resolve deterministically.
- Full simulator tests complete both seats with finite rewards and no invalid
  actions or cross-episode state leakage.
- Standalone multi-module package completes a full-season smoke game.

## 8. Evaluation

- Report hiring distribution, hands/day, hand-active turns, recovered deadline
  tasks, predicted versus realized marginal value, task conflicts prevented,
  distinct worked tiles, avoidable weeds, and inference latency.
- Run paired screening against `task_teacher_v1`, `roi_teacher_v3`, and
  `starter` with recorded seeds and both seats.
- v2 may become the coverage teacher without replacing the competitive champion
  if it expands valid action coverage but lacks confident win improvement.

## 9. Approval Questions

1. Approve bounded exhaustive assignment over top-eight tasks and expected
   farmer plus 1–3 hands?
2. Approve intra-day hiring evaluation with at most one hire per turn?
3. Approve same-day hand hysteresis and mandatory day-boundary clearing?
4. Approve the acceptance and evaluation gates above?

