"""Tests for the v18 paired diagnostic evaluation harness."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "evaluate_task_teacher_v18.py"

spec = importlib.util.spec_from_file_location("evaluate_task_teacher_v18", SCRIPT)
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


def test_fresh_loader_isolates_module_globals_per_game_and_seat(tmp_path):
    agent_path = tmp_path / "stateful_agent.py"
    agent_path.write_text(
        "calls = 0\n"
        "def agent(obs, config):\n"
        "    global calls\n"
        "    calls += 1\n"
        "    return calls\n"
    )

    first = evaluate.load_fresh_agent_module(agent_path, game=0, seat=0)
    second = evaluate.load_fresh_agent_module(agent_path, game=1, seat=1)

    assert first is not second
    assert first.agent({}, {}) == 1
    assert first.agent({}, {}) == 2
    assert second.agent({}, {}) == 1


def test_diagnostic_wrapper_returns_identical_action_and_copies_diagnostics():
    action = {"farmer": ["PASS"], "hands": [["WATER"]], "market": []}
    latest = {"threat_level": "BUILDING", "nested": {"value": 1}}

    def agent(obs, config):
        return action

    module = SimpleNamespace(
        agent=agent,
        get_last_diagnostics=lambda player: latest,
    )
    records = []
    wrapped = evaluate.make_diagnostic_wrapper(module, records, seat=1)
    obs = {
        "step": 7,
        "player": 1,
        "farms": [{}, {"money": 1234.0, "hands": [[0, 0]]}],
        "market": {"prices": {"WHEAT": 9.0}},
    }

    returned = wrapped(obs, {"episodeSteps": 96})
    latest["nested"]["value"] = 99

    assert returned is action
    assert records[0]["step"] == 7
    assert records[0]["player"] == 1
    assert records[0]["seat"] == 1
    assert records[0]["threat_level"] == "BUILDING"
    assert records[0]["nested"] == {"value": 1}
    assert records[0]["action"] == action
    assert records[0]["action"] is not action
    assert records[0]["money"] == 1234.0
    assert records[0]["hand_count"] == 1
    assert records[0]["market_prices"] == {"WHEAT": 9.0}


def test_diagnostic_wrapper_ablation_changes_only_agent_config():
    seen_configs = []
    module = SimpleNamespace(
        agent=lambda obs, config: seen_configs.append(config) or {
            "farmer": ["PASS"],
            "hands": [],
            "market": [],
        },
        get_last_diagnostics=lambda player: {},
    )
    records = []
    wrapped = evaluate.make_diagnostic_wrapper(
        module, records, seat=0, disable_threat_expansion=True
    )
    environment_config = {"episodeSteps": 96, "seed": 4}
    obs = {
        "step": 0,
        "player": 0,
        "farms": [{"money": 3000.0, "hands": []}, {}],
        "market": {"prices": {}},
    }

    wrapped(obs, environment_config)

    assert seen_configs == [
        {"episodeSteps": 96, "seed": 4, "enableThreatExpansion": False}
    ]
    assert environment_config == {"episodeSteps": 96, "seed": 4}


def test_aggregate_diagnostics_counts_policy_and_action_metrics():
    records = [
        {
            "step": 0,
            "player": 0,
            "seat": 0,
            "threat_level": "COMPACT",
            "threat_changed": False,
            "threat_reason": "compact",
            "land_authorized": False,
            "land_reason": "third_land_threat_not_compounding",
            "money": 1000.0,
            "hand_count": 2,
            "productive_utilization": 0.5,
            "feed_shortage": 0,
            "hire_cost_reserved": 20.0,
            "market_prices": {"WHEAT": 5.0, "MILK": 7.0},
            "action": {
                "farmer": ["PASS"],
                "hands": [["WATER"], ["PASS"]],
                "market": [["SELL", "WHEAT", 3], ["SELL", "MILK", 2]],
            },
        },
        {
            "step": 1,
            "player": 0,
            "seat": 0,
            "threat_level": "BUILDING",
            "threat_changed": True,
            "threat_reason": "extra_quadrant",
            "land_authorized": True,
            "land_reason": "third_land_compounding",
            "money": 800.0,
            "hand_count": 3,
            "productive_utilization": 0.75,
            "feed_shortage": 2,
            "hire_cost_reserved": 30.0,
            "market_prices": {"STRAWBERRY": 10.0, "EGG": 3.0},
            "action": {
                "farmer": ["DIG"],
                "hands": [["PASS"], ["CARE"]],
                "market": [
                    ["SELL", "STRAWBERRY", 2],
                    ["SELL", "EGG", 4],
                ],
            },
        },
    ]

    aggregate = evaluate.aggregate_diagnostics(records)

    assert aggregate["threat_transition_count"] == 1
    assert aggregate["threat_transition_counts"] == {"BUILDING": 1}
    assert aggregate["threat_reason_counts"] == {"extra_quadrant": 1}
    assert aggregate["land_authorized_count"] == 1
    assert aggregate["land_authorization_counts"] == {"authorized": 1, "rejected": 1}
    assert aggregate["land_reason_counts"] == {
        "third_land_compounding": 1,
        "third_land_threat_not_compounding": 1,
    }
    assert aggregate["minimum_cash"] == 800.0
    assert aggregate["maximum_hands"] == 3
    assert aggregate["mean_productive_utilization"] == 0.625
    assert aggregate["pass_action_rate"] == 0.5
    assert aggregate["feed_shortage_turns"] == 1
    assert aggregate["total_hire_spend"] == 50.0
    assert aggregate["crop_sale_value_by_type"] == {
        "STRAWBERRY": 20.0,
        "WHEAT": 15.0,
    }
    assert aggregate["animal_product_sale_value_by_type"] == {
        "EGG": 12.0,
        "MILK": 14.0,
    }


def test_cli_parser_accepts_the_documented_flags():
    args = evaluate.build_parser().parse_args(
        [
            "candidate.py",
            "opponent.py",
            "--episodes",
            "2",
            "--episode-steps",
            "96",
            "--seed",
            "11",
            "--disable-threat-expansion",
            "--output-json",
            "result.json",
        ]
    )

    assert args.candidate == "candidate.py"
    assert args.opponent == "opponent.py"
    assert args.episodes == 2
    assert args.episode_steps == 96
    assert args.seed == 11
    assert args.disable_threat_expansion is True
    assert args.output_json == Path("result.json")


def test_two_pair_real_smoke_uses_tracked_v18_fixture_and_checks_both_seats(tmp_path):
    """Keep the real smoke runnable from a clean checkout.

    The 96-step horizon makes adaptive land time-ineligible, so committed v18
    is a suitable real opponent fixture here. Task 4 separately proves that
    disabled v18 is action-identical to v16; this test owns harness integration,
    both-seat coverage, diagnostics, and action-schema validation.
    """
    tracked_v18 = str(REPO_ROOT / "agents" / "task_teacher_v18" / "main.py")
    report = evaluate.evaluate(
        candidate=tracked_v18,
        opponent=tracked_v18,
        episodes=2,
        episode_steps=96,
        base_seed=31,
    )
    output = tmp_path / "report.json"
    evaluate.write_json(report, output)
    output_text = output.read_text()
    parsed = json.loads(output_text)

    assert output_text == json.dumps(parsed, indent=2, sort_keys=True) + "\n"
    assert len(parsed["games"]) == 4
    assert all(len(game["rewards"]) == 2 for game in parsed["games"])
    assert {game["candidate_seat"] for game in parsed["games"]} == {0, 1}
    assert parsed["seeds"] == [31, 32]
    assert parsed["config"]["episodeSteps"] == 96
    assert parsed["config"]["startingMoney"] == 3000
    assert set(parsed["aggregate"]) >= {
        "win_rate",
        "mean_money_margin",
        "hoeffding_95_ci",
        "minimum_cash",
        "maximum_hands",
        "pass_action_rate",
    }
    diagnostics = [record for game in parsed["games"] for record in game["diagnostics"]]
    assert diagnostics
    assert {record["seat"] for record in diagnostics} == {0, 1}
    assert all(set(record["action"]) == {"farmer", "hands", "market"} for record in diagnostics)
