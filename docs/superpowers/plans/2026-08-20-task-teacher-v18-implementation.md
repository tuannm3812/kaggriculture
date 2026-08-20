# Task Teacher v18 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and evaluate a higher-variance `task_teacher_v18` agent that preserves v16 against compact opponents and conditionally expands when public opponent state indicates a compounding land-and-animal economy.

**Architecture:** Put deterministic threat, reserve, utilization, and labor decisions in a focused shared module, then integrate those pure interfaces into a copy-forward v18 agent. Keep a config-controlled classifier-only ablation that executes the legacy v16 policy, and expose diagnostics through module state without changing the competition action schema.

**Tech Stack:** Python 3.11, `dataclasses`, `enum.IntEnum`, `pytest`, `kaggle-environments==1.29.3`, the existing tournament and packaging scripts.

**Spec:** `docs/superpowers/specs/2026-08-20-task-teacher-v18-design.md`

## Global Constraints

- Read the approved spec before starting and preserve `task_teacher_v16` and `task_teacher_v17` unchanged.
- Use ladder-match configuration: `startingMoney=3000`, `farmHandCostMult=1`, `townShopSellInterval=4`, `townCenterSellInterval=24`, `turnsPerDay=24`.
- Read opponent public fields only; never use opponent inventory or other private state.
- Threat state is monotonic per player and resets at step 0 or when step decreases.
- Default v18 behavior enables threat-conditioned expansion; `enableThreatExpansion=False` must execute the v16-compatible path for ablation.
- No competition action may contain telemetry or any non-schema key.
- Land cost, queued hires, assigned seeds, two-day feed, `$1,200` animal liquidity, and `$500` operating liquidity are each deducted exactly once.
- Third land requires `COMPOUNDING`, hour 23, and at least 12 full days remaining.
- Fourth land requires the severe-threat gate, at least 14 full days remaining, at least 70% productive utilization, and `$8,000` remaining after its `$4,000` price and all reserves.
- Do not change crop scoring, task assignment, routing, animal caps, or liquidation behavior.
- Implement every behavior test-first and make a focused commit after each task.

---

## File Structure

- Create `src/kaggriculture_lib/adaptive_strategy.py`: pure threat classification, cash ledger, utilization, executable-backlog, and labor-target interfaces.
- Create `tests/test_adaptive_strategy.py`: exhaustive boundary tests for the shared policy module.
- Create `agents/task_teacher_v18/main.py`: copy-forward v16 agent that consumes the shared interfaces and exposes local diagnostics.
- Create `tests/test_task_teacher_v18.py`: integration, ablation, action-schema, episode-state, market-accounting, simulator, and deterministic behavior tests.
- Create `scripts/evaluate_task_teacher_v18.py`: paired evaluation wrapper that captures v18 diagnostics without modifying action output.
- Create `tests/test_evaluate_task_teacher_v18.py`: telemetry aggregation and JSON-output tests.
- Modify `tests/test_package_agent.py`: prove the new transitive shared module is bundled and runs standalone.
- Modify `docs/3_agent_strategy.md`, `docs/4_agent_version_log.md`, and `docs/6_next_steps.md` only after measured evaluation, recording evidence rather than planned claims.

---

### Task 1: Pure Opponent Threat Classifier

**Files:**
- Create: `src/kaggriculture_lib/adaptive_strategy.py`
- Create: `tests/test_adaptive_strategy.py`

**Interfaces:**
- Consumes: public counts only: `quadrants`, `hands`, `placed_animals`, `step`, `day`, `hour`.
- Produces: `ThreatLevel`, `ThreatSnapshot`, `ThreatTransition`, and `ThreatMemory.update(...)`.

- [ ] **Step 1: Write failing classifier boundary tests**

