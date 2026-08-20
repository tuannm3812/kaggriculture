"""Pure, public-state opponent threat classification utilities."""

from dataclasses import dataclass, field
from enum import IntEnum
from math import isfinite

from kaggriculture_lib.tasking import Task, TaskKind


_SUPPORTED_ANIMALS = frozenset({"COW", "SHEEP", "GOOSE"})


class ThreatLevel(IntEnum):
    """Monotonic opponent expansion-risk levels."""

    COMPACT = 0
    BUILDING = 1
    COMPOUNDING = 2


def quadrant_of(x: int, y: int, board_size: int) -> str:
    """Return the board quadrant containing the given tile coordinate."""
    half = board_size // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def productive_utilization(tiles: list[list], quadrants: list[str], board_size: int) -> float:
    """Return the productive share of tiles in the supplied quadrants."""
    unlocked = set(quadrants)
    total = productive = 0
    for y in range(board_size):
        for x in range(board_size):
            if quadrant_of(x, y, board_size) not in unlocked:
                continue
            total += 1
            tile = tiles[y][x]
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "PLANT" or (
                tile.get("kind") in {"COOP", "PASTURE"}
                and tile.get("animal") in _SUPPORTED_ANIMALS
            ):
                productive += 1
    return productive / total if total else 0.0


def count_executable_backlog(
    tasks: list[Task],
    inventories: list[dict[str, int]] | dict[str, int],
    queued_items: list[object] | dict[str, int],
    positions: list[tuple[int, int]],
    hour: int,
    last_hour: int,
    *,
    terminal_only: bool = False,
) -> int:
    """Count unique tasks with resources and time to be completed this turn.

    Queued market items cover a resource prerequisite for planning purposes;
    held items must be carried by the unit that travels to the task.
    """
    remaining_actions = last_hour - hour + 1
    if remaining_actions <= 0:
        return 0

    unit_inventories = [inventories] if isinstance(inventories, dict) else inventories
    queued_by_item = _queued_quantities(queued_items)
    seen = set()
    count = 0
    terminal_kinds = {TaskKind.HARVEST, TaskKind.PICKUP}

    for task in tasks:
        if task.task_id in seen:
            continue
        seen.add(task.task_id)
        if terminal_only and task.task_id.kind not in terminal_kinds:
            continue
        if _task_is_executable(task, unit_inventories, queued_by_item, positions, remaining_actions):
            count += 1
    return count


def attack_hand_target(executable_backlog: int) -> int:
    """Return the attack-mode hand target justified by useful workload."""
    if executable_backlog < 0:
        raise ValueError("executable backlog must be nonnegative")
    if executable_backlog <= 9:
        return 8
    if executable_backlog == 10:
        return 9
    if executable_backlog == 11:
        return 10
    return 11


def _queued_quantities(queued_items: list[object] | dict[str, int]) -> dict[str, int]:
    """Aggregate queued order quantities without changing caller-owned data."""
    if isinstance(queued_items, dict):
        return {item: quantity for item, quantity in queued_items.items() if quantity > 0}

    quantities: dict[str, int] = {}
    for queued in queued_items:
        if isinstance(queued, dict):
            item, quantity = queued.get("item"), queued.get("quantity", 0)
        else:
            item, quantity = getattr(queued, "item", None), getattr(queued, "quantity", 0)
        if isinstance(item, str) and isinstance(quantity, (int, float)) and quantity > 0:
            quantities[item] = quantities.get(item, 0) + quantity
    return quantities


def _task_is_executable(
    task: Task,
    inventories: list[dict[str, int]],
    queued_by_item: dict[str, int],
    positions: list[tuple[int, int]],
    remaining_actions: int,
) -> bool:
    """Whether one unit can reach a task and satisfy each resource need."""
    for index, position in enumerate(positions):
        distance = abs(task.target[0] - position[0]) + abs(task.target[1] - position[1])
        if distance + 1 > remaining_actions:
            continue
        inventory = inventories[index] if index < len(inventories) else {}
        if all(
            inventory.get(need.item, 0) >= need.quantity
            or queued_by_item.get(need.item, 0) >= need.quantity
            for need in task.resource_needs
        ):
            return True
    return False


