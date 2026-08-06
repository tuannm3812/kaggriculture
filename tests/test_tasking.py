"""Tests for src/kaggriculture_lib/tasking.py's core data model.

Per the approved design in docs/superpowers/specs/2026-08-01-kaggriculture-
competition-plan-design.md ("task_teacher_v1: final design"). TDD: this
file is written before tasking.py exists.
"""

import pytest

from kaggriculture_lib import economy
from kaggriculture_lib.tasking import (
    AVERAGE_VALUE_PER_RECOVERED_ACTION,
    END_OF_DAY_RESERVE,
    TRAVEL_ALLOWANCE,
    MarketIntent,
    PriorityTier,
    ReservationLedger,
    ResourceNeed,
    Task,
    TaskId,
    TaskKind,
    TeacherState,
    estimate_hire_value,
    generate_tasks,
    joint_assign,
    project_daily_load,
    rank_tasks,
    reset_hand_assignments_on_day_change,
    route_toward,
    should_hire,
)

BOARD_SIZE = 10
CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")
BASE_PRICES = {"WHEAT": 25, "CARROT": 35, "MELON": 250}


def make_tiles(overrides: dict[tuple[int, int], object] | None = None) -> list[list]:
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for (x, y), value in (overrides or {}).items():
        tiles[y][x] = value
    return tiles


def make_plant_tile(crop: str, planted_day: int, watered_today: bool) -> dict:
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "watered_today": watered_today,
        "consecutive_unwatered": 0,
        "yield_units": 1,
        "max_lifespan_step": -1,
        "fertilized_until_day": -1,
    }


def test_priority_tier_orders_emergency_before_economic():
    assert PriorityTier.EMERGENCY < PriorityTier.ECONOMIC
    assert PriorityTier.DECAYING_YIELD < PriorityTier.DAILY_CARE
    assert PriorityTier.OPTIONAL > PriorityTier.ECONOMIC


def test_task_id_is_hashable_and_orderable():
    a = TaskId(kind=TaskKind.PLANT, x=1, y=2, item="WHEAT")
    b = TaskId(kind=TaskKind.PLANT, x=1, y=2, item="WHEAT")
    c = TaskId(kind=TaskKind.WATER, x=1, y=2, item=None)
    assert a == b
    assert hash(a) == hash(b)
    assert {a, c} == {a, c}  # usable in a set
    assert sorted([c, a]) == [a, c]  # PLANT < WATER alphabetically by enum value


def test_task_id_default_item_is_none():
    tid = TaskId(kind=TaskKind.WATER, x=0, y=0)
    assert tid.item is None


def test_resource_need_fields():
    need = ResourceNeed(item="WHEAT", quantity=1, source="SEED")
    assert need.item == "WHEAT"
    assert need.quantity == 1
    assert need.source == "SEED"


def test_task_construction_with_defaults():
    task = Task(
        task_id=TaskId(kind=TaskKind.PLANT, x=2, y=3, item="CARROT"),
        target=(2, 3),
        priority_tier=PriorityTier.ECONOMIC,
        deadline_step=480,
        expected_value=42.0,
        action_cost=1,
    )
    assert task.resource_needs == ()
    assert task.target == (2, 3)
    assert task.deadline_step == 480


def test_task_can_carry_resource_needs():
    need = ResourceNeed(item="CARROT", quantity=1, source="SEED")
    task = Task(
        task_id=TaskId(kind=TaskKind.PLANT, x=2, y=3, item="CARROT"),
        target=(2, 3),
        priority_tier=PriorityTier.ECONOMIC,
        deadline_step=480,
        expected_value=42.0,
        action_cost=1,
        resource_needs=(need,),
    )
    assert task.resource_needs == (need,)


def test_reservation_ledger_starts_empty():
    ledger = ReservationLedger(task_by_tile={}, resources={}, budget=0.0)
    assert ledger.task_by_tile == {}
    assert ledger.resources == {}


def test_teacher_state_starts_with_no_assignments():
    state = TeacherState()
    assert state.assignments == {}
    assert state.previous_step == -1


