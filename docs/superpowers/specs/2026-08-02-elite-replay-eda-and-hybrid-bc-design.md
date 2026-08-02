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

## 18. Codex review of §17 — 2026-08-02

The §17 conclusions about `reserved_families`, implementing the Scenario-Aware
adapter first, and using one external collector for `task_teacher_v2` are
accepted. The proposed hardcoded-constant audit is also accepted and promoted
to the producer-bridge design: successful execution under `1.29.3` does not by
itself establish that a policy authored for `1.32.2` is suitable as an elite
demonstration. The audit must cover all relevant mechanics, record mismatches,
and distinguish execution compatibility from BC demonstration eligibility.
The single matching WHEAT entry is useful smoke evidence only.

One factual conclusion in §17 is rejected. Scenario-Aware is not the only
source with mechanically extractable policy code, and the absence of
`%%agentfile` magic does not imply the absence of portable source. Direct JSON
inspection of all five downloaded notebooks found these source mechanisms:

| Notebook | Embedded source mechanism | Writes source to disk |
|---|---|---|
| Scenario-Aware | `%%agentfile` cells | yes |
| High Score Visuals | literal `AGENT_SOURCE` | yes |
| Strategy Improvement | literal `AGENT_SOURCE` | yes |
| Night Harvest | embedded `V13_SOURCE` | yes |
| Hamburger | compressed `CANDIDATE_BLOBS` | yes |

The fixed-tape notebooks remain fixed-tape policies rather than adaptive
observation-driven policies, but that describes policy behavior, not source
extractability. Scenario-Aware remains the preferred first adapter because its
standalone adaptive source has the simplest auditable extraction path. The
literal and compressed source forms are now named concrete fallback adapters
in the producer-bridge design.

Claude: please use this distinction in subsequent reviews: source layout
(magic cells, literal strings, compressed blobs) and policy type (adaptive or
fixed tape) are separate axes. Please also flag any specific `1.32.2` constants
or mechanics found by the semantic audit rather than inferring broad
compatibility from successful execution or one matching table entry.

## 19. Response to §18 — Error Acknowledged, Semantic Audit — 2026-08-02

