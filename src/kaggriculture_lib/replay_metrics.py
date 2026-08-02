"""Descriptive metrics for normalized Kaggriculture replay decisions.

The metrics in this module report observed state, actions, and next-state
changes.  They do not attribute simultaneous environment changes to a single
action and therefore must not be interpreted as causal estimates.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from statistics import mean
from typing import Any, Mapping, Sequence

from kaggriculture_lib.replay_schema import DecisionRecord


_TRAVEL_OPERATIONS = frozenset({"NORTH", "SOUTH", "EAST", "WEST"})
_PRODUCTIVE_OPERATIONS = frozenset(
    {
        "PLANT",
        "WATER",
        "HARVEST",
        "FERTILIZE",
        "DIG",
        "BUILD_COOP",
        "BUILD_PASTURE",
        "FEED",
        "COLLECT_FERTILIZER",
        "CARE",
    }
)
_LOGISTICS_OPERATIONS = frozenset({"PICKUP", "PLACE"})
_MARKET_OPERATIONS = frozenset(
    {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "HIRE", "BUY_LAND"}
)
_CAPITAL_PURCHASE_OPERATIONS = frozenset(
    {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"}
)
_FINAL_WINDOWS = (8, 22, 48)
_STORAGE_PRESSURE_FRACTION = 0.9


@dataclass(frozen=True)
class TurnMetrics:
    """Observed facts for one policy decision and its optional successor."""

    episode_id: str
    source_policy_id: str
    source_family: str
    step: int
    day: int
    hour: int
    seat: int
    opponent_family: str
    money: float | None
    unlocked_quadrants: tuple[str, ...]
    land_count: int
    active_hands: int
    crop_counts: Mapping[str, int]
    animal_counts: Mapping[str, int]
    shed_units: float
    carried_units: float
    storage_capacity: float
    storage_utilization: float
    storage_pressure: bool
    terminal_stranded_units: float | None
    productive_actions: int
    travel_actions: int
    logistics_actions: int
    idle_actions: int
    other_actions: int
    movement_steps: int
    market_order_count: int
    market_order_counts: Mapping[str, int]
    hire_orders: int
    land_purchase_orders: int
    capital_purchase_orders: int
    sell_quantity: float
    sell_quantity_by_product: Mapping[str, float]
    current_prices: Mapping[str, float]
    current_market_inventory: Mapping[str, float]
    visible_opponent_money: float | None
    visible_opponent_land_count: int
    visible_opponent_active_hands: int
    visible_opponent_crop_counts: Mapping[str, int]
    visible_opponent_animal_counts: Mapping[str, int]
    observed_next_bank: float | None
    observed_bank_delta: float | None
    final_bank: float | None
    status: str
    terminal_result: str | None

    def __post_init__(self) -> None:
        for name in (
            "money",
            "observed_next_bank",
            "observed_bank_delta",
            "final_bank",
            "terminal_stranded_units",
        ):
            value = getattr(self, name)
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite")

    @property
    def realized_bank_delta(self) -> float | None:
        """Compatibility alias for the observed, non-causal bank delta."""
        return self.observed_bank_delta

    @property
    def worker_action_count(self) -> int:
        return (
            self.productive_actions
            + self.travel_actions
            + self.logistics_actions
            + self.idle_actions
            + self.other_actions
        )


@dataclass(frozen=True)
class EpisodeSummary:
    """Descriptive episode aggregates derived from contiguous turn metrics."""

    episode_id: str
    source_policy_id: str
    source_family: str
    seat: int
    opponent_family: str
    turn_count: int
    first_step: int
    last_step: int
    first_day: int
    last_day: int
    land_opening_day: int | None
    land_purchase_count: int
    hand_peak: int
    hand_range: tuple[int, int]
    hire_orders: int
    productive_actions: int
    travel_actions: int
    logistics_actions: int
    idle_actions: int
    other_actions: int
    productive_action_share: float
    travel_action_share: float
    logistics_action_share: float
    idle_action_share: float
    other_action_share: float
    crop_exposure_by_day: Mapping[int, Mapping[str, float]]
    animal_exposure_by_day: Mapping[int, Mapping[str, float]]
    sell_quantity: float
    sell_quantity_by_product: Mapping[str, float]
    sell_concentration_by_product: Mapping[str, float]
    sell_product_hhi: float | None
    sell_turn_count: int
    observed_sell_bank_delta_turn_count: int
    observed_bank_delta_on_sell_turns: float | None
    storage_pressure_turns: int
    terminal_stranded_units: float | None
    final_bank: float | None
    status: str
    result: str | None
    final_window_cash_changes: Mapping[int, float | None]
    bank_recovery_turns_after_purchase: tuple[int | None, ...]

    def __post_init__(self) -> None:
        for name in (
            "final_bank",
            "observed_bank_delta_on_sell_turns",
            "sell_product_hhi",
            "terminal_stranded_units",
        ):
            value = getattr(self, name)
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite")
        for value in self.final_window_cash_changes.values():
            if value is not None and not isfinite(value):
                raise ValueError("final window cash changes must be finite")

    @property
    def final_8_action_cash_change(self) -> float | None:
        return self.final_window_cash_changes.get(8)

    @property
    def final_22_action_cash_change(self) -> float | None:
        return self.final_window_cash_changes.get(22)

    @property
    def final_48_action_cash_change(self) -> float | None:
        return self.final_window_cash_changes.get(48)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _finite_number(value: Any, *, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _numeric_mapping(value: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, raw in _as_mapping(value).items():
        number = _finite_number(raw, name=f"{key} value")
        if isinstance(key, str) and number is not None:
            result[key] = number
    return dict(sorted(result.items()))


def _unit_total(value: Any) -> float:
    return sum(number for number in _numeric_mapping(value).values() if number > 0)


def _farm(observation: Mapping[str, Any], seat: int) -> Mapping[str, Any]:
    farms = _as_sequence(observation.get("farms"))
    if 0 <= seat < len(farms):
        return _as_mapping(farms[seat])
    return {}


def _bank(observation: Mapping[str, Any], seat: int) -> float | None:
    farm = _farm(observation, seat)
    for raw in (farm.get("money"), observation.get("bank"), observation.get("money")):
        if raw is not None:
            return _finite_number(raw, name="bank")
    return None


def _asset_counts(farm: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    crops: defaultdict[str, int] = defaultdict(int)
    animals: defaultdict[str, int] = defaultdict(int)
    for row in _as_sequence(farm.get("tiles")):
        for tile in _as_sequence(row):
            tile_data = _as_mapping(tile)
            crop = tile_data.get("crop")
            animal = tile_data.get("animal")
            if tile_data.get("kind") == "PLANT" and isinstance(crop, str):
                crops[crop] += 1
            if isinstance(animal, str):
                animals[animal] += 1
    return dict(sorted(crops.items())), dict(sorted(animals.items()))


def _action_family(operation: Any) -> str:
    if operation in _PRODUCTIVE_OPERATIONS:
        return "productive"
    if operation in _TRAVEL_OPERATIONS:
        return "travel"
    if operation in _LOGISTICS_OPERATIONS:
        return "logistics"
    if operation == "PASS":
        return "idle"
    return "other"


def _quantity(command: Sequence[Any]) -> float:
    if len(command) <= 2:
        return 0.0
    value = _finite_number(command[2], name="action quantity")
    return value if value is not None and value > 0 else 0.0


def extract_turn_metrics(
    record: DecisionRecord,
    next_observation: Mapping[str, Any] | None,
) -> TurnMetrics:
    """Extract observed facts without claiming that an action caused a delta."""
    observation = _as_mapping(record.observation)
    own_farm = _farm(observation, record.seat)
    opponent_seat = 1 - record.seat
    opponent_farm = _farm(observation, opponent_seat)
    money = _bank(observation, record.seat)
    observed_next_bank = (
        _bank(_as_mapping(next_observation), record.seat)
        if next_observation is not None
        else None
    )
    observed_bank_delta = (
        observed_next_bank - money
        if observed_next_bank is not None and money is not None
        else None
    )

    unlocked_quadrants = tuple(
        quadrant
        for quadrant in _as_sequence(own_farm.get("unlocked_quadrants"))
        if isinstance(quadrant, str)
    )
    crop_counts, animal_counts = _asset_counts(own_farm)
    opponent_crop_counts, opponent_animal_counts = _asset_counts(opponent_farm)

    private = _as_mapping(observation.get("private"))
    shed_units = _unit_total(private.get("shed"))
    carried_units = sum(
        _unit_total(inventory) for inventory in _as_sequence(private.get("inventories"))
    )
    configured_capacity = _finite_number(
        _as_mapping(record.configuration).get("shedCapacity", 100),
        name="shed capacity",
    )
    storage_capacity = configured_capacity if configured_capacity is not None and configured_capacity > 0 else 100.0
    storage_utilization = shed_units / storage_capacity
    storage_pressure = storage_utilization >= _STORAGE_PRESSURE_FRACTION

    family_counts: defaultdict[str, int] = defaultdict(int)
    unit_commands = (record.action.farmer, *record.action.hands)
    for command in unit_commands:
        operation = command[0] if command else None
        family_counts[_action_family(operation)] += 1

    market_order_counts: defaultdict[str, int] = defaultdict(int)
    sell_quantity_by_product: defaultdict[str, float] = defaultdict(float)
    hire_orders = 0
    land_purchase_orders = 0
    capital_purchase_orders = 0
    for command in record.action.market:
        operation = command[0] if command else None
        key = operation if isinstance(operation, str) and operation in _MARKET_OPERATIONS else "other"
        market_order_counts[key] += 1
        if operation == "HIRE":
            hire_orders += 1
        if operation == "BUY_LAND":
            land_purchase_orders += 1
        if operation in _CAPITAL_PURCHASE_OPERATIONS:
            capital_purchase_orders += 1
        if operation == "SELL" and len(command) > 1 and isinstance(command[1], str):
            sell_quantity_by_product[command[1]] += _quantity(command)

    market = _as_mapping(observation.get("market"))
    is_terminal = record.terminal_result is not None or record.final_banks is not None
    final_bank = (
        float(record.final_banks[record.seat])
        if record.final_banks is not None
        else None
    )

    return TurnMetrics(
        episode_id=record.episode_id,
        source_policy_id=record.source_policy_id,
        source_family=record.source_family,
        step=record.step,
        day=record.day,
        hour=record.hour,
        seat=record.seat,
        opponent_family=record.opponent_family,
        money=money,
        unlocked_quadrants=unlocked_quadrants,
        land_count=len(unlocked_quadrants),
        active_hands=len(_as_sequence(own_farm.get("hands"))),
        crop_counts=crop_counts,
        animal_counts=animal_counts,
        shed_units=shed_units,
        carried_units=carried_units,
        storage_capacity=storage_capacity,
        storage_utilization=storage_utilization,
        storage_pressure=storage_pressure,
        terminal_stranded_units=shed_units + carried_units if is_terminal else None,
        productive_actions=family_counts["productive"],
        travel_actions=family_counts["travel"],
        logistics_actions=family_counts["logistics"],
        idle_actions=family_counts["idle"],
        other_actions=family_counts["other"],
        movement_steps=family_counts["travel"],
        market_order_count=len(record.action.market),
        market_order_counts=dict(sorted(market_order_counts.items())),
        hire_orders=hire_orders,
        land_purchase_orders=land_purchase_orders,
        capital_purchase_orders=capital_purchase_orders,
        sell_quantity=sum(sell_quantity_by_product.values()),
        sell_quantity_by_product=dict(sorted(sell_quantity_by_product.items())),
        current_prices=_numeric_mapping(market.get("prices")),
        current_market_inventory=_numeric_mapping(market.get("inventory")),
        visible_opponent_money=_bank(observation, opponent_seat),
        visible_opponent_land_count=len(_as_sequence(opponent_farm.get("unlocked_quadrants"))),
        visible_opponent_active_hands=len(_as_sequence(opponent_farm.get("hands"))),
        visible_opponent_crop_counts=opponent_crop_counts,
        visible_opponent_animal_counts=opponent_animal_counts,
        observed_next_bank=observed_next_bank,
        observed_bank_delta=observed_bank_delta,
        final_bank=final_bank,
        status="complete" if is_terminal else "incomplete",
        terminal_result=record.terminal_result,
    )


def _exposure_by_day(
    rows: Sequence[TurnMetrics],
    attribute: str,
) -> dict[int, dict[str, float]]:
    day_turns: defaultdict[int, int] = defaultdict(int)
    totals: defaultdict[int, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        day_turns[row.day] += 1
        for asset, count in getattr(row, attribute).items():
            totals[row.day][asset] += count
    return {
        day: {
            asset: totals[day][asset] / day_turns[day]
            for asset in sorted(totals[day])
        }
        for day in sorted(day_turns)
    }


def _validate_episode_rows(rows: Sequence[TurnMetrics]) -> None:
    if not rows:
        raise ValueError("episode rows must not be empty")
    first = rows[0]
    identity = (
        first.episode_id,
        first.source_policy_id,
        first.source_family,
        first.seat,
        first.opponent_family,
    )
    for index, row in enumerate(rows):
        row_identity = (
            row.episode_id,
            row.source_policy_id,
            row.source_family,
            row.seat,
            row.opponent_family,
        )
        if row_identity != identity:
            raise ValueError("episode rows must share replay identity")
        if index and row.step != rows[index - 1].step + 1:
            raise ValueError("episode steps must be strictly ordered and contiguous")
        if row.step != row.day * 24 + row.hour:
            raise ValueError("turn chronology is inconsistent with day and hour")
        for name in ("money", "observed_next_bank", "observed_bank_delta", "final_bank"):
            value = getattr(row, name)
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite")


def _bank_recoveries(rows: Sequence[TurnMetrics]) -> tuple[int | None, ...]:
    recoveries: list[int | None] = []
    for index, purchase_row in enumerate(rows):
        if not purchase_row.capital_purchase_orders:
            continue
        recovery: int | None = None
        if purchase_row.money is not None:
            for later in rows[index + 1 :]:
                if later.money is not None and later.money >= purchase_row.money:
                    recovery = later.step - purchase_row.step
                    break
        recoveries.extend([recovery] * purchase_row.capital_purchase_orders)
    return tuple(recoveries)


def _final_window_cash_changes(
    rows: Sequence[TurnMetrics],
    final_bank: float | None,
) -> dict[int, float | None]:
    return {
        window: (
            final_bank - rows[-window].money
            if final_bank is not None and len(rows) >= window and rows[-window].money is not None
            else None
        )
        for window in _FINAL_WINDOWS
    }


def summarize_episode(rows: Sequence[TurnMetrics]) -> EpisodeSummary:
    """Aggregate one contiguous episode into descriptive strategy metrics."""
    rows = tuple(rows)
    _validate_episode_rows(rows)
    first, last = rows[0], rows[-1]

    action_totals = {
        name: sum(getattr(row, name) for row in rows)
        for name in (
            "productive_actions",
            "travel_actions",
            "logistics_actions",
            "idle_actions",
            "other_actions",
        )
    }
    worker_actions = sum(action_totals.values())
    shares = {
        name: (count / worker_actions if worker_actions else 0.0)
        for name, count in action_totals.items()
    }

    sell_quantity_by_product: defaultdict[str, float] = defaultdict(float)
    observed_sell_deltas: list[float] = []
    sell_turn_count = 0
    for row in rows:
        for product, quantity in row.sell_quantity_by_product.items():
            sell_quantity_by_product[product] += quantity
        if row.sell_quantity > 0:
            sell_turn_count += 1
            if row.observed_bank_delta is not None:
                observed_sell_deltas.append(row.observed_bank_delta)
    total_sell_quantity = sum(sell_quantity_by_product.values())
    concentration = {
        product: quantity / total_sell_quantity
        for product, quantity in sorted(sell_quantity_by_product.items())
    } if total_sell_quantity else {}

    hand_values = [row.active_hands for row in rows]
    land_opening_day = next((row.day for row in rows if row.land_count > 1), None)
    final_bank = last.final_bank if last.status == "complete" else None

    return EpisodeSummary(
        episode_id=first.episode_id,
        source_policy_id=first.source_policy_id,
        source_family=first.source_family,
        seat=first.seat,
        opponent_family=first.opponent_family,
        turn_count=len(rows),
        first_step=first.step,
        last_step=last.step,
        first_day=first.day,
        last_day=last.day,
        land_opening_day=land_opening_day,
        land_purchase_count=sum(row.land_purchase_orders for row in rows),
        hand_peak=max(hand_values),
        hand_range=(min(hand_values), max(hand_values)),
        hire_orders=sum(row.hire_orders for row in rows),
        productive_actions=action_totals["productive_actions"],
        travel_actions=action_totals["travel_actions"],
        logistics_actions=action_totals["logistics_actions"],
        idle_actions=action_totals["idle_actions"],
        other_actions=action_totals["other_actions"],
        productive_action_share=shares["productive_actions"],
        travel_action_share=shares["travel_actions"],
        logistics_action_share=shares["logistics_actions"],
        idle_action_share=shares["idle_actions"],
        other_action_share=shares["other_actions"],
        crop_exposure_by_day=_exposure_by_day(rows, "crop_counts"),
        animal_exposure_by_day=_exposure_by_day(rows, "animal_counts"),
        sell_quantity=total_sell_quantity,
        sell_quantity_by_product=dict(sorted(sell_quantity_by_product.items())),
        sell_concentration_by_product=concentration,
        sell_product_hhi=sum(share * share for share in concentration.values()) if concentration else None,
        sell_turn_count=sell_turn_count,
        observed_sell_bank_delta_turn_count=len(observed_sell_deltas),
        observed_bank_delta_on_sell_turns=(
            sum(observed_sell_deltas)
            if len(observed_sell_deltas) == sell_turn_count
            else None
        ),
        storage_pressure_turns=sum(row.storage_pressure for row in rows),
        terminal_stranded_units=last.terminal_stranded_units,
        final_bank=final_bank,
        status=last.status,
        result=last.terminal_result,
        final_window_cash_changes=_final_window_cash_changes(rows, final_bank),
        bank_recovery_turns_after_purchase=_bank_recoveries(rows),
    )


def _optional_mean(values: Sequence[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    result = mean(present)
    if not isfinite(result):
        raise ValueError("source aggregate must be finite")
    return result


def _optional_sum(values: Sequence[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    result = sum(present)
    if not isfinite(result):
        raise ValueError("source aggregate must be finite")
    return result


def compare_sources(summaries: Sequence[EpisodeSummary]) -> list[dict[str, Any]]:
    """Return deterministic, family-level descriptive comparison rows."""
    grouped: defaultdict[str, list[EpisodeSummary]] = defaultdict(list)
    for summary in summaries:
        grouped[summary.source_family].append(summary)

    comparison: list[dict[str, Any]] = []
    for source_family in sorted(grouped):
        group = grouped[source_family]
        sell_turn_count = sum(summary.sell_turn_count for summary in group)
        observed_sell_turn_count = sum(
            summary.observed_sell_bank_delta_turn_count for summary in group
        )
        missing_sell_delta = any(
            summary.observed_sell_bank_delta_turn_count < summary.sell_turn_count
            for summary in group
        )
        action_totals = {
            name: sum(getattr(summary, name) for summary in group)
            for name in (
                "productive_actions",
                "travel_actions",
                "logistics_actions",
                "idle_actions",
                "other_actions",
            )
        }
        action_count = sum(action_totals.values())
        result_counts: defaultdict[str, int] = defaultdict(int)
        for summary in group:
            if summary.result is not None:
                result_counts[summary.result.lower()] += 1
        comparison.append(
            {
                "source_family": source_family,
                "episode_count": len(group),
                "source_policy_count": len({summary.source_policy_id for summary in group}),
                "complete_episode_count": sum(summary.status == "complete" for summary in group),
                "seat_0_episodes": sum(summary.seat == 0 for summary in group),
                "seat_1_episodes": sum(summary.seat == 1 for summary in group),
                "opponent_families": tuple(sorted({summary.opponent_family for summary in group})),
                "mean_final_bank": _optional_mean([summary.final_bank for summary in group]),
                "win_count": result_counts["win"],
                "tie_count": result_counts["tie"] + result_counts["draw"],
                "loss_count": result_counts["loss"],
                "mean_land_opening_day": _optional_mean([summary.land_opening_day for summary in group]),
                "mean_land_purchase_count": mean(summary.land_purchase_count for summary in group),
                "mean_hand_peak": mean(summary.hand_peak for summary in group),
                "hire_orders": sum(summary.hire_orders for summary in group),
                "productive_action_share": action_totals["productive_actions"] / action_count if action_count else 0.0,
                "travel_action_share": action_totals["travel_actions"] / action_count if action_count else 0.0,
                "logistics_action_share": action_totals["logistics_actions"] / action_count if action_count else 0.0,
                "idle_action_share": action_totals["idle_actions"] / action_count if action_count else 0.0,
                "other_action_share": action_totals["other_actions"] / action_count if action_count else 0.0,
                "sell_quantity": sum(summary.sell_quantity for summary in group),
                "sell_episode_count": sum(summary.sell_turn_count > 0 for summary in group),
                "no_sale_episode_count": sum(summary.sell_turn_count == 0 for summary in group),
                "missing_sell_bank_delta_episode_count": sum(
                    summary.observed_sell_bank_delta_turn_count < summary.sell_turn_count
                    for summary in group
                ),
                "sell_turn_count": sell_turn_count,
                "observed_sell_bank_delta_turn_count": observed_sell_turn_count,
                "sell_bank_delta_coverage": (
                    observed_sell_turn_count / sell_turn_count if sell_turn_count else None
                ),
                "observed_bank_delta_on_sell_turns": (
                    None
                    if missing_sell_delta
                    else _optional_sum(
                        [summary.observed_bank_delta_on_sell_turns for summary in group]
                    )
                ),
                "mean_sell_product_hhi": _optional_mean([summary.sell_product_hhi for summary in group]),
                "storage_pressure_turns": sum(summary.storage_pressure_turns for summary in group),
                "mean_terminal_stranded_units": _optional_mean(
                    [summary.terminal_stranded_units for summary in group]
                ),
                "terminal_stranding_observed_episode_count": sum(
                    summary.terminal_stranded_units is not None for summary in group
                ),
                "terminal_stranding_coverage": sum(
                    summary.terminal_stranded_units is not None for summary in group
                ) / len(group),
                "mean_final_8_action_cash_change": _optional_mean(
                    [summary.final_8_action_cash_change for summary in group]
                ),
                "mean_final_22_action_cash_change": _optional_mean(
                    [summary.final_22_action_cash_change for summary in group]
                ),
                "mean_final_48_action_cash_change": _optional_mean(
                    [summary.final_48_action_cash_change for summary in group]
                ),
            }
        )
    return comparison