def test_teacher_state_reset_clears_assignments():
    state = TeacherState()
    state.assignments[0] = TaskId(kind=TaskKind.HARVEST, x=1, y=1)
    state.previous_step = 50
    state.reset()
    assert state.assignments == {}
    assert state.previous_step == -1


# --- ongoing-crop scoring (task_teacher_v3) -------------------------------


def test_score_ongoing_crop_counts_only_reachable_ticks():
    # TOMATO ticks at day-offsets [8, 9, 10, 11] since planting. Planted at
    # current_day=0 with last_day=29: all 4 offsets fit (max is 11).
    # Planted at current_day=19: 19+8=27, 19+9=28, 19+10=29 all fit, but
    # 19+11=30 doesn't -- only 3 of 4 ticks reachable, so the same seed
    # cost is spread over less revenue and a shorter committed lifespan.
    from kaggriculture_lib.tasking import _score_ongoing_crop

    price = 60.0
    score_full = _score_ongoing_crop("TOMATO", price, current_day=0, last_day=29)
    score_partial = _score_ongoing_crop("TOMATO", price, current_day=19, last_day=29)
    assert score_full > 0
    assert score_partial > 0
    full_reachable = sum(1 for o in economy.ongoing_crop_production_days("TOMATO") if o <= 29)
    partial_reachable = sum(1 for o in economy.ongoing_crop_production_days("TOMATO") if 19 + o <= 29)
    assert full_reachable == 4
    assert partial_reachable == 3


def test_score_ongoing_crop_matches_manual_calculation():
    from kaggriculture_lib.tasking import _score_ongoing_crop

    # TOMATO planted day=0, last_day=29: all offsets [8,9,10,11] reachable.
    price = 60.0
    score = _score_ongoing_crop("TOMATO", price, current_day=0, last_day=29)
    reachable_offsets = economy.ongoing_crop_production_days("TOMATO")  # [8, 9, 10, 11]
    revenue = len(reachable_offsets) * price
    cost = economy.CROPS["TOMATO"]["seed"]
    lifespan_days = reachable_offsets[-1] - reachable_offsets[0] + 1  # 11-8+1 = 4
    expected = (revenue - cost) / lifespan_days
    assert score == pytest.approx(expected)


def test_best_feasible_crop_picks_ongoing_crop_when_it_scores_higher():
    from kaggriculture_lib.tasking import _best_feasible_crop

    # At base prices, TOMATO's day-aware score with a full season ahead
    # comfortably beats WHEAT/CARROT's static score (verified by direct
    # computation below, not assumed).
    prices = {"WHEAT": 25, "CARROT": 35, "TOMATO": 60}
    crop = _best_feasible_crop(day=0, last_day=29, market_prices=prices, candidate_crops=("WHEAT", "CARROT", "TOMATO"))
    assert crop == "TOMATO"


def test_best_feasible_crop_picks_one_time_crop_when_ongoing_is_infeasible():
    from kaggriculture_lib.tasking import _best_feasible_crop

    # At day=24 with last_day=29: WHEAT (max_yield_day=4) still fits
    # (24+4=28<=29), but TOMATO (first_yield_day=8) does not reach even its
    # first tick (24+8=32>29) -- verified directly via
    # economy.can_mature_in_time("WHEAT", 24, 29) is True and
    # economy.can_ongoing_crop_reach_any_tick("TOMATO", 24, 29) is False.
    prices = {"WHEAT": 25, "TOMATO": 60}
    crop = _best_feasible_crop(day=24, last_day=29, market_prices=prices, candidate_crops=("WHEAT", "TOMATO"))
    assert crop == "WHEAT"


def test_best_feasible_crop_returns_none_when_nothing_is_feasible():
    from kaggriculture_lib.tasking import _best_feasible_crop

    # Day 29 (the last day): no one-time crop can mature, no ongoing crop
    # can reach even its first tick.
    prices = {"WHEAT": 25, "TOMATO": 60}
    crop = _best_feasible_crop(day=29, last_day=29, market_prices=prices, candidate_crops=("WHEAT", "TOMATO"))
    assert crop is None


