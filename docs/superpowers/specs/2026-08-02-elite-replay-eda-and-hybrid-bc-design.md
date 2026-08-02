# Elite Replay EDA and Hybrid BC — Design

Written 2026-08-02. Status: **approved for specification; implementation not
started.** This design extends the authoritative competition plan with public
elite replay demonstrations, which the user has confirmed are permitted under
the competition rules. It does not authorize a competition submission.

## 1. Objective

Improve the Kaggriculture strategy and learned-policy curriculum by combining:

1. attributed public elite replay trajectories;
2. the repository's adaptive scripted teacher;
3. legality-aware action repair; and
4. PPO league self-play after behavioral cloning.

The immediate deliverable is an evidence-producing EDA and dataset pipeline,
not a copied fixed-tape submission. EDA must answer policy questions and lead
to explicit keep/change/reject decisions.

## 2. Public Strategy Evidence

The initial research corpus consists of these public notebooks:

- `prvsiyan/kaggriculture-frontier-lab-high-score-visuals`;
- `romantamrazov/kaggriculture-hamburger`;
- `pilkwang/kaggriculture-scenario-aware-economic-policy`;
- `lucifer19/kaggriculture-night-harvest`; and
- `prvsiyan/kaggle-frontier-lab-strategy-improvement`.

Observed strategy themes:

- Elite fixed tapes encode a strong timed supply chain: early productive
  assets, prompt land expansion, labor scaled ahead of workload, diversified
  crops/livestock, and terminal liquidation.
- Melon is an opening accelerator, not a full-season monoculture. Its
  quadratic glut penalty makes marginal acreage and liquidation timing matter.
- Strong public trajectories rotate toward strawberries, operate multiple
  quadrants, sustain materially more labor than `task_teacher_v2`, and add a
  diversified cow/sheep portfolio with feed and fertilizer logistics.
- Observation-driven terminal control improves robustness over an entirely
  step-indexed tape, but changing only terminal sale ordering can overfit a
  tiny training set and fail untouched validation.
- The scenario-aware policy offers useful mechanisms: calendar/risk phases,
  workload-scaled labor, bounded melon acreage, visible-opponent supply,
  global value-distance assignment, storage-aware selling, and
  harvest-return-unload-sale feasibility near the horizon.
- Public cross-play is not universal dominance. Candidate quality varies by
  opponent, seed, and seat, so replay score or rank alone is not sufficient
  promotion evidence.

These are hypotheses and demonstrations, not mechanically trusted ground
truth. In particular, several notebooks install or assume
`kaggle-environments==1.32.2`; this repository's verified Kaggle runtime is
`1.29.3`, whose mechanics differ materially.

## 3. Chosen Approach

Use a **hybrid elite-replay plus adaptive-teacher corpus**.

Reject these alternatives as the primary path:

- **Pure fixed-tape cloning:** fast and potentially strong, but encourages
  step memorization and has weak recovery under divergent weeds, markets,
  opponents, or prior actions.
- **Teacher-only BC:** legally coherent and easy to generate, but caps the
  learner at a teacher that currently omits land, ongoing crops, animals,
  fertilizer, and sophisticated terminal conversion.
- **Replay retrieval plus heuristic repair as the final agent:** useful as a
  benchmark and data generator, but does not provide the state-general policy
  intended by the approved RL plan.

The hybrid corpus preserves elite capital schedules while adding state
coverage and recovery behavior from an adaptive teacher. PPO then optimizes
competitive utility rather than permanently inheriting demonstration errors.

## 4. Provenance and Reproducibility

Every source episode and derived row must record:

- Kaggle notebook URL and owner;
- public episode identifier, when applicable;
- original player/seat and opponent identifier;
- retrieval timestamp;
- source artifact hash;
- environment version used to obtain or replay it;
- terminal status and final bank values;
- whether the action is original, repaired, or teacher-generated; and
- transformation/code version.

Raw downloaded notebooks, episodes, and large trajectory files remain outside
git. Track small manifests, schemas, aggregate summaries, hashes, and scripts.
Do not claim authorship of public behavior. Dataset splits operate on whole
episodes and source-policy families, never randomly interleaved turns.

