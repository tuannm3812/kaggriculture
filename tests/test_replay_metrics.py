from dataclasses import replace
import math
import sys

import pytest

from kaggriculture_lib.replay_metrics import (
    compare_sources,
    extract_turn_metrics,
    summarize_episode,
)
from kaggriculture_lib.replay_schema import ActionOrigin, DecisionRecord, NormalizedAction


def _tile_grid(*tiles):
    return [list(tiles)]


def _observation(
    *,
    money=100.0,
    opponent_money=80.0,
    hands=(),
    unlocked=("NW",),
    tiles=(),
    opponent_tiles=(),
    shed=None,
    inventories=None,
    prices=None,
    market_inventory=None,
    capacity=100,
):
    return {
        "player": 0,
        "day": 0,
        "hour": 0,
        "farms": [
            {
                "money": money,
                "hands": [list(position) for position in hands],
                "unlocked_quadrants": list(unlocked),
                "tiles": _tile_grid(*tiles),
            },
            {
                "money": opponent_money,
                "hands": [[1, 1]],
                "unlocked_quadrants": ["NW", "NE"],
                "tiles": _tile_grid(*opponent_tiles),
            },
        ],
        "market": {
            "prices": prices or {"MILK": 11, "WHEAT": 25},
            "inventory": market_inventory or {"MILK": 9_990, "WHEAT": 10_010},
        },
        "private": {
            "shed": shed or {},
            "inventories": inventories if inventories is not None else [{}],
        },
        "shedCapacity": capacity,
    }


def _record(
    step,
    *,
    observation=None,
    farmer=("PASS",),
    hands=(),
    market=(),
    source_policy_id="owner/policy",
    source_family="family-a",
    seat=0,
    opponent_family="starter",
    terminal=False,
    result="win",
    final_banks=(200.0, 150.0),
):
    return DecisionRecord(
        episode_id="episode-1",
        source_policy_id=source_policy_id,
        source_family=source_family,
        step=step,
        day=step // 24,
        hour=step % 24,
        seat=seat,
        opponent_family=opponent_family,
        environment_version="1.32.4",
        configuration={"seed": 31, "shedCapacity": 100},
        observation=observation or _observation(),
        action=NormalizedAction(farmer, hands, market),
        action_origin=ActionOrigin.PUBLIC_ORIGINAL,
        original_action=None,
        repair_reason=None,
        terminal_result=result if terminal else None,
        final_banks=final_banks if terminal else None,
        compatibility_ok=True,
        legality_ok=True,
        completeness_ok=True,
        duplicate=False,
    )


def test_terminal_stranded_value_counts_carried_and_shed_products():
    record = _record(
        0,
        terminal=True,
        observation=_observation(
            shed={"MILK": 7},
            inventories=[{"MILK": 1}, {"EGG": 2}],
        ),
    )

    metrics = extract_turn_metrics(record, next_observation=None)

    assert metrics.shed_units == 7
    assert metrics.carried_units == 3
    assert metrics.terminal_stranded_units == 10


def test_incomplete_terminal_stranding_is_missing_not_observed_zero():
    incomplete = summarize_episode(
        [
            extract_turn_metrics(
                _record(
                    0,
                    observation=_observation(
                        shed={"MILK": 4},
                        inventories=[{"EGG": 2}],
                    ),
                ),
                None,
            )
        ]
    )
    observed_zero = summarize_episode(
        [
            extract_turn_metrics(
                replace(_record(0, terminal=True), episode_id="episode-2"),
                None,
            )
        ]
    )

    assert incomplete.terminal_stranded_units is None
    assert observed_zero.terminal_stranded_units == 0.0

    comparison = compare_sources([incomplete, observed_zero])[0]
    assert comparison["mean_terminal_stranded_units"] == 0.0
    assert comparison["terminal_stranding_observed_episode_count"] == 1
    assert comparison["terminal_stranding_coverage"] == 0.5