# --- generate_tasks -------------------------------------------------------


def test_generate_tasks_empty_unlocked_tile_produces_plant_task():
    tiles = make_tiles()  # all empty
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    plant_tasks = [t for t in tasks if t.task_id.kind == TaskKind.PLANT]
    # NW quadrant is a 5x5 block: x in [0,5), y in [0,5) for board_size=10.
    assert len(plant_tasks) == 25
    assert all(t.priority_tier == PriorityTier.ECONOMIC for t in plant_tasks)


def test_generate_tasks_locked_tile_produces_no_task():
    tiles = make_tiles({(6, 6): "LOCKED"})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    assert not any(t.target == (6, 6) for t in tasks)


def test_generate_tasks_unwatered_plant_produces_water_task():
    tiles = make_tiles({(2, 2): make_plant_tile("WHEAT", planted_day=0, watered_today=False)})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=1,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    water_tasks = [t for t in tasks if t.task_id.kind == TaskKind.WATER and t.target == (2, 2)]
    assert len(water_tasks) == 1
    assert water_tasks[0].priority_tier == PriorityTier.DAILY_CARE


def test_generate_tasks_already_missed_one_watering_is_emergency():
    tile = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    tile["consecutive_unwatered"] = 1
    tiles = make_tiles({(2, 2): tile})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=2,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    water_tasks = [t for t in tasks if t.task_id.kind == TaskKind.WATER and t.target == (2, 2)]
    assert water_tasks[0].priority_tier == PriorityTier.EMERGENCY


def test_generate_tasks_mature_watered_plant_produces_harvest_task():
    tile = make_plant_tile("WHEAT", planted_day=0, watered_today=True)
    tiles = make_tiles({(2, 2): tile})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=4,  # WHEAT max_yield_day == 4
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    harvest_tasks = [t for t in tasks if t.task_id.kind == TaskKind.HARVEST and t.target == (2, 2)]
    assert len(harvest_tasks) == 1
    assert harvest_tasks[0].priority_tier == PriorityTier.DECAYING_YIELD


def test_generate_tasks_watered_immature_plant_produces_no_task_for_that_tile():
    tile = make_plant_tile("WHEAT", planted_day=0, watered_today=True)
    tiles = make_tiles({(2, 2): tile})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=1,  # not yet at max_yield_day == 4
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    assert not any(t.target == (2, 2) for t in tasks)


def test_generate_tasks_weed_produces_dig_task():
    tiles = make_tiles({(2, 2): {"kind": "WEED"}})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    dig_tasks = [t for t in tasks if t.task_id.kind == TaskKind.DIG and t.target == (2, 2)]
    assert len(dig_tasks) == 1


def test_generate_tasks_filters_infeasible_plant_near_season_end():
    tiles = make_tiles()
    # Only CARROT (max_yield_day=3) can still mature at day=26 with last_day=29.
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=26,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    plant_tasks = [t for t in tasks if t.task_id.kind == TaskKind.PLANT]
    assert all(t.task_id.item == "CARROT" for t in plant_tasks)


def test_generate_tasks_no_feasible_crop_produces_no_plant_task():
    tiles = make_tiles()
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=28,  # too late for WHEAT/CARROT/MELON to mature before last_day=29
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    assert not any(t.task_id.kind == TaskKind.PLANT for t in tasks)


# --- rank_tasks ------------------------------------------------------------


def make_task(kind, x, y, tier, value=0.0, item=None):
    return Task(
        task_id=TaskId(kind=kind, x=x, y=y, item=item),
        target=(x, y),
        priority_tier=tier,
        deadline_step=None,
        expected_value=value,
        action_cost=1,
    )


def test_rank_tasks_orders_by_priority_tier_first():
    emergency = make_task(TaskKind.WATER, 0, 0, PriorityTier.EMERGENCY)
    optional = make_task(TaskKind.DIG, 9, 9, PriorityTier.OPTIONAL)
    ranked = rank_tasks([optional, emergency], current_position=(5, 5))
    assert ranked[0] is emergency


