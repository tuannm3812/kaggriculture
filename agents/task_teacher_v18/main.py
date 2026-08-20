"""Kaggriculture threat-aware task/route teacher agent, v18 (v16 policy scaffold).
"""

from __future__ import annotations

from kaggriculture_lib import economy
from kaggriculture_lib.adaptive_strategy import (
    ThreatLevel,
    ThreatMemory,
    ThreatSnapshot,
    ThreatTransition,
    parse_public_threat_snapshot,
)
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

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON", "STRAWBERRY")
DEFAULT_TURNS_PER_DAY = 24

MAX_GEESE = 4
MAX_COWS = 8
MAX_SHEEP = 4
MAX_FEED_ACTIONS_PER_DAY = 10

COW_COST = economy.ANIMALS["COW"]["cost"]      # 600
SHEEP_COST = economy.ANIMALS["SHEEP"]["cost"]  # 500
GOOSE_COST = economy.ANIMALS["GOOSE"]["cost"]  # 300

_state = TeacherState()
_threat_memory = ThreatMemory()
_last_diagnostics: dict[int, dict] = {}


def get_last_diagnostics(player: int) -> dict:
    """Return a detached copy of the latest scalar diagnostics for one player."""
    return dict(_last_diagnostics.get(player, {}))


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


def _farm_stats(tiles: list[list]) -> dict:
    stats = {
        "placed_cows": 0,
        "placed_sheep": 0,
        "placed_geese": 0,
        "unfed_cows": 0,
        "unfed_sheep": 0,
        "unfed_geese": 0,
        "empty_pastures": 0,
        "empty_coops": 0,
        "plant_tiles": 0,
    }
    for row in tiles:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            animal = tile.get("animal")
            if animal == "COW":
                stats["placed_cows"] += 1
                if not tile["fed_today"]:
                    stats["unfed_cows"] += 1
            elif animal == "SHEEP":
                stats["placed_sheep"] += 1
                if not tile["fed_today"]:
                    stats["unfed_sheep"] += 1
            elif animal == "GOOSE":
                stats["placed_geese"] += 1
                if not tile["fed_today"]:
                    stats["unfed_geese"] += 1
            elif tile.get("kind") == "PASTURE" and tile.get("animal") is None:
                stats["empty_pastures"] += 1
            elif tile.get("kind") == "COOP" and tile.get("animal") is None:
                stats["empty_coops"] += 1
            elif tile.get("kind") == "PLANT":
                stats["plant_tiles"] += 1
    return stats


def _owned_animal_count(animal: str, placed: int, shed: dict, inventories: list[dict]) -> int:
    """Placed + shed + inventory counts for an animal type."""
    return (
        placed
        + int(shed.get(animal, 0))
        + sum(int(inv.get(animal, 0)) for inv in inventories)
    )


