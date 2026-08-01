"""Kaggriculture multi-tile task/route teacher agent, v1.

New agent family (not `roi_teacher_v4`) per the approved design in
docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md
("task_teacher_v1: final design") — a structurally different architecture
(task arbitration + routing) from `roi_teacher_v1-v3`'s single-tile ROI
loop, built to be an adequate behavioral-cloning teacher rather than a
better single-tile agent.

Scope: one farmer, initial unlocked quadrant only, one-time crops only
(Wheat/Carrot/Melon), multi-tile plant/water/harvest/dig, deterministic
task generation/ranking/routing, seed acquisition and shed selling
consistent with kaggle-environments==1.29.3's turn order (manual `DROP`
is a no-op there; harvested produce reaches the shed automatically at
end of day — no explicit shed-logistics action needed). No hands, land,
animals, fertilizer, `PICKUP`/`PLACE`, or manual `DROP` — those are later
versions.

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
    rank_tasks,
    route_toward,
)

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")

# Module-level state for the Kaggle submission path. Explicitly reset on an
# observed game-state signal (obs["step"] == 0), never relied on module
# re-exec: verified that kaggle_environments' file-agent loader happens to
# give a fresh exec per env.run(), but that's an implementation detail of
# one calling path, not a guarantee for direct calls, BC trajectory
# generation, or interleaved parallel rollout workers (each of which should
# construct and own their own TeacherState instead of using this global).
_state = TeacherState()


def _reset_if_new_episode(state: TeacherState, step: int) -> None:
    if step == 0 or step < state.previous_step:
        state.reset()
    state.previous_step = step


def agent(obs, config=None):
    _reset_if_new_episode(_state, obs["step"])

    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    prices = obs["market"]["prices"]
    shed = private["shed"]
    day = obs["day"]
    board_size = len(me["tiles"])

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

    fx, fy = me["farmer"]
    current_assignment = _state.assignments.get(0)
    ranked = rank_tasks(tasks, current_position=(fx, fy), current_assignment=current_assignment)

    market_orders = [["SELL", crop, shed[crop]] for crop in CANDIDATE_CROPS if shed.get(crop, 0) > 0]
    farmer_action = ["PASS"]

    if not ranked:
        _state.assignments.pop(0, None)
    else:
        best = ranked[0]
        _state.assignments[0] = best.task_id
        tx, ty = best.target

        if (fx, fy) != (tx, ty):
            farmer_action = [route_toward((fx, fy), (tx, ty), me["tiles"], board_size)]
        elif best.task_id.kind == TaskKind.PLANT:
            crop = best.task_id.item
            if private["seeds"].get(crop, 0) > 0:
                farmer_action = ["PLANT", crop]
            elif me["money"] >= economy.CROPS[crop]["seed"]:
                # Unit actions execute before market actions this turn, so a
                # seed bought now can't plant now -- queue the purchase for
                # next turn instead of emitting an illegal same-turn PLANT.
                market_orders.append(["BUY_SEED", crop, 1])
        elif best.task_id.kind == TaskKind.WATER:
            farmer_action = ["WATER"]
        elif best.task_id.kind == TaskKind.HARVEST:
            farmer_action = ["HARVEST"]
        elif best.task_id.kind == TaskKind.DIG:
            farmer_action = ["DIG"]

    return {"farmer": farmer_action, "hands": [], "market": market_orders}