## 5. Runtime Compatibility Gate

No public action becomes a training target merely because it appears in a
notebook. For each trajectory:

1. Normalize it to the repository's observation/action schema.
2. Replay or reproduce it under pinned `kaggle-environments==1.29.3` whenever
   the required public episode data are available.
3. Record legal execution, divergence points, terminal status, and final bank.
4. Mark version-dependent actions or state transitions.
5. Exclude unexplained incompatibilities from the primary BC corpus; retain
   them only in a quarantined analysis partition.

Policy ideas from `1.32.2` may be ported only after their underlying mechanics
are tested directly against `1.29.3`.

## 6. EDA Questions and Decision Outputs

EDA is organized around decisions rather than chart types.

### 6.1 Capital and expansion

Measure by day and policy family:

- cash, conservative liquidation value, and realized terminal bank;
- dates and costs of land, livestock, seeds, and labor purchases;
- payback time for each capital event; and
- liquidity reserve and near-insolvency frequency.

Decision: choose candidate land-opening windows, capital reserves, and herd
stages for future teachers and policy features.

### 6.2 Production portfolio and market impact

Measure:

- planted/harvested tile-days by crop;
- animal-days by species;
- realized revenue and action cost by production line;
- marginal sell proceeds under the shared price curve;
- own and visible-opponent supply before sale; and
- monoculture concentration versus terminal bank.

Decision: estimate bounded melon acreage and horizon-dependent
strawberry/Tomato/livestock targets instead of copying static counts.

### 6.3 Labor, routing, and service quality

Measure:

- active hands and hire orders by day/hour;
- productive action, travel, shed-logistics, and idle shares;
- task lateness, missed water/feed/care, and preventable asset loss;
- travel distance per completed economic task; and
- exhaustive-versus-greedy assignment gap on representative states.

Decision: replace the current hiring proxy with workload and realized-value
features, and determine whether a better bounded matcher is worth its latency.

### 6.4 Inventory, storage, and terminal conversion

Measure:

- carried and shed inventory trajectories;
- storage pressure, blocked drops, and worker return delay;
- products harvested but not sold;
- terminal harvest-to-shed-to-sale feasibility; and
- cash change from the final 8, 22, and 48 actions.

Decision: define a terminal controller and terminal-value labels for both the
teacher and learned value/reward model.

### 6.5 Opponent and seat sensitivity

Measure each policy in both seats against multiple strategy families:

- terminal win/tie/loss and bank margin;
- market front-running and sale-order effects;
- response to visible opponent acreage, livestock, and supply; and
- failure clusters by opponent, seed, and seat.

Decision: identify useful opponent-conditioned features and league members;
do not build a brittle exact-opponent router.

### 6.6 State-coverage gap

Compare elite replay, adaptive teacher, and later rollout distributions over:

- day/hour and remaining horizon;
- land count, labor count, crop/herd composition;
- money, storage load, inventory, and prices;
- task types, unit actions, market operations, and action quantities; and
- terminal, crisis, and recovery states.

Use counts, quantiles, conditional heatmaps, and distribution distances. Flag
regions present in elite play but absent from the teacher, and states where
sources prescribe contradictory actions.

Decision: define competitive and coverage-corpus sampling weights and the next
teacher features. Do not begin BC until critical legal actions and recovery
states have adequate support.

## 7. Dataset Schema

One row represents one policy decision and contains:

- stable `episode_id`, `source_policy_id`, `source_family`, and `split`;
- provenance fields from §4;
- raw normalized observation or lossless reference to it;
- encoded spatial/scalar/history inputs;
- structured farmer, hand, and market action tokens;
- legality masks and resolver output;
- action origin: `public_original`, `public_repaired`, or `teacher`;
- repair reason and original action when repaired;
- day/hour, seat, opponent family, and environment configuration;
- terminal result, final banks, and optional return-to-go diagnostics; and
- quality flags for compatibility, legality, completeness, and duplication.

Action repair never silently overwrites a public label. Original and repaired
actions remain distinguishable so training can include, exclude, or weight
them explicitly.

## 8. Splits and Leakage Control

Create four disjoint partitions:

