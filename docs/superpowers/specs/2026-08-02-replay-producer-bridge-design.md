# Replay Producer Bridge — Design

Written 2026-08-02. Status: **approved for specification; implementation not
started.** This design closes the producer and live-validation gaps found in
the final review of Elite Replay EDA Phase 1. It does not authorize BC
collection, model training, PPO, or competition submission.

## 1. Objective and Completion Boundary

Build two real, provenance-bound trajectory producers:

1. one public-policy adapter that extracts and executes the approved
   scenario-aware notebook policy; and
2. one native collector for `task_teacher_v2`.

Both producers execute under `kaggle-environments==1.29.3`, capture the actual
observation/action stream, write normalized `DecisionRecord` JSONL, generate
execution receipts, pass family/base-episode leakage checks, and feed the
existing compatibility and EDA pipeline.

This bridge is complete only when at least one public-policy episode and one
teacher episode run end to end in both seats and produce populated measured
EDA tables. Successful ingestion does not by itself pass the EDA/data gate;
the resulting decisions must be reviewed separately.

## 2. Considered Approaches

### 2.1 Execute entire public notebooks

Rejected. Public notebooks contain package installation, plotting, file writes,
and unrelated evaluation code. Whole-notebook execution is unnecessary,
difficult to audit, and unsafe as an ingestion mechanism.

### 2.2 Import self-attested normalized JSONL

Rejected as a compatibility authority. It remains useful as a serialization
format, but status, environment version, terminal banks, and legality must come
from a local pinned-runtime execution receipt rather than fields supplied by
the input rows.

### 2.3 Static source extraction plus controlled execution

Chosen. Parse only explicitly supported source-bearing cells, produce a
standalone `main.py`, hash and review it, then execute it through the same
instrumented `1.29.3` collector used for native teachers. This creates one
trust boundary and one trajectory format for all policy families.

## 3. First Public Adapter

The first adapter targets:

`pilkwang/kaggriculture-scenario-aware-economic-policy`

The downloaded notebook constructs its standalone policy through IPython
`%%agentfile` cells. The adapter must:

1. parse the `.ipynb` as JSON without executing cells;
2. select code cells whose source begins with `%%agentfile`;
3. respect only the supported write modes: the first cell writes and later
   `append` cells append;
4. strip the magic header and concatenate the remaining source verbatim;
5. reject notebooks with an append before a write, multiple resets, unsupported
   magic arguments, missing `agent`, or unexpected extra source mechanisms;
6. write the candidate source to an ignored staging directory;
7. compile it without importing it;
8. compute and record SHA-256 for both notebook bytes and extracted source; and
9. require the extracted-source hash to appear in a reviewed allowlist before
   execution.

The adapter never evaluates setup cells, installs packages, or trusts notebook
outputs. If the extracted policy cannot import or run under `1.29.3`, retain
the extraction and failure receipt in quarantine. Do not patch the public
policy silently. A later explicitly attributed port would be a distinct
`source_policy_id`, transformation version, and source hash.

If this scenario-aware source is genuinely incompatible with `1.29.3`, the
same static-adapter interface may next target a fixed-tape notebook, but that
fallback requires a recorded adapter extension and cannot weaken the
end-to-end public-path success criterion.

## 4. Execution Safety

Extracted public source is untrusted code. Execute it in a dedicated child
process with:

- a temporary working directory;
- no inherited Kaggle credentials or project secrets;
- no network-dependent operation;
- an explicit wall-clock timeout per episode;
- bounded stdout/stderr capture;
- the pinned project Python environment;
- a minimal input/output protocol; and
- termination on timeout, malformed output, import failure, or nonzero exit.

The child receives the extracted source path, seed, seat, opponent identifier,
and output path. It imports the policy and environment inside the child,
asserts `kaggle-environments==1.29.3`, runs one episode, and atomically writes a
trajectory bundle. The parent validates the bundle before admission.

This is process isolation, not a claim of a hardened security sandbox. Only
reviewed public sources with an allowlisted hash may run locally.

## 5. Unified Instrumented Collector

Both public and teacher policies use one collector interface:

```text
collect_episode(
    policy_ref,
    source_provenance,
    opponent_ref,
    seed,
    seat,
    configuration,
) -> CollectedEpisode
```

