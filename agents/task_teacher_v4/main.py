"""Kaggriculture multi-tile task/route teacher agent, v4.

Extends `task_teacher_v2` (the current ladder champion) with two new
capabilities, per the approved design in
docs/superpowers/specs/2026-08-10-task-teacher-v4-design.md:

1. ROI-gated purchase of at most one extra quadrant (NE at $1000), via
   `kaggriculture_lib.tasking.should_buy_land`.
2. A Goose loop -- build coop, buy/pickup/place a goose, daily feed/care,
   harvest/sell eggs -- capped at `MAX_GEESE` animals.

Same one-time crop scope as v2 (Wheat/Carrot/Melon); no ongoing crops
(that's `task_teacher_v3`, evaluated but not promoted), no Cow/Sheep,
no fertilizer, no third/fourth quadrant. `task_teacher_v2`/`v3`'s own
`main.py` files are never modified -- this is a fresh, independent copy.

Key mechanics respected by construction, not by accident (all verified
against `kaggle_environments/envs/kaggriculture/kaggriculture.py`,
pinned 1.29.3 -- see the design doc's Verified Mechanics section):
- Unit actions execute before market actions each turn, so a seed/animal
  bought this turn can't be planted/placed this same turn.
- `BUY_ANIMAL` deposits the Goose into `private["shed"]`, not unit
  inventory -- a `PICKUP` is required before `PLACE` can succeed, and
  `FEED` consumes WHEAT from the acting unit's own inventory, so a
  `PICKUP` of WHEAT is likewise required when inventory is empty.
- Farmer position and all hired hands reset unconditionally every day, so
  hand-indexed assignments never persist across a day boundary, while the
  farmer's own assignment naturally revalidates via `joint_assign`'s
  hysteresis check.
- Same-turn budget stack (design doc §4): hire reservation first (cheaper
  overload fix), then land, then the Goose-purchase market order, then
  per-unit deferred seed purchases -- each reservation lowers
  `available_money` before the next check, so none of them can silently
  overspend the same turn's budget together.
- At most one `HIRE` and one `BUY_LAND` order is emitted per turn.
- Wheat is never sold below `economy.wheat_reserved_for_feed`'s reserve
  for the currently-held geese.

Local testing only: imports `kaggriculture_lib.economy`/`.tasking`
assuming `src/` is on `sys.path` (handled by `scripts/run_tournament.py`).
Use `scripts/package_agent.py` to generate a standalone submission
artifact.
"""

from __future__ import annotations

