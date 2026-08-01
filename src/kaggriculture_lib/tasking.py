"""Multi-tile task scheduling for task_teacher_v* agents.

Data model and scheduling logic per the approved design in
docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md
("task_teacher_v1: final design"). Shared across every task_teacher_v*
version the way economy.py is shared across ROI decisions — stable
interfaces, additive evolution as new task/resource types arrive (not
promised to stay unchanged through v2-v6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum

from kaggriculture_lib import economy


class TaskKind(str, Enum):
    PLANT = "PLANT"
    WATER = "WATER"
    HARVEST = "HARVEST"
    DIG = "DIG"


class PriorityTier(IntEnum):
    """Lexicographic safety-first ordering. Lower sorts first (higher priority)."""

    EMERGENCY = 0
    DECAYING_YIELD = 1
    DAILY_CARE = 2
    ECONOMIC = 3
    OPTIONAL = 4


@dataclass(frozen=True, order=True)
class TaskId:
    """Canonical, stable identity for a task instance."""

    kind: TaskKind
    x: int
    y: int
    item: str | None = None


@dataclass(frozen=True)
class ResourceNeed:
    item: str
    quantity: int
    source: str  # "SEED" | "SHED" | "INVENTORY"


@dataclass(frozen=True)
class Task:
    """One candidate action, generated fresh from farm state every turn."""

    task_id: TaskId
    target: tuple[int, int]
    priority_tier: PriorityTier
    deadline_step: int | None
    expected_value: float
    action_cost: int
    resource_needs: tuple[ResourceNeed, ...] = ()


@dataclass
class ReservationLedger:
    """Per-turn reservations so multiple units can't select conflicting tasks.

    Movement cells are never reserved (this game has no movement collision —
    see docs/2_environment_notes.md).
    """

    task_by_tile: dict[tuple[int, int], TaskId]
    resources: dict[tuple[str, str], int]
    budget: float


def _quadrant_of(x: int, y: int, board_size: int) -> str:
    """Mirrors kaggle-environments==1.29.3's kaggriculture.py:110-112 (`_quadrant_of`)."""
    half = board_size // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def _expected_total_units(crop: str) -> int:
    """Total harvestable units assuming watering every day in the bonus window."""
    cd = economy.CROPS[crop]
    start, end = economy.one_time_crop_watering_bonus_window(crop)
    bonus_days = end - start + 1
    return min(cd["max_yield"], 1 + bonus_days)


def _score_crop(crop: str, price: float) -> float:
    """Static $/day ROI estimate, same formula as roi_teacher_v1-v3."""
    cd = economy.CROPS[crop]
    lifespan_days = cd["max_yield_day"] + 1
    revenue = _expected_total_units(crop) * price
    return (revenue - cd["seed"]) / lifespan_days


def _best_feasible_crop(
    day: int, last_day: int, market_prices: dict[str, float], candidate_crops: tuple[str, ...]
) -> str | None:
    feasible = [c for c in candidate_crops if economy.can_mature_in_time(c, day, last_day)]
    if not feasible:
        return None
    return max(feasible, key=lambda c: _score_crop(c, market_prices.get(c, economy.CROPS[c]["seed"])))


def generate_tasks(
    tiles: list[list],
    unlocked_quadrants: list[str],
    day: int,
    last_day: int,
    market_prices: dict[str, float],
    candidate_crops: tuple[str, ...],
    board_size: int = 10,
) -> list[Task]:
    """Regenerate the full task list fresh from current farm state.

    Tasks are derived state, never persisted themselves (see `TeacherState`,
    which persists only the unit -> `TaskId` assignment). One-time crops
    only, per `task_teacher_v1`'s scope.
    """
    tasks: list[Task] = []
    unlocked = set(unlocked_quadrants)

    for y in range(board_size):
        for x in range(board_size):
            if _quadrant_of(x, y, board_size) not in unlocked:
                continue
            tile = tiles[y][x]

            if tile is None:
                crop = _best_feasible_crop(day, last_day, market_prices, candidate_crops)
                if crop is None:
                    continue
                price = market_prices.get(crop, economy.CROPS[crop]["seed"])
                tasks.append(
                    Task(
                        task_id=TaskId(kind=TaskKind.PLANT, x=x, y=y, item=crop),
                        target=(x, y),
                        priority_tier=PriorityTier.ECONOMIC,
                        deadline_step=None,
                        expected_value=_score_crop(crop, price),
                        action_cost=1,
                        resource_needs=(ResourceNeed(item=crop, quantity=1, source="SEED"),),
                    )
                )

            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                cd = economy.CROPS[tile["crop"]]
                if not tile["watered_today"]:
                    tier = PriorityTier.EMERGENCY if tile["consecutive_unwatered"] >= 1 else PriorityTier.DAILY_CARE
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.WATER, x=x, y=y),
                            target=(x, y),
                            priority_tier=tier,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                        )
                    )
                elif day - tile["planted_day"] >= cd["max_yield_day"]:
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.HARVEST, x=x, y=y),
                            target=(x, y),
                            priority_tier=PriorityTier.DECAYING_YIELD,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                        )
                    )

            elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                tasks.append(
                    Task(
                        task_id=TaskId(kind=TaskKind.DIG, x=x, y=y),
                        target=(x, y),
                        priority_tier=PriorityTier.DAILY_CARE,
                        deadline_step=None,
                        expected_value=0.0,
                        action_cost=1,
                    )
                )

    return tasks


