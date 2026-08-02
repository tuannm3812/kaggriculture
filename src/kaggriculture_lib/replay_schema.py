"""Normalized, serializable decision records for replay analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from math import isfinite
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


class ActionOrigin(str, Enum):
    PUBLIC_ORIGINAL = "public_original"
    PUBLIC_REPAIRED = "public_repaired"
    TEACHER = "teacher"


ActionAtom = str | int


def _validate_action_atom(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must contain only strings or integers")


def _as_tuple(value: Any, name: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple")
    return tuple(value)


@dataclass(frozen=True)
class NormalizedAction:
    farmer: tuple[ActionAtom, ...]
    hands: tuple[tuple[ActionAtom, ...], ...]
    market: tuple[tuple[ActionAtom, ...], ...]

    def __post_init__(self) -> None:
        farmer = _as_tuple(self.farmer, "farmer")
        hands = _as_tuple(self.hands, "hands")
        market = _as_tuple(self.market, "market")
        for name, commands in (("farmer", farmer), ("hands", hands), ("market", market)):
            for command in commands:
                if name == "farmer":
                    _validate_action_atom(command, name)
                    continue
                command_tuple = _as_tuple(command, f"{name} action")
                for atom in command_tuple:
                    _validate_action_atom(atom, f"{name} action")
        object.__setattr__(self, "farmer", farmer)
        object.__setattr__(self, "hands", tuple(_as_tuple(command, "hands action") for command in hands))
        object.__setattr__(self, "market", tuple(_as_tuple(command, "market action") for command in market))


def normalize_action(action: Mapping[str, Any]) -> NormalizedAction:
    """Convert a raw action mapping into the contract's tuple-only form."""
    if not isinstance(action, Mapping):
        raise ValueError("action must be a mapping")
    expected = {"farmer", "hands", "market"}
    if set(action) != expected:
        raise ValueError("action must contain exactly farmer, hands, and market")
    return NormalizedAction(
        farmer=_as_tuple(action["farmer"], "farmer"),
        hands=tuple(_as_tuple(command, "hands action") for command in _as_tuple(action["hands"], "hands")),
        market=tuple(_as_tuple(command, "market action") for command in _as_tuple(action["market"], "market")),
    )


def _json_normalize(value: Any, name: str = "value") -> Any:
    """Return a recursively JSON-compatible copy with stable mapping keys."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(f"{name} mapping keys must be strings")
        return {key: _json_normalize(value[key], f"{name}.{key}") for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_json_normalize(item, name) for item in value]
    raise ValueError(f"{name} must be JSON-compatible")


@dataclass(frozen=True)
class DecisionRecord:
    episode_id: str
    source_policy_id: str
    source_family: str
    step: int
    day: int
    hour: int
    seat: int
    opponent_family: str
    environment_version: str
    configuration: Mapping[str, Any]
    observation: Mapping[str, Any]
    action: NormalizedAction
    action_origin: ActionOrigin
    original_action: NormalizedAction | None
    repair_reason: str | None
    terminal_result: str | None
    final_banks: tuple[float, float] | None
    compatibility_ok: bool
    legality_ok: bool
    completeness_ok: bool
    duplicate: bool

    def __post_init__(self) -> None:
        for name in ("episode_id", "source_policy_id", "source_family", "opponent_family", "environment_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (self.step, self.day, self.hour)):
            raise ValueError("step, day, and hour must be integers")
        if self.step != self.day * 24 + self.hour:
            raise ValueError("step must equal day * 24 + hour")
        if self.seat not in {0, 1}:
            raise ValueError("seat must be 0 or 1")
        if not isinstance(self.action, NormalizedAction):
            raise ValueError("action must be a NormalizedAction")
        if not isinstance(self.action_origin, ActionOrigin):
            raise ValueError("action_origin must be an ActionOrigin")
        repaired = self.action_origin is ActionOrigin.PUBLIC_REPAIRED
        if repaired and (self.original_action is None or self.repair_reason is None):
            raise ValueError("repair fields are required for public_repaired actions")
        if repaired and self.original_action == self.action:
            raise ValueError("repaired action must differ from original_action")
        if not repaired and (self.original_action is not None or self.repair_reason is not None):
            raise ValueError("repair fields are only allowed for public_repaired actions")
        if self.original_action is not None and not isinstance(self.original_action, NormalizedAction):
            raise ValueError("original_action must be a NormalizedAction")
        if self.repair_reason is not None and (not isinstance(self.repair_reason, str) or not self.repair_reason):
            raise ValueError("repair_reason must be a non-empty string")
        if self.terminal_result is not None and not isinstance(self.terminal_result, str):
            raise ValueError("terminal_result must be a string or None")
        if self.final_banks is not None:
            if not isinstance(self.final_banks, tuple) or len(self.final_banks) != 2:
                raise ValueError("final_banks must contain 2 values")
            if any(isinstance(bank, bool) or not isinstance(bank, (int, float)) or not isfinite(bank) for bank in self.final_banks):
                raise ValueError("final_banks must be finite")
            object.__setattr__(self, "final_banks", (float(self.final_banks[0]), float(self.final_banks[1])))
        for name in ("compatibility_ok", "legality_ok", "completeness_ok", "duplicate"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if not isinstance(self.configuration, Mapping) or not isinstance(self.observation, Mapping):
            raise ValueError("configuration and observation must be mappings")
        object.__setattr__(self, "configuration", _json_normalize(self.configuration, "configuration"))
        object.__setattr__(self, "observation", _json_normalize(self.observation, "observation"))


def _record_from_json(value: Any) -> DecisionRecord:
    if not isinstance(value, Mapping):
        raise ValueError("decision row must be an object")
    data = dict(value)
    data["action"] = normalize_action(data["action"])
    if data.get("original_action") is not None:
        data["original_action"] = normalize_action(data["original_action"])
    data["action_origin"] = ActionOrigin(data["action_origin"])
    if data.get("final_banks") is not None:
        data["final_banks"] = tuple(data["final_banks"])
    return DecisionRecord(**data)


def write_decisions(records: Iterable[DecisionRecord], path: Path) -> None:
    """Write one canonical, sorted-key JSON decision record per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as destination:
        for record in records:
            if not isinstance(record, DecisionRecord):
                raise ValueError("records must contain DecisionRecord instances")
            destination.write(json.dumps(_json_normalize(asdict(record)), sort_keys=True, separators=(",", ":")))
            destination.write("\n")


def read_decisions(path: Path) -> Iterator[DecisionRecord]:
    """Yield canonical decision records, identifying malformed input rows exactly."""
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: malformed JSON: {error.msg}") from error
            try:
                yield _record_from_json(raw)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: schema violation: {error}") from error
