"""Multi-tile task scheduling for task_teacher_v* agents.

Data model and scheduling logic per the approved design in
docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md
("task_teacher_v1: final design"). Shared across every task_teacher_v*
version the way economy.py is shared across ROI decisions — stable
interfaces, additive evolution as new task/resource types arrive (not
promised to stay unchanged through v2-v6).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum, IntEnum

from kaggriculture_lib import economy


class TaskKind(str, Enum):
    PLANT = "PLANT"
    WATER = "WATER"
    HARVEST = "HARVEST"
    DIG = "DIG"
    BUILD_COOP = "BUILD_COOP"
    PLACE = "PLACE"
    FEED = "FEED"
    CARE = "CARE"
    PICKUP = "PICKUP"


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


def _score_ongoing_crop(crop: str, price: float, current_day: int, last_day: int) -> float:
    """Day-aware $/day ROI estimate for an ongoing crop planted *today*.

    Generalizes `_score_crop` to a multi-tick lifecycle: only ticks that
    actually land on or before `last_day` count toward revenue, and the
    lifespan denominator is days from planting through the last reachable
    tick (`reachable[-1] + 1`), mirroring one-time crops' `max_yield_day + 1`.
    Only meaningful once `economy.can_ongoing_crop_reach_any_tick` has
    already confirmed at least one tick is reachable.
    """
    offsets = economy.ongoing_crop_production_days(crop)
    reachable = [o for o in offsets if current_day + o <= last_day]
    revenue = len(reachable) * price
    cost = economy.CROPS[crop]["seed"]
    lifespan_days = reachable[-1] + 1
    return (revenue - cost) / lifespan_days


def _best_feasible_crop(
    day: int, last_day: int, market_prices: dict[str, float], candidate_crops: tuple[str, ...]
) -> str | None:
    scored: list[tuple[float, str]] = []
    for crop in candidate_crops:
        cd = economy.CROPS[crop]
        price = market_prices.get(crop, cd["seed"])
        if cd["ongoing"]:
            if not economy.can_ongoing_crop_reach_any_tick(crop, day, last_day):
                continue
            score = _score_ongoing_crop(crop, price, day, last_day)
        else:
            if not economy.can_mature_in_time(crop, day, last_day):
                continue
            score = _score_crop(crop, price)
        scored.append((score, crop))
    if not scored:
        return None
    return max(scored, key=lambda pair: pair[0])[1]


def _board_has_coop(tiles: list[list], unlocked: set[str], board_size: int) -> bool:
    """Whether any COOP structure (empty or occupied) already exists on an
    unlocked tile, so `want_coop` never queues a redundant BUILD_COOP."""
    for y in range(board_size):
        for x in range(board_size):
            if _quadrant_of(x, y, board_size) not in unlocked:
                continue
            tile = tiles[y][x]
            if isinstance(tile, dict) and tile.get("kind") == "COOP":
                return True
    return False


def _first_empty_unlocked_build_target(
    tiles: list[list], unlocked: set[str], board_size: int
) -> tuple[int, int] | None:
    """Pick where a BUILD_COOP should land: prefer the first empty, unlocked
    shed-access tile (keeps the coop close to where PICKUP/PLACE happen),
    else fall back to the first empty unlocked tile in scan order."""
    access_tiles = [
        (ax, ay)
        for ax, ay in economy.shed_access_tiles(board_size)
        if _quadrant_of(ax, ay, board_size) in unlocked and tiles[ay][ax] is None
    ]
    if access_tiles:
        return access_tiles[0]

    for y in range(board_size):
        for x in range(board_size):
            if _quadrant_of(x, y, board_size) in unlocked and tiles[y][x] is None:
                return (x, y)
    return None


def generate_tasks(
    tiles: list[list],
    unlocked_quadrants: list[str],
    day: int,
    last_day: int,
    market_prices: dict[str, float],
    candidate_crops: tuple[str, ...],
    board_size: int = 10,
    shed: dict | None = None,
    want_coop: bool = False,
    goose_in_any_inventory: bool = False,
    wheat_needed_for_feed: bool = False,
) -> list[Task]:
    """Regenerate the full task list fresh from current farm state.

    Tasks are derived state, never persisted themselves (see `TeacherState`,
    which persists only the unit -> `TaskId` assignment). One-time crops
    only, per `task_teacher_v1`'s scope.
    """
    tasks: list[Task] = []
    unlocked = set(unlocked_quadrants)

    has_empty_coop = False
    coop_planned = False
    build_target = (
        None
        if not want_coop or _board_has_coop(tiles, unlocked, board_size)
        else _first_empty_unlocked_build_target(tiles, unlocked, board_size)
    )

    for y in range(board_size):
        for x in range(board_size):
            if _quadrant_of(x, y, board_size) not in unlocked:
                continue
            tile = tiles[y][x]

            if tile is None:
                if want_coop and not coop_planned and (x, y) == build_target:
                    coop_planned = True
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.BUILD_COOP, x=x, y=y),
                            target=(x, y),
                            priority_tier=PriorityTier.ECONOMIC,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                        )
                    )
                    continue
                crop = _best_feasible_crop(day, last_day, market_prices, candidate_crops)
                if crop is None:
                    continue
                cd = economy.CROPS[crop]
                price = market_prices.get(crop, cd["seed"])
                value = (
                    _score_ongoing_crop(crop, price, day, last_day)
                    if cd["ongoing"]
                    else _score_crop(crop, price)
                )
                tasks.append(
                    Task(
                        task_id=TaskId(kind=TaskKind.PLANT, x=x, y=y, item=crop),
                        target=(x, y),
                        priority_tier=PriorityTier.ECONOMIC,
                        deadline_step=None,
                        expected_value=value,
                        action_cost=1,
                        resource_needs=(ResourceNeed(item=crop, quantity=1, source="SEED"),),
                    )
                )

            elif isinstance(tile, dict) and tile.get("kind") == "COOP" and "animal" not in tile:
                has_empty_coop = True
                if goose_in_any_inventory:
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.PLACE, x=x, y=y, item="GOOSE"),
                            target=(x, y),
                            priority_tier=PriorityTier.ECONOMIC,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                            resource_needs=(ResourceNeed(item="GOOSE", quantity=1, source="INVENTORY"),),
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
                elif cd["ongoing"]:
                    if tile["yield_units"] > 0:
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

            elif isinstance(tile, dict) and "animal" in tile:
                if not tile["fed_today"]:
                    tier = (
                        PriorityTier.EMERGENCY
                        if tile.get("consecutive_unfed", 0) >= 1
                        else PriorityTier.DAILY_CARE
                    )
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.FEED, x=x, y=y),
                            target=(x, y),
                            priority_tier=tier,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                            resource_needs=(ResourceNeed(item="WHEAT", quantity=1, source="INVENTORY"),),
                        )
                    )
                elif tile.get("yield_units", 0) > 0:
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
                elif not tile["cared_today"]:
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.CARE, x=x, y=y),
                            target=(x, y),
                            priority_tier=PriorityTier.DAILY_CARE,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                        )
                    )

    if shed:
        access_tiles = [
            (ax, ay) for ax, ay in economy.shed_access_tiles(board_size) if _quadrant_of(ax, ay, board_size) in unlocked
        ]
        if access_tiles:
            pickup_target = access_tiles[0]
            if shed.get("GOOSE", 0) > 0 and not goose_in_any_inventory and has_empty_coop:
                tasks.append(
                    Task(
                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="GOOSE"),
                        target=pickup_target,
                        priority_tier=PriorityTier.ECONOMIC,
                        deadline_step=None,
                        expected_value=0.0,
                        action_cost=1,
                        resource_needs=(ResourceNeed(item="GOOSE", quantity=1, source="SHED"),),
                    )
                )
            if wheat_needed_for_feed and shed.get("WHEAT", 0) > 0:
                tasks.append(
                    Task(
                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="WHEAT"),
                        target=pickup_target,
                        priority_tier=PriorityTier.ECONOMIC,
                        deadline_step=None,
                        expected_value=0.0,
                        action_cost=1,
                        resource_needs=(ResourceNeed(item="WHEAT", quantity=1, source="SHED"),),
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


MAX_CANDIDATES_PER_UNIT = 8

# Exhaustive search is (max_candidates_per_unit + 1)^n_units. Beyond this
# many units, fall back to a fast deterministic greedy assignment instead
# -- per the v2 design's explicit "if supported unit bounds are exceeded,
# use a deterministic greedy fallback ... do not fail silently" instruction.
# Found via a real bug: an uncapped hiring policy let unit count grow
# large enough (7-8) that exhaustive search over 9^7+ combinations made a
# single full 720-turn episode take ~20s. Measured directly (25 tasks,
# this repo's actual joint_assign): n=4 costs ~8ms/call, n=5 ~70ms, n=6
# ~650ms -- the jump from n=5 to n=6 is what made whole episodes slow.
# Capped at 4, matching the v2 design's own "expected farmer plus 1-3
# hands" assumption plus one unit of headroom.
MAX_EXHAUSTIVE_UNITS = 4


def _task_id_sort_key(task_id: TaskId | None) -> tuple:
    """Deterministic, always-comparable sort key -- `TaskId`'s own field
    order can't safely compare `item=None` against `item="CARROT"` across
    different task kinds, and `None` (PASS) needs to sort against real
    `TaskId`s too."""
    if task_id is None:
        return (1,)
    return (0, task_id.kind, task_id.x, task_id.y, task_id.item or "")


def _greedy_assign(
    unit_positions: list[tuple[int, int]],
    tasks: list[Task],
    current_assignments: dict[int, TaskId],
) -> dict[int, TaskId | None]:
    """Deterministic greedy fallback for when there are too many units for
    exhaustive search: each unit, in order, claims its own top-ranked task
    from whatever remains unclaimed. Not joint-optimal (an earlier unit can
    still claim a task a later unit would have been better positioned
    for), but fast and always correct (no duplicate claims)."""
    remaining = list(tasks)
    assignment: dict[int, TaskId | None] = {}
    for i, pos in enumerate(unit_positions):
        if not remaining:
            assignment[i] = None
            continue
        ranked = rank_tasks(remaining, current_position=pos, current_assignment=current_assignments.get(i))
        chosen = ranked[0]
        assignment[i] = chosen.task_id
        remaining = [t for t in remaining if t.task_id != chosen.task_id]
    return assignment


def _exhaustive_assign(
    unit_positions: list[tuple[int, int]],
    tasks: list[Task],
    current_assignments: dict[int, TaskId],
    max_candidates_per_unit: int = MAX_CANDIDATES_PER_UNIT,
) -> dict[int, TaskId | None]:
    """Bounded exhaustive joint assignment across units (farmer + hands).

    Each unit's candidate set is its own top `max_candidates_per_unit`
    feasible tasks (by `rank_tasks` from that unit's position) plus an
    implicit `PASS` (`None`). Every combination that doesn't claim the same
    task twice is scored by, in order: how many tasks get covered per
    priority tier (more coverage of higher tiers always wins, checked
    tier-by-tier before anything else), total travel distance, total
    expected value, then a deterministic tiebreak.

    This is what makes it superior to a naive "each unit picks its own
    top-ranked task first" sequential pass: that lets an earlier-decided
    unit claim a task purely because of its own ranking (e.g. tier
    dominates distance), even when a later unit is better positioned for
    it — see `docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md`.

    Factored out of `joint_assign` (which applies the `MAX_EXHAUSTIVE_UNITS`
    production cap) so offline measurement tooling can invoke exhaustive
    search directly on larger unit counts to quantify the greedy fallback's
    quality gap (`docs/6_next_steps.md` item 15) -- exponential cost is
    acceptable for that one-off analysis even though it's too slow per-turn.
    """
    task_by_id = {t.task_id: t for t in tasks}
    n_tiers = len(PriorityTier)

    candidate_lists: list[list[TaskId | None]] = []
    for i, pos in enumerate(unit_positions):
        ranked = rank_tasks(tasks, current_position=pos, current_assignment=current_assignments.get(i))
        candidate_lists.append([t.task_id for t in ranked[:max_candidates_per_unit]] + [None])

    best_key = None
    best_combo: tuple[TaskId | None, ...] = tuple(None for _ in unit_positions)

    for combo in itertools.product(*candidate_lists):
        claimed = [tid for tid in combo if tid is not None]
        if len(claimed) != len(set(claimed)):
            continue  # duplicate claim this combination -- invalid

        tier_counts = [0] * n_tiers
        total_distance = 0
        total_value = 0.0
        for i, tid in enumerate(combo):
            if tid is None:
                continue
            task = task_by_id[tid]
            tier_counts[task.priority_tier] += 1
            total_distance += abs(task.target[0] - unit_positions[i][0]) + abs(task.target[1] - unit_positions[i][1])
            total_value += task.expected_value

        key = (
            tuple(-c for c in tier_counts),  # more coverage per tier wins, tier order first
            total_distance,
            -total_value,
            tuple(_task_id_sort_key(tid) for tid in combo),
        )
        if best_key is None or key < best_key:
            best_key = key
            best_combo = combo

    return dict(enumerate(best_combo))


def joint_assign(
    unit_positions: list[tuple[int, int]],
    tasks: list[Task],
    current_assignments: dict[int, TaskId],
    max_candidates_per_unit: int = MAX_CANDIDATES_PER_UNIT,
) -> dict[int, TaskId | None]:
    """Bounded exhaustive joint assignment across units (farmer + hands),
    falling back to `_greedy_assign` (fast, not joint-optimal) if there are
    more than `MAX_EXHAUSTIVE_UNITS` units, since exhaustive search over
    `(max_candidates_per_unit + 1) ** len(unit_positions)` combinations
    becomes impractically slow well before that. See `_exhaustive_assign`
    for the scoring objective.
    """
    if len(unit_positions) > MAX_EXHAUSTIVE_UNITS:
        return _greedy_assign(unit_positions, tasks, current_assignments)
    return _exhaustive_assign(unit_positions, tasks, current_assignments, max_candidates_per_unit)


@dataclass(frozen=True)
class MarketIntent:
    """A future-turn market order: buying this now doesn't make a task
    executable this same turn (unit actions execute before market actions,
    per the game's turn processing order)."""

    item: str
    quantity: int
    reason: str  # e.g. "PLANT" -- why this intent was created


# Calibrated constants for the service-capacity load check (§ below).
# A 2026-08-02 recalibration attempt (TRAVEL_ALLOWANCE 4->8,
# AVERAGE_VALUE_PER_RECOVERED_ACTION 15.0->65.0 below, from real
# task_teacher_v2 telemetry) was reverted after full-gate re-evaluation
# showed it was a net regression, not an improvement -- see
# docs/4_agent_version_log.md and
# docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md §23 for the
# full account of why a single-shot measurement under one hiring regime
# didn't transfer once it changed that regime. Kept at the original,
# already-evaluated values pending a non-naive recalibration approach.
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


# Calibration constant for the hiring decision (task_teacher_v2): estimated
# dollar value of one recovered service-capacity turn. Measured 2026-08-02
# at $65.26/action under the original (less-aggressive) hiring behavior --
# but plugging that number back in drove much more aggressive hiring (flat
# 7 hands, ~111 hire orders/episode vs. the original ~71), which measurably
# hurt win rate against task_teacher_v1 (0.970 -> 0.750 over 50 pairs, CI
# dropping from [0.730, 1.000] to a barely-above-0.50 [0.510, 0.990]) --
# see docs/4_agent_version_log.md for the full account. Reverted to the
# original estimate, which is a worse point estimate of $/action but a
# better-performing operating point once its own feedback effect on
# hiring behavior is accounted for.
AVERAGE_VALUE_PER_RECOVERED_ACTION = 15.0

LAND_MIN_DAYS_REMAINING = 12
LAND_BUDGET_RESERVE = 400
MIN_HANDS_BEFORE_LAND = 3
NW_SATURATION_PLANTS = 18


def estimate_hire_value(projected_load: int, remaining_turns_today: int, existing_hands: int = 0) -> float:
    """Estimated dollar value of hiring one *more* hand today.

    Value only exists if the projected service load exceeds the capacity
    already available today — every existing unit (the farmer, plus each
    hand already hired today) already contributes `remaining_turns_today`
    of capacity, so hiring hand N+1 is only valuable if load still exceeds
    what N hands (plus the farmer) can already absorb. Without this, a
    static load estimate never decreases as hands are hired and
    `should_hire` would keep approving hire after hire in the same day —
    a real bug found via a full simulator run, where the resulting unit
    count made `joint_assign`'s combinatorial search explode. The
    recovered-turns proxy is additionally capped at how many turns are
    left today, since a hand can't do more work today than today has turns
    for.
    """
    existing_capacity = remaining_turns_today * (1 + existing_hands)  # farmer + hired hands
    overload = projected_load - existing_capacity
    if overload <= 0:
        return 0.0
    recovered_turns = min(overload, remaining_turns_today)
    return recovered_turns * AVERAGE_VALUE_PER_RECOVERED_ACTION


def should_hire(
    projected_load: int,
    remaining_turns_today: int,
    hires_today: int,
    money: float,
    safety_margin: float = 0.0,
    existing_hands: int = 0,
) -> bool:
    """Whether hiring one more hand today clears its fibonacci-scaled cost.

    Per the v2 design: hire only when the estimated recovered value
    exceeds the next hire's cost plus a configurable safety margin, and
    only if affordable at all. Not a diversity-seeking heuristic — value
    must be real and load-driven, per the design's explicit "do not hire
    merely to create training action diversity" rule.
    """
    cost = economy.hire_cost(hires_today)
    if money < cost:
        return False
    value = estimate_hire_value(projected_load, remaining_turns_today, existing_hands)
    return value > cost + safety_margin


def should_buy_land(
    unlocked_quadrants: list[str],
    money: float,
    projected_load: int,
    remaining_turns_today: int,
    existing_hands: int,
    day: int,
    last_day: int,
    reserved_for_hire: float,
    plant_tile_count: int,
) -> bool:
    """Whether to emit BUY_LAND for NE this turn (v4 hard-cap: one extra quadrant)."""
    if len(unlocked_quadrants) != 1:
        return False
    if plant_tile_count < NW_SATURATION_PLANTS:
        return False
    if existing_hands < MIN_HANDS_BEFORE_LAND:
        return False
    if last_day - day < LAND_MIN_DAYS_REMAINING:
        return False
    cost = economy.land_cost(0)
    if cost is None:
        return False
    if money - reserved_for_hire < cost + LAND_BUDGET_RESERVE:
        return False
    if estimate_hire_value(projected_load, remaining_turns_today, existing_hands) > 0:
        return False
    return True


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
    previous_day: int = -1

    def reset(self) -> None:
        self.assignments.clear()
        self.previous_step = -1
        self.previous_day = -1


def reset_hand_assignments_on_day_change(state: TeacherState, day: int) -> None:
    """Clear non-farmer (unit index > 0) assignments when `day` changes.

    Both the farmer's position and every hired hand reset unconditionally
    at every end-of-day boundary in the real game (confirmed against
    kaggriculture.py's `_end_of_day`) — a hand's index identity in
    `obs["farms"][player]["hands"]` never survives a day boundary, even if
    an identical hand is re-hired. The farmer's own assignment (unit 0)
    is left untouched here; it revalidates naturally next turn, since
    `rank_tasks`/`joint_assign` only apply hysteresis when the persisted
    `TaskId` still matches a freshly generated task.
    """
    if day != state.previous_day:
        state.assignments = {unit: task_id for unit, task_id in state.assignments.items() if unit == 0}
        state.previous_day = day
