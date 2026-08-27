"""Kaggriculture multi-tile task/route teacher agent, v9 (v5 + inventory-aware Cow loop + direct feed buy).

Extends `task_teacher_v5` and `v7` with:
1. Inventory-aware task assignment in joint_assign (prevents empty PLACE/FEED passes).
2. Direct feed purchasing (buys WHEAT product directly from the market when feed is low, saving hand labor).
3. Early cow bootstrap capped at MAX_COWS = 3.
"""

from __future__ import annotations

from kaggriculture_lib import economy
from kaggriculture_lib.tasking import (
    PriorityTier,
    TaskKind,
    TeacherState,
    generate_tasks,
    joint_assign,
    project_daily_load,
    reset_hand_assignments_on_day_change,
    route_toward,
    should_buy_land,
    should_hire,
)

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")
DEFAULT_TURNS_PER_DAY = 24

MAX_GEESE = 0
MAX_COWS = 3
MAX_FEED_ACTIONS_PER_DAY = 6

COW_COST = economy.ANIMALS["COW"]["cost"]  # 600 on pinned 1.29.3

_state = TeacherState()


def _reset_if_new_episode(state: TeacherState, step: int) -> None:
    if step == 0 or step < state.previous_step:
        state.reset()
    state.previous_step = step


def _count_immediately_completing_tasks(unit_positions, assignment, task_by_id, seeds_remaining) -> int:
    """Count assigned units already standing on crop WATER/PLANT/HARVEST tiles."""
    available_seeds = dict(seeds_remaining)
    count = 0
    for unit_idx in sorted(assignment):
        task_id = assignment[unit_idx]
        if task_id is None or task_id.kind not in (TaskKind.WATER, TaskKind.PLANT, TaskKind.HARVEST):
            continue
        task = task_by_id.get(task_id)
        if task is None or unit_positions[unit_idx] != task.target:
            continue
        if task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if available_seeds.get(crop, 0) <= 0:
                continue
            available_seeds[crop] -= 1
        count += 1
    return count


def _farm_cow_and_structure_counts(tiles: list[list]) -> tuple[int, int, int, int]:
    """Returns `(cows_count, unfed_cows_count, empty_pasture_count, plant_tile_count)`."""
    cows_count = 0
    unfed_cows_count = 0
    empty_pasture_count = 0
    plant_tile_count = 0
    for row in tiles:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if tile.get("animal") == "COW":
                cows_count += 1
                if not tile["fed_today"]:
                    unfed_cows_count += 1
            elif tile.get("kind") == "PASTURE" and "animal" not in tile:
                empty_pasture_count += 1
            elif tile.get("kind") == "PLANT":
                plant_tile_count += 1
    return cows_count, unfed_cows_count, empty_pasture_count, plant_tile_count


def _owned_cow_count(placed_cows: int, shed: dict, inventories: list[dict]) -> int:
    """Placed + shed + inventory cows."""
    return (
        placed_cows
        + int(shed.get("COW", 0))
        + sum(int(inv.get("COW", 0)) for inv in inventories)
    )