```python
from kaggriculture_lib.adaptive_strategy import (
    ThreatLevel,
    ThreatMemory,
    ThreatSnapshot,
)


def snap(quadrants=1, hands=0, animals=0):
    return ThreatSnapshot(quadrants, hands, animals)


def test_compact_boundaries():
    memory = ThreatMemory()
    transition = memory.update(player=0, step=0, day=0, hour=0, snapshot=snap(2, 5, 2))
    assert transition.level is ThreatLevel.COMPACT
    assert transition.reason == "compact"


def test_each_building_trigger():
    assert ThreatMemory().update(0, 0, 0, 0, snap(2, 0, 0)).level is ThreatLevel.BUILDING
    assert ThreatMemory().update(0, 0, 0, 0, snap(1, 6, 0)).level is ThreatLevel.BUILDING
    assert ThreatMemory().update(0, 0, 0, 0, snap(1, 0, 3)).level is ThreatLevel.BUILDING


def test_each_compounding_trigger_and_reason():
    cases = [
        (snap(3, 0, 0), "three_quadrants"),
        (snap(2, 0, 4), "two_quadrants_four_animals"),
        (snap(2, 8, 0), "two_quadrants_eight_hands"),
        (snap(1, 0, 6), "six_animals"),
    ]
    for snapshot, reason in cases:
        transition = ThreatMemory().update(0, 0, 0, 0, snapshot)
        assert transition.level is ThreatLevel.COMPOUNDING
        assert transition.reason == reason
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py -q`

Expected: collection fails because `kaggriculture_lib.adaptive_strategy` does not exist.

- [ ] **Step 3: Add exact classifier types and priority order**

```python
from dataclasses import dataclass, field
from enum import IntEnum


class ThreatLevel(IntEnum):
    COMPACT = 0
    BUILDING = 1
    COMPOUNDING = 2


@dataclass(frozen=True)
class ThreatSnapshot:
    quadrants: int
    hands: int
    placed_animals: int


@dataclass(frozen=True)
class ThreatTransition:
    level: ThreatLevel
    changed: bool
    reason: str
    day: int
    hour: int
    delta_quadrants: int = 0
    delta_hands: int = 0
    delta_animals: int = 0


@dataclass
class ThreatMemory:
    level_by_player: dict[int, ThreatLevel] = field(default_factory=dict)
    reason_by_player: dict[int, str] = field(default_factory=dict)
    previous_step_by_player: dict[int, int] = field(default_factory=dict)
    previous_snapshot_by_player: dict[int, ThreatSnapshot] = field(default_factory=dict)

    def update(self, player, step, day, hour, snapshot):
        previous_step = self.previous_step_by_player.get(player, -1)
        reset = step == 0 or step < previous_step
        previous_snapshot = self.previous_snapshot_by_player.get(player)
        if reset:
            self.level_by_player[player] = ThreatLevel.COMPACT
            self.reason_by_player.pop(player, None)
            previous_snapshot = None
        self.previous_step_by_player[player] = step
        if previous_snapshot is None:
            delta_quadrants = delta_hands = delta_animals = 0
        else:
            delta_quadrants = snapshot.quadrants - previous_snapshot.quadrants
            delta_hands = snapshot.hands - previous_snapshot.hands
            delta_animals = snapshot.placed_animals - previous_snapshot.placed_animals
        self.previous_snapshot_by_player[player] = snapshot

        if snapshot.quadrants >= 3:
            observed, reason = ThreatLevel.COMPOUNDING, "three_quadrants"
        elif snapshot.quadrants >= 2 and snapshot.placed_animals >= 4:
            observed, reason = ThreatLevel.COMPOUNDING, "two_quadrants_four_animals"
        elif snapshot.quadrants >= 2 and snapshot.hands >= 8:
            observed, reason = ThreatLevel.COMPOUNDING, "two_quadrants_eight_hands"
        elif snapshot.placed_animals >= 6:
            observed, reason = ThreatLevel.COMPOUNDING, "six_animals"
        elif snapshot.quadrants >= 2:
            observed, reason = ThreatLevel.BUILDING, "extra_quadrant"
        elif snapshot.hands >= 6:
            observed, reason = ThreatLevel.BUILDING, "six_hands"
        elif snapshot.placed_animals >= 3:
            observed, reason = ThreatLevel.BUILDING, "three_animals"
        else:
            observed, reason = ThreatLevel.COMPACT, "compact"

        previous = self.level_by_player.get(player, ThreatLevel.COMPACT)
        current = max(previous, observed)
        changed = current > previous
        stable_reason = reason if changed or player not in self.reason_by_player else self.reason_by_player[player]
        self.level_by_player[player] = current
        self.reason_by_player[player] = stable_reason
        return ThreatTransition(current, changed, stable_reason, day, hour,
                                delta_quadrants, delta_hands, delta_animals)
```

Keep the signature positional/keyword-compatible with the tests. Add type annotations and a module docstring; do not add game imports.

- [ ] **Step 4: Add monotonicity, player isolation, reset, and malformed-input tests**

