"""Pinned-runtime validation for normalized Kaggriculture action tapes."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import inspect
import json
from math import isfinite
from typing import Any, Callable, Mapping

import kaggle_environments

if kaggle_environments.__version__ != "1.32.4":
    raise RuntimeError(
        "compatibility evaluation requires kaggle-environments==1.32.4; "
        f"found {kaggle_environments.__version__}"
    )

from kaggle_environments import make

from kaggriculture_lib.replay_schema import NormalizedAction, normalize_action


PINNED_ENVIRONMENT_VERSION = "1.32.4"
EXPECTED_ACTION_CALLS = 719
MAX_MARKET_ORDERS = 10


@dataclass(frozen=True)
class CompatibilityIssue:
    """One stable, machine-readable action compatibility finding."""

    code: str
    message: str
    step: int | None = None
    location: str | None = None


@dataclass(frozen=True)
class CompatibilityReport:
    """Outcome of executing one policy seat on the pinned runtime."""

    environment_version: str
    seed: int
    seat: int
    opponent: str
    status: str
    action_calls: int
    exception: str | None
    issues: tuple[CompatibilityIssue, ...]
    final_banks: tuple[float, float] | None
    state_rewards: tuple[float | None, float | None] | None
    score: float | None
    action_sha256: str

    @property
    def eligible(self) -> bool:
        """Whether this execution is safe for the primary replay corpus."""
        return (
            self.environment_version == PINNED_ENVIRONMENT_VERSION
            and self.status == "DONE"
            and self.action_calls == EXPECTED_ACTION_CALLS
            and self.exception is None
            and not self.issues
        )


_UNIT_ARITIES: dict[str, frozenset[int]] = {
    "NORTH": frozenset({1}),
    "SOUTH": frozenset({1}),
    "EAST": frozenset({1}),
    "WEST": frozenset({1}),
    "PASS": frozenset({1}),
    "PICKUP": frozenset({2, 3}),
    "PLANT": frozenset({2}),
    "WATER": frozenset({1}),
    "HARVEST": frozenset({1}),
    "FERTILIZE": frozenset({1}),
    "BUILD_COOP": frozenset({1}),
    "BUILD_PASTURE": frozenset({1}),
    "DIG": frozenset({1}),
    "PLACE": frozenset({2, 3}),
    "FEED": frozenset({1}),
    "COLLECT_FERTILIZER": frozenset({1}),
    "CARE": frozenset({1}),
}

_MARKET_ARITIES: dict[str, frozenset[int]] = {
    "BUY_SEED": frozenset({3}),
    "BUY_PRODUCT": frozenset({3}),
    "BUY_ANIMAL": frozenset({3}),
    "SELL": frozenset({3}),
    "HIRE": frozenset({1}),
    "BUY_LAND": frozenset({1}),
}

_QUANTITY_INDEX = {
    "PICKUP": 2,
    "PLACE": 2,
    "BUY_SEED": 2,
    "BUY_PRODUCT": 2,
    "BUY_ANIMAL": 2,
    "SELL": 2,
}


def _issue(code: str, message: str, location: str) -> CompatibilityIssue:
    return CompatibilityIssue(code=code, message=message, location=location)


def _validate_command(
    command: Any,
    arities: Mapping[str, frozenset[int]],
    location: str,
) -> list[CompatibilityIssue]:
    if not isinstance(command, (list, tuple)):
        return [_issue("invalid_action_container", "action command must be a list or tuple", location)]
    if not command:
        return [_issue("operation_arity", "action command must contain an operation", location)]

    op = command[0]
    if not isinstance(op, str) or op not in arities:
        return [_issue("unknown_operation", f"unknown operation: {op!r}", location)]

    issues: list[CompatibilityIssue] = []
    if len(command) not in arities[op]:
        allowed = ", ".join(str(value) for value in sorted(arities[op]))
        issues.append(
            _issue(
                "operation_arity",
                f"{op} expects command length {allowed}; found {len(command)}",
                location,
            )
        )

    quantity_index = _QUANTITY_INDEX.get(op)
    if quantity_index is not None and len(command) > quantity_index:
        quantity = command[quantity_index]
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            issues.append(
                _issue(
                    "invalid_quantity",
                    f"{op} quantity must be a positive integer",
                    f"{location}[{quantity_index}]",
                )
            )

    for index, value in enumerate(command[1:], start=1):
        if isinstance(value, float) and not isfinite(value):
            issues.append(
                _issue(
                    "non_finite_number",
                    "action values must be finite",
                    f"{location}[{index}]",
                )
            )
    return issues


def validate_action_shape(
    action: NormalizedAction,
    expected_hands: int,
) -> tuple[CompatibilityIssue, ...]:
    """Report pinned-runtime shape problems without changing *action*."""
    if isinstance(expected_hands, bool) or not isinstance(expected_hands, int) or expected_hands < 0:
        raise ValueError("expected_hands must be a non-negative integer")

    issues: list[CompatibilityIssue] = []
    farmer = getattr(action, "farmer", None)
    hands = getattr(action, "hands", None)
    market = getattr(action, "market", None)

    if not isinstance(farmer, (list, tuple)):
        issues.append(_issue("invalid_farmer_container", "farmer must be a list or tuple", "farmer"))
    else:
        issues.extend(_validate_command(farmer, _UNIT_ARITIES, "farmer"))

    if not isinstance(hands, (list, tuple)):
        issues.append(_issue("invalid_hands_container", "hands must be a list or tuple", "hands"))
    else:
        if len(hands) != expected_hands:
            issues.append(
                _issue(
                    "hand_count_mismatch",
                    f"expected {expected_hands} hand actions; found {len(hands)}",
                    "hands",
                )
            )
        for index, command in enumerate(hands):
            issues.extend(_validate_command(command, _UNIT_ARITIES, f"hands[{index}]"))

    if not isinstance(market, (list, tuple)):
        issues.append(_issue("invalid_market_container", "market must be a list or tuple", "market"))
    else:
        if len(market) > MAX_MARKET_ORDERS:
            issues.append(
                _issue(
                    "market_order_limit",
                    f"market contains {len(market)} orders; maximum is {MAX_MARKET_ORDERS}",
                    "market",
                )
            )
        for index, command in enumerate(market):
            issues.extend(_validate_command(command, _MARKET_ARITIES, f"market[{index}]"))

    return tuple(issues)


def _policy_accepts_config(policy: Callable[..., Any]) -> bool:
    try:
        inspect.signature(policy).bind(object(), object())
    except (TypeError, ValueError):
        return False
    return True


def _fallback_action(observation: Mapping[str, Any]) -> dict[str, Any]:
    player = observation["player"]
    hand_count = len(observation["farms"][player]["hands"])
    return {"farmer": ["PASS"], "hands": [["PASS"]] * hand_count, "market": []}


def _as_optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    return float(value)


def run_tape_compatibility(
    policy: Callable[..., Any],
    seed: int,
    seat: int,
    opponent: str = "starter",
) -> CompatibilityReport:
    """Execute *policy* in one seat and retain diagnostics for quarantine."""
    if not callable(policy):
        raise ValueError("policy must be callable")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(seat, bool) or seat not in {0, 1}:
        raise ValueError("seat must be 0 or 1")
    if not isinstance(opponent, str) or not opponent:
        raise ValueError("opponent must be a non-empty string")

    action_calls = 0
    issue_rows: list[CompatibilityIssue] = []
    action_digest = sha256()
    captured_exception: str | None = None
    accepts_config = _policy_accepts_config(policy)

    def recording_policy(observation: Mapping[str, Any], configuration: Any = None) -> dict[str, Any]:
        nonlocal action_calls, captured_exception
        step = action_calls
        action_calls += 1
        fallback = _fallback_action(observation)

        if captured_exception is not None:
            raw_action: Any = fallback
        else:
            try:
                raw_action = policy(observation, configuration) if accepts_config else policy(observation)
            except Exception as error:  # the report, rather than env.run, owns policy failures
                captured_exception = f"{type(error).__name__}: {error}"
                raw_action = fallback

        try:
            normalized = normalize_action(raw_action)
            expected_hands = len(observation["farms"][observation["player"]]["hands"])
            for issue in validate_action_shape(normalized, expected_hands):
                issue_rows.append(
                    CompatibilityIssue(
                        code=issue.code,
                        message=issue.message,
                        step=step,
                        location=issue.location,
                    )
                )
            emitted = {
                "farmer": list(normalized.farmer),
                "hands": [list(command) for command in normalized.hands],
                "market": [list(command) for command in normalized.market],
            }
        except (TypeError, ValueError) as error:
            issue_rows.append(
                CompatibilityIssue(
                    code="invalid_action_container",
                    message=str(error),
                    step=step,
                    location=None,
                )
            )
            emitted = fallback

        action_digest.update(json.dumps(emitted, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        action_digest.update(b"\n")
        return emitted

    agents: list[Any] = [opponent, opponent]
    agents[seat] = recording_policy
    env = None
    try:
        env = make("kaggriculture", configuration={"seed": seed})
        env.run(agents)
    except Exception as error:
        if captured_exception is None:
            captured_exception = f"{type(error).__name__}: {error}"

    status = "ERROR"
    final_banks: tuple[float, float] | None = None
    state_rewards: tuple[float | None, float | None] | None = None
    if env is not None and getattr(env, "state", None):
        status = str(env.state[seat].status)
        try:
            farms = env.state[0].observation.farms
            banks = tuple(_as_optional_float(farm.money) for farm in farms)
            if len(banks) == 2 and all(bank is not None for bank in banks):
                final_banks = (float(banks[0]), float(banks[1]))  # type: ignore[arg-type]
        except (AttributeError, IndexError, TypeError):
            final_banks = None
        rewards = tuple(_as_optional_float(state.reward) for state in env.state)
        if len(rewards) == 2:
            state_rewards = (rewards[0], rewards[1])

    # Public farm balances are the score source of record. Rewards are only a
    # fallback for runtimes that fail before exposing the final public farms.
    if final_banks is not None:
        score = final_banks[seat]
    elif state_rewards is not None:
        score = state_rewards[seat]
    else:
        score = None

    return CompatibilityReport(
        environment_version=kaggle_environments.__version__,
        seed=seed,
        seat=seat,
        opponent=opponent,
        status=status,
        action_calls=action_calls,
        exception=captured_exception,
        issues=tuple(issue_rows),
        final_banks=final_banks,
        state_rewards=state_rewards,
        score=score,
        action_sha256=action_digest.hexdigest(),
    )