def test_worker_allocation_separates_productive_travel_logistics_and_idle():
    records = [
        _record(
            0,
            farmer=("PLANT", "WHEAT"),
            hands=(("EAST",), ("PICKUP", "MILK", 1)),
        ),
        _record(
            1,
            farmer=("HARVEST",),
            hands=(("PLACE", "GOOSE"), ("PASS",)),
        ),
    ]

    summary = summarize_episode([extract_turn_metrics(record, None) for record in records])

    assert summary.productive_actions == 2
    assert summary.travel_actions == 1
    assert summary.logistics_actions == 2
    assert summary.idle_actions == 1
    assert summary.other_actions == 0
    assert summary.productive_action_share == pytest.approx(2 / 6)


def test_sell_proceeds_use_observed_bank_delta_not_spot_times_quantity():
    sale_record = _record(
        0,
        observation=_observation(money=100.0, prices={"MILK": 11}),
        market=(("SELL", "MILK", 4),),
    )
    next_observation = _observation(money=137.0)

    metrics = extract_turn_metrics(sale_record, next_observation)

    assert metrics.observed_bank_delta == 37.0
    assert metrics.realized_bank_delta == 37.0
    assert metrics.realized_bank_delta != 4 * sale_record.observation["market"]["prices"]["MILK"]


def test_episode_sell_delta_is_missing_when_any_positive_sale_lacks_a_successor():
    rows = [
        extract_turn_metrics(
            _record(
                0,
                observation=_observation(money=100.0),
                market=(("SELL", "MILK", 1),),
            ),
            _observation(money=110.0),
        ),
        extract_turn_metrics(
            _record(
                1,
                terminal=True,
                observation=_observation(money=110.0),
                market=(("SELL", "EGG", 1),),
            ),
            None,
        ),
    ]

    summary = summarize_episode(rows)

    assert summary.sell_turn_count == 2
    assert summary.observed_sell_bank_delta_turn_count == 1
    assert summary.observed_bank_delta_on_sell_turns is None


def test_turn_metrics_extract_state_market_actions_and_visible_opponent_assets():
    plant = {"kind": "PLANT", "crop": "CARROT"}
    cow = {"kind": "PASTURE", "animal": "COW"}
    opponent_plant = {"kind": "PLANT", "crop": "MELON"}
    opponent_goose = {"kind": "COOP", "animal": "GOOSE"}
    record = _record(
        25,
        observation=_observation(
            money=123.0,
            hands=((2, 3), (3, 3)),
            unlocked=("NW", "NE"),
            tiles=(plant, cow, None),
            opponent_tiles=(opponent_plant, opponent_goose),
            shed={"WHEAT": 9},
            inventories=[{"MILK": 2}],
            prices={"MILK": 160},
            market_inventory={"MILK": 10_002},
        ),
        farmer=("NORTH",),
        hands=(("WATER",), ("PASS",)),
        market=(("SELL", "MILK", 2), ("HIRE",), ("BUY_LAND",)),
    )

    metrics = extract_turn_metrics(record, _observation(money=110.0))

    assert (metrics.day, metrics.hour, metrics.money) == (1, 1, 123.0)
    assert metrics.unlocked_quadrants == ("NW", "NE")
    assert metrics.active_hands == 2
    assert metrics.crop_counts == {"CARROT": 1}
    assert metrics.animal_counts == {"COW": 1}
    assert metrics.movement_steps == 1
    assert metrics.market_order_count == 3
    assert metrics.market_order_counts == {"BUY_LAND": 1, "HIRE": 1, "SELL": 1}
    assert metrics.sell_quantity_by_product == {"MILK": 2}
    assert metrics.current_prices == {"MILK": 160.0}
    assert metrics.current_market_inventory == {"MILK": 10002.0}
    assert metrics.visible_opponent_money == 80.0
    assert metrics.visible_opponent_land_count == 2
    assert metrics.visible_opponent_active_hands == 1
    assert metrics.visible_opponent_crop_counts == {"MELON": 1}
    assert metrics.visible_opponent_animal_counts == {"GOOSE": 1}