The collector wraps the candidate callable. For every agent call, it captures:

- the exact observation passed to the candidate;
- the returned raw action before environment processing;
- the normalized action;
- step, day, hour, player seat, and opponent family;
- action-shape/legality findings available before execution; and
- deterministic observation and action hashes.

After the environment finishes, it attaches status, call count, final public
banks, terminal result, and receipt ID to every row. The collector must not
invent a candidate action for the final non-actionable state. A normal complete
episode contains exactly 719 decision rows.

The `task_teacher_v2` producer loads the committed agent module through an
explicit file path and records its file hash and git commit. It uses the same
child protocol when practical so public and native policy evidence have the
same failure semantics.

## 6. Execution Receipt

Every episode produces an immutable receipt containing:

- `receipt_id`;
- policy, family, base-episode, opponent, seed, and seat identifiers;
- environment version and full configuration;
- notebook/artifact hash, extracted or native source hash, and transformation
  version;
- collector code version and repository git commit;
- ordered observation-stream and action-stream hashes;
- row count and step range;
- status and exception summary;
- final public banks and score source;
- terminal win/tie/loss;
- start/end timestamps and runtime; and
- compatibility eligibility plus stable failure codes.

`receipt_id` is a SHA-256 of the canonical receipt payload excluding mutable
timestamps and the ID itself. JSONL rows reference the receipt and duplicate
the minimum binding fields needed to detect a manifest or transformation swap.

Compatibility is derived from this receipt and the captured stream. JSONL
fields cannot override executed status, version, banks, call count, hashes, or
eligibility.

## 7. Schema Extension

Extend `DecisionRecord` with:

- `base_episode_id: str`;
- `artifact_sha256: str`;
- `source_code_sha256: str`;
- `transformation_version: str`;
- `collector_version: str`;
- `receipt_id: str`;
- `split: SplitName`; and
- `retrieved_at: str` plus source URL/owner, either directly or through a
  validated immutable provenance snapshot embedded in the row.

Reject boolean seats explicitly. Validate all hashes and require non-empty
base episode IDs even for non-replay policies; native teacher episodes use a
stable family-root identifier such as `task-teacher-v2` rather than deriving
one from numeric prefixes.

Schema migration must be explicit. Existing synthetic tests can use a helper
that supplies complete provenance, but production readers must reject legacy
rows that lack the new binding fields.

## 8. Split Assignment and Leakage Gate

Assign the split before writing final rows, using the approved explicit
`reserved_families` interface. The producer must:

1. load a tracked split manifest containing family/base-episode assignments;
2. reject any competitive-test family presented for training/validation
   collection;
3. ensure all variants of a notebook episode share one canonical
   `base_episode_id` and split;
4. run `audit_split_leakage()` over the complete output set; and
5. refuse to publish JSONL or EDA tables if the audit fails.

Remove numeric-prefix inference from the effective data path. Canonical
base-episode identity comes from explicit metadata.

## 9. Live Compatibility and Divergence

Replace self-attestation in `validate_public_replays.py` with receipt-backed
validation:

- recompute JSONL observation/action stream hashes and match the receipt;
- match artifact, extracted/native source, transformation, collector, policy,
  family, base episode, seed, seat, opponent, configuration, and split;
- require executed `1.29.3`, `DONE`, exactly 719 decisions, finite final banks,
  zero uncaught exceptions, and no unexplained invalid action;
- report the final farm balance as the primary score source; and
- quarantine any stale, spliced, mutated, or self-attested-only data.

For replay-derived fixed action tapes, divergence includes invalid/missed
commands and differences between expected and actual action availability. For
an observation-driven callable, compatibility means successful execution of
the exact extracted source under `1.29.3`; its `1.32.2` notebook declaration is
historical provenance, not an automatic rejection after successful pinned
reproduction.

## 10. Paired Evaluation Evidence

Initial bridge verification uses seeds `217`, `317`, and `733`, both seats,
against the built-in starter for each admitted policy. These six games per
policy are an integration gate, not a population win-rate estimate.

Produce paired rows with:

- seed and candidate seat;
- candidate/opponent final banks;
- win/tie/loss;
- bank margin;
- both-seat aggregate margin for the seed;
- statuses and receipt IDs; and
- policy/opponent family.

The opponent/seat EDA decision may be `KEEP` only when real paired outcomes
exist. Completeness alone cannot justify it. Larger promotion samples continue
to follow the authoritative Hoeffding protocol and are outside this bridge.

## 11. Error Handling and Quarantine

Stable failure codes include:

- `unsupported_notebook_source_layout`;
- `source_hash_not_allowlisted`;
- `source_compile_failure`;
- `source_import_failure`;
- `runtime_version_mismatch`;
- `episode_timeout`;
- `episode_exception`;
- `incomplete_game`;
- `invalid_action`;
- `stream_hash_mismatch`;
- `receipt_mismatch`;
- `provenance_mismatch`;
- `split_leakage`; and
- `nonfinite_terminal_bank`.

Every requested run produces either eligible rows plus a receipt or a
quarantine receipt. Never silently drop a source, seed, or seat.

## 12. Outputs and Repository Boundaries

Tracked:

- public source allowlist and extraction metadata;
- split manifest;
- compact execution-receipt index without raw observations;
- compatibility/quarantine CSVs;
- paired-outcome and aggregate EDA tables;
- refreshed EDA decision report; and
- tests and implementation scripts.

Ignored:

- downloaded notebooks and episodes;
- extracted public `main.py` files;
- full observation/action JSONL;
- child-process logs beyond small failure excerpts; and
- temporary execution directories.

No credentials, absolute machine paths, raw private observations, or public
source bodies enter tracked summaries.

## 13. Test Strategy

Test-first coverage must include:

- static extraction of ordered `%%agentfile` cells;
- rejection of unsupported/reset/append-first layouts;
- exact notebook and extracted-source hashes;
- allowlist rejection;
- compile/import/runtime/timeout quarantine;
- 719-row collection and terminal attachment;
- public and teacher producers using the same collector contract;
- receipt canonicalization and tamper detection;
- schema migration and boolean-seat rejection;
- artifact/transformation/collector binding;
- explicit nonnumeric base-episode splitting;
- competitive-test reservation and full leakage audit;
- live compatibility overriding historical notebook version declarations;
- both-seat paired outcomes and margins; and
- deterministic regeneration of receipts, summaries, and EDA decisions.

Integration tests run at least one complete teacher episode in both seats.
The reviewed allowlisted public source must run in both seats or produce an
honest incompatibility receipt; before phase completion, at least one supported
public adapter must also produce eligible end-to-end rows in both seats.

## 14. Execution Sequence

1. Extend provenance/schema and define execution receipts.
2. Implement and test the static `%%agentfile` source adapter and allowlist.
3. Implement the child runner and unified instrumented collector.
4. Add `task_teacher_v2` collection and verify both seats.
5. Extract and run the scenario-aware public source under `1.29.3`.
6. If genuinely incompatible, add one explicitly reviewed fixed-tape adapter
   as the minimum public fallback.
7. Integrate receipt-backed compatibility, splits, and leakage auditing.
8. Generate the six-game-per-policy paired integration set.
9. Rebuild EDA tables/report and review the resulting strategy decisions.

Stop after step 9 for user and Claude review. Do not proceed into teacher
modification, BC corpus approval, GPU training, PPO, or submission.

## 15. Acceptance Criteria

- At least one allowlisted public policy and `task_teacher_v2` produce 719-row
  complete trajectories for seeds `217`, `317`, and `733` in both seats.
- Every row is bound to an execution receipt, artifact/source hashes,
  transformation/collector version, explicit base episode, and split.
- All eligible evidence is executed under exactly `1.29.3`; historical
  `1.32.2` provenance is retained without overriding successful reproduction.
- Mutation of any row, receipt, source hash, provenance field, or split causes
  deterministic quarantine.
- Family and base-episode leakage audit passes before summaries are published.
- Paired outcome tables contain all requested seeds/seats and drive the
  opponent/seat decision.
- EDA tables contain real public and teacher measurements rather than headers
  only.
- The full test suite passes with zero new warnings attributable to bridge
  code.
- BC remains blocked until the refreshed EDA/data gate is reviewed and
  explicitly approved.