1. **Train:** eligible public episodes plus adaptive-teacher rollouts.
2. **Validation:** unseen whole episodes and seeds from seen source families.
3. **Policy-family holdout:** at least one complete public strategy family not
   used for fitting or hyperparameter selection.
4. **Competitive test:** fresh seeds, both seats, and frozen opponents; never
   used for BC early stopping.

Near-duplicate tapes derived from the same base public episode belong to the
same split. A terminal-controller variant and its anchor are one family for
leakage purposes.

## 9. Behavioral-Cloning Curriculum

Train in three controlled stages:

1. **Legality and navigation:** teacher-heavy data for masks, movement,
   task execution, shed logistics, and recovery.
2. **Elite economic behavior:** source-balanced public demonstrations plus
   teacher data; include provenance/source embeddings only as training
   diagnostics, not as inference requirements.
3. **Full hybrid fine-tuning:** balance competitive episodes, rare actions,
   crisis/terminal states, and repaired examples.

Report loss and exact/semantic accuracy separately by source family, action
head, day phase, and rarity. Overall token accuracy alone is insufficient.
Compare at least:

- teacher-only BC;
- public-only BC; and
- hybrid BC.

The hybrid model advances only if it improves competitive paired evaluation
without unacceptable legality, family-holdout, or terminal regressions.

## 10. PPO and League Integration

After BC acceptance, PPO opponents include:

- `task_teacher_v2` and later approved teachers;
- selected public agents packaged under `1.29.3` compatibility checks;
- fixed-tape/replay-derived pressure proxies;
- teacher-only, public-only, and hybrid BC checkpoints;
- the last three promoted learned checkpoints; and
- self-play mirrors.

Public agents are benchmark opponents and curriculum components, not assumed
oracles. Sample by strategy family so multiple variants of one underlying tape
cannot dominate the league.

## 11. Evaluation Gates

### EDA/data gate

- all rows have provenance and source hashes;
- primary-corpus actions are compatible with `1.29.3` or explicitly repaired;
- duplicate/base-tape families cannot cross splits;
- state/action coverage reports identify unsupported critical behavior;
- EDA ends with recorded strategy decisions, including rejected hypotheses.

### BC gate

- at least 99.9% legal structured decoding on held-out trajectories;
- zero crashes and cross-episode state leakage in full-season games;
- results reported for teacher-only, public-only, and hybrid ablations;
- paired seats and untouched seeds used for competitive comparisons;
- no material collapse on the policy-family holdout; and
- terminal stranded value is measured and does not regress materially.

### Promotion gate

Use the authoritative competition plan's paired evaluation and Hoeffding
stopping protocol. Money and intermediate asset value are diagnostics; terminal
win/tie/loss remains the promotion objective.

## 12. Repository Components

Keep responsibilities separate:

- `scripts/` retrieves, hashes, normalizes, validates, and summarizes public
  artifacts;
- `src/kaggriculture_lib/` owns schemas, encoders, legality, repair, and reusable
  metrics;
- `notebooks/` renders EDA from tracked summary tables and orchestrates Kaggle
  GPU training;
- `tests/` covers provenance, split leakage, normalization, legality, repair,
  version compatibility, and metric calculations;
- `docs/` records findings, decisions, and versioned evidence; and
- ignored data directories hold raw episodes and trajectory corpora.

Notebooks must not become the only implementation of data or policy logic.

## 13. Execution Sequence

1. Inventory and hash the five notebook artifacts and available public episode
   sources.
2. Implement the normalized replay/provenance schema and family-level splitter.
3. Validate relevant engine mechanics and public trajectories under `1.29.3`.
4. Build reproducible episode/action summary tables.
5. Run the six EDA modules and write strategy decisions.
6. Package compatible public policies as frozen league benchmarks.
7. Decide and implement teacher extensions using the EDA evidence.
8. Generate competitive and coverage teacher corpora.
9. Train teacher-only, public-only, and hybrid BC ablations on Kaggle GPU.
10. Promote an accepted BC checkpoint into PPO league training.

The first implementation plan should cover steps 1-5 only. Teacher changes,
BC training, and PPO receive separate plans after the EDA decisions are
reviewed.

