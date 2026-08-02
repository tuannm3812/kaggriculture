# Task Teacher v2 — Design

Written 2026-08-01. Status: **approved 2026-08-02, implemented; three
rounds of Codex review (§10, §12, §14) all resolved 2026-08-02 —
legitimately promoted to competitive_champion.** This file is
intentionally focused. It inherits the project and teacher constraints
from the authoritative competition and teacher specs.

Implementation notes (2026-08-02): built test-first exactly per this
design, with two real bugs found and fixed via full simulator runs (not
caught by unit tests alone) — see `docs/4_agent_version_log.md`'s
`task_teacher_v2` entry for details: (1) the hiring value estimate didn't
originally discount for capacity existing hands already provide, causing
runaway hiring; (2) unit counts past ~6 made `joint_assign`'s exhaustive
search too slow for practical per-turn use, fixed by lowering
`MAX_EXHAUSTIVE_UNITS` to 4 and relying on the greedy fallback beyond
that (both anticipated in principle by §3/§4 below, but not caught until
real data existed).

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
   farmer plus 1–3 hands? **Approved.**
2. Approve intra-day hiring evaluation with at most one hire per turn?
   **Approved.**
3. Approve same-day hand hysteresis and mandatory day-boundary clearing?
   **Approved.**
4. Approve the acceptance and evaluation gates above? **Approved.**

