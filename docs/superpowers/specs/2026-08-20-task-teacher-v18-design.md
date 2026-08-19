# Task Teacher v18: Threat-Conditioned Expansion

**Date:** 2026-08-20  
**Status:** Approved design; implementation not started

## Objective

Build a higher-variance ladder candidate that preserves `task_teacher_v16`'s
efficient two-quadrant economy against compact opponents, but expands
aggressively when public opponent state shows a land-and-animal economy
beginning to compound.

The primary hypothesis is:

> Matching an opponent's expansion before its land-and-animal economy compounds
> will improve results against expanded opponents without paying unnecessary
> land and labor costs against compact crop agents.

The candidate is `task_teacher_v18`. `task_teacher_v17` remains the static
third-quadrant experiment and is a required comparison policy.

## Evidence and Scope

Replay diagnostics show that recent agents lose disproportionately to
opponents combining land, animals, and sufficient labor. They do not show that
unconditional land expansion is profitable: separate v10 replay samples did
not establish a monotonic relationship between more quadrants and greater
reward, and early land has previously starved otherwise productive crop
economies.

Accordingly, v18 changes only these policy areas:

1. opponent threat classification;
2. conditional land authorization;
3. reserve accounting used by expansion decisions; and
4. workload-gated labor scaling after expansion.

Crop scoring, animal caps, task generation, task assignment, liquidation, and
the existing v16 animal-purchase liquidity gate remain unchanged unless a
correctness fix is explicitly required by the cash ledger described below.

## Opponent Threat Classifier

The classifier reads public game state only:

- opponent unlocked quadrants;
- opponent hand count;
- opponent placed-animal count;
- increases in those values observed during the episode; and
- current day and days remaining.

It must not read or infer private opponent inventory.

The state is monotonic within an episode:

```text
COMPACT -> BUILDING -> COMPOUNDING
```

Initial thresholds are:

- **COMPACT:** at most two quadrants, fewer than six hands, and fewer than
  three placed animals.
- **BUILDING:** at least one extra quadrant, at least six hands, or at least
  three placed animals.
- **COMPOUNDING:** at least three quadrants; two quadrants plus at least four
  placed animals; two quadrants plus at least eight hands; or at least six
  placed animals on any land footprint.

The classifier emits the current state plus a stable reason code. Telemetry
records the first day, hour, and reason for every escalation. State must never
de-escalate, even if public counts later fall.

Monotonic state is held in module memory keyed by `observation["player"]`.
State resets on step 0 or when the observed step moves backwards, which keeps
paired local games isolated while preserving ladder determinism.

## Capital and Expansion Policy

### COMPACT

Retain v16 behavior: at most two quadrants and the existing animal liquidity
buffer. No speculative third-land purchase is allowed.

### BUILDING

Continue the v16 production policy and accumulate an earmarked third-land
reserve. Do not purchase the third quadrant merely because the opponent has
crossed one weak signal.

### COMPOUNDING

Authorize the third quadrant only at hour 23 when all conditions hold:

- at least 12 full days remain;
- the next land price is valid;
- post-purchase money covers queued hires;
- post-purchase money covers seed purchases already required by assigned
  planting tasks;
- post-purchase money covers two days of forecast feed;
- post-purchase money preserves the v16 `$1,200` animal liquidity buffer; and
- post-purchase money preserves an additional `$500` operating buffer.

After the third quadrant unlocks, the existing eight-hand branch becomes
eligible. Existing animal caps and animal-purchase liquidity checks do not rise
with land count.

### Fourth-Quadrant Attack Mode

The fourth quadrant is exceptional rather than a normal milestone. It is
authorized only when:

- the opponent has four quadrants or at least ten placed animals;
- at least 14 full days remain;
- at least 70% of our first three quadrants are productively utilized; and
- at least `$8,000` remains after paying the `$4,000` land price and all
  essential reserves.

Attack mode may accept greater terminal-value variance, but it may not spend
reserved feed, assigned-seed money, or the next day's core hiring budget.

## Cash Ledger

Expansion decisions use one explicit ledger. Each planned expense is deducted
exactly once in this order:

1. queued hires;
2. assigned seeds;
3. two-day feed forecast;
4. animal liquidity buffer;
5. operating buffer;
6. proposed land purchase; and
7. later discretionary market orders.

The implementation must correct two existing hazards before expansion is
evaluated:

- calculated seed and feed reserves must participate in affordability; and
- land cost must not be subtracted once from `available_money` and again from
  seed-buying capacity.

Focused regression tests must demonstrate both properties. These are scoped
correctness fixes, not permission to redesign unrelated market behavior.

## Productive Utilization and Labor

A productive tile is a growing crop, a ready harvest, or an occupied animal
structure. Empty unlocked tiles and unused structures do not count.

Fourth-land authorization requires at least 70% productive utilization across
the first three quadrants.