@dataclass(frozen=True)
class CashLedger:
    """Planned cash commitments that must be reserved before expansion."""

    queued_hires: float
    assigned_seeds: float
    two_day_feed: float
    animal_liquidity: float = 1200.0
    operating: float = 500.0

    def __post_init__(self) -> None:
        for value in (
            self.queued_hires,
            self.assigned_seeds,
            self.two_day_feed,
            self.animal_liquidity,
            self.operating,
        ):
            _require_nonnegative_finite(value)

    @property
    def total_reserved(self) -> float:
        """Return the total of each reserve, counted exactly once."""
        return sum((
            self.queued_hires,
            self.assigned_seeds,
            self.two_day_feed,
            self.animal_liquidity,
            self.operating,
        ))

    def remaining(self, money: float, purchase_cost: float = 0.0) -> float:
        """Return money after all reserves and one prospective purchase."""
        _require_finite(money)
        _require_finite(purchase_cost)
        return money - self.total_reserved - purchase_cost


@dataclass(frozen=True)
class LandDecision:
    """An expansion authorization and its telemetry-friendly explanation."""

    authorized: bool
    reason: str
    remaining_cash: float


@dataclass(frozen=True)
class ThreatSnapshot:
    """The public opponent counts used to determine threat level."""

    quadrants: int
    hands: int
    placed_animals: int


@dataclass(frozen=True)
class ThreatTransition:
    """A classified snapshot together with episode-local changes."""

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
    """Per-player, episode-local monotonic classifier state."""

    level_by_player: dict[int, ThreatLevel] = field(default_factory=dict)
    reason_by_player: dict[int, str] = field(default_factory=dict)
    previous_step_by_player: dict[int, int] = field(default_factory=dict)
    previous_snapshot_by_player: dict[int, ThreatSnapshot] = field(default_factory=dict)

    def update(
        self,
        player: int,
        step: int,
        day: int,
        hour: int,
        snapshot: ThreatSnapshot,
    ) -> ThreatTransition:
        """Classify a public snapshot without allowing in-episode de-escalation."""
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

        observed, reason = _classify(snapshot)
        previous = self.level_by_player.get(player, ThreatLevel.COMPACT)
        current = max(previous, observed)
        changed = current > previous
        stable_reason = reason if changed or player not in self.reason_by_player else self.reason_by_player[player]
        self.level_by_player[player] = current
        self.reason_by_player[player] = stable_reason
        return ThreatTransition(
            current,
            changed,
            stable_reason,
            day,
            hour,
            delta_quadrants,
            delta_hands,
            delta_animals,
        )


def parse_public_threat_snapshot(farm: dict) -> tuple[ThreatSnapshot, str | None]:
    """Return public counts, or a safe snapshot for malformed public state."""
    try:
        tiles = farm["tiles"]
        hands = farm["hands"]
        quadrants = farm["unlocked_quadrants"]
        if not all(isinstance(value, list) for value in (tiles, hands, quadrants)):
            raise TypeError("public state collections must be lists")

        placed_animals = 0
        for row in tiles:
            if not isinstance(row, list):
                raise TypeError("tile rows must be lists")
            for tile in row:
                if tile is not None and not isinstance(tile, dict):
                    raise TypeError("tiles must be mappings")
                if isinstance(tile, dict) and tile.get("animal") in {"COW", "SHEEP", "GOOSE"}:
                    placed_animals += 1
        return ThreatSnapshot(len(quadrants), len(hands), placed_animals), None
    except (KeyError, TypeError):
        return ThreatSnapshot(0, 0, 0), "malformed_public_state"