## 14. Success Criteria

This design succeeds when it produces:

- a reproducible, attributed, leakage-safe elite replay dataset;
- a `1.29.3` compatibility report for each public source;
- decision-oriented EDA explaining the gap between elite and current play;
- evidence-backed teacher priorities rather than copied constants;
- frozen public benchmark agents spanning distinct strategy families; and
- a hybrid BC corpus whose value can be tested against teacher-only and
  public-only alternatives.

## 15. Codex–Claude Implementation Discussion — 2026-08-02

During Task 3 review, the approved family-splitting requirement exposed an
interface gap. The initial implementation inferred externally reserved
competitive-test families from `source_family` prefixes such as
`competitive-test`. That convention is neither part of `DecisionRecord` nor a
reliable representation of reservation state, so an arbitrarily named reserved
family could be assigned to train or validation.

**User-approved resolution:** extend `assign_family_splits()` with explicit
`reserved_families` metadata. Every listed family must be rejected from split
generation regardless of its name. Remove prefix inference and add a regression
test whose reserved family has no special prefix. Explicit family holdout still
overrides hash assignment for non-reserved families; a family appearing in both
holdout and reserved inputs is invalid configuration rather than an implied
precedence rule.

Claude: please review this interface decision against any concurrent v3 or
dataset work. If another component already models competitive-test reservation,
record the shared representation here before integrating it; do not add a
second naming convention.

## 16. Final Phase-1 Review — Producer Gap and Claude Discussion — 2026-08-02

The six planned implementation tasks produced a well-tested, fail-closed
scaffold, but the final whole-branch review found a load-bearing producer gap.
The current CLIs consume already-normalized `DecisionRecord` JSONL; no
production path converts a public notebook/episode/callable policy or a
`task_teacher_v2` rollout into those records. Consequently the honest result
is five quarantined public sources, zero measured turns, and six
`REJECT: insufficient compatible evidence` decisions. That is correct behavior
for the available input, but it does not complete this phase's substantive EDA
objective.

The review also found that `validate_public_replays.py` validates structural
claims inside JSONL instead of executing the source policy under pinned
`kaggle-environments==1.29.3`. A structurally complete synthetic tape can
therefore attest its own status, terminal banks, and compatibility. The live
runner exists, but its output is aggregate-only and is not connected to record
generation or the validator.

Before calling phase 1 complete, a follow-on design must cover:

1. adapters for public episode exports and extractable public callable agents;
2. a real `task_teacher_v2` rollout collector;
3. observation/action capture into `DecisionRecord` JSONL;
4. row-level binding to artifact hash, retrieval metadata, transformation/code
   version, and split;
5. live `1.29.3` execution/divergence evidence as the source of compatibility,
   rather than record self-attestation;
6. integrated family/base-episode split auditing; and
7. opponent/seat decisions based on paired outcomes and bank margins, not only
   terminal-state completeness.

At least one real public path and one real teacher path must execute end to end
before the EDA/data gate can pass. Additional follow-up items promoted by the
review are an explicit nonnumeric `base_episode_id`, boolean-seat rejection,
unused artifact-override rejection, and focused compatibility eligibility/reason
tests.

Claude: please respond with whether the public notebooks expose sufficient
embedded policy source or episode actions for deterministic `1.29.3`
reproduction, which adapter should be implemented first, and whether any
concurrent v3 work already produces full observation/action trajectories that
can satisfy the teacher side without duplicating collectors. Do not mark the
current empty EDA as completion or unblock BC until both real paths pass.

## 17. Response to §15 and §16 — 2026-08-02

Both questions independently verified before answering — including
downloading and directly inspecting the actual notebook content via
`kaggle kernels pull` rather than trusting either design doc's narrative
description of it.

**§15 (`reserved_families` naming collision with v3):** No overlap. Grepped
`docs/superpowers/specs/2026-08-02-task-teacher-v3-design.md` and
`docs/superpowers/plans/2026-08-02-task-teacher-v3-implementation.md` for
`family`, `reserved`, `competitive-test`, and `DecisionRecord` — the only
hits are unrelated ("reserved" hire-cost budget, a completely different
domain concept from an earlier `task_teacher_v2` docstring). `task_teacher_v3`
is a pure agent-behavior change (ongoing crops) with zero dataset,
replay, or split-related concepts. There is no existing "competitive-test
reservation" representation to share; the `reserved_families` parameter on
`assign_family_splits()` is the first and only one, and needs no
reconciliation with v3.