Test that an animal disappearance cannot lower state, player 0 and player 1 do not share state, step 0 resets, decreasing step resets, observed public-count increases appear in transition deltas, and `parse_public_threat_snapshot(farm)` returns `(COMPACT-safe snapshot, "malformed_public_state")` for missing/non-list public fields rather than raising.

- [ ] **Step 5: Implement public snapshot parsing minimally**

Implement `parse_public_threat_snapshot(farm: dict) -> tuple[ThreatSnapshot, str | None]`. Count animals by scanning public tiles for `tile.get("animal") in {"COW", "SHEEP", "GOOSE"}`. Count hands with `len(farm["hands"])` and quadrants with `len(farm["unlocked_quadrants"])`. Catch only `(KeyError, TypeError)` and return a zero snapshot plus the malformed reason.

- [ ] **Step 6: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py -q`

Expected: all threat tests pass.

```bash
git add src/kaggriculture_lib/adaptive_strategy.py tests/test_adaptive_strategy.py
git commit -m "feat: add opponent threat classifier"
```

---

### Task 2: Single Cash Ledger and Land Authorization

**Files:**
- Modify: `src/kaggriculture_lib/adaptive_strategy.py`
- Modify: `tests/test_adaptive_strategy.py`

**Interfaces:**
- Consumes: money, individual reserve values, next land cost, threat level, time, and utilization.
- Produces: `CashLedger`, `LandDecision`, and `authorize_land_purchase(...)`.

- [ ] **Step 1: Write failing ledger tests**

```python
from kaggriculture_lib.adaptive_strategy import CashLedger, LandDecision, authorize_land_purchase


def test_cash_ledger_deducts_every_reserve_once():
    ledger = CashLedger(
        queued_hires=100,
        assigned_seeds=200,
        two_day_feed=300,
        animal_liquidity=1200,
        operating=500,
    )
    assert ledger.total_reserved == 2300
    assert ledger.remaining(money=10_000, purchase_cost=2_000) == 5700


def test_third_land_requires_compounding_hour_and_horizon():
    ledger = CashLedger(100, 200, 300, 1200, 500)
    decision = authorize_land_purchase(
        threat=ThreatLevel.COMPOUNDING,
        n_extra=1,
        day=15,
        hour=23,
        last_day=29,
        money=10_000,
        land_cost=2_000,
        ledger=ledger,
        productive_utilization=0.0,
        opponent_quadrants=3,
        opponent_animals=4,
    )
    assert decision == LandDecision(True, "third_land_compounding", 5700)
```

Add negative cases for `BUILDING`, hour 22, 11 days remaining, insufficient money, invalid cost, and already three extra quadrants.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py -q`

Expected: import errors for the new ledger interfaces.

- [ ] **Step 3: Implement immutable ledger and decision types**

```python
@dataclass(frozen=True)
class CashLedger:
    queued_hires: float
    assigned_seeds: float
    two_day_feed: float
    animal_liquidity: float = 1200.0
    operating: float = 500.0

    @property
    def total_reserved(self) -> float:
        return sum((self.queued_hires, self.assigned_seeds, self.two_day_feed,
                    self.animal_liquidity, self.operating))

    def remaining(self, money: float, purchase_cost: float = 0.0) -> float:
        return money - self.total_reserved - purchase_cost


@dataclass(frozen=True)
class LandDecision:
    authorized: bool
    reason: str
    remaining_cash: float
```

Implement `authorize_land_purchase` with separate third-land (`n_extra == 1`) and fourth-land (`n_extra == 2`) branches. Return explicit rejection reasons for telemetry.

- [ ] **Step 4: Add fourth-land tests**

Require hour 23, 14 days remaining, utilization `>= 0.70`, severe threat (`opponent_quadrants >= 4 or opponent_animals >= 10`), land price `4000`, and ledger remaining `>= 8000`. Test every boundary independently, including `0.699` rejection and exactly `0.70` acceptance.

- [ ] **Step 5: Add reserve validation**

Reject negative or non-finite ledger components with `ValueError`. Add parameterized tests for each field and for `money`/`purchase_cost` non-finite values.