def _classify(snapshot: ThreatSnapshot) -> tuple[ThreatLevel, str]:
    """Apply the fixed public-count threshold priority order."""
    if snapshot.quadrants >= 3:
        return ThreatLevel.COMPOUNDING, "three_quadrants"
    if snapshot.quadrants >= 2 and snapshot.placed_animals >= 4:
        return ThreatLevel.COMPOUNDING, "two_quadrants_four_animals"
    if snapshot.quadrants >= 2 and snapshot.hands >= 8:
        return ThreatLevel.COMPOUNDING, "two_quadrants_eight_hands"
    if snapshot.placed_animals >= 6:
        return ThreatLevel.COMPOUNDING, "six_animals"
    if snapshot.quadrants >= 2:
        return ThreatLevel.BUILDING, "extra_quadrant"
    if snapshot.hands >= 6:
        return ThreatLevel.BUILDING, "six_hands"
    if snapshot.placed_animals >= 3:
        return ThreatLevel.BUILDING, "three_animals"
    return ThreatLevel.COMPACT, "compact"


def authorize_land_purchase(
    threat: ThreatLevel,
    n_extra: int,
    day: int,
    hour: int,
    last_day: int,
    money: float,
    land_cost: float,
    ledger: CashLedger,
    productive_utilization: float,
    opponent_quadrants: int,
    opponent_animals: int,
) -> LandDecision:
    """Authorize the third or fourth quadrant without spending reserves twice."""
    _require_finite(money)
    _require_finite(land_cost)
    if land_cost <= 0:
        return LandDecision(False, "invalid_land_cost", ledger.remaining(money))

    remaining_cash = ledger.remaining(money, land_cost)
    if n_extra >= 3:
        return LandDecision(False, "maximum_extra_quadrants_reached", remaining_cash)
    if n_extra < 1:
        return LandDecision(False, "unsupported_land_stage", remaining_cash)
    if remaining_cash < 0:
        return LandDecision(False, "insufficient_cash", remaining_cash)

    if n_extra == 1:
        if threat < ThreatLevel.COMPOUNDING:
            return LandDecision(False, "third_land_threat_not_compounding", remaining_cash)
        if hour != 23:
            return LandDecision(False, "third_land_not_end_of_day", remaining_cash)
        if last_day - day < 12:
            return LandDecision(False, "third_land_horizon_too_short", remaining_cash)
        return LandDecision(True, "third_land_compounding", remaining_cash)

    if n_extra != 2:
        return LandDecision(False, "unsupported_land_stage", remaining_cash)

    if hour != 23:
        return LandDecision(False, "fourth_land_not_end_of_day", remaining_cash)
    if last_day - day < 14:
        return LandDecision(False, "fourth_land_horizon_too_short", remaining_cash)
    if productive_utilization < 0.70:
        return LandDecision(False, "fourth_land_utilization_too_low", remaining_cash)
    if opponent_quadrants < 4 and opponent_animals < 10:
        return LandDecision(False, "fourth_land_threat_not_severe", remaining_cash)
    if land_cost != 4_000:
        return LandDecision(False, "fourth_land_cost_must_be_4000", remaining_cash)
    if remaining_cash < 8_000:
        return LandDecision(False, "fourth_land_cash_below_reserve", remaining_cash)
    return LandDecision(True, "fourth_land_severe_threat", remaining_cash)


def _require_nonnegative_finite(value: float) -> None:
    """Reject amounts that cannot represent a real cash commitment."""
    _require_finite(value)
    if value < 0:
        raise ValueError("cash amounts must be nonnegative")


def _require_finite(value: float) -> None:
    """Reject NaN and infinities before they can bypass affordability checks."""
    try:
        valid = isfinite(value)
    except TypeError as error:
        raise ValueError("cash amounts must be finite") from error
    if not valid:
        raise ValueError("cash amounts must be finite")
