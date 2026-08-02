"""Behavior tests for agents/task_teacher_v2/main.py.

Extends tests/test_task_teacher_v1.py's synthetic-obs pattern to multiple
units (farmer + hands) and hiring. Per the approved design in
docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md.
"""

import math
import sys
from pathlib import Path

from conftest import load_agent_module

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from kaggle_environments import make  # noqa: E402
from kaggriculture_lib.tasking import PriorityTier, Task, TaskId, TaskKind  # noqa: E402

BOARD_SIZE = 10
V2_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


def make_obs(
    *,
    day=0,
    hour=0,
    money=2000.0,
    farmer=(4, 4),
    hands=None,
    hires_today=0,
    tiles=None,
    farmer_inventory=None,
    hand_inventories=None,
    shed=None,
    seeds=None,
    prices=None,
):
    board = tiles if tiles is not None else [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    opponent_tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    hands = hands or []
    fx, fy = farmer
    me = {
        "money": money,
        "tiles": board,
        "farmer": [fx, fy],
        "hands": [list(h) for h in hands],
        "unlocked_quadrants": ["NW"],
        "hires_today": hires_today,
    }
    opponent = {
        "money": 3000.0,
        "tiles": opponent_tiles,
        "farmer": [fx, fy],
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    inventories = [farmer_inventory or {}] + [inv or {} for inv in (hand_inventories or [{}] * len(hands))]
    return {
        "player": 0,
        "step": day * 24 + hour,
        "day": day,
        "hour": hour,
        "farms": [me, opponent],
        "market": {"inventory": {}, "prices": prices if prices is not None else {}},
        "town": {"unlocked_shops": []},
        "private": {
            "shed": shed or {},
            "seeds": seeds or {},
            "inventories": inventories,
        },
    }


def make_plant_tile(crop, planted_day, watered_today, consecutive_unwatered=0):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "watered_today": watered_today,
        "consecutive_unwatered": consecutive_unwatered,
        "yield_units": 1,
        "max_lifespan_step": -1,
        "fertilized_until_day": -1,
    }


def test_farmer_and_hand_get_distinct_tasks_not_duplicated():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = {"kind": "WEED"}  # at the farmer's position
    tiles[2][2] = {"kind": "WEED"}  # at the hand's position
    obs = make_obs(farmer=(4, 4), hands=[(2, 2)], tiles=tiles)
    action = module.agent(obs, V2_CONFIG)

    assert action["farmer"] == ["DIG"]
    assert len(action["hands"]) == 1
    assert action["hands"][0] == ["DIG"]


def test_hand_action_list_length_matches_hands_list():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(farmer=(4, 4), hands=[(1, 1), (8, 8)], tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    assert len(action["hands"]) == 2


def test_hires_when_service_load_is_overloaded():
    module = load_agent_module("task_teacher_v2")
    # Many unwatered plants -> heavy pending-water obligation, comfortably
    # early in the day (lots of remaining turns to justify hiring), no
    # hands yet, plenty of money.
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for i in range(20):
        x, y = i % BOARD_SIZE, i // BOARD_SIZE  # 20 tiles across rows 0-1
        tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    obs = make_obs(farmer=(4, 4), hands=[], hour=0, money=2000, tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    assert any(order[0] == "HIRE" for order in action["market"])


def test_does_not_hire_when_not_overloaded():
    module = load_agent_module("task_teacher_v2")
    # An all-empty farm is NOT a "nothing to do" scenario -- every empty
    # tile is a PLANT opportunity (25 of them), which genuinely can exceed
    # one farmer's capacity and justify hiring. For a truly empty task
    # list, use a day late enough that no candidate crop can mature (so no
    # PLANT tasks get generated at all -- see economy.can_mature_in_time).
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(farmer=(4, 4), hands=[], hour=0, money=2000, day=29, tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    assert not any(order[0] == "HIRE" for order in action["market"])


def test_does_not_hire_again_when_existing_hand_already_covers_the_load():
    """Regression test for a real, confirmed bug Codex's review found: the
    call site in agent() never passed existing_hands=len(me["hands"]) to
    should_hire(), so every turn evaluated workload as if only the farmer
    existed -- even with an active hand standing by. This is the direct
    cause of the reported 54-122 hire orders/episode and 7-8 simultaneously
    active hands (the estimate_hire_value/should_hire *functions* were
    fixed and unit-tested correctly in isolation; the fix was just never
    wired into the agent that calls them).
    """
    module = load_agent_module("task_teacher_v2")
    # 25 already-growing, unwatered plants (pending_water=25) -> load=31
    # (25 + TRAVEL_ALLOWANCE(4) + END_OF_DAY_RESERVE(2)), remaining_turns
    # =23 (hour=1) -- with the farmer alone (existing_hands=0) this
    # overloads and justifies a hire; with the one hand already hired this
    # day correctly counted (existing_hands=1), its capacity already
    # covers the load and no further hire is justified this turn.
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    obs = make_obs(
        farmer=(4, 4),
        hands=[(1, 1)],
        hour=1,
        hires_today=1,
        money=1_000_000,
        tiles=tiles,
    )
    action = module.agent(obs, V2_CONFIG)
    assert not any(order[0] == "HIRE" for order in action["market"])


# --- end-of-day hiring timing (Codex's 2026-08-02 follow-up review §12.1) --
# Hiring is a market order, resolved after this turn's unit actions, so a
# hand hired at hour H gets its first action at hour H+1. A hire queued on
# the day's last hour therefore recovers zero actions before every hand is
# cleared at the day boundary -- a guaranteed-worthless hire.


def test_never_hires_on_the_last_hour_of_the_day_even_when_heavily_overloaded():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    last_hour = V2_CONFIG["turnsPerDay"] - 1
    obs = make_obs(farmer=(4, 4), hands=[], hour=last_hour, hires_today=0, money=1_000_000, tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    assert not any(order[0] == "HIRE" for order in action["market"])


def test_still_hires_one_hour_before_the_last_hour_when_genuinely_overloaded():
    """Sanity check the fix isn't an overcorrection that kills hiring near
    end of day generally -- one hour earlier, a new hire still gets a real
    (if short) action window and should still be justified under enough
    load."""
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    second_to_last_hour = V2_CONFIG["turnsPerDay"] - 2
    obs = make_obs(
        farmer=(4, 4), hands=[], hour=second_to_last_hour, hires_today=0, money=1_000_000, tiles=tiles
    )
    action = module.agent(obs, V2_CONFIG)
    assert any(order[0] == "HIRE" for order in action["market"])


def test_count_immediately_completing_tasks_counts_only_units_already_on_target():
    """Direct test of the helper backing the second half of Codex's §12.1
    finding: load is counted before this turn's assigned field actions
    resolve, so a task an already-positioned unit is about to complete
    this turn must not also count as still-outstanding demand when sizing
    the hiring decision. A unit still travelling toward its assigned
    task's tile has not resolved anything yet and must not be counted."""
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    tiles[4][4] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    tasks = module.generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=1,
        last_day=29,
        market_prices={},
        candidate_crops=module.CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    task_by_id = {t.task_id: t for t in tasks}
    unit_positions = [(0, 0), (9, 9)]  # unit 0 on-target; unit 1 far from any task
    assignment = module.joint_assign(unit_positions, tasks, {})
    assert (
        module._count_immediately_completing_tasks(unit_positions, assignment, task_by_id, seeds_remaining={})
        == 1
    )


def _plant_task(x, y, crop):
    return Task(
        task_id=TaskId(kind=TaskKind.PLANT, x=x, y=y, item=crop),
        target=(x, y),
        priority_tier=PriorityTier.ECONOMIC,
        deadline_step=None,
        expected_value=1.0,
        action_cost=1,
    )


# --- seed-aware immediate completion (Codex's 2026-08-02 §14.1 finding) ----
# resolve_unit_action() only actually emits PLANT (completing the task) when
# a matching seed is held; otherwise it emits PASS and queues a deferred
# BUY_SEED. _count_immediately_completing_tasks() must mirror that exactly,
# not just check "on target" -- an on-target PLANT with no seed does not
# complete this turn and must not be subtracted from the hiring load.


def test_immediately_completing_excludes_on_target_plant_with_no_seed():
    module = load_agent_module("task_teacher_v2")
    task = _plant_task(0, 0, "WHEAT")
    task_by_id = {task.task_id: task}
    assignment = {0: task.task_id}
    unit_positions = [(0, 0)]
    assert (
        module._count_immediately_completing_tasks(
            unit_positions, assignment, task_by_id, seeds_remaining={"WHEAT": 0}
        )
        == 0
    )


def test_immediately_completing_includes_on_target_plant_with_matching_seed():
    module = load_agent_module("task_teacher_v2")
    task = _plant_task(0, 0, "WHEAT")
    task_by_id = {task.task_id: task}
    assignment = {0: task.task_id}
    unit_positions = [(0, 0)]
    assert (
        module._count_immediately_completing_tasks(
            unit_positions, assignment, task_by_id, seeds_remaining={"WHEAT": 1}
        )
        == 1
    )


def test_immediately_completing_does_not_double_count_a_shared_scarce_seed():
    """Two on-target PLANT assignments for the same crop with only one seed
    held: resolve_unit_action() processes units in order (farmer=0, then
    hands), so only the first actually plants -- the second gets PASS. The
    helper must consume its local seed copy in the same unit order to match,
    contributing 1, not 2."""
    module = load_agent_module("task_teacher_v2")
    task_a = _plant_task(0, 0, "WHEAT")
    task_b = _plant_task(1, 1, "WHEAT")
    task_by_id = {task_a.task_id: task_a, task_b.task_id: task_b}
    assignment = {0: task_a.task_id, 1: task_b.task_id}
    unit_positions = [(0, 0), (1, 1)]
    assert (
        module._count_immediately_completing_tasks(
            unit_positions, assignment, task_by_id, seeds_remaining={"WHEAT": 1}
        )
        == 1
    )


def test_immediately_completing_seed_counts_are_independent_by_crop():
    module = load_agent_module("task_teacher_v2")
    task_wheat = _plant_task(0, 0, "WHEAT")
    task_carrot = _plant_task(1, 1, "CARROT")
    task_by_id = {task_wheat.task_id: task_wheat, task_carrot.task_id: task_carrot}
    assignment = {0: task_wheat.task_id, 1: task_carrot.task_id}
    unit_positions = [(0, 0), (1, 1)]
    assert (
        module._count_immediately_completing_tasks(
            unit_positions, assignment, task_by_id, seeds_remaining={"WHEAT": 1, "CARROT": 0}
        )
        == 1
    )


def test_does_not_hire_when_seedless_plant_would_have_falsely_suppressed_the_hire():
    """Agent-level boundary test: a scenario tuned so that (incorrectly)
    crediting a seedless on-target PLANT as completing would drop the
    computed load just enough to make should_hire's threshold fail --
    while correctly excluding it (no seed held) keeps the load high enough
    to still justify a hire.

    All 25 NW tiles are empty (every task is PLANT, load is a constant 31 =
    25 + TRAVEL_ALLOWANCE(4) + END_OF_DAY_RESERVE(2) regardless of
    composition). The farmer at (0,0) is the obvious top candidate for the
    PLANT task at its own tile (0 distance) and no seed is held for any
    crop, so that task cannot complete this turn. The lone hand at (9,9) is
    assigned a distant PLANT tile it must move toward, contributing no
    immediately-completing task. At hour=8 (future_action_turns=15) with
    one hand already hired today (existing_hands=1, hires_today=1,
    cost=hire_cost(1)=10): existing_capacity=15*2=30, so correctly *not*
    crediting the farmer's seedless PLANT gives overload=31-30=1
    (value=15>10, hires); incorrectly crediting it regardless of seeds
    would give overload=30-30=0 (value=0<=10, no hire).
    """
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]  # all NW tiles empty -> all PLANT
    obs = make_obs(
        farmer=(0, 0),
        hands=[(9, 9)],
        hour=8,
        hires_today=1,
        money=1_000_000,
        tiles=tiles,
        seeds={},
        day=1,
    )
    action = module.agent(obs, V2_CONFIG)
    assert any(order[0] == "HIRE" for order in action["market"])


def test_full_episode_never_hires_on_the_last_hour_of_any_day():
    """`env.steps[i].action` is the decision made from `env.steps[i-1].observation`,
    not from `env.steps[i].observation`'s own hour (kaggle_environments records
    the action that caused the transition *into* step i at index i, one step
    ahead of the observation it was decided from) -- confirmed by direct
    instrumentation of `should_hire`'s real call arguments. Comparing an
    action against the *same* index's observation silently checks the wrong
    hour entirely; must look at the *previous* step's observation instead."""
    module = load_agent_module("task_teacher_v2")
    turns_per_day = V2_CONFIG["turnsPerDay"]
    env = make("kaggriculture", configuration={"episodeSteps": 480, "seed": 4242}, debug=True)
    env.run(["agents/task_teacher_v2/main.py", "starter"])
    for step_index in range(1, len(env.steps)):
        action = env.steps[step_index][0].action
        if not isinstance(action, dict):
            continue
        decided_from_hour = env.steps[step_index - 1][0].observation["hour"]
        if decided_from_hour == turns_per_day - 1:
            assert not any(order[0] == "HIRE" for order in action.get("market", []) or []), (
                f"HIRE order at step {step_index}, decided from hour {decided_from_hour} "
                "(last hour of the day)"
            )


def test_at_most_one_hire_order_per_turn():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if (x, y) != (4, 4):
                tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    obs = make_obs(farmer=(4, 4), hands=[], hour=0, money=100000, tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    hire_orders = [order for order in action["market"] if order[0] == "HIRE"]
    assert len(hire_orders) <= 1


def test_hand_assignments_clear_on_day_boundary():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[2][2] = {"kind": "WEED"}
    obs_day0 = make_obs(farmer=(4, 4), hands=[(2, 2)], day=0, tiles=tiles)
    module.agent(obs_day0, V2_CONFIG)
    assert 1 in module._state.assignments

    # New day: hands vanish in the real game. No hands in this turn's obs.
    obs_day1 = make_obs(farmer=(4, 4), hands=[], day=1, tiles=tiles)
    module.agent(obs_day1, V2_CONFIG)
    assert 1 not in module._state.assignments


def test_simulator_full_episode_two_seats_done_and_finite():
    for agents in (["agents/task_teacher_v2/main.py", "starter"], ["starter", "agents/task_teacher_v2/main.py"]):
        env = make("kaggriculture", configuration={"episodeSteps": 240, "seed": 42}, debug=True)
        env.run(agents)
        final = env.steps[-1]
        assert all(s.status == "DONE" for s in final)
        assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
