# Elite Replay EDA Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, attributed, leakage-safe pipeline that inventories the five public Kaggriculture notebooks, normalizes replay decisions, validates them against `kaggle-environments==1.29.3`, and produces decision-oriented elite-versus-teacher EDA.

**Architecture:** Raw public artifacts and trajectories stay in ignored `replays/public/raw/`; tested library modules own provenance, schemas, family splits, compatibility evaluation, and metrics. Thin CLI scripts orchestrate those modules into tracked manifests and summary tables, while one analysis-only notebook renders the summaries without duplicating computation.

**Tech Stack:** Python 3.11, `kaggle-environments==1.29.3`, standard-library `dataclasses`/`hashlib`/`json`/`csv`, pytest, pandas, matplotlib, seaborn, Jupyter notebook JSON.

## Global Constraints

- The verified execution contract is exactly `kaggle-environments==1.29.3`; do not silently install or evaluate with `1.32.2`.
- Preserve the public source owner, notebook URL, episode identifier, source hash, retrieval time, environment version, and action origin for every derived record.
- Do not claim authorship of public behavior.
- Raw notebooks, episodes, observations, normalized JSONL, and other large artifacts remain outside git under ignored paths.
- Dataset splits operate on complete source-policy families; variants derived from the same base episode may never cross splits.
- Original and repaired actions remain separate; repair must never overwrite the original label.
- The executable agent/package remains the source of truth; the EDA notebook contains visualization only.
- This phase does not modify a teacher, collect BC training data, train a model, run PPO, or submit to Kaggle.
- Commit only files belonging to the current task; preserve Claude's unrelated `docs/superpowers/plans/2026-08-02-task-teacher-v3-implementation.md` work.

---

## File Structure

- `src/kaggriculture_lib/replay_provenance.py`: immutable public-artifact manifest records, hashing, validation, and manifest I/O.
- `src/kaggriculture_lib/replay_schema.py`: normalized observation/action decision records and lossless JSONL serialization.
- `src/kaggriculture_lib/replay_splits.py`: deterministic family-level train/validation/family-holdout assignment and leakage audit.
- `src/kaggriculture_lib/replay_compat.py`: `1.29.3` action-shape checks, tape execution, divergence accounting, and compatibility reports.
- `src/kaggriculture_lib/replay_metrics.py`: reusable per-turn/per-day/per-episode feature extraction and source-comparison summaries.
- `scripts/inventory_public_artifacts.py`: hashes local raw notebook/episode artifacts and writes a tracked manifest.
- `scripts/validate_public_replays.py`: normalizes supplied trajectory exports and writes compatibility/quarantine reports.
- `scripts/build_elite_eda.py`: writes tracked aggregate CSV tables and a decision-report Markdown skeleton populated with measured facts.
- `notebooks/02_elite_replay_eda.ipynb`: thin rendering layer over tracked aggregate tables.
- `replays/public/manifest.json`: tracked small provenance manifest; no raw notebook content.
- `replays/analysis/elite_*.csv`: tracked compact aggregate tables.
- `docs/7_elite_replay_eda.md`: findings, evidence, and explicit keep/change/reject decisions.
- `tests/test_replay_provenance.py`, `tests/test_replay_schema.py`, `tests/test_replay_splits.py`, `tests/test_replay_compat.py`, `tests/test_replay_metrics.py`: focused unit/integration coverage.

---

### Task 1: Public Artifact Provenance and Inventory

**Files:**
- Create: `src/kaggriculture_lib/replay_provenance.py`
- Create: `scripts/inventory_public_artifacts.py`
- Create: `tests/test_replay_provenance.py`
- Modify: `.gitignore`
- Create: `replays/public/manifest.json`

**Interfaces:**
- Produces: `PublicArtifact`, `sha256_file(path: Path) -> str`, `load_manifest(path: Path) -> list[PublicArtifact]`, `write_manifest(records: Sequence[PublicArtifact], path: Path) -> None`.
- Consumes: five user-approved Kaggle notebook URLs and locally downloaded `.ipynb` files supplied with `--artifact owner/slug=path`.