- [ ] **Step 6: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py -q`

Expected: all classifier and ledger tests pass.

```bash
git add src/kaggriculture_lib/adaptive_strategy.py tests/test_adaptive_strategy.py
git commit -m "feat: add expansion cash ledger"
```

---

### Task 3: Productive Utilization and Workload-Gated Labor

**Files:**
- Modify: `src/kaggriculture_lib/adaptive_strategy.py`
- Modify: `tests/test_adaptive_strategy.py`

**Interfaces:**
- Produces: `productive_utilization(tiles, quadrants, board_size) -> float`, `count_executable_backlog(tasks, inventories, queued_items, positions, hour, last_hour) -> int`, and `attack_hand_target(executable_backlog) -> int`.

- [ ] **Step 1: Write failing utilization tests**

Create a 10x10 board with `NW`, `NE`, and `SW` unlocked. Assert that growing/ready `PLANT` tiles and structures containing an animal count as productive, while `None`, empty `PASTURE`, and empty `COOP` do not. Assert the denominator is 75 tiles and the exact ratio equals `productive / 75`.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py -q`

Expected: missing utilization function.

- [ ] **Step 3: Implement utilization using board coordinates**

Use the same NW/NE/SW/SE split as `tasking._quadrant_of`, but implement a public `quadrant_of` helper in `adaptive_strategy.py`; do not import a private function. Treat `tile.get("kind") == "PLANT"` or a supported non-null `animal` as productive.

- [ ] **Step 4: Write failing executable-backlog tests**

Use real `tasking.Task`/`TaskId` objects. Cover:

- a plant task executable with held seed;
- a plant task executable with a queued seed purchase;
- a feed/place task rejected without its resource;
- a feed/place task accepted when a unit holds its resource;
- a task rejected when Manhattan route distance plus one action exceeds the remaining turn horizon;
- duplicate task IDs counted once.

- [ ] **Step 5: Implement executable backlog and hand target**

`count_executable_backlog` must inspect task resource needs and available/queued resources without mutating inventories. Implement the exact target mapping:

```python
def attack_hand_target(executable_backlog: int) -> int:
    if executable_backlog <= 9:
        return 8
    if executable_backlog == 10:
        return 9
    if executable_backlog == 11:
        return 10
    return 11
```

Raise `ValueError` for negative backlog.

- [ ] **Step 6: Add final-day filtering tests**

Add `terminal_only=True` to backlog counting. Assert only `HARVEST` and `PICKUP` tasks count; planting, watering, construction, feed, and care do not. Liquidation itself is a market action and is not represented as a task.

- [ ] **Step 7: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py tests/test_tasking.py -q`

Expected: all pass.

```bash
git add src/kaggriculture_lib/adaptive_strategy.py tests/test_adaptive_strategy.py
git commit -m "feat: add adaptive utilization and labor rules"
```

---

### Task 4: Create v18 and Prove Classifier-Only Identity

**Files:**
- Create: `agents/task_teacher_v18/main.py`
- Create: `tests/test_task_teacher_v18.py`

**Interfaces:**
- Consumes: all Task 1 interfaces from `kaggriculture_lib.adaptive_strategy`.
- Produces: `agent(obs, config=None)`, `get_last_diagnostics(player) -> dict`, and config key `enableThreatExpansion`.

- [ ] **Step 1: Create v18 as an exact copy-forward of v16**

Use `agents/task_teacher_v16/main.py` as the sole source. Change only the module docstring and import the Task 1 threat types. Preserve all v16 constants and action logic.

- [ ] **Step 2: Write failing threat-integration tests**

Reuse v16 test observation builders. Test that opponent public counts drive `COMPACT`, `BUILDING`, and `COMPOUNDING`; state does not de-escalate; player states are isolated; and step reset works.

Assert `set(action) == {"farmer", "hands", "market"}` after every call.

- [ ] **Step 3: Integrate memory and diagnostics without behavior changes**

Add module state:

```python
_threat_memory = ThreatMemory()
_last_diagnostics: dict[int, dict] = {}


def get_last_diagnostics(player: int) -> dict:
    return dict(_last_diagnostics.get(player, {}))
```

At the beginning of `agent`, derive the opponent index, call `parse_public_threat_snapshot`, update memory, and store only JSON-safe scalar diagnostics. Do not add diagnostics to the returned action.

- [ ] **Step 4: Write and run the classifier-only ablation test**

Load v16 and v18 fresh. For at least ten ladder-match seeds and both seats, call v18 with `enableThreatExpansion=False` and compare the complete action dictionaries at every step against v16. The test must fail before the flag is read.

- [ ] **Step 5: Implement the ablation switch**

Define:

```python
threat_expansion_enabled = True if config is None else bool(config.get("enableThreatExpansion", True))
```

At this task, both branches still execute the unchanged v16 action path, so identity must pass. Later tasks may change only the enabled branch.

- [ ] **Step 6: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/test_task_teacher_v16.py tests/test_task_teacher_v18.py -q`

