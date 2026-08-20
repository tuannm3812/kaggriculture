#!/usr/bin/env python3
"""Run paired v18 matches while capturing policy and action diagnostics."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
for import_root in (REPO_ROOT, REPO_ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from kaggle_environments import make  # noqa: E402

from scripts.run_tournament import (  # noqa: E402
    final_rewards,
    hoeffding_ci,
    pairwise_score,
    tournament_configuration,
)


CROP_TYPES = frozenset({"WHEAT", "CARROT", "MELON", "STRAWBERRY"})
ANIMAL_PRODUCT_TYPES = frozenset({"MILK", "WOOL", "EGG", "FERTILIZER"})
_MODULE_SEQUENCE = itertools.count()


def load_fresh_agent_module(agent_path: str | Path, *, game: int, seat: int) -> ModuleType:
    """Load a file-path agent into a unique module instance for one game seat."""
    path = Path(agent_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"agent file does not exist: {path}")
    sequence = next(_MODULE_SEQUENCE)
    module_name = f"_task_teacher_eval_g{game}_s{seat}_{sequence}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load agent module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if not callable(getattr(module, "agent", None)):
        raise TypeError(f"agent module has no callable agent: {path}")
    return module


def _public_turn_snapshot(obs: dict, action: dict) -> dict[str, Any]:
    player = int(obs["player"])
    farm = obs["farms"][player]
    return {
        "action": copy.deepcopy(action),
        "money": float(farm["money"]),
        "hand_count": len(farm["hands"]),
        "market_prices": copy.deepcopy(dict(obs["market"]["prices"])),
    }


def make_diagnostic_wrapper(
    module: ModuleType,
    diagnostics: list[dict],
    *,
    seat: int,
    disable_threat_expansion: bool = False,
) -> Callable[[dict, dict], dict]:
    """Return an action-transparent wrapper that records detached v18 telemetry."""
    get_last_diagnostics = getattr(module, "get_last_diagnostics", None)
    if not callable(get_last_diagnostics):
        raise TypeError("candidate module must define callable get_last_diagnostics")

    def wrapped(obs: dict, config: dict) -> dict:
        agent_config = config
        if disable_threat_expansion:
            agent_config = dict(config or {})
            agent_config["enableThreatExpansion"] = False
        action = module.agent(obs, agent_config)
        copied = copy.deepcopy(get_last_diagnostics(obs["player"]))
        record = {
            **copied,
            "step": int(obs["step"]),
            "player": int(obs["player"]),
            "seat": int(seat),
            **_public_turn_snapshot(obs, action),
        }
        diagnostics.append(record)
        return action

    return wrapped


def _unit_actions(record: dict) -> list:
    action = record.get("action")
    if not isinstance(action, dict):
        return []
    unit_actions = [action.get("farmer")]
    hands = action.get("hands", [])
    if isinstance(hands, list):
        unit_actions.extend(hands)
    return unit_actions


def _is_pass(action: Any) -> bool:
    return isinstance(action, (list, tuple)) and bool(action) and action[0] == "PASS"


def _sale_values(records: list[dict]) -> tuple[dict[str, float], dict[str, float]]:
    crops: Counter[str] = Counter()
    animal_products: Counter[str] = Counter()
    for record in records:
        action = record.get("action")
        prices = record.get("market_prices", {})
        if not isinstance(action, dict) or not isinstance(prices, dict):
            continue
        for order in action.get("market", []):
            if not isinstance(order, (list, tuple)) or len(order) < 3 or order[0] != "SELL":
                continue
            item, quantity = order[1], order[2]
            price = prices.get(item)
            if not isinstance(quantity, (int, float)) or not isinstance(price, (int, float)):
                continue
            value = float(quantity) * float(price)
            if item in CROP_TYPES:
                crops[item] += value
            elif item in ANIMAL_PRODUCT_TYPES:
                animal_products[item] += value
    return dict(sorted(crops.items())), dict(sorted(animal_products.items()))


def aggregate_diagnostics(records: list[dict]) -> dict[str, Any]:
    """Aggregate v18 policy diagnostics and metrics derived from actual actions."""
    transitions = [record for record in records if record.get("threat_changed") is True]
    transition_counts = Counter(
        str(record["threat_level"])
        for record in transitions
        if record.get("threat_level") is not None
    )
    threat_reasons = Counter(
        str(record["threat_reason"])
        for record in transitions
        if record.get("threat_reason") is not None
    )
    land_reasons = Counter(
        str(record["land_reason"])
        for record in records
        if record.get("land_reason") is not None
    )

    cash_values = [
        float(record["money"])
        for record in records
        if isinstance(record.get("money"), (int, float))
    ]
    hand_values = [
        int(record["hand_count"])
        for record in records
        if isinstance(record.get("hand_count"), int)
    ]
    utilizations = [
        float(record["productive_utilization"])
        for record in records
        if isinstance(record.get("productive_utilization"), (int, float))
    ]
    unit_actions = [action for record in records for action in _unit_actions(record)]
    crop_sales, animal_product_sales = _sale_values(records)
    authorized_land_turns = sum(record.get("land_authorized") is True for record in records)
    rejected_land_turns = sum(record.get("land_authorized") is False for record in records)

    minimum_cash_by_seat = {}
    maximum_hands_by_seat = {}
    for seat in sorted({record.get("seat") for record in records if "seat" in record}):
        seat_records = [record for record in records if record.get("seat") == seat]
        seat_cash = [
            float(record["money"])
            for record in seat_records
            if isinstance(record.get("money"), (int, float))
        ]
        seat_hands = [
            int(record["hand_count"])
            for record in seat_records
            if isinstance(record.get("hand_count"), int)
        ]
        if seat_cash:
            minimum_cash_by_seat[str(seat)] = min(seat_cash)
        if seat_hands:
            maximum_hands_by_seat[str(seat)] = max(seat_hands)

    return {
        "animal_product_sale_value_by_type": animal_product_sales,
        "crop_sale_value_by_type": crop_sales,
        "feed_shortage_turns": sum(
            1
            for record in records
            if isinstance(record.get("feed_shortage"), (int, float))
            and record["feed_shortage"] > 0
        ),
        "land_authorization_counts": {
            "authorized": authorized_land_turns,
            "rejected": rejected_land_turns,
        },
        "land_authorized_count": authorized_land_turns,
        "land_reason_counts": dict(sorted(land_reasons.items())),
        "maximum_hands": max(hand_values) if hand_values else None,
        "maximum_hands_by_seat": maximum_hands_by_seat,
        "mean_productive_utilization": (
            sum(utilizations) / len(utilizations) if utilizations else None
        ),
        "minimum_cash": min(cash_values) if cash_values else None,
        "minimum_cash_by_seat": minimum_cash_by_seat,
        "pass_action_rate": (
            sum(_is_pass(action) for action in unit_actions) / len(unit_actions)
            if unit_actions
            else None
        ),
        "threat_reason_counts": dict(sorted(threat_reasons.items())),
        "threat_transition_count": len(transitions),
        "threat_transition_counts": dict(sorted(transition_counts.items())),
        "total_hire_spend": sum(
            float(record.get("hire_cost_reserved", 0.0))
            for record in records
            if isinstance(record.get("hire_cost_reserved", 0.0), (int, float))
        ),
        "turn_count": len(records),
    }


def _agent_reference(ref: str, *, game: int, seat: int) -> str | Callable:
    path = Path(ref).expanduser()
    if path.is_file():
        return load_fresh_agent_module(path, game=game, seat=seat).agent
    return ref


def _play_game(
    candidate: str,
    opponent: str,
    *,
    game_index: int,
    candidate_seat: int,
    episode_steps: int,
    seed: int,
    disable_threat_expansion: bool,
) -> dict[str, Any]:
    config = tournament_configuration(episode_steps=episode_steps, seed=seed)
    candidate_module = load_fresh_agent_module(
        candidate, game=game_index, seat=candidate_seat
    )
    diagnostics: list[dict] = []
    wrapped_candidate = make_diagnostic_wrapper(
        candidate_module,
        diagnostics,
        seat=candidate_seat,
        disable_threat_expansion=disable_threat_expansion,
    )
    opponent_seat = 1 - candidate_seat
    loaded_opponent = _agent_reference(opponent, game=game_index, seat=opponent_seat)
    agents = (
        [wrapped_candidate, loaded_opponent]
        if candidate_seat == 0
        else [loaded_opponent, wrapped_candidate]
    )

    env = make("kaggriculture", configuration=config, debug=False)
    env.run(agents)
    rewards = final_rewards(env)
    candidate_reward = rewards[candidate_seat]
    opponent_reward = rewards[opponent_seat]
    return {
        "candidate_reward": candidate_reward,
        "candidate_seat": candidate_seat,
        "diagnostics": diagnostics,
        "opponent_reward": opponent_reward,
        "rewards": list(rewards),
        "seed": seed,
    }


def evaluate(
    candidate: str,
    opponent: str,
    episodes: int,
    episode_steps: int,
    base_seed: int,
    *,
    disable_threat_expansion: bool = False,
) -> dict[str, Any]:
    """Run paired ladder matches and return a deterministic JSON-ready report."""
    if episodes < 1:
        raise ValueError("episodes must be >= 1")
    if episode_steps < 1:
        raise ValueError("episode_steps must be >= 1")

    seeds = [base_seed + index for index in range(episodes)]
    games = []
    pair_scores = []
    pair_margins = []
    for pair_index, seed in enumerate(seeds):
        pair_games = []
        for candidate_seat in (0, 1):
            game = _play_game(
                candidate,
                opponent,
                game_index=pair_index * 2 + candidate_seat,
                candidate_seat=candidate_seat,
                episode_steps=episode_steps,
                seed=seed,
                disable_threat_expansion=disable_threat_expansion,
            )
            pair_games.append(game)
            games.append(game)
        pair_scores.append(
            sum(
                pairwise_score(game["candidate_reward"], game["opponent_reward"])
                for game in pair_games
            )
            / 2.0
        )
        pair_margins.append(
            sum(game["candidate_reward"] - game["opponent_reward"] for game in pair_games)
            / 2.0
        )

    all_records = [record for game in games for record in game["diagnostics"]]
    aggregate = aggregate_diagnostics(all_records)
    aggregate.update(
        {
            "hoeffding_95_ci": list(hoeffding_ci(pair_scores)),
            "mean_money_margin": sum(pair_margins) / len(pair_margins),
            "win_rate": sum(pair_scores) / len(pair_scores),
        }
    )
    return {
        "aggregate": aggregate,
        "candidate": candidate,
        "candidate_config": {
            "enableThreatExpansion": not disable_threat_expansion,
        },
        "config": tournament_configuration(episode_steps=episode_steps),
        "episodes": episodes,
        "games": games,
        "opponent": opponent,
        "seeds": seeds,
    }


def write_json(report: dict, output_path: str | Path) -> None:
    """Write stable, human-readable JSON with lexicographically sorted keys."""
    Path(output_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", help="File path to the v18 candidate")
    parser.add_argument("opponent", help="File path or built-in opponent name")
    parser.add_argument("--episodes", type=int, default=10, help="Paired seeds (default: 10)")
    parser.add_argument(
        "--episode-steps", type=int, default=720, help="Steps per game (default: 720)"
    )
    parser.add_argument("--seed", type=int, default=0, help="First paired seed (default: 0)")
    parser.add_argument(
        "--disable-threat-expansion",
        action="store_true",
        help="Pass enableThreatExpansion=False only to the candidate agent",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="Destination for the deterministic JSON report",
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    report = evaluate(
        candidate=args.candidate,
        opponent=args.opponent,
        episodes=args.episodes,
        episode_steps=args.episode_steps,
        base_seed=args.seed,
        disable_threat_expansion=args.disable_threat_expansion,
    )
    write_json(report, args.output_json)
    return report


if __name__ == "__main__":
    main()