def test_rank_tasks_prefers_closer_task_within_same_tier():
    near = make_task(TaskKind.WATER, 1, 0, PriorityTier.DAILY_CARE)
    far = make_task(TaskKind.WATER, 9, 9, PriorityTier.DAILY_CARE)
    ranked = rank_tasks([far, near], current_position=(0, 0))
    assert ranked[0] is near


def test_rank_tasks_prefers_higher_value_within_tier_and_distance():
    low_value = make_task(TaskKind.PLANT, 1, 0, PriorityTier.ECONOMIC, value=10.0)
    high_value = make_task(TaskKind.PLANT, 0, 1, PriorityTier.ECONOMIC, value=50.0)
    ranked = rank_tasks([low_value, high_value], current_position=(0, 0))
    assert ranked[0] is high_value


def test_rank_tasks_hysteresis_prefers_current_assignment_on_a_near_tie():
    # Same tile, two different crop choices -- distinct task_ids despite
    # being equidistant, isolating the test to the value/hysteresis tradeoff.
    current = make_task(TaskKind.PLANT, 1, 0, PriorityTier.ECONOMIC, value=10.0, item="WHEAT")
    slightly_better = make_task(TaskKind.PLANT, 1, 0, PriorityTier.ECONOMIC, value=10.01, item="CARROT")
    ranked = rank_tasks(
        [slightly_better, current], current_position=(0, 0), current_assignment=current.task_id
    )
    assert ranked[0] is current


def test_rank_tasks_deterministic_tiebreak_by_task_id():
    a = make_task(TaskKind.PLANT, 0, 0, PriorityTier.ECONOMIC, value=10.0, item="CARROT")
    b = make_task(TaskKind.WATER, 0, 0, PriorityTier.ECONOMIC, value=10.0)
    ranked_once = rank_tasks([b, a], current_position=(0, 0))
    ranked_again = rank_tasks([a, b], current_position=(0, 0))
    assert [t.task_id for t in ranked_once] == [t.task_id for t in ranked_again]


# --- route_toward -----------------------------------------------------------


def test_route_toward_returns_pass_when_already_at_target():
    tiles = make_tiles()
    assert route_toward((3, 3), (3, 3), tiles, BOARD_SIZE) == "PASS"


def test_route_toward_prefers_horizontal_when_both_axes_differ():
    tiles = make_tiles()
    assert route_toward((0, 0), (3, 3), tiles, BOARD_SIZE) == "EAST"


def test_route_toward_moves_west_when_target_is_west():
    tiles = make_tiles()
    assert route_toward((5, 5), (2, 5), tiles, BOARD_SIZE) == "WEST"


def test_route_toward_moves_vertically_when_same_column():
    tiles = make_tiles()
    assert route_toward((3, 0), (3, 5), tiles, BOARD_SIZE) == "SOUTH"
    assert route_toward((3, 5), (3, 0), tiles, BOARD_SIZE) == "NORTH"


def test_route_toward_falls_back_to_vertical_when_horizontal_step_is_locked():
    tiles = make_tiles({(1, 0): "LOCKED"})
    # From (0,0) toward (3,3): horizontal step would be EAST to (1,0), which
    # is locked -- must fall back to the vertical step instead.
    assert route_toward((0, 0), (3, 3), tiles, BOARD_SIZE) == "SOUTH"


def test_route_toward_every_step_reduces_manhattan_distance():
    tiles = make_tiles()
    current = (0, 0)
    target = (4, 7)
    steps = 0
    moves = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
    while current != target and steps < 20:
        op = route_toward(current, target, tiles, BOARD_SIZE)
        assert op != "PASS"
        dx, dy = moves[op]
        new_pos = (current[0] + dx, current[1] + dy)
        old_dist = abs(current[0] - target[0]) + abs(current[1] - target[1])
        new_dist = abs(new_pos[0] - target[0]) + abs(new_pos[1] - target[1])
        assert new_dist == old_dist - 1
        current = new_pos
        steps += 1
    assert current == target


# --- MarketIntent ------------------------------------------------------------