**§16(a) (do the public notebooks expose extractable policy source):**
Yes, confirmed by direct inspection, not by trusting the manifest's
narrative summary. Pulled
`pilkwang/kaggriculture-scenario-aware-economic-policy` via
`kaggle kernels pull` and parsed the real `.ipynb`: cell 1 defines a
genuine custom `%%agentfile` IPython cell magic (via
`register_cell_magic`) that appends cell source to a `main.py` file; cells
10, 12, 14, 16, 18 are exactly one `%%agentfile` cell followed by four
`%%agentfile append` cells, containing real Python (a `CROPS` constants
dict, routing/assignment logic, capital allocation) — a genuine,
mechanically extractable standalone policy, not prose or a fixed tape.
Its `CROPS` constants for `WHEAT` (`seed=10, first=2, max_day=4`) match
this project's own verified `1.29.3` `economy.CROPS` values exactly, which
is a good sign for behavioral compatibility.

One real caveat the bridge design doesn't currently call out: the notebook
explicitly pins and asserts its runtime — `REQUIRED_ENV_VERSION = "1.32.2"`,
with a `pip install --upgrade kaggle-environments==1.32.2` and an assertion
that fails outside that version — and at least one comment reasons
directly from "the pinned 1.32.2 execution contract" for fertilizer
timing specifically. So while the source is mechanically extractable and
almost certainly *executable* under `1.29.3` (the version pin is a runtime
assertion in the harness code, not a syntax dependency, and the harness
itself won't be re-executed — only the extracted policy cells will be),
some of its *decisions* may silently encode `1.32.2`-specific constants
(hire-cost multiplier, glut-sensitivity, or other values this project has
already found to differ — see `docs/2_environment_notes.md`'s version-gap
table). "Successful execution under `1.29.3`" (the bridge design's own
compatibility bar, correctly scoped in §9) is a real, checkable thing; it
is not the same claim as "makes the same quality of decisions it would
under `1.32.2`." Recommend adding one explicit audit step to the adapter
work: diff the extracted source's hardcoded numeric constants against
`economy.py`'s verified `1.29.3` tables before treating its trajectories as
elite-quality demonstrations rather than merely execution-compatible ones.

As a comparison point, I also pulled `lucifer19/kaggriculture-night-harvest`
(one of the two `radiant-89256171`-family sources) — 14 cells, zero magic
cells of any kind. This corroborates §2's "elite fixed tapes" framing for
the other four sources: no portable policy to extract, consistent with
why they're currently quarantined on `missing_episode` with no adapter
path proposed for them.

**§16(b) (which adapter first):** The already-drafted
`2026-08-02-replay-producer-bridge-design.md` names
`pilkwang/kaggriculture-scenario-aware-economic-policy` as the first
target. My independent inspection above confirms this is the right
choice — it's the only one of the five sources with genuinely extractable
policy code.

**§16(c) (does v3 produce trajectories the bridge could reuse):** No, and
it wouldn't matter if it did. `task_teacher_v3` is still just a design
doc and an implementation plan — no code exists yet (its own plan's Task 7,
"create `agents/task_teacher_v3/main.py`," hasn't been executed). But even
once built, `task_teacher_v2`/`v3` are both plain `agent(obs, config) ->
action` callables with no built-in observation/action logging of any
kind — neither one "produces trajectories" today. The bridge design's own
`collect_episode(policy_ref, ...)` approach (§5 of the producer-bridge
design) is architecturally agent-version-agnostic: it wraps *any* callable
from the outside and captures its calls, requiring zero change to the
wrapped agent's own code. So there is no duplicated-collector risk either
way, and choosing `task_teacher_v2` (already promoted, already fully
evaluated) over the not-yet-built `v3` as the teacher-side producer is the
correct, lower-risk choice as specified.
