"""Kaggriculture multi-tile task/route teacher agent, v2.

Extends `task_teacher_v1` with daily hiring and deterministic multi-unit
task assignment, per the approved design in
docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md. Same crop
scope as v1 (Wheat/Carrot/Melon, one-time crops only); no animals,
fertilizer, or land purchases.

Key mechanics respected by construction, not by accident:
- Unit actions execute before market actions each turn, so a seed bought
  this turn can't plant this same turn (see `_resolve_unit_action`).
- Farmer position and all hired hands reset unconditionally every day
  (confirmed against `kaggriculture.py`'s `_end_of_day`), so hand-indexed
  assignments never persist across a day boundary
  (`reset_hand_assignments_on_day_change`), while the farmer's own
  assignment naturally revalidates via `joint_assign`'s hysteresis check.
- Hire cost is reserved before seed-purchase affordability is checked, so
  the two never silently overspend the same turn's budget together.
- At most one `HIRE` order is emitted per turn.

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
    should_hire,
)

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")
DEFAULT_TURNS_PER_DAY = 24

# Module-level state for the Kaggle submission path. See task_teacher_v1's
# docstring for why this is explicitly reset on obs["step"] == 0 rather
# than relying on module-reload behavior.
_state = TeacherState()


def _reset_if_new_episode(state: TeacherState, step: int) -> None:
    if step == 0 or step < state.previous_step:
        state.reset()
    state.previous_step = step


def agent(obs, config=None):
    _reset_if_new_episode(_state, obs["step"])
    reset_hand_assignments_on_day_change(_state, obs["day"])

    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    prices = obs["market"]["prices"]
    shed = private["shed"]
    day = obs["day"]
    hour = obs["hour"]
    board_size = len(me["tiles"])
    turns_per_day = config.get("turnsPerDay", DEFAULT_TURNS_PER_DAY) if config else DEFAULT_TURNS_PER_DAY

    last_day = economy.last_day_index(config)
    tasks = generate_tasks(
        tiles=me["tiles"],
        unlocked_quadrants=me["unlocked_quadrants"],
        day=day,
        last_day=last_day,
        market_prices=prices,
        candidate_crops=CANDIDATE_CROPS,
        board_size=board_size,
    )
    task_by_id = {t.task_id: t for t in tasks}

    unit_positions = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
    assignment = joint_assign(unit_positions, tasks, _state.assignments)
    _state.assignments = {unit: tid for unit, tid in assignment.items() if tid is not None}

    market_orders = [["SELL", crop, shed[crop]] for crop in CANDIDATE_CROPS if shed.get(crop, 0) > 0]

    # Hiring decision first, so seed-purchase affordability below reflects
    # the reserved hire budget -- not the other way around.
    pending_water = sum(1 for t in tasks if t.task_id.kind == TaskKind.WATER)
    pending_plant = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
    pending_harvest = sum(1 for t in tasks if t.task_id.kind == TaskKind.HARVEST)
    load = project_daily_load(pending_water, pending_plant, pending_harvest)
    remaining_turns_today = max(0, turns_per_day - hour)

    available_money = me["money"]
    if should_hire(
        load, remaining_turns_today, me["hires_today"], me["money"], existing_hands=len(me["hands"])
    ):
        market_orders.append(["HIRE"])
        available_money -= economy.hire_cost(me["hires_today"])

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
        return ["PASS"]

    farmer_action = resolve_unit_action(unit_positions[0], assignment.get(0))
    hands_actions = [
        resolve_unit_action(unit_positions[i + 1], assignment.get(i + 1)) for i in range(len(me["hands"]))
    ]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