def agent(obs, config=None):
    _reset_if_new_episode(_state, obs["step"])
    reset_hand_assignments_on_day_change(_state, obs["day"])

    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    prices = obs["market"]["prices"]
    shed = private["shed"]
    inventories = private["inventories"]
    day = obs["day"]
    hour = obs["hour"]
    board_size = len(me["tiles"])
    turns_per_day = config.get("turnsPerDay", DEFAULT_TURNS_PER_DAY) if config else DEFAULT_TURNS_PER_DAY

    last_day = economy.last_day_index(config)

    placed_cows, unfed_cows_count, empty_pasture_count, plant_tile_count = _farm_cow_and_structure_counts(
        me["tiles"]
    )
    owned_cows = _owned_cow_count(placed_cows, shed, inventories)
    cow_in_any_inventory = any(inv.get("COW", 0) > 0 for inv in inventories)

    cows_unlocked = len(me["unlocked_quadrants"]) >= 2 and day >= 11
    # Build a pasture when under owned cap or placing in-flight cows
    want_pasture = (
        cows_unlocked
        and (owned_cows < MAX_COWS or shed.get("COW", 0) > 0 or cow_in_any_inventory)
        and empty_pasture_count == 0
    )

    # Generate WHEAT PICKUP tasks as long as there is an unfed cow
    wheat_needed_for_feed = unfed_cows_count > 0

    tasks = generate_tasks(
        tiles=me["tiles"],
        unlocked_quadrants=me["unlocked_quadrants"],
        day=day,
        last_day=last_day,
        market_prices=prices,
        candidate_crops=CANDIDATE_CROPS,
        board_size=board_size,
        shed=shed,
        want_coop=False,
        goose_in_any_inventory=False,
        wheat_needed_for_feed=wheat_needed_for_feed,
        want_pasture=want_pasture,
        cow_in_any_inventory=cow_in_any_inventory,
        max_feed_tasks=MAX_FEED_ACTIONS_PER_DAY,
        non_emergency_feed_tier=PriorityTier.DAILY_CARE,
        care_tier=PriorityTier.DAILY_CARE,  # Set CARE priority to DAILY_CARE to double yields
    )
    task_by_id = {t.task_id: t for t in tasks}

    unit_positions = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
    assignment = joint_assign(unit_positions, tasks, _state.assignments, unit_inventories=inventories)
    _state.assignments = {unit: tid for unit, tid in assignment.items() if tid is not None}

    market_orders: list[list] = []
    for crop in CANDIDATE_CROPS:
        if crop == "WHEAT" and owned_cows > 0:
            continue
        available = shed.get(crop, 0)
        if available > 0:
            market_orders.append(["SELL", crop, available])
    if shed.get("MILK", 0) > 0:
        market_orders.append(["SELL", "MILK", shed["MILK"]])

    pending_water = sum(1 for t in tasks if t.task_id.kind == TaskKind.WATER)
    pending_plant = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
    pending_harvest = sum(1 for t in tasks if t.task_id.kind == TaskKind.HARVEST)
    pending_cow = sum(1 for t in tasks if t.task_id.kind in (
        TaskKind.BUILD_PASTURE, TaskKind.PICKUP, TaskKind.PLACE, TaskKind.FEED, TaskKind.CARE
    ))
    load = project_daily_load(pending_water, pending_plant, pending_harvest) + pending_cow
    future_action_turns = max(0, turns_per_day - hour - 1)
    immediately_completing = _count_immediately_completing_tasks(
        unit_positions, assignment, task_by_id, private["seeds"]
    )
    future_load = max(0, load - immediately_completing)

    available_money = me["money"]
    reserved_for_hire = 0.0
    if should_hire(
        future_load, future_action_turns, me["hires_today"], me["money"], existing_hands=len(me["hands"])
    ):
        market_orders.append(["HIRE"])
        reserved_for_hire = economy.hire_cost(me["hires_today"])
        available_money -= reserved_for_hire

    if should_buy_land(
        unlocked_quadrants=me["unlocked_quadrants"],
        money=me["money"],
        projected_load=future_load,
        remaining_turns_today=future_action_turns,
        existing_hands=len(me["hands"]),
        day=day,
        last_day=last_day,
        reserved_for_hire=reserved_for_hire,
        plant_tile_count=plant_tile_count,
    ):
        market_orders.append(["BUY_LAND"])
        available_money -= economy.land_cost(len(me["unlocked_quadrants"]) - 1)

    # Buy cows under owned cap, and only if they can mature before the season ends (takes 8 days)
    cows_in_transit = int(shed.get("COW", 0)) + sum(int(inv.get("COW", 0)) for inv in inventories)
    pasture_slots = empty_pasture_count + (1 if want_pasture else 0)
    if (
        cows_unlocked
        and day + 8 <= last_day
        and owned_cows < MAX_COWS
        and cows_in_transit < pasture_slots
        and available_money >= COW_COST
    ):
        market_orders.append(["BUY_ANIMAL", "COW", 1])
        available_money -= COW_COST

    # Direct wheat feed purchasing from market
    if owned_cows > 0:
        total_wheat = shed.get("WHEAT", 0) + sum(inv.get("WHEAT", 0) for inv in inventories)
        target_wheat = max(2, owned_cows * 2)
        if total_wheat < target_wheat:
            buy_qty = target_wheat - total_wheat
            wheat_unit_price = prices.get("WHEAT", 25.0)
            buy_cost = buy_qty * wheat_unit_price
            if available_money >= buy_cost:
                market_orders.append(["BUY_PRODUCT", "WHEAT", buy_qty])
                available_money -= buy_cost

    seeds_remaining = dict(private["seeds"])
    seed_orders_queued: set[str] = set()

    def resolve_unit_action(position: tuple[int, int], task_id, unit_idx: int) -> list:
        nonlocal available_money
        if task_id is None:
            return ["PASS"]
        task = task_by_id.get(task_id)
        if task is None:
            return ["PASS"]

        tx, ty = task.target
        if position != (tx, ty):
            return [route_toward(position, (tx, ty), me["tiles"], board_size)]

        unit_inv = inventories[unit_idx] if unit_idx < len(inventories) else {}

        if task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if seeds_remaining.get(crop, 0) > 0:
                seeds_remaining[crop] -= 1
                return ["PLANT", crop]
            if crop not in seed_orders_queued and available_money >= economy.CROPS[crop]["seed"]:
                market_orders.append(["BUY_SEED", crop, 1])
                seed_orders_queued.add(crop)
                available_money -= economy.CROPS[crop]["seed"]
            return ["PASS"]
        if task_id.kind == TaskKind.WATER:
            return ["WATER"]
        if task_id.kind == TaskKind.HARVEST:
            return ["HARVEST"]
        if task_id.kind == TaskKind.DIG:
            return ["DIG"]
        if task_id.kind == TaskKind.BUILD_COOP:
            return ["BUILD_COOP"]
        if task_id.kind == TaskKind.BUILD_PASTURE:
            return ["BUILD_PASTURE"]
        if task_id.kind == TaskKind.PLACE:
            if unit_inv.get(task_id.item, 0) <= 0:
                return ["PASS"]
            return ["PLACE", task_id.item]
        if task_id.kind == TaskKind.FEED:
            if unit_inv.get("WHEAT", 0) <= 0:
                return ["PASS"]
            return ["FEED"]
        if task_id.kind == TaskKind.CARE:
            return ["CARE"]
        if task_id.kind == TaskKind.PICKUP:
            return ["PICKUP", task_id.item, 1]
        return ["PASS"]

    farmer_action = resolve_unit_action(unit_positions[0], assignment.get(0), 0)
    hands_actions = [
        resolve_unit_action(unit_positions[i + 1], assignment.get(i + 1), i + 1)
        for i in range(len(me["hands"]))
    ]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