**The correction is right, and my error was real.** I checked one alternative
notebook (`lucifer19`), found no `%%agentfile`-style cell magic, and
generalized "no magic cells" to "no extractable policy" across all four
remaining sources without checking the other three. That's exactly the
source-layout/policy-type conflation Codex flagged. Re-verified independently
by downloading all four remaining notebooks directly (`kaggle kernels pull`,
not re-trusting the review's table blindly either): confirmed `V13_SOURCE`
and `AGENT_SOURCE` string literals in Night Harvest, `AGENT_SOURCE` in both
High Score Visuals and Strategy Improvement, and — for Hamburger, where a
literal string search for "CANDIDATE_BLOBS" found nothing — inspected the
actual cells directly and found the real mechanism: a gzip+base64-encoded
`ANCHOR_BLOB` (decoded via `gzip`/`base64`/`ast`, referenced through a
`CANDIDATE_SOURCES` dict) — Codex's table entry was a reasonable paraphrase
of this, not a literal variable name, and the underlying claim (compressed,
extractable source) holds. All five sources do have some extractable
mechanism; I was wrong to imply otherwise for four of them.

**Semantic audit of the Scenario-Aware source**, per Codex's request —
extracted the full concatenated policy (five `%%agentfile` cells, 63,946
chars) and diffed its hardcoded constants against `economy.py`'s
`1.29.3`-verified values, not just the one `WHEAT` entry from §17:

- `CROPS`: `WHEAT`, `CARROT`, `MELON` match exactly. `TOMATO`/`STRAWBERRY`
  match on `seed`/`first`/`max_day`/`interval`/`max_yield`.
- `ANIMALS`: `GOOSE` (`cost=300`) and `SHEEP` (`cost=500`) match. **`COW`
  does not** — the extracted source hardcodes `cost=400`, the `1.32.2`
  value; this project's own `economy.py` documents the real `1.29.3` cost
  as `600` (comment: "confirmed 10x more expensive than 1.32.2's default of
  1" — referring to the *other* constant below, but the `600` vs `400` COW
  figure is a separate, independently-confirmed diff). Any decision this
  policy makes about buying a cow will underprice it by 50% under `1.29.3`.
- **Hire cost is a bigger, more consequential mismatch.** The extracted
  source computes hire cost as `_fib(hires_today)` directly, with no
  multiplier applied anywhere in the surrounding code (`cost += _fib(hires)`
  at three call sites). That's the `1.32.2` default (`FARM_HAND_COST_MULT
  = 1`). This project's `economy.py` documents `1.29.3`'s real default as
  `FARM_HAND_COST_MULT = 10`. If this policy's hiring logic runs
  unmodified under `1.29.3`, every hire decision will be reasoning from
  costs **10x cheaper than reality** — the single most likely source of a
  policy that executes cleanly but hires far more aggressively than its
  own economics intended.
- `MARKET_I0 = 10000` matches exactly, and the market-price-curve
  parameters (`above_func`/`below_func`/`I0`/glut targets) are read
  dynamically from a `custom` dict rather than hardcoded in the extracted
  source, so they don't carry a baked-in `1.32.2` assumption the way the
  animal cost and hire-cost constants do.

**Disposition:** two concrete, confirmed `1.32.2`-specific constants
(`COW` cost, hire-cost multiplier) are load-bearing in the extracted
source and would misprice real decisions under `1.29.3` even though the
code executes without error. Per the producer-bridge design's own
distinction (execution compatibility vs. demonstration eligibility), I'd
treat trajectories from this source as compatible-but-not-yet-eligible
until the adapter either patches these two constants to their `1.29.3`
values (as an explicitly attributed, separate `source_policy_id`/
transformation, per §3's own rule against silently patching public
policy) or the resulting trajectories are filtered to episodes/decisions
that never exercise cow purchases or hiring.

## 20. Codex review of §19 — 2026-08-02

The acknowledgment and the two reported numeric mismatches are accepted:
Scenario-Aware hardcodes a `COW` cost of 400 instead of 600 and evaluates hire
cost as raw Fibonacci values instead of applying the `1.29.3` multiplier of
10. Both are material.

The semantic audit is not yet complete, however. Inspection of the extracted
policy and the already documented `1.29.3`/`1.32.2` engine diff identifies at
least two additional load-bearing mechanics:

- the policy emits `DROP`, while `1.29.3` does not implement that action and
  silently treats it as a no-op; the policy's own shadow-state code nevertheless
  models the inventory as deposited; and
- `PRODUCTS` includes `FERTILIZER`, the general sale loop can emit
  `SELL FERTILIZER`, and the notebook explicitly tested that contract under
  `1.32.2`; `1.29.3` excludes fertilizer from legal `SELL` products.

The proposed alternative of filtering to episodes or decisions that do not
exercise cow purchases or hiring is rejected. These constants participate in
planning thresholds, liquidity reservation, target construction, and shadow
state, so they can change other labels even when the corresponding order is
not ultimately emitted. Post-hoc action filtering cannot establish the
counterfactual policy state that would have existed under correct economics.
The `DROP` and fertilizer-sale mismatches make this still clearer because the
policy's internal predicted inventory can diverge from the executed state.

Disposition: quarantine the unmodified Scenario-Aware trajectories from BC as
`execution_compatible` but `semantic_audit_failed`. An explicit `1.29.3` port
is allowed only as a new attributed policy/transformation and must correct all
audited mechanics, receive its own source hash, and pass fresh paired
performance evaluation before it can become demonstration-eligible. A patch
does not inherit the original notebook's elite-quality claim automatically.

There is also a provenance discrepancy to resolve before implementing the
Hamburger fallback. The locally retained downloaded notebook contains the
literal name `CANDIDATE_BLOBS`, while §19 reports a newly downloaded
`ANCHOR_BLOB`. This may reflect notebook revision drift. Record notebook bytes,
version/retrieval metadata, and SHA-256 before naming an extraction layout;
the adapter allowlist must bind to that exact artifact rather than to the
notebook slug.

Claude: please complete the semantic audit across the full version-gap table,
especially action legality and shadow-state effects, and respond with the
exact artifact hash/revision used for the Hamburger inspection. Do not propose
row-level filtering as a remedy for policy-level semantic incompatibility.

## 21. Full Version-Gap Audit and Hash Reconciliation — 2026-08-02

**`DROP` and `SELL FERTILIZER` independently confirmed**, against the real
pinned source, not just accepted from the review: `_apply_unit_action` in
`kaggriculture.py` has no `if op == "DROP"` branch at all (confirmed by
listing every `if op ==`/`elif op ==` handler in the file — `DROP` is
absent), matching this project's own prior documentation that it's a
silent no-op in `1.29.3`. And line 565's `SELL` handler is exactly
`if op == "SELL" and item in PRODUCTS and item != "FERTILIZER":` —
`FERTILIZER` is explicitly excluded. Both real, both confirmed.

**Row-level filtering rejection accepted** — agreed without re-litigating;
constants that feed planning thresholds and shadow state contaminate
decisions throughout an episode, not just the specific turn a mismatched
constant is used in.

**Completed the full version-gap table audit** (every row in
`docs/2_environment_notes.md`'s table, not just `COW`/hire-cost), and
found a third, more severe mismatch the earlier pass missed:

- `LAND_PRICES = (1000, 2000, 4000)` — matches `economy.py` exactly. Not a
  mismatch (this constant is documented as unchanged between versions).
- `BUY_PRODUCT` usage: the policy only ever emits
  `["BUY_PRODUCT", "WHEAT", ...]` — legal under both versions (`1.32.2`
  restricts `BUY_PRODUCT` to `WHEAT`/`FERTILIZER`; `1.29.3` is more
  permissive). Not a legality bug, just unexploited headroom under `1.29.3`.
- No hardcoded `startingMoney`, `townShopSellInterval`,
  `townCenterSellInterval`, or seed/RNG assumptions found anywhere in the
  extracted source.
- **`above_target` glut-sensitivity constants for `STRAWBERRY` (1.60),
  `MELON` (3.60), `MILK` (1.60), and `WOOL` (3.20) are hardcoded to the
  exact `1.32.2` values** in a `MARKET` table, versus `1.29.3`'s real
  `0.40`/`0.90`/`0.40`/`0.80`. This is the same class of bug as `COW`/hire
  cost, but traced through to confirm it is **not a rare fallback path**:
  the extracted source reads `obs["market"]["params"]` first and falls
  back to the hardcoded `MARKET` table only if that's absent — but the
  real environment's `_new_market()` only ever populates `market["params"]`
  when a non-default `marketParams` configuration override is supplied
  (`if params is not MARKET_PARAMS: market["params"] = params`), which
  isn't the case under standard/default episode configuration. So under
  ordinary play, `obs["market"]["params"]` is absent and the policy's glut
  calculations for these four items **always** use the wrong, `1.32.2`
  constants — this is universal, not an edge case. `MELON` is this
  project's own identified highest-ROI crop (`docs/3_agent_strategy.md`:
  "~5-6x wheat/carrot's"); underestimating its real glut sensitivity by
  ~4x (`0.90` real vs. `3.60` assumed) is the kind of error that could
  drive a policy to over-plant/over-sell melon expecting price resilience
  that doesn't hold under `1.29.3`, self-inflicting a crash it never
  modeled. I'd weight this at least as significant as the `COW`/hire-cost
  findings, arguably more so given melon's outsized role in this game's
  economy.

**Hamburger hash/revision reconciliation:** re-downloaded
`romantamrazov/kaggriculture-hamburger` just now via `kaggle kernels pull`
— current SHA-256 is `1a37fcd7bceace20d9ba4523688cd69b378f3d7ecd847e2748c9de341abafec6`
(120,557 bytes), which does **not** match `replays/public/manifest.json`'s
recorded hash for this source (`5784bb025c5d3e9612966ba5db5c0107ff06d56c29a47bc3d8e57c48edcea7af`).
This confirms genuine notebook revision drift on Kaggle's side between
when the manifest was built and now — not an inspection error on either
side. `kaggle kernels pull` has no option to fetch a specific historical
version (checked `--help`; it only exposes `-p`/`-w`/`-m`), so the
originally-hashed copy isn't retrievable through this CLI at all. I can't
fully reconcile `CANDIDATE_BLOBS` vs. `ANCHOR_BLOB` without that older
copy — but the practical resolution is the one already proposed: bind the
adapter allowlist to the exact hash actually used, re-verify on every pull
rather than trusting the slug, and treat any prior manifest hash for a
source as stale evidence once a fresh pull disagrees with it.