from kaggriculture_lib import economy
from kaggriculture_lib.tasking import (
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

# Hard cap on how many geese v4 will ever try to hold at once -- keeps the
# wheat/feed and land/hire budgets solvable, per the design doc §4 (which
# proposes 2, well under ANIMALS["GOOSE"]["max_held"] == 4).
MAX_GEESE = 2

GOOSE_COST = economy.ANIMALS["GOOSE"]["cost"]  # 300, verified against economy.ANIMALS / the env's ANIMALS table.

# Module-level state for the Kaggle submission path. See task_teacher_v1's
# docstring for why this is explicitly reset on obs["step"] == 0 rather
# than relying on module-reload behavior.
_state = TeacherState()


def _reset_if_new_episode(state: TeacherState, step: int) -> None:
    if step == 0 or step < state.previous_step:
        state.reset()
    state.previous_step = step


def _count_immediately_completing_tasks(unit_positions, assignment, task_by_id, seeds_remaining) -> int:
    """Count assigned units already standing on their task's tile whose
    action will actually resolve this turn.

    Those units emit the field action (not movement) this turn, so that
    task resolves regardless of any hiring decision -- it must not also
    count as still-outstanding load when sizing whether a new hire is
    justified. WATER and HARVEST always resolve when on-target (generated
    tasks are already legality-filtered). PLANT only resolves if a
    matching seed is held -- mirroring `resolve_unit_action`'s own check --
    otherwise it emits PASS and queues a deferred BUY_SEED, completing
    nothing. Seed availability is consumed from a local copy in the same
    farmer-then-hands order `resolve_unit_action` uses, so two on-target
    PLANT assignments sharing one scarce seed aren't both counted.

    New v4 task kinds (BUILD_COOP, PLACE, FEED, CARE, PICKUP) are
    deliberately not counted here: the daily-load service-capacity check
    they'd feed into isn't in v4's scope (see the design doc's
    non-goals -- hire constants aren't recalibrated for the Goose loop).
    """
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


def _farm_animal_and_structure_counts(tiles: list[list]) -> tuple[int, int, int, int]:
    """Single pass over `tiles` for every count the agent needs this turn.

    Returns `(geese_count, unfed_geese_count, has_empty_coop, plant_tile_count)`.
    `has_empty_coop` is 0/1 (not a running count -- only "does at least one
    exist" matters to callers).
    """
    geese_count = 0
    unfed_geese_count = 0
    has_empty_coop = 0
    plant_tile_count = 0
    for row in tiles:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if "animal" in tile:
                geese_count += 1
                if not tile["fed_today"]:
                    unfed_geese_count += 1
            elif tile.get("kind") == "COOP":
                has_empty_coop = 1
            elif tile.get("kind") == "PLANT":
                plant_tile_count += 1
    return geese_count, unfed_geese_count, has_empty_coop, plant_tile_count


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

    geese_count, unfed_geese_count, has_empty_coop, plant_tile_count = _farm_animal_and_structure_counts(
        me["tiles"]
    )
    # Don't queue a redundant BUILD_COOP once an empty coop is already
    # standing (waiting to be PLACE'd into) -- `generate_tasks` also
    # guards against a second coop appearing anywhere on the board, but
    # this keeps the intent explicit at the call site.
    want_coop = geese_count < MAX_GEESE and not has_empty_coop
    goose_in_any_inventory = any(inv.get("GOOSE", 0) > 0 for inv in inventories)
    wheat_in_inventories = sum(inv.get("WHEAT", 0) for inv in inventories)
    # Minimal correct signal: only queue a WHEAT PICKUP when there's an
    # unfed goose today and the wheat already carried isn't enough to feed
    # every currently-unfed goose -- avoids pestering PICKUP tasks once a
    # unit already holds enough to cover today's feeding.
    wheat_needed_for_feed = unfed_geese_count > 0 and wheat_in_inventories < unfed_geese_count

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
    )
    task_by_id = {t.task_id: t for t in tasks}

    unit_positions = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
    assignment = joint_assign(unit_positions, tasks, _state.assignments)
    _state.assignments = {unit: tid for unit, tid in assignment.items() if tid is not None}

    # Sell every held crop and EGG, except wheat kept back to feed geese --
    # `wheat_reserved_for_feed` over the remaining season (at least one day
    # of horizon so a same-day sell-everything glitch can't zero it out).
    market_orders: list[list] = []
    wheat_reserve = economy.wheat_reserved_for_feed(geese_count, max(1, last_day - day))
    for crop in CANDIDATE_CROPS:
        available = shed.get(crop, 0)
        sellable = max(0, available - wheat_reserve) if crop == "WHEAT" else available
        if sellable > 0:
            market_orders.append(["SELL", crop, sellable])
    if shed.get("EGG", 0) > 0:
        market_orders.append(["SELL", "EGG", shed["EGG"]])

    # Hiring decision first, so land/animal/seed-purchase affordability
    # below reflects the reserved hire budget -- not the other way around.
    pending_water = sum(1 for t in tasks if t.task_id.kind == TaskKind.WATER)
    pending_plant = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
    pending_harvest = sum(1 for t in tasks if t.task_id.kind == TaskKind.HARVEST)
    load = project_daily_load(pending_water, pending_plant, pending_harvest)
    # A hire is a market order, resolved after this turn's unit actions, so a
    # hand hired now gets its first action next turn -- its recoverable
    # capacity (and, symmetrically, any existing unit's still-outstanding
    # capacity) only spans turns *after* this one. A task an already-
    # positioned unit is about to complete this turn resolves regardless of
    # the hiring decision, so it isn't outstanding load for that decision
    # either. See docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md
    # §12.1.
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

    # Land is evaluated on the money remaining after the hire reservation
    # (hire is the cheaper overload fix -- design doc §3, ordering rule 5),
    # then reduces `available_money` in turn so a same-turn BUY_ANIMAL/seed
    # buy below can't double-spend the same dollars.
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

    if geese_count < MAX_GEESE and (has_empty_coop or want_coop) and available_money >= GOOSE_COST:
        market_orders.append(["BUY_ANIMAL", "GOOSE", 1])
        available_money -= GOOSE_COST

    seeds_remaining = dict(private["seeds"])
    seed_orders_queued: set[str] = set()

    def resolve_unit_action(position: tuple[int, int], task_id) -> list:
        nonlocal available_money
        if task_id is None:
            return ["PASS"]
        task = task_by_id.get(task_id)
        if task is None:
            return ["PASS"]

        tx, ty = task.target
        if position != (tx, ty):
            return [route_toward(position, (tx, ty), me["tiles"], board_size)]

        if task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if seeds_remaining.get(crop, 0) > 0:
                seeds_remaining[crop] -= 1
                return ["PLANT", crop]
            # Unit actions execute before market actions this turn, so a
            # seed bought now can't plant now -- queue for next turn.
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
        if task_id.kind == TaskKind.PLACE:
            return ["PLACE", task_id.item]
        if task_id.kind == TaskKind.FEED:
            return ["FEED"]
        if task_id.kind == TaskKind.CARE:
            return ["CARE"]
        if task_id.kind == TaskKind.PICKUP:
            return ["PICKUP", task_id.item, 1]
        return ["PASS"]

    farmer_action = resolve_unit_action(unit_positions[0], assignment.get(0))
    hands_actions = [
        resolve_unit_action(unit_positions[i + 1], assignment.get(i + 1)) for i in range(len(me["hands"]))
    ]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