- [ ] **Step 1: Write failing provenance tests**

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kaggriculture_lib.replay_provenance import (
    PublicArtifact,
    load_manifest,
    sha256_file,
    write_manifest,
)


def test_sha256_file_is_content_addressed(tmp_path: Path):
    source = tmp_path / "source.ipynb"
    source.write_bytes(b"public notebook bytes")
    assert sha256_file(source) == "5eb611ebdfd3dcc277d94d8e7684a4592caad2f5de7c9fb443f94e468385b5ce"


def test_manifest_round_trip_is_sorted_and_lossless(tmp_path: Path):
    fetched = datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc)
    records = [
        PublicArtifact(
            source_policy_id="prvsiyan/frontier-v12",
            source_family="radiant-89256171",
            owner="prvsiyan",
            notebook_url="https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-lab-high-score-visuals",
            episode_id="89256171",
            retrieved_at=fetched.isoformat(),
            sha256="a" * 64,
            declared_environment="1.32.2",
        )
    ]
    path = tmp_path / "manifest.json"
    write_manifest(records, path)
    assert load_manifest(path) == records


def test_artifact_rejects_missing_attribution():
    with pytest.raises(ValueError, match="owner"):
        PublicArtifact(
            source_policy_id="x",
            source_family="family",
            owner="",
            notebook_url="https://www.kaggle.com/code/a/b",
            episode_id=None,
            retrieved_at="2026-08-02T07:00:00+00:00",
            sha256="a" * 64,
            declared_environment="unknown",
        )
```

- [ ] **Step 2: Run the tests and verify the expected import failure**

Run: `.venv/bin/python -m pytest tests/test_replay_provenance.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: kaggriculture_lib.replay_provenance`.

- [ ] **Step 3: Implement the immutable manifest model and deterministic I/O**

```python
@dataclass(frozen=True)
class PublicArtifact:
    source_policy_id: str
    source_family: str
    owner: str
    notebook_url: str
    episode_id: str | None
    retrieved_at: str
    sha256: str
    declared_environment: str

    def __post_init__(self) -> None:
        required = {
            "source_policy_id": self.source_policy_id,
            "source_family": self.source_family,
            "owner": self.owner,
            "notebook_url": self.notebook_url,
            "retrieved_at": self.retrieved_at,
            "declared_environment": self.declared_environment,
        }
        for name, value in required.items():
            if not value:
                raise ValueError(f"{name} must be non-empty")
        if len(self.sha256) != 64 or any(c not in hexdigits for c in self.sha256.lower()):
            raise ValueError("sha256 must contain 64 hexadecimal characters")
```

Implement JSON output with `sort_keys=True`, `indent=2`, a trailing newline,
and records sorted by `source_policy_id`. `load_manifest()` must reject duplicate
policy IDs and duplicate `(sha256, source_policy_id)` records.

- [ ] **Step 4: Implement the inventory CLI and ignored raw-data boundary**

The CLI signature must be:

```text
python scripts/inventory_public_artifacts.py \
  --spec scripts/public_artifacts.json \
  --output replays/public/manifest.json