The third-quadrant policy permits up to eight hands. Fourth-quadrant attack
mode permits up to eleven, but the target is workload-gated:

- light useful backlog: retain eight hands;
- medium useful backlog: target nine or ten hands;
- heavy useful backlog: target eleven hands.

Useful backlog includes unresolved harvest, water, feed, care, pickup,
placement, construction, and profitable planting work. Thresholds for light,
medium, and heavy backlog count unique tasks whose resource prerequisite is
already held or covered by a queued market order and whose route plus action
can finish within the relevant day or terminal horizon. With the farmer
included as one working unit, attack-mode hand targets are:

- 9 or fewer executable tasks: 8 hands;
- 10 executable tasks: 9 hands;
- 11 executable tasks: 10 hands; and
- 12 or more executable tasks: 11 hands.

On the final day, added labor is allowed only for harvest, pickup, and
liquidation work forecast to finish before episode termination.

New land uses the existing crop policy: Melon by default, Strawberry after day
10 when another profitable harvest remains, and Wheat only to satisfy forecast
animal-feed demand. Expansion does not itself raise animal caps.

## Data Flow

Each turn follows this order:

1. Parse public self and opponent state.
2. Update the monotonic opponent threat state and transition telemetry.
3. Generate tasks and assignments using the existing scheduler.
4. Measure productive utilization and executable useful backlog.
5. Calculate the single cash ledger from current assignments and animal needs.
6. Select the threat-conditioned land authorization.
7. Select a workload-gated hand target.
8. Resolve market and unit actions with existing policy behavior.
9. Expose diagnostic values to the local evaluation harness without adding
   non-schema keys to the competition action.

The classifier produces state; it never issues orders directly. Expansion and
labor policies consume classifier output through explicit inputs so they can be
unit-tested and disabled independently.

## Safety and Failure Behavior

- Missing or malformed opponent public fields default to `COMPACT` when no
  prior state exists and emit a diagnostic reason; they must not crash the
  agent.
- Once valid evidence escalates threat, later missing fields do not de-escalate
  it.
- Unknown land price or insufficient ledger balance means no land purchase.
- Missing workload evidence retains the current hand target rather than hiring.
- No branch may issue more than one `BUY_LAND` order in a turn.
- Every action remains deterministic for identical observation and config.

## Verification

### Unit and Behavior Tests

Tests must cover:

- every threat trigger and exact boundary;
- monotonic state escalation;
- public-data-only classification;
- transition reason and timing telemetry;
- third- and fourth-land affordability;
- land cost deducted exactly once;
- seed, feed, hire, animal, and operating reserves;
- productive-utilization calculation;
- executable-backlog and labor thresholds;
- final-day labor restriction;
- deterministic full-episode simulator execution; and
- standalone packaging.

### Acceptance

Run 100 episodes against `starter`, both seats, using ladder-match
configuration. Require:

- all terminal statuses `DONE`;
- all rewards finite;
- deterministic repeated actions;
- no invalid land orders;
- no starvation or repeated-bankruptcy loop; and
- observed threat transitions and land purchases consistent with their gates.

### Ablation and Paired Evaluation

1. Disable expansion while retaining the classifier. The resulting policy must
   be behaviorally identical to v16 except for telemetry.
2. Run a 20-pair screen against v16 on fresh seeds.
3. Run a 50-pair promotion evaluation against v16 on different fresh seeds.
4. Run regression comparisons against:
   - v17 static third-quadrant expansion;
   - the strongest available v10 policy;
   - a compact crop opponent; and
   - an aggressive land-and-animal opponent.

Record threat transitions, trigger reasons, land-buy timing, productive
utilization per quadrant, daily hands, hiring cost, executable backlog, pass
rate, minimum cash, feed shortages, crop revenue by type, animal-product
revenue, win rate, mean money margin, and the Hoeffding 95% interval.

## Submission and Promotion Rules

The project accepts higher variance for this candidate but distinguishes an
experiment from a champion:

- **Experimental Kaggle submission:** permitted after clean acceptance and a
  50-pair result with win rate at least `0.55`, positive mean margin, and no
  catastrophic regression against the compact crop opponent. The Hoeffding
  interval may cross `0.50`; the submission must be labeled experimental.
- **Local champion:** requires the 95% Hoeffding interval wholly above `0.50`.
- **Ladder champion:** requires a sustained public score above the strongest
  visible benchmark, not a single transient peak.

Failure of the experimental threshold stops submission and returns the design
to diagnostics. Passing the experimental threshold does not authorize claims
that v18 is promoted.

## Non-Goals

- Redesigning task assignment or routing.
- Raising animal caps.
- Learning classifier weights from the current small replay sample.
- Treating a leaderboard target such as 600 as an engineering guarantee.
- Replacing the two-quadrant default with unconditional full-board expansion.