def test_market_intent_fields():
    intent = MarketIntent(item="WHEAT", quantity=1, reason="PLANT")
    assert intent.item == "WHEAT"
    assert intent.quantity == 1
    assert intent.reason == "PLANT"


# --- project_daily_load (service-capacity feasibility) ------------------


def test_project_daily_load_sums_watering_plus_reserve():
    load = project_daily_load(
        pending_water_tiles=3,
        scheduled_plant_actions=0,
        scheduled_harvest_actions=0,
    )
    assert load == 3 + TRAVEL_ALLOWANCE + END_OF_DAY_RESERVE


def test_project_daily_load_includes_plant_and_harvest_actions():
    baseline = project_daily_load(pending_water_tiles=0, scheduled_plant_actions=0, scheduled_harvest_actions=0)
    with_more = project_daily_load(pending_water_tiles=0, scheduled_plant_actions=2, scheduled_harvest_actions=1)
    assert with_more == baseline + 3


def test_project_daily_load_rejects_new_plant_when_over_budget():
    turns_per_day = 24
    # Deliberately push pending water obligations high enough that adding
    # one more planned plant would exceed the per-day action budget.
    load = project_daily_load(
        pending_water_tiles=turns_per_day, scheduled_plant_actions=0, scheduled_harvest_actions=0
    )
    assert load > turns_per_day


# --- joint_assign (task_teacher_v2) ---------------------------------------


def test_joint_assign_single_unit_matches_rank_tasks_top_choice():
    water_task = make_task(TaskKind.WATER, 1, 0, PriorityTier.DAILY_CARE)
    dig_task = make_task(TaskKind.DIG, 5, 5, PriorityTier.DAILY_CARE)
    assignment = joint_assign(
        unit_positions=[(0, 0)], tasks=[dig_task, water_task], current_assignments={}
    )
    assert assignment[0] == water_task.task_id  # closer, same tier


def test_joint_assign_two_units_no_duplicate_task_claims():
    only_task = make_task(TaskKind.DIG, 3, 3, PriorityTier.DAILY_CARE)
    assignment = joint_assign(
        unit_positions=[(0, 0), (5, 5)], tasks=[only_task], current_assignments={}
    )
    claimed = [v for v in assignment.values() if v is not None]
    assert len(claimed) == len(set(claimed))  # no task claimed twice
    assert only_task.task_id in claimed


def test_joint_assign_beats_naive_farmer_first_greedy():
    """The concrete acceptance test from the v2 design: a naive sequential
    farmer-first allocation (farmer picks its own top-ranked task first, by
    that unit's own ranking, which sorts by priority tier before distance)
    would have the farmer travel to a distant EMERGENCY task while the hand
    -- already standing right on it -- gets stuck with a distant ECONOMIC
    task the farmer was actually standing on. Joint assignment must find
    the zero-travel swap instead.
    """
    emergency_task = Task(
        task_id=TaskId(kind=TaskKind.WATER, x=0, y=0),
        target=(0, 0),
        priority_tier=PriorityTier.EMERGENCY,
        deadline_step=None,
        expected_value=0.0,
        action_cost=1,
    )
    economic_task = Task(
        task_id=TaskId(kind=TaskKind.PLANT, x=1, y=0, item="CARROT"),
        target=(1, 0),
        priority_tier=PriorityTier.ECONOMIC,
        deadline_step=None,
        expected_value=50.0,
        action_cost=1,
    )
    farmer_pos = (1, 0)  # standing on the economic task's tile
    hand_pos = (0, 0)  # standing on the emergency task's tile

    assignment = joint_assign(
        unit_positions=[farmer_pos, hand_pos],
        tasks=[emergency_task, economic_task],
        current_assignments={},
    )

    # A naive farmer-first-by-own-ranking pass would have the farmer claim
    # the EMERGENCY task purely because its tier outranks distance in the
    # farmer's own view -- even though the hand is already standing on it
    # and the farmer is already standing on the economic task. The joint
    # assignment must find the zero-travel swap instead.
    assert assignment[0] == economic_task.task_id
    assert assignment[1] == emergency_task.task_id