```

The local `scripts/public_artifacts.json` configuration contains policy ID,
family, owner, URL, episode, declared environment, and raw path. The script
hashes bytes and inserts an explicit UTC retrieval timestamp. Add these rules:

```gitignore
replays/public/raw/
replays/public/*.jsonl
scripts/public_artifacts.json
```

Do not commit raw downloaded notebooks or the machine-specific configuration.
Commit the generated manifest only after reviewing that it contains no local
paths.

- [ ] **Step 5: Run tests and a CLI smoke check**

Run:

```bash
.venv/bin/python -m pytest tests/test_replay_provenance.py -q
.venv/bin/python scripts/inventory_public_artifacts.py --help
```

Expected: all provenance tests PASS; CLI exits 0 and documents both required
arguments.

- [ ] **Step 6: Commit the provenance slice**

```bash
git add .gitignore src/kaggriculture_lib/replay_provenance.py scripts/inventory_public_artifacts.py tests/test_replay_provenance.py replays/public/manifest.json
git commit -m "feat: inventory attributed public Kaggriculture artifacts"
```

---

### Task 2: Normalized Decision Schema and Lossless Serialization

**Files:**
- Create: `src/kaggriculture_lib/replay_schema.py`
- Create: `tests/test_replay_schema.py`

**Interfaces:**
- Consumes: `PublicArtifact.source_policy_id` and raw observation/action dictionaries.
- Produces: `ActionOrigin`, `NormalizedAction`, `DecisionRecord`, `normalize_action(action: Mapping[str, Any]) -> NormalizedAction`, `write_decisions(records: Iterable[DecisionRecord], path: Path) -> None`, `read_decisions(path: Path) -> Iterator[DecisionRecord]`.

- [ ] **Step 1: Write failing schema tests**

```python
def test_normalize_action_preserves_order_and_quantities():
    raw = {
        "farmer": ["PLANT", "MELON"],
        "hands": [["MOVE", "N"], ["PASS"]],
        "market": [["SELL", "MILK", 4], ["HIRE"]],
    }
    normalized = normalize_action(raw)
    assert normalized.farmer == ("PLANT", "MELON")
    assert normalized.hands == (("MOVE", "N"), ("PASS",))
    assert normalized.market == (("SELL", "MILK", 4), ("HIRE",))


def test_repaired_record_keeps_original_and_reason(sample_record):
    repaired = replace(
        sample_record,
        action_origin=ActionOrigin.PUBLIC_REPAIRED,
        original_action=sample_record.action,
        action=NormalizedAction(("PASS",), (), ()),
        repair_reason="seed unavailable",
    )
    assert repaired.original_action != repaired.action
    assert repaired.repair_reason == "seed unavailable"


def test_jsonl_round_trip_is_lossless(tmp_path, sample_record):
    path = tmp_path / "decisions.jsonl"
    write_decisions([sample_record], path)
    assert list(read_decisions(path)) == [sample_record]
```

The `sample_record` fixture includes episode/source/family, step/day/hour,
seat, opponent family, environment/configuration, normalized observation,
action, origin, optional repair fields, terminal result/final banks, and
compatibility/legality/completeness/duplication flags.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest tests/test_replay_schema.py -q`

Expected: FAIL with missing `replay_schema` module.

- [ ] **Step 3: Implement frozen schema types**

```python
class ActionOrigin(str, Enum):
    PUBLIC_ORIGINAL = "public_original"
    PUBLIC_REPAIRED = "public_repaired"
    TEACHER = "teacher"


@dataclass(frozen=True)
class NormalizedAction:
    farmer: tuple[str | int, ...]
    hands: tuple[tuple[str | int, ...], ...]
    market: tuple[tuple[str | int, ...], ...]


@dataclass(frozen=True)
class DecisionRecord:
    episode_id: str
    source_policy_id: str
    source_family: str
    step: int
    day: int
    hour: int
    seat: int
    opponent_family: str
    environment_version: str
    configuration: Mapping[str, Any]
    observation: Mapping[str, Any]
    action: NormalizedAction
    action_origin: ActionOrigin
    original_action: NormalizedAction | None
    repair_reason: str | None
    terminal_result: str | None
    final_banks: tuple[float, float] | None
    compatibility_ok: bool
    legality_ok: bool
    completeness_ok: bool
    duplicate: bool
```

Validate `step == day * 24 + hour`, seats in `{0, 1}`, repair fields only for
`PUBLIC_REPAIRED`, finite final banks, and exact action container structure.
Use recursive JSON-compatible normalization so serialization is deterministic.

- [ ] **Step 4: Implement JSONL I/O with row-numbered errors**

`write_decisions()` writes one sorted-key JSON object per line. `read_decisions()`
must raise `ValueError("<path>:<line>: ...")` for malformed JSON or schema
violations so quarantine reports can point to exact records.

- [ ] **Step 5: Run schema tests and full regression suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_replay_schema.py -q
.venv/bin/python -m pytest tests/ -q
```

Expected: schema tests and the existing suite PASS.

- [ ] **Step 6: Commit the schema slice**

```bash
git add src/kaggriculture_lib/replay_schema.py tests/test_replay_schema.py
git commit -m "feat: define normalized replay decision schema"
```

---

### Task 3: Family-Level Splits and Leakage Audit

**Files:**
- Create: `src/kaggriculture_lib/replay_splits.py`
- Create: `tests/test_replay_splits.py`

**Interfaces:**
- Consumes: sequences of `DecisionRecord` or `(episode_id, source_family)` metadata.
- Produces: `SplitName`, `SplitAssignment`, `assign_family_splits(families: Sequence[str], seed: int, validation_fraction: float, holdout_families: AbstractSet[str]) -> dict[str, SplitName]`, `audit_split_leakage(records: Iterable[DecisionRecord], assignments: Mapping[str, SplitName]) -> LeakageReport`.

- [ ] **Step 1: Write failing deterministic split tests**

```python
def test_variants_of_same_family_never_cross_splits():
    families = ["radiant-89468208", "radiant-89468208", "scenario-aware", "teacher-v2"]
    assignment = assign_family_splits(
        families,
        seed=20260802,
        validation_fraction=0.25,
        holdout_families={"scenario-aware"},
    )
    assert assignment["scenario-aware"] is SplitName.FAMILY_HOLDOUT
    assert set(assignment) == set(families)


def test_split_assignment_is_order_independent():
    forward = assign_family_splits(["a", "b", "c"], 7, 0.34, {"c"})
    reverse = assign_family_splits(["c", "b", "a"], 7, 0.34, {"c"})
    assert forward == reverse


def test_audit_rejects_episode_and_family_leakage(leaking_records, assignments):
    report = audit_split_leakage(leaking_records, assignments)
    assert not report.ok
    assert report.family_leaks == ("radiant-89468208",)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest tests/test_replay_splits.py -q`

Expected: FAIL with missing `replay_splits` module.

- [ ] **Step 3: Implement stable family hashing and reserved test semantics**

Hash `f"{seed}:{family}"` with SHA-256 and map the first eight bytes to
`[0, 1)`. Explicit holdout families override hashing. Produce train,
validation, and family-holdout assignments here; competitive-test episodes
remain externally reserved and must be rejected if passed to training split
generation.

- [ ] **Step 4: Implement leakage auditing**

The report contains duplicate episode IDs across splits, source families across
splits, base episode IDs across splits, and missing assignments. It must render
a deterministic human-readable error summary for CI and the EDA report.

- [ ] **Step 5: Run split tests and full suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_replay_splits.py -q
.venv/bin/python -m pytest tests/ -q
```

Expected: all tests PASS.

- [ ] **Step 6: Commit the split slice**

```bash
git add src/kaggriculture_lib/replay_splits.py tests/test_replay_splits.py
git commit -m "feat: enforce replay family split isolation"
```

---

### Task 4: Pinned-Runtime Compatibility and Quarantine Reports

**Files:**
- Create: `src/kaggriculture_lib/replay_compat.py`
- Create: `scripts/validate_public_replays.py`
- Create: `tests/test_replay_compat.py`

**Interfaces:**
- Consumes: `DecisionRecord` sequences, a callable tape policy, a seed, and a seat.
- Produces: `CompatibilityIssue`, `CompatibilityReport`, `validate_action_shape(action: NormalizedAction, expected_hands: int) -> tuple[CompatibilityIssue, ...]`, `run_tape_compatibility(policy: Callable, seed: int, seat: int, opponent: str = "starter") -> CompatibilityReport`.

- [ ] **Step 1: Write failing action and runtime tests**

```python
def test_shape_validator_rejects_wrong_hand_count():
    action = NormalizedAction(("PASS",), (("PASS",),), ())
    issues = validate_action_shape(action, expected_hands=0)
    assert [issue.code for issue in issues] == ["hand_count_mismatch"]


def test_shape_validator_rejects_more_than_ten_market_orders():
    action = NormalizedAction(("PASS",), (), tuple(("HIRE",) for _ in range(11)))
    issues = validate_action_shape(action, expected_hands=0)
    assert "market_order_limit" in {issue.code for issue in issues}


def test_pass_tape_completes_both_seats_under_pinned_runtime():
    def pass_policy(obs, config=None):
        hands = len(obs["farms"][obs["player"]]["hands"])
        return {"farmer": ["PASS"], "hands": [["PASS"]] * hands, "market": []}

    reports = [run_tape_compatibility(pass_policy, seed=31, seat=seat) for seat in (0, 1)]
    assert all(report.environment_version == "1.29.3" for report in reports)
    assert all(report.status == "DONE" for report in reports)
    assert all(report.action_calls == 719 for report in reports)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest tests/test_replay_compat.py -q`

Expected: FAIL with missing `replay_compat` module.

- [ ] **Step 3: Implement static action validation**

Check farmer/hands/market containers, exact hand count, the ten-order market
limit, known operation arities, integer positive quantities, and finite numeric
values. Static validation reports issues; it does not mutate actions.

- [ ] **Step 4: Implement live compatibility execution**

Before importing the environment, assert:

```python
import kaggle_environments

if kaggle_environments.__version__ != "1.29.3":
    raise RuntimeError(
        f"compatibility evaluation requires kaggle-environments==1.29.3; "
        f"found {kaggle_environments.__version__}"
    )
```

Execute both seats through `make("kaggriculture", configuration={"seed": seed})`.
Capture status, 719-call count, exceptions, action-shape issues, final public
farm balances, and SHA-256 of the emitted action stream. Never use zero-valued
`state.reward` as the primary score when final farm balances are available.

- [ ] **Step 5: Implement validation CLI and quarantine classification**

CLI signature:

```text
python scripts/validate_public_replays.py \
  --manifest replays/public/manifest.json \
  --input replays/public/raw/normalized \
  --output replays/analysis/elite_compatibility.csv \
  --quarantine replays/analysis/elite_quarantine.csv
```

Primary eligibility requires pinned version, `DONE`, 719 calls, no exception,
and no unexplained invalid action. Each rejected source receives stable reason
codes such as `version_mismatch`, `missing_episode`, `invalid_action`,
`incomplete_game`, or `unreproducible_source`.

- [ ] **Step 6: Run compatibility tests and full suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_replay_compat.py -q
.venv/bin/python -m pytest tests/ -q
```

Expected: compatibility tests pass under `1.29.3`; full suite remains green.

- [ ] **Step 7: Commit compatibility work**

```bash
git add src/kaggriculture_lib/replay_compat.py scripts/validate_public_replays.py tests/test_replay_compat.py
git commit -m "feat: validate public policies on pinned Kaggriculture runtime"
```

---

### Task 5: Decision-Oriented Replay Metrics

**Files:**
- Create: `src/kaggriculture_lib/replay_metrics.py`
- Create: `tests/test_replay_metrics.py`

**Interfaces:**
- Consumes: ordered `DecisionRecord` rows and their post-action observations.
- Produces: `TurnMetrics`, `EpisodeSummary`, `extract_turn_metrics(record: DecisionRecord, next_observation: Mapping[str, Any] | None) -> TurnMetrics`, `summarize_episode(rows: Sequence[TurnMetrics]) -> EpisodeSummary`, `compare_sources(summaries: Sequence[EpisodeSummary]) -> list[dict[str, Any]]`.

- [ ] **Step 1: Write failing metric tests using tiny synthetic episodes**

```python
def test_terminal_stranded_value_counts_carried_and_shed_products(terminal_record):
    metrics = extract_turn_metrics(terminal_record, next_observation=None)
    assert metrics.shed_units == 7
    assert metrics.carried_units == 3
    assert metrics.terminal_stranded_units == 10


def test_worker_allocation_separates_productive_travel_logistics_and_idle(records):
    summary = summarize_episode([extract_turn_metrics(r, None) for r in records])
    assert summary.productive_actions == 2
    assert summary.travel_actions == 1
    assert summary.logistics_actions == 2
    assert summary.idle_actions == 1


def test_sell_proceeds_use_observed_bank_delta_not_spot_times_quantity(sale_record, next_obs):
    metrics = extract_turn_metrics(sale_record, next_obs)
    assert metrics.realized_bank_delta == 37.0
    assert metrics.realized_bank_delta != 4 * sale_record.observation["market"]["prices"]["MILK"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest tests/test_replay_metrics.py -q`

Expected: FAIL with missing `replay_metrics` module.

- [ ] **Step 3: Implement turn-level facts without causal overclaiming**

Extract day/hour, money, unlocked quadrants, active hands, crop/animal counts,
shed/carried units, action-family counts, movement steps, market order counts,
visible opponent assets, current prices/inventory, and observed next-state bank
delta. Name simultaneous-action values `observed_*`, not `caused_by_*`.

- [ ] **Step 4: Implement episode and source summaries**

Aggregate:

- land-opening day and purchase count;
- hand peak/range and hire orders;
- productive/travel/logistics/idle action shares;
- crop and animal exposure by day;
- sell quantity, observed bank delta, and concentration by product;
- storage-pressure turns and terminal stranded units;
- final bank, seat, opponent family, status, and result; and
- final-window cash changes over 8, 22, and 48 actions.

Do not label a capital event's payback as causal unless a counterfactual exists;
report `bank_recovery_turns_after_purchase` as a descriptive diagnostic.

- [ ] **Step 5: Add invariant and missing-data tests**

Test empty episodes, non-contiguous steps, missing next observations, partial
inventories, unknown actions, and non-finite banks. Unknown actions are counted
as `other`, while broken chronology and non-finite money raise `ValueError`.

- [ ] **Step 6: Run metrics tests and full suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_replay_metrics.py -q
.venv/bin/python -m pytest tests/ -q
```

Expected: all tests PASS.

- [ ] **Step 7: Commit metrics work**

```bash
git add src/kaggriculture_lib/replay_metrics.py tests/test_replay_metrics.py
git commit -m "feat: summarize elite replay strategy metrics"
```

---

### Task 6: Aggregate EDA, Thin Notebook, and Strategy Decisions

**Files:**
- Create: `scripts/build_elite_eda.py`
- Create: `tests/test_build_elite_eda.py`
- Create: `notebooks/02_elite_replay_eda.ipynb`
- Create: `docs/7_elite_replay_eda.md`
- Modify: `docs/0_coding_standards.md`
- Modify: `docs/6_next_steps.md`
- Create: `replays/analysis/elite_daily.csv`
- Create: `replays/analysis/elite_episode_summary.csv`
- Create: `replays/analysis/elite_source_comparison.csv`
- Create: `replays/analysis/elite_coverage_gap.csv`
- Create: `replays/analysis/elite_compatibility.csv`
- Create: `replays/analysis/elite_quarantine.csv`

**Interfaces:**
- Consumes: manifest, normalized primary/quarantine decisions, compatibility reports, and `task_teacher_v2` comparison trajectories.
- Produces: deterministic compact CSVs and `docs/7_elite_replay_eda.md`; the notebook reads only those outputs.

- [ ] **Step 1: Write a failing end-to-end fixture test**

```python
def test_build_eda_outputs_are_deterministic_and_decision_complete(tmp_path, fixture_dataset):
    result = build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=tmp_path / "analysis",
        report_path=tmp_path / "report.md",
    )
    assert result.source_count == 3
    assert (tmp_path / "analysis/elite_daily.csv").exists()
    report = (tmp_path / "report.md").read_text()
    for section in ("Capital and expansion", "Portfolio and market", "Labor and routing",
                    "Storage and terminal", "Opponent and seat", "Coverage gap"):
        assert f"## {section}" in report
    assert "Decision: KEEP" in report
    assert "Decision: CHANGE" in report
    assert "Decision: REJECT" in report
```

- [ ] **Step 2: Run the test to verify failure**

Run: `.venv/bin/python -m pytest tests/test_build_elite_eda.py -q`

Expected: FAIL because `scripts.build_elite_eda` does not exist.

- [ ] **Step 3: Implement deterministic aggregate-table generation**

`build_eda()` must call library metrics rather than reimplement them. Sort every
CSV by stable keys, format floats consistently, and write atomically. Generate
the six required decision sections with measured table references, source
counts, eligibility/quarantine counts, and explicit `KEEP`, `CHANGE`, or
`REJECT` lines. If evidence is insufficient, write `REJECT: insufficient
compatible evidence` rather than a placeholder.

- [ ] **Step 4: Add coverage-gap comparisons**

For elite, teacher, and repaired sources, emit counts/quantiles for day/hour,
land count, hand count, crop/animal composition, money, storage load, prices,
action families, market operations, and terminal/crisis states. Include
Jensen-Shannon distance only for normalized categorical distributions with
shared support; use standardized median difference for scalar diagnostics.
Record zero-support critical actions explicitly.

- [ ] **Step 5: Create the analysis-only notebook**

The notebook may import pandas/matplotlib/seaborn and read the tracked CSVs. It
must contain no artifact retrieval, normalization, compatibility, split,
metric, or policy logic. Required views:

1. daily capital/land/labor trajectories by source family;
2. crop and herd composition over time;
3. action allocation and travel/logistics shares;
4. sell concentration versus observed proceeds;
5. storage pressure and final-window conversion; and
6. elite-versus-teacher coverage-gap heatmap.

Add a note to `docs/0_coding_standards.md` allowing this narrow analysis-only
notebook exception while retaining tested library code as the source of truth.

- [ ] **Step 6: Run the real pipeline on available compatible artifacts**

Run:

```bash
.venv/bin/python scripts/validate_public_replays.py --manifest replays/public/manifest.json --input replays/public/raw/normalized --output replays/analysis/elite_compatibility.csv --quarantine replays/analysis/elite_quarantine.csv
.venv/bin/python scripts/build_elite_eda.py --manifest replays/public/manifest.json --decisions replays/public/raw/normalized --output-dir replays/analysis --report docs/7_elite_replay_eda.md
```

Expected: both commands exit 0; unavailable episodes are quarantined with
reason codes; no source is silently dropped.

- [ ] **Step 7: Verify the notebook and generated evidence**

Run:

```bash
.venv/bin/jupyter nbconvert --to notebook --execute notebooks/02_elite_replay_eda.ipynb --output /tmp/02_elite_replay_eda.executed.ipynb --ExecutePreprocessor.timeout=600
.venv/bin/python -m pytest tests/test_build_elite_eda.py -q
.venv/bin/python -m pytest tests/ -q
git diff --check
```

Expected: notebook execution succeeds, tests pass, and no whitespace errors are
reported. Manually verify every report claim cites a generated table or clearly
states it is an inference.

- [ ] **Step 8: Update next steps from measured decisions**

In `docs/6_next_steps.md`, link the EDA report and add only the teacher/public-
benchmark tasks supported by `docs/7_elite_replay_eda.md`. Do not approve BC
collection merely because summaries exist; the EDA/data gate in the design
must explicitly pass first.

- [ ] **Step 9: Commit the completed EDA phase**

```bash
git add scripts/build_elite_eda.py tests/test_build_elite_eda.py notebooks/02_elite_replay_eda.ipynb docs/0_coding_standards.md docs/6_next_steps.md docs/7_elite_replay_eda.md replays/analysis
git commit -m "feat: add decision-oriented elite replay EDA"
```

---

## Final Phase Verification

- [ ] Run `.venv/bin/python -m pytest tests/ -q`; expected: all tests pass.
- [ ] Run the inventory, compatibility, and EDA CLIs twice; expected: tracked
  outputs are byte-identical except when an explicitly refreshed retrieval
  timestamp changes the manifest.
- [ ] Run `git diff --check`; expected: no errors.
- [ ] Run `git status --short`; expected: only ignored raw artifacts and any
  explicitly preserved unrelated user/Claude work remain outside the phase's
  commits.
- [ ] Audit `replays/public/manifest.json` and tracked CSVs for credentials,
  absolute local paths, or raw private state; expected: none.
- [ ] Confirm `docs/7_elite_replay_eda.md` contains all six decisions and a
  compatibility/quarantine accounting for every source.
- [ ] Stop for user review. Do not begin teacher modifications, BC dataset
  generation, Kaggle GPU training, PPO, or competition submission.