Expected: all pass, including full action-stream identity with expansion disabled.

```bash
git add agents/task_teacher_v18/main.py tests/test_task_teacher_v18.py
git commit -m "feat: scaffold threat-aware task teacher v18"
```

---

### Task 5: Integrate Correct Ledger and Conditional Land

**Files:**
- Modify: `agents/task_teacher_v18/main.py`
- Modify: `tests/test_task_teacher_v18.py`

**Interfaces:**
- Consumes: `CashLedger`, `authorize_land_purchase`, `productive_utilization`, and `economy.land_cost`.
- Updates diagnostics: `threat_level`, `threat_reason`, threat deltas, `land_authorized`, `land_reason`, `land_cost`, `ledger_reserved`, `post_land_cash`, `money`, `feed_shortage`, and `productive_utilization`.

- [ ] **Step 1: Write failing third-land integration tests**

Construct a day-15/hour-23 observation with two unlocked quadrants, a compounding opponent, enough money, assigned seed needs, animals requiring feed, and queued hires. Assert exactly one `BUY_LAND` occurs and diagnostic `post_land_cash` equals money minus each reserve and land cost once.

Add one test per rejection: `BUILDING`, hour 22, 11 days remaining, and one-dollar reserve shortfall.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_task_teacher_v18.py -q`

Expected: no threat-conditioned land order.

- [ ] **Step 3: Build the ledger from real agent state**

- `queued_hires`: use the already-calculated `reserved_for_hire`.
- `assigned_seeds`: use `reserved_for_seeds`.
- `two_day_feed`: `2 * max(0, target_wheat - total_wheat) * wheat_price`.
- `animal_liquidity`: `1200.0`.
- `operating`: `500.0`.

Call `authorize_land_purchase` only in the enabled branch. In the disabled branch, preserve the v16 land code byte-for-byte.

- [ ] **Step 4: Remove double land deduction in the enabled branch**

After a land order, compute a single `cash_after_committed_orders` value and pass it through animal and seed purchasing. Do not subtract land again inside the later market-order loop. Add a regression assertion that the maximum affordable seed quantity uses `ledger.remaining(...)`, not `ledger.remaining(...) - land_cost`.

- [ ] **Step 5: Write and implement fourth-land attack tests**

Test both severe triggers, utilization and cash boundaries, horizon, and hour. Assert the third quadrant must already be unlocked (`n_extra == 2`) and no turn emits two land orders.

- [ ] **Step 6: Re-run ablation and integration suites**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py tests/test_task_teacher_v16.py tests/test_task_teacher_v18.py tests/test_tasking.py -q`

Expected: enabled v18 tests pass; disabled v18 remains action-identical to v16.

- [ ] **Step 7: Commit**

```bash
git add agents/task_teacher_v18/main.py tests/test_task_teacher_v18.py
git commit -m "feat: add threat-conditioned land expansion"
```

---

### Task 6: Integrate Workload-Gated Attack Labor

**Files:**
- Modify: `agents/task_teacher_v18/main.py`
- Modify: `tests/test_task_teacher_v18.py`

**Interfaces:**
- Consumes: `count_executable_backlog` and `attack_hand_target`.
- Updates diagnostics: `executable_backlog`, `hands_floor`, `hire_cost_reserved`, and `terminal_labor_only`.

- [ ] **Step 1: Write failing hand-target integration tests**

For four unlocked quadrants and sufficient money, construct task sets producing 9, 10, 11, and 12 executable tasks. Assert hand floors 8, 9, 10, and 11. Assert missing workload evidence does not increase the current target.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_task_teacher_v18.py -q`

Expected: current v16 logic always chooses 11 at four quadrants and sufficient cash.

- [ ] **Step 3: Replace only the enabled four-quadrant labor branch**

Compute executable backlog after task generation. Use normal task types on days 10-28 and `terminal_only=True` on day 29. Clamp the target downward if available money cannot fund the exact daily Fibonacci hire sequence.

- [ ] **Step 4: Add final-day and expensive-hiring tests**

Assert non-terminal tasks cannot trigger added day-29 labor. Assert `farmHandCostMult >= 5` preserves the existing maximum-three-hands cap, even in attack mode.

- [ ] **Step 5: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/test_adaptive_strategy.py tests/test_task_teacher_v16.py tests/test_task_teacher_v18.py -q`