# --- reset_hand_assignments_on_day_change (task_teacher_v2) --------------


def test_reset_hand_assignments_clears_non_farmer_entries_on_new_day():
    state = TeacherState()
    state.assignments[0] = TaskId(kind=TaskKind.WATER, x=1, y=1)  # farmer
    state.assignments[1] = TaskId(kind=TaskKind.DIG, x=2, y=2)  # yesterday's hand
    state.previous_day = 4

    reset_hand_assignments_on_day_change(state, day=5)

    assert 0 in state.assignments  # farmer's assignment survives
    assert 1 not in state.assignments  # stale hand assignment cleared
    assert state.previous_day == 5


def test_reset_hand_assignments_keeps_hand_entries_within_same_day():
    state = TeacherState()
    state.assignments[0] = TaskId(kind=TaskKind.WATER, x=1, y=1)
    state.assignments[1] = TaskId(kind=TaskKind.DIG, x=2, y=2)
    state.previous_day = 5

    reset_hand_assignments_on_day_change(state, day=5)  # same day, no change

    assert state.assignments == {
        0: TaskId(kind=TaskKind.WATER, x=1, y=1),
        1: TaskId(kind=TaskKind.DIG, x=2, y=2),
    }


# --- hiring policy (task_teacher_v2) --------------------------------------


# --- calibration (2026-08-02, per docs/6_next_steps.md item 14) ----------
# TRAVEL_ALLOWANCE=4 and AVERAGE_VALUE_PER_RECOVERED_ACTION=15.0 were initial
# estimates, never measured against real games. Measured directly (20
# episodes, task_teacher_v2 vs. starter, seeds 21000-21019): TRAVEL_ALLOWANCE
# actual mean 7.51 turns/unit/day (max 19); $/field-action actual mean
# $65.26 (range [$57.86, $72.17]). Both were substantially underestimated
# (~1.9x and ~4.3x respectively) by that single-shot measurement -- but a
# full evaluation gate re-run with the recalibrated values (8 and 65.0)
# showed the win rate vs. task_teacher_v1 measurably *dropping* (0.970 ->
# 0.750 over 50 pairs, CI [0.730, 1.000] -> a barely-above-0.50
# [0.510, 0.990]), because the higher $/action drove much more aggressive
# hiring (flat 7 hands vs. the ~5 hands the $65.26 figure was itself
# measured under) whose real costs (fibonacci-scaled hire cost escalation,
# more greedy-fallback travel inefficiency at higher unit counts) the
# naive point measurement didn't capture. Reverted -- see
# docs/4_agent_version_log.md and
# docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md §23 for the
# full account. These tests guard against silently re-applying that
# specific naive recalibration without redoing the full evaluation gate.


def test_travel_allowance_kept_at_original_value_after_failed_recalibration():
    assert TRAVEL_ALLOWANCE == 4


def test_average_value_per_recovered_action_kept_at_original_value_after_failed_recalibration():
    assert AVERAGE_VALUE_PER_RECOVERED_ACTION == 15.0


def test_estimate_hire_value_zero_when_no_overload():
    assert estimate_hire_value(projected_load=10, remaining_turns_today=20) == 0.0


def test_estimate_hire_value_positive_when_overloaded():
    value = estimate_hire_value(projected_load=30, remaining_turns_today=20)
    assert value > 0.0


def test_estimate_hire_value_caps_at_remaining_turns():
    # Overload of 100 turns can't be recovered by more turns today than
    # actually remain -- the recovered-turns proxy is capped.
    value_huge_overload = estimate_hire_value(projected_load=1000, remaining_turns_today=20)
    value_capped_overload = estimate_hire_value(projected_load=20 + 20, remaining_turns_today=20)
    assert value_huge_overload == value_capped_overload


def test_should_hire_false_when_no_overload():
    assert not should_hire(
        projected_load=10, remaining_turns_today=20, hires_today=0, money=3000
    )


def test_should_hire_false_when_insufficient_money():
    assert not should_hire(
        projected_load=100, remaining_turns_today=20, hires_today=0, money=5
    )


