"""Deterministic replay-family splits and leakage checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import AbstractSet, Iterable, Mapping, Sequence, TypeAlias

from kaggriculture_lib.replay_schema import DecisionRecord


class SplitName(str, Enum):
    """Named replay partitions, including the externally-managed test split."""

    TRAIN = "train"
    VALIDATION = "validation"
    FAMILY_HOLDOUT = "family_holdout"
    COMPETITIVE_TEST = "competitive_test"


SplitAssignment: TypeAlias = dict[str, SplitName]


@dataclass(frozen=True)
class LeakageReport:
    """Deterministically ordered split-isolation violations."""

    episode_leaks: tuple[str, ...] = ()
    family_leaks: tuple[str, ...] = ()
    base_episode_leaks: tuple[str, ...] = ()
    missing_assignments: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(
            (
                self.episode_leaks,
                self.family_leaks,
                self.base_episode_leaks,
                self.missing_assignments,
            )
        )

    @property
    def duplicate_episode_ids(self) -> tuple[str, ...]:
        """Alias that makes the report's episode-leak meaning explicit."""
        return self.episode_leaks

    @property
    def source_family_leaks(self) -> tuple[str, ...]:
        return self.family_leaks

    @property
    def base_episode_ids(self) -> tuple[str, ...]:
        return self.base_episode_leaks

    def __str__(self) -> str:
        if self.ok:
            return "no split leakage detected"
        violations = (
            ("episode_leaks", self.episode_leaks),
            ("family_leaks", self.family_leaks),
            ("base_episode_leaks", self.base_episode_leaks),
            ("missing_assignments", self.missing_assignments),
        )
        details = "; ".join(
            f"{name}={','.join(values)}" for name, values in violations if values
        )
        return f"split leakage detected: {details}"


_BASE_EPISODE = re.compile(r"^(\d+)(?:[-_:].*)?$")


def _family_fraction(seed: int, family: str) -> float:
    digest = hashlib.sha256(f"{seed}:{family}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") / 2**64


def _base_episode_id(episode_id: str) -> str:
    """Collapse a derived tape identifier to its numeric public episode id."""
    match = _BASE_EPISODE.fullmatch(episode_id)
    return match.group(1) if match else episode_id


def assign_family_splits(
    families: Sequence[str],
    seed: int,
    validation_fraction: float,
    holdout_families: AbstractSet[str],
    *,
    reserved_families: AbstractSet[str] = frozenset(),
) -> SplitAssignment:
    """Assign each unique source family to one non-competitive training split."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not 0.0 <= validation_fraction < 1.0:
        raise ValueError("validation_fraction must be in [0, 1)")
    if any(not isinstance(family, str) or not family for family in families):
        raise ValueError("families must contain non-empty strings")
    if any(not isinstance(family, str) or not family for family in holdout_families):
        raise ValueError("holdout_families must contain non-empty strings")
    if any(not isinstance(family, str) or not family for family in reserved_families):
        raise ValueError("reserved_families must contain non-empty strings")
    overlap = sorted(holdout_families & reserved_families)
    if overlap:
        raise ValueError(
            "holdout_families and reserved_families must not overlap: "
            + ", ".join(overlap)
        )

    unique_families = set(families)
    reserved = sorted(unique_families & reserved_families)
    if reserved:
        raise ValueError(f"reserved families cannot be split: {', '.join(reserved)}")

    return {
        family: (
            SplitName.FAMILY_HOLDOUT
            if family in holdout_families
            else SplitName.VALIDATION
            if _family_fraction(seed, family) < validation_fraction
            else SplitName.TRAIN
        )
        for family in sorted(unique_families)
    }


def _record_split(record: DecisionRecord, assignments: Mapping[str, SplitName]) -> SplitName | None:
    """Support normal family mappings and episode mappings for audit diagnostics."""
    split = assignments.get(record.source_family, assignments.get(record.episode_id))
    if split is None:
        return None
    if not isinstance(split, SplitName):
        raise ValueError("assignments must map to SplitName values")
    return split


def _cross_split_keys(values: Iterable[tuple[str, SplitName]]) -> tuple[str, ...]:
    observed: dict[str, set[SplitName]] = {}
    for key, split in values:
        observed.setdefault(key, set()).add(split)
    return tuple(sorted(key for key, splits in observed.items() if len(splits) > 1))


def audit_split_leakage(
    records: Iterable[DecisionRecord], assignments: Mapping[str, SplitName]
) -> LeakageReport:
    """Audit records for episode, family, and derived-tape split leakage."""
    episode_splits: list[tuple[str, SplitName]] = []
    family_splits: list[tuple[str, SplitName]] = []
    base_episode_splits: list[tuple[str, SplitName]] = []
    missing: set[str] = set()

    for record in records:
        if not isinstance(record, DecisionRecord):
            raise ValueError("records must contain DecisionRecord instances")
        split = _record_split(record, assignments)
        if split is None:
            missing.add(record.source_family)
            continue
        episode_splits.append((record.episode_id, split))
        family_splits.append((record.source_family, split))
        base_episode_splits.append((_base_episode_id(record.episode_id), split))

    return LeakageReport(
        episode_leaks=_cross_split_keys(episode_splits),
        family_leaks=_cross_split_keys(family_splits),
        base_episode_leaks=_cross_split_keys(base_episode_splits),
        missing_assignments=tuple(sorted(missing)),
    )