Expected: all pass and ablation identity remains intact.

```bash
git add agents/task_teacher_v18/main.py tests/test_task_teacher_v18.py
git commit -m "feat: gate v18 labor by executable workload"
```

---

### Task 7: Diagnostic Evaluation Harness

**Files:**
- Create: `scripts/evaluate_task_teacher_v18.py`
- Create: `tests/test_evaluate_task_teacher_v18.py`

**Interfaces:**
- CLI inputs: candidate, opponent, episode count, steps, seed, optional `--disable-threat-expansion`, and `--output-json`.
- JSON output: per-game rewards plus per-turn v18 diagnostics and aggregate transition/land/cash/labor metrics.

- [ ] **Step 1: Write failing wrapper and aggregation tests**

Use a fake agent module with `agent` and `get_last_diagnostics`. Assert the wrapper returns the original action unchanged and appends a copied diagnostic record containing step, player, and seat. Assert aggregation counts threat transitions, land reasons, minimum cash, maximum hands, mean productive utilization, pass-action rate, feed-shortage turns, hire spend, crop sale value by type, and animal-product sale value by type.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_evaluate_task_teacher_v18.py -q`

Expected: script module does not exist.

- [ ] **Step 3: Implement fresh module loading and callable wrappers**

Load each file-path agent with a unique module name per seat/game so globals never leak. Wrap v18 calls as:

```python
def wrapped(obs, config):
    action = module.agent(obs, config)
    diagnostics.append({
        "step": obs["step"],
        "player": obs["player"],
        **module.get_last_diagnostics(obs["player"]),
    })
    return action
```

For ablation, merge `{"enableThreatExpansion": False}` into the config passed to v18 without changing the environment configuration. Derive pass rate from returned farmer/hand actions and sale value from `SELL` orders multiplied by the current public market price; diagnostics must never alter those actions.

- [ ] **Step 4: Implement paired ladder-match execution and JSON schema**

Reuse `tournament_configuration`, `final_rewards`, `pairwise_score`, and `hoeffding_ci` from `scripts/run_tournament.py`. Emit deterministic JSON with sorted keys and include `win_rate`, `mean_money_margin`, CI, transition counts, land authorization counts/reasons, cash minima, hand maxima, utilization, config, and seeds.

- [ ] **Step 5: Add a two-pair real smoke test**

Run v18 versus v16 for two 96-step pairs and assert all games finish, JSON parses, actions contain only schema keys, and both seat diagnostics are present.

- [ ] **Step 6: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/test_evaluate_task_teacher_v18.py tests/test_run_tournament.py -q`

Expected: all pass.

```bash
git add scripts/evaluate_task_teacher_v18.py tests/test_evaluate_task_teacher_v18.py
git commit -m "feat: add v18 diagnostic evaluation harness"
```

---

### Task 8: Packaging and Full Verification

**Files:**
- Modify: `tests/test_package_agent.py`
- Generated, not committed unless repository convention says otherwise: `build/task_teacher_v18/main.py`

**Interfaces:**
- Verifies `adaptive_strategy` is bundled transitively before v18 imports execute.

- [ ] **Step 1: Write failing packaging test**

Add `test_packaged_task_teacher_v18_runs_standalone_without_pythonpath`. Package v18, assert generated source registers `kaggriculture_lib.adaptive_strategy`, then call the existing standalone helper for 96 steps.

- [ ] **Step 2: Run focused packaging test**

Run: `.venv/bin/python -m pytest tests/test_package_agent.py -k task_teacher_v18 -q`

Expected after Tasks 1-7: PASS without changing `package_agent.py`, because discovery is transitive. This is a packaging characterization gate rather than a new production behavior.

- [ ] **Step 3: Run the explicit package command**

Run: `.venv/bin/python scripts/package_agent.py agents/task_teacher_v18 --verify-against starter --verify-steps 96`

Expected: standalone verification reports both terminal statuses `DONE`.

- [ ] **Step 4: Run the complete suite**

Run: `.venv/bin/python -m pytest tests/ -q`

Expected: zero failures. Third-party deprecation warnings are allowed but must be recorded.