HYSTERESIS_BONUS = 0.5  # switch-away penalty, in the same units as expected_value


def rank_tasks(
    tasks: list[Task],
    current_position: tuple[int, int],
    current_assignment: TaskId | None = None,
) -> list[Task]:
    """Deterministic full ordering: safety tier first, then nearest, then
    highest value, with hysteresis toward the current assignment on a near
    tie, with `task_id` as the final deterministic tiebreak.
    """

    def _key(task: Task):
        distance = abs(task.target[0] - current_position[0]) + abs(task.target[1] - current_position[1])
        switch_penalty = 0.0 if task.task_id == current_assignment else HYSTERESIS_BONUS
        return (
            task.priority_tier,
            distance,
            -task.expected_value + switch_penalty,
            task.task_id,
        )

    return sorted(tasks, key=_key)


@dataclass(frozen=True)
class MarketIntent:
    """A future-turn market order: buying this now doesn't make a task
    executable this same turn (unit actions execute before market actions,
    per the game's turn processing order)."""

    item: str
    quantity: int
    reason: str  # e.g. "PLANT" -- why this intent was created


# Calibrated constants for the service-capacity load check (§ below);
# revise from real task_teacher_v1 data once it exists, per the "measure
# before fixing the number" discipline used throughout this project.
TRAVEL_ALLOWANCE = 4  # turns/day reserved for moving between tiles
END_OF_DAY_RESERVE = 2  # turns/day reserved for selling/end-of-day cleanup


def project_daily_load(
    pending_water_tiles: int, scheduled_plant_actions: int, scheduled_harvest_actions: int
) -> int:
    """O(1) service-capacity estimate — a load-accounting check, not a
    lookahead planner. Sums known daily obligations (watering every owned
    tile) plus this turn's proposed new work (planting, harvesting) plus
    two calibrated constants for travel and end-of-day selling/cleanup.
    """
    return pending_water_tiles + scheduled_plant_actions + scheduled_harvest_actions + TRAVEL_ALLOWANCE + END_OF_DAY_RESERVE


def route_toward(
    current: tuple[int, int], target: tuple[int, int], tiles: list[list], board_size: int
) -> str:
    """Deterministic greedy Manhattan routing: horizontal first unless that
    move would enter a locked tile, then vertical. Confirmed no obstacles
    exist in this game besides board bounds and locked quadrants (plants,
    weeds, structures, and other units never block movement — see
    docs/2_environment_notes.md) — a BFS pathfinder is unnecessary.
    """
    cx, cy = current
    tx, ty = target
    if current == target:
        return "PASS"

    candidates: list[tuple[str, int, int]] = []
    if tx > cx:
        candidates.append(("EAST", cx + 1, cy))
    elif tx < cx:
        candidates.append(("WEST", cx - 1, cy))
    if ty > cy:
        candidates.append(("SOUTH", cx, cy + 1))
    elif ty < cy:
        candidates.append(("NORTH", cx, cy - 1))

    for op, nx, ny in candidates:
        if 0 <= nx < board_size and 0 <= ny < board_size and tiles[ny][nx] != "LOCKED":
            return op
    return "PASS"


@dataclass
class TeacherState:
    """Explicit, caller-owned state — never read/written via module globals.

    Reset on an observed game-state signal (`obs["step"] == 0` or
    `obs["step"] < previous_step`), not on module-load lifecycle: verified
    empirically that kaggle_environments' file-agent loader happens to give
    a fresh module exec per `env.run()`, but that's an implementation detail
    of one calling path, not a guarantee for direct unit-test calls, BC
    trajectory generation, or interleaved parallel rollout workers.
    """

    assignments: dict[int, TaskId] = field(default_factory=dict)
    previous_step: int = -1

    def reset(self) -> None:
        self.assignments.clear()
        self.previous_step = -1