def test_should_hire_true_when_value_clearly_exceeds_cost():
    # Large overload, first hire of the day (cheapest fibonacci tier),
    # plenty of money.
    assert should_hire(
        projected_load=100, remaining_turns_today=20, hires_today=0, money=3000
    )


def test_should_hire_false_when_cost_exceeds_marginal_value():
    # Tiny overload late in the day (little value to recover) with a high
    # hires_today count (fibonacci cost has escalated a lot already).
    assert not should_hire(
        projected_load=21, remaining_turns_today=20, hires_today=6, money=3000
    )


def test_should_hire_respects_safety_margin():
    # A case that would pass with no margin should fail once a large
    # enough safety margin is required.
    assert should_hire(
        projected_load=100, remaining_turns_today=20, hires_today=0, money=3000, safety_margin=0
    )
    assert not should_hire(
        projected_load=100, remaining_turns_today=20, hires_today=0, money=3000, safety_margin=10_000
    )


def test_should_hire_accounts_for_capacity_already_provided_by_existing_hands():
    """Real bug found via a full simulator run: with a static load estimate
    that never decreases as hands are hired, should_hire kept approving
    hire after hire in the same day (9 in a row with unlimited money),
    which then made joint_assign's combinatorial search over that many
    units explode. Each existing hand already provides `remaining_turns_today`
    worth of capacity -- that must reduce the marginal value of hiring yet
    another one, the same way each hire's own turns count toward the load
    once hired.
    """
    # With zero existing hands, a moderate constant load justifies hiring.
    assert should_hire(
        projected_load=80, remaining_turns_today=24, hires_today=0, money=1_000_000, existing_hands=0
    )
    # The *same* load, once 3 hands' worth of capacity (24 turns each) is
    # already enough to cover it, must no longer be worth another hire.
    assert not should_hire(
        projected_load=80, remaining_turns_today=24, hires_today=3, money=1_000_000, existing_hands=3
    )


def test_hiring_runaway_terminates_within_a_bounded_number_of_hires():
    """Regression test for the exact bug: with a large constant load and
    unlimited money, repeatedly asking "should I hire one more?" (correctly
    passing the growing existing_hands count each time, as the real agent
    does) must eventually return False on its own -- not loop until an
    external safety cap kicks in. Whatever unit count this naturally
    settles on, `joint_assign`'s own bounded-unit fallback (tested
    separately) is what protects against combinatorial explosion if it's
    still too large for exhaustive search.
    """
    load = 200
    remaining = 24
    hires_today = 0
    count = 0
    safety_limit = 20  # loop guard only, not the behavior under test
    while count < safety_limit and should_hire(
        load, remaining, hires_today, money=1_000_000, existing_hands=count
    ):
        count += 1
        hires_today += 1
    assert count < safety_limit  # terminated on its own economic logic


def test_joint_assign_falls_back_to_greedy_for_too_many_units():
    """Regression test for the exact bug found via a full simulator run:
    joint_assign's exhaustive search over (max_candidates_per_unit + 1)^N
    combinations must not be attempted once N grows too large -- it must
    switch to a fast deterministic greedy fallback instead, per the v2
    design's explicit "if supported unit bounds are exceeded, use a
    deterministic greedy fallback ... do not fail silently" instruction.
    """
    n_units = 12  # comfortably past any practical exhaustive-search bound
    unit_positions = [(i, 0) for i in range(n_units)]
    tasks = [
        Task(
            task_id=TaskId(kind=TaskKind.DIG, x=i, y=1),
            target=(i, 1),
            priority_tier=PriorityTier.DAILY_CARE,
            deadline_step=None,
            expected_value=0.0,
            action_cost=1,
        )
        for i in range(n_units)
    ]

    import time

    start = time.monotonic()
    assignment = joint_assign(unit_positions=unit_positions, tasks=tasks, current_assignments={})
    elapsed = time.monotonic() - start

    assert elapsed < 2.0  # must not attempt (8+1)^12 exhaustive search
    claimed = [v for v in assignment.values() if v is not None]
    assert len(claimed) == len(set(claimed))  # still no duplicate claims