def test_episode_summary_aggregates_expansion_sales_exposure_storage_and_terminal():
    rows = [
        extract_turn_metrics(
            _record(
                0,
                observation=_observation(
                    money=100.0,
                    tiles=({"kind": "PLANT", "crop": "WHEAT"},),
                    shed={"WHEAT": 95},
                ),
                market=(("BUY_LAND",), ("HIRE",)),
            ),
            _observation(money=40.0),
        ),
        extract_turn_metrics(
            _record(
                1,
                observation=_observation(
                    money=40.0,
                    unlocked=("NW", "NE"),
                    hands=((1, 1),),
                    tiles=({"kind": "PLANT", "crop": "WHEAT"}, {"kind": "COOP", "animal": "GOOSE"}),
                ),
                market=(("SELL", "WHEAT", 3),),
            ),
            _observation(money=110.0),
        ),
        extract_turn_metrics(
            _record(
                2,
                terminal=True,
                observation=_observation(
                    money=110.0,
                    unlocked=("NW", "NE"),
                    shed={"EGG": 4},
                    inventories=[{"MILK": 2}],
                    tiles=({"kind": "PLANT", "crop": "CARROT"}, {"kind": "COOP", "animal": "GOOSE"}),
                ),
                market=(("SELL", "EGG", 1),),
                final_banks=(200.0, 150.0),
            ),
            _observation(money=200.0),
        ),
    ]

    summary = summarize_episode(rows)

    assert summary.land_opening_day == 0
    assert summary.land_purchase_count == 1
    assert summary.hand_peak == 1
    assert summary.hand_range == (0, 1)
    assert summary.hire_orders == 1
    assert summary.crop_exposure_by_day == {0: {"CARROT": 1 / 3, "WHEAT": 2 / 3}}
    assert summary.animal_exposure_by_day == {0: {"GOOSE": 2 / 3}}
    assert summary.sell_quantity == 4
    assert summary.sell_quantity_by_product == {"EGG": 1, "WHEAT": 3}
    assert summary.sell_concentration_by_product == {"EGG": 0.25, "WHEAT": 0.75}
    assert summary.observed_bank_delta_on_sell_turns == 160.0
    assert summary.storage_pressure_turns == 1
    assert summary.terminal_stranded_units == 6
    assert summary.final_bank == 200.0
    assert summary.status == "complete"
    assert summary.result == "win"
    assert summary.bank_recovery_turns_after_purchase == (2, 2)


def test_final_window_cash_changes_require_a_complete_window():
    rows = []
    for step in range(48):
        terminal = step == 47
        rows.append(
            extract_turn_metrics(
                _record(
                    step,
                    terminal=terminal,
                    observation=_observation(money=float(step)),
                    final_banks=(48.0, 0.0),
                ),
                _observation(money=float(step + 1)),
            )
        )

    summary = summarize_episode(rows)

    assert summary.final_window_cash_changes == {8: 8.0, 22: 22.0, 48: 48.0}
    short_summary = summarize_episode(rows[-8:])
    assert short_summary.final_window_cash_changes == {8: 8.0, 22: None, 48: None}


def test_empty_episode_is_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        summarize_episode([])


def test_non_contiguous_steps_are_rejected():
    rows = [
        extract_turn_metrics(_record(0), None),
        extract_turn_metrics(_record(2), None),
    ]

    with pytest.raises(ValueError, match="contiguous"):
        summarize_episode(rows)


def test_missing_next_observation_keeps_observed_bank_change_unknown():
    metrics = extract_turn_metrics(_record(0), None)

    assert metrics.observed_next_bank is None
    assert metrics.observed_bank_delta is None


def test_partial_inventories_are_counted_without_requiring_every_product():
    record = _record(
        0,
        observation=_observation(
            shed={"WHEAT": 2},
            inventories=[{}, {"MILK": 3}, None],
        ),
    )

    metrics = extract_turn_metrics(record, None)

    assert metrics.shed_units == 2
    assert metrics.carried_units == 3


def test_unknown_unit_and_market_actions_are_counted_as_other():
    record = _record(
        0,
        farmer=("DANCE",),
        hands=(("PASS",),),
        market=(("BARTER", "MILK", 1),),
    )

    metrics = extract_turn_metrics(record, None)

    assert metrics.other_actions == 1
    assert metrics.idle_actions == 1
    assert metrics.market_order_counts == {"other": 1}