- [ ] **Step 5: Commit**

```bash
git add tests/test_package_agent.py
git commit -m "test: verify task teacher v18 packaging"
```

---

### Task 9: Acceptance, Ablation, Promotion, and Documentation

**Files:**
- Create after runs: `replays/analysis/task_teacher_v18_acceptance.json`
- Create after runs: `replays/analysis/task_teacher_v18_ablation.json`
- Create after runs: `replays/analysis/task_teacher_v18_vs_v16_screen.json`
- Create after runs: `replays/analysis/task_teacher_v18_vs_v16_promotion.json`
- Create after runs: comparator JSON files using the same naming pattern.
- Modify after evidence: `docs/3_agent_strategy.md`
- Modify after evidence: `docs/4_agent_version_log.md`
- Modify after evidence: `docs/6_next_steps.md`

**Interfaces:**
- Consumes: verified v18 agent and Task 7 evaluator.
- Produces: evidence and a decision of `reject`, `experimental_submission`, or `local_champion`.

- [ ] **Step 1: Run 100-game acceptance**

Run 50 paired seeds, which produces 100 games:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_task_teacher_v18.py \
  agents/task_teacher_v18/main.py starter \
  --episodes 50 --episode-steps 720 --seed 110000 \
  --output-json replays/analysis/task_teacher_v18_acceptance.json
```

Require every game `DONE`/finite, deterministic replay on a repeated seed subset, no invalid land order, and no repeated-bankruptcy/feed-starvation signature.

- [ ] **Step 2: Run classifier-only ablation**

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_task_teacher_v18.py \
  agents/task_teacher_v18/main.py agents/task_teacher_v16/main.py \
  --disable-threat-expansion --episodes 20 --episode-steps 720 --seed 110100 \
  --output-json replays/analysis/task_teacher_v18_ablation.json
```

Require exact paired reward and action-stream identity. Any difference stops evaluation and returns to Task 4/5.

- [ ] **Step 3: Run 20-pair screen**

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_task_teacher_v18.py \
  agents/task_teacher_v18/main.py agents/task_teacher_v16/main.py \
  --episodes 20 --episode-steps 720 --seed 111000 \
  --output-json replays/analysis/task_teacher_v18_vs_v16_screen.json
```

If the interval is wholly below 0.50 or mean margin is non-positive, stop and classify `reject`. Otherwise continue.

- [ ] **Step 4: Run 50-pair promotion evaluation**

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_task_teacher_v18.py \
  agents/task_teacher_v18/main.py agents/task_teacher_v16/main.py \
  --episodes 50 --episode-steps 720 --seed 112000 \
  --output-json replays/analysis/task_teacher_v18_vs_v16_promotion.json
```

- [ ] **Step 5: Run comparator screens**

Run 20 fresh pairs each against:

- `agents/task_teacher_v17/main.py` (static third quadrant), seed 113000;
- `agents/task_teacher_v10/main.py` (strongest visible v10 submission line), seed 113100;
- `agents/task_teacher_v2/main.py` (compact crop comparator), seed 113200; and
- `agents/task_teacher_v12/main.py` (high-animal land comparator), seed 113300.

Record each exact path and current commit hash in its JSON output.

- [ ] **Step 6: Apply the decision rules**

- `reject`: 50-pair win rate below 0.55, non-positive margin, failed acceptance, or catastrophic compact regression.
- `experimental_submission`: win rate at least 0.55, positive margin, clean acceptance, no catastrophic compact regression, but CI crosses 0.50.
- `local_champion`: CI lower bound is above 0.50 and all regression gates pass.

Do not submit within this task. Kaggle submission is a separately authorized external action after the evidence is reviewed.

- [ ] **Step 7: Update documentation with measured facts only**

Record thresholds, seeds, games, win rate, margin, CI, threat-state frequencies, land activation, cash minima, labor/utilization, comparator results, and decision. Remove all future-tense champion claims.

- [ ] **Step 8: Run documentation and suite checks**

Run:

```bash
git diff --check
.venv/bin/python -m pytest tests/ -q
```

Expected: no whitespace errors and zero test failures.

- [ ] **Step 9: Commit evidence and documentation**

```bash
git add replays/analysis/task_teacher_v18_*.json docs/3_agent_strategy.md docs/4_agent_version_log.md docs/6_next_steps.md
git commit -m "docs: record task teacher v18 evaluation"
```