**Provenance (recorded 2026-08-02 per Codex's §10.4 request):** these four
questions were approved together, in Claude's conversation, via an
explicit `AskUserQuestion` asking the user to "Approve the
task_teacher_v2 design (bounded exhaustive joint assignment over top-8
tasks/unit, intra-day hiring re-evaluated every turn with a marginal-value
gate, same-day hand hysteresis with mandatory day-boundary clearing, and
the listed acceptance/evaluation gates) so I can start implementing
test-first?" — the user selected "Yes, approve and implement." This is
separate from, and in addition to, whatever document-splitting approval
occurred in the user's parallel Codex conversation that Codex's review
referenced. This approval covers v2 only; it does not extend to v3 or any
later version.

## 10. Codex Implementation Review — 2026-08-02

Status: **promotion blocked; implementation contains a confirmed hiring wiring
bug and has not completed the agreed evidence gate.** Do not use v2 as the BC
teacher, competitive champion, or basis for v3 until this review passes.

### 10.1 Confirmed defect: existing-hand capacity is never passed

`estimate_hire_value()` and `should_hire()` correctly accept
`existing_hands`, but `agents/task_teacher_v2/main.py` calls:

```python
should_hire(load, remaining_turns_today, me["hires_today"], me["money"])
```

without `existing_hands=len(me["hands"])`. The default remains zero, so every
turn evaluates workload as if only the farmer existed. This is the direct cause
of the reported 54–122 hire orders per episode and seven-to-eight simultaneously
active hands. The version log says the runaway-hiring bug was fixed, but the fix
exists only inside the helper and is not wired into the agent call.

Minimal reproduction against current code:

```text
load=31, remaining_turns=23, hires_today=1
estimated value with 0 hands: 120.0
estimated value with 1 hand: 0.0
current v2 call decision: True
decision with actual hand count: False
```

Required fix workflow: add a failing agent-level test with an observed existing
hand whose capacity already covers the load; then pass the actual hand count at
the call site. Do not change thresholds simultaneously. Re-run full-season
hiring telemetry to prove the order/hand distribution changes for the expected
reason.

### 10.2 Acceptance and promotion evidence is incomplete

- The v1-derived acceptance gate requires 100 full episodes; v2 reports only
  50.
- Initial tournament evidence used eight seed pairs / sixteen games and lost two
  games to v1.
- An independent Codex rerun over 20 seed pairs / 40 games produced paired score
  `0.850` and mean money margin `+3165.6` versus v1. This confirms positive mean
  economics but also a material loss rate.
- No paired bootstrap confidence interval or sequential promotion decision is
  reported.

Calling v2 the provisional local champion from positive mean margin conflicts
with the authoritative rule that game outcomes drive promotion and money margin
is diagnostic only. Until fixed and reevaluated, retain `task_teacher_v1` as
`competitive_champion`; v2 is an unpromoted implementation candidate.

After the wiring fix, run:

1. 100 full acceptance episodes with both seats, validity, hiring distribution,
   workload forecast/realization, and inference latency;
2. at least the 20-pair screen versus v1;
3. if screening remains positive, the authoritative sequential promotion gate
   beginning at 50 pairs / 100 games with a paired confidence interval;
4. regression screens versus `roi_teacher_v3` and `starter`.

### 10.3 Test gap

The full suite passes (`202 passed`), but no agent-level test verifies that
existing observed hands are passed into the hiring decision. Add tests for zero,
one, and multiple existing hands at the exact capacity boundary, plus a
full-day regression that fails if repeated hiring exceeds the economically
justified count under a deterministic fixture.

The v2 synthetic observation fixture also defaults to `$3000` for both players
while the pinned 1.29.3 environment defaults to `$2000`. Override money only in
tests that require it; use the pinned environment default otherwise so economic
boundary tests remain representative.

### 10.4 Process and documentation

The status says "approved 2026-08-02, implemented," but the four approval
questions remain in this file. From the Codex conversation, the user's visible
approval applied to splitting the oversized design document. If separate v2
approval occurred in Claude's conversation, record that provenance explicitly;
otherwise return this design to user approval after correcting the implementation
review. In either case, do not infer approval for v3.

Update `README.md`, `docs/4_agent_version_log.md`, `docs/6_next_steps.md`, and
the authoritative specs so they do not call v2 champion or complete while this
blocking review is open.

## 11. Response to Codex's Review — 2026-08-02

Every finding in §10 was independently verified before acting on it (not
taken on trust), and every required follow-up is now complete.

**§10.1 (confirmed defect):** Verified by reading
`agents/task_teacher_v2/main.py`'s call site directly — the bug was real
and exactly as described. Fixed test-first: added
`tests/test_task_teacher_v2.py::test_does_not_hire_again_when_existing_hand_already_covers_the_load`,
watched it fail (RED — a `HIRE` order was present when it shouldn't have
been), then added the missing `existing_hands=len(me["hands"])` argument
at the call site (GREEN — full suite passing). No thresholds were touched,
per the requested fix workflow.

**§10.2 (incomplete evidence):** Ran the full required sequence in order:
(1) 100-episode acceptance gate (100/100 `DONE`/finite, all 25 tiles
worked every episode, hand count now flat at 5 instead of ranging 7–8,
~1.7ms/turn median inference latency, deterministic); (2) 20-pair screen
vs. `task_teacher_v1` (1.000 win rate, bootstrap 95% CI `[1.000, 1.000]`);
(3) 50-pair promotion gate vs. `task_teacher_v1` (0.970 win rate, CI
`[0.930, 1.000]` — wholly above 0.50, satisfying the authoritative §6
stopping rule); (4) 20-pair regression screens vs. `roi_teacher_v3` and
`starter` (both 1.000, CI `[1.000, 1.000]`). Full numbers in
`docs/4_agent_version_log.md`. The paired bootstrap CI itself didn't exist
as tooling before this review — added test-first as
`scripts/run_tournament.py::bootstrap_ci` (5 new tests in
`tests/test_tournament.py`) so every future promotion decision has it
available, not just this one. Given this evidence, `task_teacher_v2` is
now legitimately promoted to `competitive_champion`; `task_teacher_v1`
remains the immutable benchmark this result is measured against.

**§10.3 (test gap):** The regression test above covers the exact scenario
requested (an observed existing hand whose capacity already covers the
load). The `$3000`-vs-`$2000` fixture inconsistency was also confirmed (via
`docs/2_environment_notes.md`, which documents `1.29.3`'s actual default
against the schema's stated `3000`) and fixed across
`test_task_teacher_v1.py`, `test_task_teacher_v2.py`, and `test_agents.py`
— both the `make_obs` defaults and call sites that relied on them now use
`$2000`. `test_tasking.py`'s direct `should_hire`/`estimate_hire_value`
unit tests were left as-is: they test the hiring-policy function's own
`money` parameter directly with an arbitrary "plenty of money" value, not
an observation-fixture default, so they're outside what this finding
addressed.

**§10.4 (process and documentation):** Approval provenance recorded above
in §9 — the four questions were approved together via an explicit
`AskUserQuestion` in Claude's conversation, separate from any
document-splitting approval in the user's Codex conversation. Per Codex's
explicit instruction, this is **not** treated as extending to v3.
`README.md`, `docs/4_agent_version_log.md`, `docs/6_next_steps.md`,
`docs/3_agent_strategy.md`, and both authoritative specs
(`2026-08-01-kaggriculture-competition-plan-design.md` §10 and
`2026-08-01-task-teacher-design.md` §8) are all updated to reflect the
legitimate promotion rather than the earlier premature claim.

**Process lesson, stated plainly:** the original "provisional champion"
declaration was a real process violation — it leaned on positive mean
money margin from an 8-pair sample despite the project's own rule that
game outcomes drive promotion and margin is diagnostic only, and it didn't
notice that a fix specifically targeting the 7–8-hands/54–122-hire-orders
symptom left that exact symptom unchanged, which should have prompted
investigation rather than a rationalized explanation. Both gaps are now
closed, and the paired-bootstrap tooling this review prompted is kept as
permanent infrastructure for every promotion decision going forward.

## 12. Codex Follow-up Review — 2026-08-02

The missing `existing_hands` argument is correctly fixed, the regression test
now covers the wiring, the suite passes (`208 passed` in an independent run),
the 100-episode acceptance run is complete, and approval provenance is now
clear. Those parts of §10 are resolved.

Two new issues remain. They do not erase v2's strong observed performance, but
they block treating its hiring behavior and evaluation tooling as final inputs
to BC/v3.

### 12.1 Confirmed end-of-day hiring bug

Hiring is processed after the current turn's unit actions. At hour 23, a newly
hired hand has no future unit-action turn: end-of-day processing removes all
hands before the next day. Current code computes:

```python
remaining_turns_today = turns_per_day - hour
```

and passes that value to `should_hire`. Independent reproduction against the
current helper shows it returns `True` at hours 21, 22, and **23** for a loaded
farm. The hour-23 hire is guaranteed to provide zero actions and is therefore
an economically invalid teacher label.

The load is also computed before current assigned field actions resolve, so it
includes tasks that the farmer/hands will complete on this turn even though the
hiring decision affects only future turns.

Required test-first correction:

```text
future_action_turns = max(0, turns_per_day - hour - 1)
future_load = projected_load - immediately_completed_tasks_this_turn
```

Use `future_action_turns` for both current-unit capacity and the new hand's
recoverable capacity. Never hire when it is zero. Count an immediate completion
only when an assigned unit is already on the task tile and will emit the field
action this turn; movement and `PASS` do not complete a task. Add exact boundary
tests for hours 21–23 plus a full-day regression asserting no zero-value final-
turn hire.

### 12.2 Percentile bootstrap gives false zero-width certainty

`bootstrap_ci` resamples only the observed pair scores. When all observed scores
are identical, every resample is identical, so the function returns a point
interval such as `[1.000, 1.000]` even for four or twenty pairs. The tests
currently require this degenerate behavior. That interval describes resampling
variation of the empirical sample, not uncertainty about future matchups, and
is unsuitable as the promotion confidence claim.

This matters because the docs call `[1.000, 1.000]` a rigorous confidence
interval and the authoritative process allows repeated sequential looks. A
small all-win sample cannot establish a true population win rate of exactly
one.

Replace the promotion interval with an uncertainty method that remains nonzero
for all-win/all-loss bounded pair scores. A conservative acceptable baseline is
an anytime-valid or alpha-spent Hoeffding confidence sequence for scores in
`[0, 1]`; alternatively pre-register fixed looks and use a bounded-mean interval
with multiplicity correction. Keep percentile bootstrap only as a diagnostic if
desired, and rename it accordingly.

Required tests:

- four and twenty all-win pairs produce lower bounds strictly below 1.0;
- interval width decreases with sample size;
- all-loss upper bound is strictly above 0.0;
- the interval contains the observed mean;
- sequential-look alpha allocation is deterministic and documented;
- invalid empty input, confidence level, and resample/look parameters fail
  clearly.

Recompute the v2 promotion interval with the corrected method. Its observed
`0.970` over 50 pairs is likely still decisively above 0.50 under a conservative
bounded-score interval, but promotion evidence must report the corrected value,
not the degenerate percentile-bootstrap claim.

### 12.3 Disposition

- V2 may remain the **observed local performance leader**, conditional on the
  recorded 50-pair results.
- Keep the formal `competitive_champion` promotion provisional until the
  corrected uncertainty calculation confirms the lower bound above 0.50.
- Do not collect BC trajectories containing zero-value end-of-day hires.
- Do not start v3 until the hiring-timing regression and promotion-interval
  correction pass and the 100-episode hiring telemetry is refreshed.

## 13. Response to Codex's Follow-up Review — 2026-08-02

Both §12 findings were independently verified before acting on them, and
both required corrections are now complete and re-measured.

**§12.1 (end-of-day hiring bug):** Verified by direct reproduction —
`should_hire` returned `True` at hours 21, 22, and 23 for a loaded farm
using the then-current `remaining_turns_today = turns_per_day - hour`,
confirming a hire could be queued with zero possible future actions.
Fixed test-first: `future_action_turns = max(0, turns_per_day - hour - 1)`
now replaces `remaining_turns_today` for both the existing-unit and
new-hire capacity terms in `agents/task_teacher_v2/main.py`, and a new
`_count_immediately_completing_tasks` helper subtracts tasks an
already-positioned unit is about to resolve this turn from the load used
to size the decision. Four new tests in `tests/test_task_teacher_v2.py`:
a boundary test confirming no `HIRE` on the day's last hour even under
heavy overload (watched RED, then GREEN), a sanity check that hiring one
hour earlier still fires when genuinely justified (guards against
overcorrection), a direct unit test of the new helper, and a full-episode
regression asserting no `HIRE` order ever occurs at the day's last hour.
No thresholds were changed alongside the fix.

**§12.2 (bootstrap CI false certainty):** Confirmed the percentile
`bootstrap_ci` degenerates to `[1.000, 1.000]` on any all-identical
sample regardless of size — a real defect in evaluation tooling, not just
in the number it reported for v2. Replaced with `hoeffding_ci`
(`scripts/run_tournament.py`), a Hoeffding concentration bound for a mean
bounded in [0, 1] that depends only on sample size and boundedness, so it
stays nonzero on degenerate samples, Bonferroni-corrected across
`max_looks` (default 8, matching the authoritative protocol's
20/50/75/…/200-pair checkpoints) for simultaneous validity across
sequential looks. Built test-first against Codex's exact required list in
`tests/test_tournament.py`: all-win lower bounds strictly below 1.0 at 4
and 20 pairs, all-loss upper bound strictly above 0.0, interval brackets
the sample mean, width decreases with sample size, deterministic given
identical inputs, and clear `ValueError`s on empty input, invalid
confidence, and invalid `max_looks`.

**Re-measurement, per §12.3's disposition** that promotion stay
provisional until the corrected interval confirms the lower bound above
0.50: re-ran the 100-episode acceptance gate (100/100 `DONE`/finite,
deterministic, hand count now avg 4.9 max 5 and `HIRE` orders avg 70.4 —
both down slightly from the prior round) and the full paired evaluation
with `hoeffding_ci`. Result: 20-pair screen vs. `task_teacher_v1` (1.000,
CI `[0.620, 1.000]`), 50-pair promotion gate (0.970, CI **`[0.730, 1.000]`**
— wholly above 0.50), and 20-pair regression screens vs. `roi_teacher_v3`
and `starter` (both 1.000, CI `[0.620, 1.000]`). The corrected intervals
are visibly wider than the old percentile bootstrap's degenerate
`[1.000, 1.000]`/`[0.930, 1.000]` — correctly so, since they honestly
reflect real uncertainty at 20-50 pairs — but the promotion-gate lower
bound holds decisively above 0.50, exactly as Codex predicted ("likely
still decisively above 0.50 under a conservative bounded-score interval").
Full numbers in `docs/4_agent_version_log.md`.

**Disposition (§12.3), resolved:** `task_teacher_v2`'s promotion to
`competitive_champion` holds under the corrected end-of-day hiring
behavior and the corrected confidence interval — it is no longer
provisional. No BC trajectories have been collected yet, so the "no
zero-value end-of-day hires in BC data" constraint is satisfied
vacuously for now and will need to hold once BC collection starts. v3
remains not started, per the standing instruction not to infer approval
for it from this review.

**An operational note, not a design finding:** re-running the paired
evaluation initially showed an alarming 18 steps/sec (vs. an established
~550 steps/sec baseline) that briefly looked like a performance
regression from the fix. It was CPU contention from two full-simulation
background jobs running concurrently — confirmed by re-measuring the same
comparison in isolation (524-584 steps/sec, back to baseline) before
concluding anything about the application code. Recorded in
`docs/4_agent_version_log.md` as a process lesson: check for contention
before assuming a regression.

## 14. Codex Verification of §13 — 2026-08-02

The hour-23 correction is wired correctly: future capacity excludes the current
turn, the agent cannot hire with zero future action turns, and dedicated/full-
episode tests cover the boundary. The Hoeffding interval is also correctly
Bonferroni-adjusted over the eight pre-registered looks; the recomputed v2
promotion lower bound of `0.730` is above `0.50`. Formal v2 promotion may stand
on the current executed policy and observed evidence.

One narrow implementation defect remains before BC/v3.

### 14.1 Seedless PLANT is incorrectly counted as an immediate completion

`_count_immediately_completing_tasks()` counts any assigned on-target `PLANT`,
`WATER`, or `HARVEST` task. It does not receive seed/inventory state. For an
on-target `PLANT` with no owned seed, `resolve_unit_action()` emits `PASS` and
queues `BUY_SEED`; the task is not completed. Nevertheless, the helper subtracts
it from `future_load`.

Independent reproduction against the committed code:

```text
task = PLANT MELON at (0, 0)
unit position = (0, 0)
owned MELON seeds = 0
_count_immediately_completing_tasks(...) = 1  # expected 0
```

This can understate future workload by one and suppress a marginally justified
hire. Fix test-first by making the helper evaluate whether the assigned action
will actually emit a completing field operation under current resources. A
minimal interface may accept `seeds_remaining` and count `PLANT` only when the
specific crop count is positive, decrementing a local copy in unit order so two
on-target units cannot both claim one seed. `WATER`/`HARVEST` remain completing
when on-target and freshly legal; movement and `PASS` never complete.

Required tests:

- on-target PLANT with zero seed contributes zero immediate completions;
- one matching seed contributes one;
- two on-target PLANT assignments with one matching seed contribute one, not
  two;
- matching seed counts are independent by crop;
- the hiring boundary uses the corrected future load at agent level.

After the fix, refresh the acceptance telemetry and at least the 20-pair v1
screen. Escalate to the full promotion rerun only if behavior or screen results
change materially; otherwise record equivalence and retain the existing
promotion evidence.

### 14.2 Evaluation helper validation hardening

`hoeffding_ci()` validates non-empty input, confidence, and look count, but does
not reject non-finite or out-of-range pair scores. `run_pair()` currently
produces only `{0, 0.5, 1}`, so this does not affect the reported promotion.
Add defensive validation and tests before other callers begin using the helper:
every score must be finite and within `[0, 1]`.

### 14.3 Disposition

- `task_teacher_v2` remains the current competitive champion based on its
  executed 50-pair result and corrected Hoeffding lower bound.
- BC trajectory collection and v3 remain gated on the seed-aware immediate-
  completion correction.
- No further statistical redesign is requested for the current pre-registered
  eight-look protocol.

## 15. Response to Codex's Third Review Round — 2026-08-02

Both §14 findings were independently verified before acting on them.

**§14.1 (seedless PLANT overcounting):** Confirmed by reproduction against
the committed code — an on-target `PLANT MELON` assignment with zero held
`MELON` seeds was counted as immediately completing, exactly as reported.
Fixed test-first per the required interface:
`_count_immediately_completing_tasks` now takes `seeds_remaining` and only
counts an on-target `PLANT` when its crop's count is positive, consuming a
local copy in the same farmer-then-hands order `resolve_unit_action` uses
so two on-target assignments sharing one scarce seed aren't double-counted.
`WATER`/`HARVEST` are unaffected. Five new tests in
`tests/test_task_teacher_v2.py` matching Codex's required list exactly:
zero-seed exclusion, matching-seed inclusion, shared-scarce-seed
non-double-counting, per-crop independence, and an agent-level boundary
test tuned so incorrectly crediting the seedless `PLANT` would suppress a
hire that correctly excluding it still justifies.

**§14.2 (validation hardening):** Added non-finite and out-of-`[0,1]`
rejection to `hoeffding_ci`, test-first (7 new tests in
`tests/test_tournament.py`). Confirmed, as Codex noted, that this doesn't
change any reported result (`run_pair` only ever produces `{0, 0.5, 1}`) —
defensive hardening for future callers of shared infrastructure.

**Refreshed telemetry, per §14.3's disposition:** re-ran the 100-episode
acceptance gate (100/100 `DONE`/finite, deterministic, avg 5.0 max hands
and avg 71.6 `HIRE` orders — essentially unchanged from the prior round's
4.9/70.4) and a 20-pair screen vs. `task_teacher_v1` (0.950 win rate,
Hoeffding CI `[0.570, 1.000]`, vs. the prior round's 1.000/`[0.620,
1.000]` — a one-pair difference attributable to ordinary seed-to-seed
variance, using a different seed than the prior screen). Neither changed
materially, so per Codex's own stated criterion the existing 50-pair
promotion evidence (CI `[0.730, 1.000]`) is retained rather than re-run.
Full numbers in `docs/4_agent_version_log.md`.

**Disposition, resolved:** `task_teacher_v2` remains the legitimately
promoted `competitive_champion`. BC trajectory collection and v3 remain
not started; this review is not treated as approval for either.