def agent(obs, config=None):
    threat_expansion_enabled = (
        True if config is None else bool(config.get("enableThreatExpansion", True))
    )
    player = obs["player"]
    opponent_index = 1 - player
    snapshot, public_state_reason = parse_public_threat_snapshot(obs["farms"][opponent_index])
    transition = _threat_memory.update(
        player=player,
        step=obs["step"],
        day=obs["day"],
        hour=obs["hour"],
        snapshot=snapshot,
    )
    _last_diagnostics[player] = {
        "threat_level": transition.level.name,
        "threat_changed": transition.changed,
        "threat_reason": transition.reason,
        "threat_day": transition.day,
        "threat_hour": transition.hour,
        "opponent_quadrants": snapshot.quadrants,
        "opponent_hands": snapshot.hands,
        "opponent_animals": snapshot.placed_animals,
        "delta_quadrants": transition.delta_quadrants,
        "delta_hands": transition.delta_hands,
        "delta_animals": transition.delta_animals,
        "public_state_reason": public_state_reason,
        "threat_expansion_enabled": threat_expansion_enabled,
    }

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

    stats = _farm_stats(me["tiles"])
    owned_cows = _owned_animal_count("COW", stats["placed_cows"], shed, inventories)
    owned_sheep = _owned_animal_count("SHEEP", stats["placed_sheep"], shed, inventories)
    owned_geese = _owned_animal_count("GOOSE", stats["placed_geese"], shed, inventories)

    cow_in_any_inventory = any(inv.get("COW", 0) > 0 for inv in inventories)
    sheep_in_any_inventory = any(inv.get("SHEEP", 0) > 0 for inv in inventories)
    goose_in_any_inventory = any(inv.get("GOOSE", 0) > 0 for inv in inventories)

    animals_unlocked = len(me["unlocked_quadrants"]) >= 2 and day >= 11

    total_owned_animals = owned_cows + owned_sheep + owned_geese
    total_max_animals = MAX_COWS + MAX_SHEEP + MAX_GEESE

    cow_in_transit = int(shed.get("COW", 0)) + sum(int(inv.get("COW", 0)) for inv in inventories)
    sheep_in_transit = int(shed.get("SHEEP", 0)) + sum(int(inv.get("SHEEP", 0)) for inv in inventories)
    goose_in_transit = int(shed.get("GOOSE", 0)) + sum(int(inv.get("GOOSE", 0)) for inv in inventories)
    animals_in_transit = cow_in_transit + sheep_in_transit + goose_in_transit

    # Build pastures under animal limits
    # Build pastures under animal limits
    total_pastures = stats["placed_cows"] + stats["placed_sheep"] + stats["empty_pastures"]
    want_pasture = (
        animals_unlocked
        and (total_pastures < (owned_cows + cow_in_transit + owned_sheep + sheep_in_transit))
    )

    # Build coops under animal limits
    total_coops = stats["placed_geese"] + stats["empty_coops"]
    want_coop = total_coops < (owned_geese + goose_in_transit)

    wheat_needed_for_feed = stats["unfed_cows"] > 0 or stats["unfed_sheep"] > 0 or stats["unfed_geese"] > 0

    tasks = generate_tasks(
        tiles=me["tiles"],
        unlocked_quadrants=me["unlocked_quadrants"],
        day=day,
        last_day=last_day,
        market_prices=prices,
        candidate_crops=CANDIDATE_CROPS,
        board_size=board_size,
        shed=shed,
        want_coop=want_coop,
        goose_in_any_inventory=goose_in_any_inventory,
        wheat_needed_for_feed=wheat_needed_for_feed,
        want_pasture=want_pasture,
        cow_in_any_inventory=cow_in_any_inventory,
        sheep_in_any_inventory=sheep_in_any_inventory,
        max_feed_tasks=MAX_FEED_ACTIONS_PER_DAY,
        non_emergency_feed_tier=PriorityTier.DAILY_CARE,
        care_tier=PriorityTier.DAILY_CARE,
    )
    task_by_id = {t.task_id: t for t in tasks}

    unit_positions = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
    assignment = joint_assign(unit_positions, tasks, _state.assignments, unit_inventories=inventories)
    _state.assignments = {unit: tid for unit, tid in assignment.items() if tid is not None}

    market_orders: list[list] = []

    is_terminal_liquidation = (day == last_day and hour >= 20)

    if is_terminal_liquidation:
        # Sell absolutely everything sellable in the shed
        for item in ["WHEAT", "CARROT", "MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "FERTILIZER"]:
            available = shed.get(item, 0)
            if available > 0:
                market_orders.append(["SELL", item, available])
    else:
        # Normal daily selling
        for crop in ["CARROT", "MELON", "STRAWBERRY"]:
            available = shed.get(crop, 0)
            if available > 0:
                market_orders.append(["SELL", crop, available])

        # Sell wheat only if no animals need it for feed
        if (owned_cows == 0 and owned_sheep == 0 and owned_geese == 0):
            available = shed.get("WHEAT", 0)
            if available > 0:
                market_orders.append(["SELL", "WHEAT", available])

        for prod in ["MILK", "WOOL", "EGG", "FERTILIZER"]:
            available = shed.get(prod, 0)
            if available > 0:
                market_orders.append(["SELL", prod, available])

    pending_water = sum(1 for t in tasks if t.task_id.kind == TaskKind.WATER)
    pending_plant = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
    pending_harvest = sum(1 for t in tasks if t.task_id.kind == TaskKind.HARVEST)
    pending_cow = sum(1 for t in tasks if t.task_id.kind in (
        TaskKind.BUILD_PASTURE, TaskKind.BUILD_COOP, TaskKind.PICKUP, TaskKind.PLACE, TaskKind.FEED, TaskKind.CARE
    ))
    load = project_daily_load(pending_water, pending_plant, pending_harvest) + pending_cow
    future_action_turns = max(0, turns_per_day - hour - 1)
    immediately_completing = _count_immediately_completing_tasks(
        unit_positions, assignment, task_by_id, private["seeds"]
    )
    future_load = max(0, load - immediately_completing)

    # Dynamic hands floor based on farm size and cash
    n_quadrants = len(me["unlocked_quadrants"])
    hands_floor = 0
    mult_val = economy.hire_cost_mult(config)
    if day < 10:
        if mult_val >= 5.0:
            hands_floor = 0
        else:
            hands_floor = 3  # Optimal Day 0-9 cheap labor scaling
    elif day == 29:
        # Last day scale up to harvest and sell everything
        if me["money"] >= 6000.0:
            hands_floor = 8
        elif me["money"] >= 2000.0:
            hands_floor = 5
        else:
            hands_floor = 2
    else:
        # Middle game (Day 10-28)
        if me["money"] >= 6000.0 and n_quadrants >= 4:
            hands_floor = 11
        elif me["money"] >= 4000.0 and n_quadrants >= 3:
            hands_floor = 8
        elif me["money"] >= 2000.0 and n_quadrants >= 2:
            hands_floor = 5
        elif me["money"] >= 1000.0:
            hands_floor = 3
        elif me["money"] >= 500.0:
            hands_floor = 2
        elif me["money"] >= 200.0:
            hands_floor = 1
        else:
            hands_floor = 0

        # Capping to save on quadratic re-hiring fees if hiring is expensive:
        if mult_val >= 5.0:
            hands_floor = min(hands_floor, 3)

    # Calculate Cash Reservation for essential expenditures (Hiring, Seed purchases, Feed)
    mult = economy.hire_cost_mult(config)
    hires_to_queue = 0
    temp_money = me["money"]
    temp_hires_today = me["hires_today"]
    temp_existing = len(me["hands"])

    # 1. Hire to meet the hands floor (no extra hiring to prevent bankruptcy)
    while temp_existing < hands_floor:
        cost = economy.hire_cost(temp_hires_today, mult=mult)
        if temp_money >= cost:
            hires_to_queue += 1
            temp_money -= cost
            temp_hires_today += 1
            temp_existing += 1
        else:
            break

    reserved_for_hire = 0.0
    temp_hires_today = me["hires_today"]
    for _ in range(hires_to_queue):
        reserved_for_hire += economy.hire_cost(temp_hires_today, mult=mult)
        temp_hires_today += 1

    # Reserve for seeds assigned to units this turn
    temp_seeds = dict(private["seeds"])
    reserved_for_seeds = 0.0
    for unit_idx, task_id in assignment.items():
        if task_id and task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if temp_seeds.get(crop, 0) > 0:
                temp_seeds[crop] -= 1
            else:
                reserved_for_seeds += economy.CROPS[crop]["seed"]

    # Reserve for wheat feed
    reserved_for_feed = 0.0
    if total_owned_animals > 0:
        total_wheat = shed.get("WHEAT", 0) + sum(inv.get("WHEAT", 0) for inv in inventories)
        target_wheat = max(2, total_owned_animals * 2)
        if total_wheat < target_wheat:
            buy_qty = target_wheat - total_wheat
            reserved_for_feed = buy_qty * prices.get("WHEAT", 25.0)

    # Dynamic minimum liquidity reserve to prevent starvation and labor shortage
    feed_reserve = total_owned_animals * 50.0
    hands_reserve = 0.0
    temp_h = 0
    for _ in range(hands_floor):
        hands_reserve += 3.0 * economy.hire_cost(temp_h, mult=mult)
        temp_h += 1
    buffer = 250.0 if total_owned_animals > 0 else 100.0
    minimum_liquidity = feed_reserve + hands_reserve + buffer

    liquidity_reserve = minimum_liquidity if (last_day - day >= 2 and day >= 2) else 0.0
    essential_reserves = reserved_for_hire + liquidity_reserve
    available_money = max(0.0, me["money"] - essential_reserves)

    # 1. HIRE hands
    for _ in range(hires_to_queue):
        market_orders.append(["HIRE"])

    # 2. BUY_LAND (up to max 1 extra quadrant, saving $6,000)
    land_cost = economy.land_cost(len(me["unlocked_quadrants"]) - 1)
    n_extra = len(me["unlocked_quadrants"]) - 1
    can_buy_land = False
    if land_cost is not None and 0 <= n_extra < 1 and last_day - day >= 12 and day >= 9:
        reserve = max(1000.0 * (n_extra + 1), minimum_liquidity)
        if me["money"] - reserved_for_hire >= land_cost + reserve:
            can_buy_land = True

    if can_buy_land:
        market_orders.append(["BUY_LAND"])
        available_money -= land_cost

    # 3. BUY_ANIMAL COW (matures in 8 days, needs at least 7 days to yield 3 milkings)
    cash_reserve = me["money"] - reserved_for_hire
    if (
        animals_unlocked
        and day + 15 <= last_day
        and (owned_cows + cow_in_transit < MAX_COWS)
        and available_money >= COW_COST
        and cash_reserve >= COW_COST + 1200.0
    ):
        market_orders.append(["BUY_ANIMAL", "COW", 1])
        available_money -= COW_COST
        cash_reserve -= COW_COST

    # 4. BUY_ANIMAL SHEEP (matures in 6 days, needs at least 9 days to yield 3 wool shearings)
    if (
        animals_unlocked
        and day + 15 <= last_day
        and (owned_sheep + sheep_in_transit < MAX_SHEEP)
        and available_money >= SHEEP_COST
        and cash_reserve >= SHEEP_COST + 1200.0
    ):
        market_orders.append(["BUY_ANIMAL", "SHEEP", 1])
        available_money -= SHEEP_COST
        cash_reserve -= SHEEP_COST

    # 4.5. BUY_ANIMAL GOOSE (matures in 4 days, needs 6 days of eggs to break even)
    max_geese_allowed = 0 if day < 10 else MAX_GEESE
    if (
        animals_unlocked
        and day + 10 <= last_day
        and (owned_geese + goose_in_transit < max_geese_allowed)
        and available_money >= GOOSE_COST
        and cash_reserve >= GOOSE_COST + 1200.0
    ):
        market_orders.append(["BUY_ANIMAL", "GOOSE", 1])
        available_money -= GOOSE_COST
        cash_reserve -= GOOSE_COST

    if hour == 1:
        # 5. BUY_PRODUCT WHEAT
        if total_owned_animals > 0:
            total_wheat = shed.get("WHEAT", 0) + sum(inv.get("WHEAT", 0) for inv in inventories)
            target_wheat = max(2, total_owned_animals * 2)
            if total_wheat < target_wheat:
                buy_qty = target_wheat - total_wheat
                wheat_unit_price = prices.get("WHEAT", 25.0)
                if me["money"] >= buy_qty * wheat_unit_price:
                    market_orders.append(["BUY_PRODUCT", "WHEAT", buy_qty])

        # Compute actual remaining cash for seed buying inside resolve_unit_action
        market_cash_remaining = available_money
        for order in market_orders:
            if order[0] == "BUY_LAND":
                market_cash_remaining -= economy.land_cost(len(me["unlocked_quadrants"]) - 1)
            elif order[0] == "BUY_ANIMAL":
                market_cash_remaining -= economy.ANIMALS[order[1]]["cost"]
            elif order[0] == "BUY_PRODUCT" and order[1] == "WHEAT":
                market_cash_remaining -= order[2] * prices.get("WHEAT", 25.0)

        # 6. BUY_SEED batch buying
        seeds_in_shed = private["seeds"]
        total_seeds_in_shed = sum(seeds_in_shed.get(c, 0) for c in CANDIDATE_CROPS)
        total_plant_tasks = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
        if total_seeds_in_shed >= total_plant_tasks:
            seeds_needed = {c: 0 for c in CANDIDATE_CROPS}
        else:
            seeds_needed = {}
            for crop in CANDIDATE_CROPS:
                plant_tasks = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT and t.task_id.item == crop)
                current_seeds = seeds_in_shed.get(crop, 0)
                seeds_needed[crop] = max(0, plant_tasks - current_seeds)

        for crop in CANDIDATE_CROPS:
            # Check if crop can mature if planted tomorrow (Day D+1)
            cd = economy.CROPS[crop]
            can_mature_tomorrow = False
            if cd["ongoing"]:
                can_mature_tomorrow = economy.can_ongoing_crop_reach_any_tick(crop, day + 1, last_day)
            else:
                can_mature_tomorrow = economy.can_mature_in_time(crop, day + 1, last_day)
            if not can_mature_tomorrow:
                continue

            needed = seeds_needed.get(crop, 0)
            if needed > 0:
                seed_cost = economy.CROPS[crop]["seed"]
                buy_limit = 25 if day == 0 else 12
                buy_qty = min(needed, buy_limit, int(market_cash_remaining // seed_cost))
                if buy_qty > 0:
                    market_orders.append(["BUY_SEED", crop, buy_qty])
                    market_cash_remaining -= buy_qty * seed_cost
    else:
        # Re-compute market_cash_remaining for resolve_unit_action when hour != 1
        market_cash_remaining = available_money
        for order in market_orders:
            if order[0] == "BUY_LAND":
                market_cash_remaining -= economy.land_cost(len(me["unlocked_quadrants"]) - 1)
            elif order[0] == "BUY_ANIMAL":
                market_cash_remaining -= economy.ANIMALS[order[1]]["cost"]

    seeds_remaining = dict(private["seeds"])
    seed_orders_queued = {order[1] for order in market_orders if order[0] == "BUY_SEED"}

    def resolve_unit_action(position: tuple[int, int], task_id, unit_idx: int) -> list:
        nonlocal market_cash_remaining
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
            # Fallback: plant any seed we have in the shed/inventory
            for fallback_crop in CANDIDATE_CROPS:
                if seeds_remaining.get(fallback_crop, 0) > 0:
                    seeds_remaining[fallback_crop] -= 1
                    return ["PLANT", fallback_crop]
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
            qty = 1
            if task.resource_needs:
                qty = task.resource_needs[0].quantity
            return ["PICKUP", task_id.item, qty]
        return ["PASS"]

    farmer_action = resolve_unit_action(unit_positions[0], assignment.get(0), 0)
    hands_actions = [
        resolve_unit_action(unit_positions[i + 1], assignment.get(i + 1), i + 1)
        for i in range(len(me["hands"]))
    ]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