@pytest.mark.parametrize("location", ["current", "next"])
def test_non_finite_bank_values_are_rejected(location):
    record = _record(0)
    if location == "current":
        record.observation["farms"][0]["money"] = math.inf
        next_observation = None
    else:
        next_observation = _observation(money=math.nan)

    with pytest.raises(ValueError, match="bank must be finite"):
        extract_turn_metrics(record, next_observation)


def test_compare_sources_groups_families_deterministically_and_weights_action_shares():
    family_b = summarize_episode(
        [
            extract_turn_metrics(
                _record(
                    0,
                    source_policy_id="owner/b",
                    source_family="family-b",
                    terminal=True,
                    farmer=("PASS",),
                ),
                None,
            )
        ]
    )
    family_a_1 = summarize_episode(
        [
            extract_turn_metrics(
                _record(
                    0,
                    source_policy_id="owner/a1",
                    terminal=True,
                    farmer=("WATER",),
                ),
                None,
            )
        ]
    )
    family_a_2 = summarize_episode(
        [
            extract_turn_metrics(
                replace(
                    _record(0, source_policy_id="owner/a2", farmer=("EAST",)),
                    episode_id="episode-2",
                    terminal_result="loss",
                    final_banks=(50.0, 100.0),
                ),
                None,
            )
        ]
    )

    comparison = compare_sources([family_b, family_a_2, family_a_1])

    assert [row["source_family"] for row in comparison] == ["family-a", "family-b"]
    assert comparison[0]["episode_count"] == 2
    assert comparison[0]["source_policy_count"] == 2
    assert comparison[0]["productive_action_share"] == 0.5
    assert comparison[0]["travel_action_share"] == 0.5
    assert comparison[0]["mean_final_bank"] == 125.0
    assert comparison[0]["win_count"] == 1
    assert comparison[0]["loss_count"] == 1


def test_compare_sources_handles_no_summaries():
    assert compare_sources([]) == []


def test_compare_sources_preserves_missing_observed_sell_deltas():
    summary = summarize_episode(
        [
            extract_turn_metrics(
                _record(0, terminal=True, market=(("SELL", "MILK", 1),)),
                None,
            )
        ]
    )

    assert compare_sources([summary])[0]["observed_bank_delta_on_sell_turns"] is None


def test_compare_sources_distinguishes_no_sales_from_missing_sell_delta_evidence():
    no_sale = summarize_episode(
        [extract_turn_metrics(_record(0, terminal=True), None)]
    )
    missing_sale = summarize_episode(
        [
            extract_turn_metrics(
                replace(
                    _record(0, terminal=True, market=(("SELL", "MILK", 1),)),
                    episode_id="episode-2",
                ),
                None,
            )
        ]
    )

    comparison = compare_sources([no_sale, missing_sale])[0]

    assert no_sale.observed_bank_delta_on_sell_turns == 0.0
    assert missing_sale.observed_bank_delta_on_sell_turns is None
    assert comparison["no_sale_episode_count"] == 1
    assert comparison["missing_sell_bank_delta_episode_count"] == 1
    assert comparison["sell_episode_count"] == 1
    assert comparison["sell_bank_delta_coverage"] == 0.0
    assert comparison["observed_bank_delta_on_sell_turns"] is None


def test_compare_sources_rejects_non_finite_derived_bank_delta_sum():
    summaries = []
    for episode_id in ("episode-1", "episode-2"):
        summaries.append(
            summarize_episode(
                [
                    extract_turn_metrics(
                        replace(
                            _record(
                                0,
                                terminal=True,
                                observation=_observation(money=0.0),
                                market=(("SELL", "MILK", 1),),
                            ),
                            episode_id=episode_id,
                        ),
                        _observation(money=sys.float_info.max),
                    )
                ]
            )
        )

    with pytest.raises(ValueError, match="source aggregate must be finite"):
        compare_sources(summaries)
