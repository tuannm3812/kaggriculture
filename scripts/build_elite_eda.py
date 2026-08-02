#!/usr/bin/env python3
"""Build deterministic decision-oriented EDA tables from normalized replays."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass
from io import StringIO
import json
from math import log2, sqrt
import os
from pathlib import Path
from statistics import median
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from kaggriculture_lib import replay_metrics
from kaggriculture_lib.replay_compat import (
    EXPECTED_ACTION_CALLS,
    PINNED_ENVIRONMENT_VERSION,
    validate_action_shape,
)
from kaggriculture_lib.replay_metrics import EpisodeSummary, TurnMetrics
from kaggriculture_lib.replay_provenance import PublicArtifact, load_manifest
from kaggriculture_lib.replay_schema import ActionOrigin, DecisionRecord, read_decisions
from scripts.validate_public_replays import (
    REPORT_FIELDS,
    _evaluate_records,
    _expected_hands,
)


DAILY_FIELDS = (
    "source_group",
    "source_policy_id",
    "source_family",
    "episode_id",
    "seat",
    "day",
    "turn_count",
    "mean_money",
    "end_money",
    "mean_land_count",
    "max_land_count",
    "mean_active_hands",
    "max_active_hands",
    "mean_shed_units",
    "mean_carried_units",
    "mean_storage_utilization",
    "storage_pressure_turns",
    "productive_actions",
    "travel_actions",
    "logistics_actions",
    "idle_actions",
    "other_actions",
    "sell_quantity",
    "sell_turn_count",
    "observed_sell_bank_delta_turn_count",
    "observed_bank_delta_on_sell_turns",
    "crop_counts",
    "animal_counts",
    "market_order_counts",
    "current_prices",
    "status",
    "terminal_result",
    "final_bank",
    "terminal_stranded_units",
)

EPISODE_FIELDS = (
    "source_group",
    "action_origins",
    "episode_id",
    "source_policy_id",
    "source_family",
    "seat",
    "opponent_family",
    "turn_count",
    "first_step",
    "last_step",
    "first_day",
    "last_day",
    "land_opening_day",
    "land_purchase_count",
    "hand_peak",
    "hand_min",
    "hand_max",
    "hire_orders",
    "productive_actions",
    "travel_actions",
    "logistics_actions",
    "idle_actions",
    "other_actions",
    "productive_action_share",
    "travel_action_share",
    "logistics_action_share",
    "idle_action_share",
    "other_action_share",
    "crop_exposure_by_day",
    "animal_exposure_by_day",
    "sell_quantity",
    "sell_quantity_by_product",
    "sell_concentration_by_product",
    "sell_product_hhi",
    "sell_turn_count",
    "observed_sell_bank_delta_turn_count",
    "observed_bank_delta_on_sell_turns",
    "storage_pressure_turns",
    "terminal_stranded_units",
    "final_bank",
    "status",
    "result",
    "final_8_action_cash_change",
    "final_22_action_cash_change",
    "final_48_action_cash_change",
    "bank_recovery_turns_after_purchase",
)

SOURCE_COMPARISON_FIELDS = (
    "source_group",
    "source_family",
    "episode_count",
    "source_policy_count",
    "complete_episode_count",
    "seat_0_episodes",
    "seat_1_episodes",
    "opponent_families",
    "mean_final_bank",
    "win_count",
    "tie_count",
    "loss_count",
    "mean_land_opening_day",
    "mean_land_purchase_count",
    "mean_hand_peak",
    "hire_orders",
    "productive_action_share",
    "travel_action_share",
    "logistics_action_share",
    "idle_action_share",
    "other_action_share",
    "sell_quantity",
    "sell_episode_count",
    "no_sale_episode_count",
    "missing_sell_bank_delta_episode_count",
    "sell_turn_count",
    "observed_sell_bank_delta_turn_count",
    "sell_bank_delta_coverage",
    "observed_bank_delta_on_sell_turns",
    "mean_sell_product_hhi",
    "storage_pressure_turns",
    "mean_terminal_stranded_units",
    "terminal_stranding_observed_episode_count",
    "terminal_stranding_coverage",
    "mean_final_8_action_cash_change",
    "mean_final_22_action_cash_change",
    "mean_final_48_action_cash_change",
)

COVERAGE_FIELDS = (
    "source_group",
    "comparison_group",
    "diagnostic",
    "diagnostic_type",
    "category",
    "count",
    "missing_count",
    "minimum",
    "q25",
    "median",
    "q75",
    "maximum",
    "distance_type",
    "distance",
    "critical_zero_support",
)

SOURCE_GROUPS = ("elite", "teacher", "repaired")
ACTION_FAMILIES = ("productive", "travel", "logistics", "idle", "other")
MARKET_OPERATIONS = (
    "BUY_ANIMAL",
    "BUY_LAND",
    "BUY_PRODUCT",
    "BUY_SEED",
    "HIRE",
    "SELL",
    "other",
)
CRITICAL_CATEGORIES = {
    ("action_family", "productive"),
    ("action_family", "logistics"),
    ("market_operation", "BUY_ANIMAL"),
    ("market_operation", "BUY_LAND"),
    ("market_operation", "HIRE"),
    ("market_operation", "SELL"),
    ("terminal_state", "complete"),
}


@dataclass(frozen=True)
class EdaBuildResult:
    """Small accounting summary returned by :func:`build_eda`."""

    source_count: int
    eligible_source_count: int
    quarantine_source_count: int
    compatible_turn_count: int
    episode_count: int


@dataclass(frozen=True)
class _MetricEpisode:
    records: tuple[DecisionRecord, ...]
    turns: tuple[TurnMetrics, ...]
    summary: EpisodeSummary


def _source_group(origin: ActionOrigin) -> str:
    if origin is ActionOrigin.TEACHER:
        return "teacher"
    if origin is ActionOrigin.PUBLIC_REPAIRED:
        return "repaired"
    return "elite"


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, (tuple, list)):
        return ";".join(_format_cell(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as destination:
            destination.write(content)
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_csv(rows: Iterable[Mapping[str, Any]], fields: Sequence[str], path: Path) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _format_cell(row.get(field)) for field in fields})
    _atomic_write_text(path, buffer.getvalue())


def _missing_compatibility_row(artifact: PublicArtifact) -> dict[str, str]:
    return {
        "source_policy_id": artifact.source_policy_id,
        "source_family": artifact.source_family,
        "episode_id": artifact.episode_id or "",
        "declared_environment": artifact.declared_environment,
        "replay_environment": "",
        "status": "MISSING",
        "action_calls": "0",
        "exception": "",
        "issue_codes": "",
        "final_bank_0": "",
        "final_bank_1": "",
        "action_sha256": "",
        "eligible": "false",
        "reason_codes": "missing_compatibility_report",
    }


def _compatibility_rows(
    artifacts: Sequence[PublicArtifact],
    compatibility_path: Path,
) -> list[dict[str, str]]:
    artifacts_by_id = {artifact.source_policy_id: artifact for artifact in artifacts}
    existing: dict[str, dict[str, str]] = {}
    if compatibility_path.is_file():
        with compatibility_path.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            missing_fields = set(REPORT_FIELDS) - set(reader.fieldnames or ())
            if missing_fields:
                names = ", ".join(sorted(missing_fields))
                raise ValueError(f"{compatibility_path}: missing fields: {names}")
            for row in reader:
                source_policy_id = row["source_policy_id"]
                if source_policy_id in existing:
                    raise ValueError(
                        f"{compatibility_path}: duplicate source_policy_id: {source_policy_id}"
                    )
                if source_policy_id not in artifacts_by_id:
                    raise ValueError(
                        f"{compatibility_path}: source_policy_id not present in manifest: "
                        f"{source_policy_id}"
                    )
                artifact = artifacts_by_id[source_policy_id]
                expected_identity = {
                    "source_family": artifact.source_family,
                    "episode_id": artifact.episode_id or "",
                    "declared_environment": artifact.declared_environment,
                }
                mismatches = [
                    name
                    for name, expected in expected_identity.items()
                    if row.get(name, "") != expected
                ]
                if mismatches:
                    raise ValueError(
                        f"{compatibility_path}: manifest identity mismatch for "
                        f"{source_policy_id}: {', '.join(mismatches)}"
                    )
                existing[source_policy_id] = {
                    field: row.get(field, "") for field in REPORT_FIELDS
                }

    rows = [
        existing.pop(artifact.source_policy_id, _missing_compatibility_row(artifact))
        for artifact in artifacts
    ]
    return sorted(rows, key=lambda row: (row["source_policy_id"], row["episode_id"]))


def _load_decisions(path: Path) -> list[DecisionRecord]:
    if path.is_file():
        paths = [path]
    elif path.is_dir():
        paths = sorted(path.rglob("*.jsonl"))
    else:
        paths = []
    records: list[DecisionRecord] = []
    for decision_path in paths:
        records.extend(read_decisions(decision_path))
    return records


def _teacher_episode_is_compatible(records: Sequence[DecisionRecord]) -> bool:
    if not records:
        return False
    first = records[0]
    if (
        first.source_policy_id != "task_teacher_v2"
        or first.source_family != "task-teacher-v2"
        or [record.step for record in records] != list(range(EXPECTED_ACTION_CALLS))
        or records[-1].terminal_result is None
        or records[-1].final_banks is None
    ):
        return False
    for record in records:
        if (
            record.source_policy_id != first.source_policy_id
            or record.source_family != first.source_family
            or record.episode_id != first.episode_id
            or record.seat != first.seat
            or record.opponent_family != first.opponent_family
            or record.configuration != first.configuration
            or record.environment_version != PINNED_ENVIRONMENT_VERSION
            or record.observation.get("player") != record.seat
            or not record.compatibility_ok
            or not record.legality_ok
            or not record.completeness_ok
            or record.duplicate
        ):
            return False
        expected_hands = _expected_hands(record)
        if expected_hands is None or validate_action_shape(record.action, expected_hands):
            return False
    return True


def _reject_compatibility_row(
    evaluated: Mapping[str, str],
    reason: str | None = None,
) -> dict[str, str]:
    rejected = {field: evaluated.get(field, "") for field in REPORT_FIELDS}
    reasons = [item for item in rejected["reason_codes"].split(";") if item]
    if reason is not None and reason not in reasons:
        reasons.append(reason)
    rejected["eligible"] = "false"
    rejected["reason_codes"] = ";".join(reasons)
    return rejected


def _bind_eligible_records(
    records: Sequence[DecisionRecord],
    artifacts: Sequence[PublicArtifact],
    compatibility_rows: Sequence[Mapping[str, str]],
) -> tuple[list[DecisionRecord], list[dict[str, str]]]:
    public_records: defaultdict[str, list[DecisionRecord]] = defaultdict(list)
    teacher_episodes: defaultdict[tuple[Any, ...], list[DecisionRecord]] = defaultdict(list)
    for record in records:
        if record.action_origin is ActionOrigin.TEACHER:
            if record.source_policy_id == "task_teacher_v2":
                teacher_episodes[
                    (
                        record.source_policy_id,
                        record.source_family,
                        record.episode_id,
                        record.seat,
                        record.opponent_family,
                    )
                ].append(record)
        else:
            public_records[record.source_policy_id].append(record)

    compatibility_by_id = {
        row["source_policy_id"]: dict(row) for row in compatibility_rows
    }
    eligible: list[DecisionRecord] = []
    bound_rows: list[dict[str, str]] = []
    for artifact in artifacts:
        report_row = compatibility_by_id[artifact.source_policy_id]
        candidates = sorted(
            public_records.get(artifact.source_policy_id, []),
            key=lambda record: record.step,
        )
        if report_row.get("eligible", "").lower() != "true":
            bound_rows.append(report_row)
            continue
        evaluated = _evaluate_records(artifact, candidates)
        if any(record.duplicate for record in candidates):
            bound_rows.append(
                _reject_compatibility_row(evaluated, "duplicate_record")
            )
            continue
        if evaluated["eligible"] != "true":
            bound_rows.append(_reject_compatibility_row(evaluated))
            continue
        if evaluated["action_sha256"] != report_row.get("action_sha256", ""):
            bound_rows.append(
                _reject_compatibility_row(evaluated, "action_digest_mismatch")
            )
            continue
        bound_rows.append(report_row)
        eligible.extend(candidates)

    for key in sorted(teacher_episodes):
        candidates = sorted(teacher_episodes[key], key=lambda record: record.step)
        if _teacher_episode_is_compatible(candidates):
            eligible.extend(candidates)

    return sorted(
        eligible,
        key=lambda record: (
            record.source_policy_id,
            record.episode_id,
            record.seat,
            record.step,
            record.action_origin.value,
        ),
    ), bound_rows


def _metric_episodes(records: Sequence[DecisionRecord]) -> list[_MetricEpisode]:
    grouped: defaultdict[tuple[Any, ...], list[DecisionRecord]] = defaultdict(list)
    for record in records:
        grouped[
            (
                record.source_policy_id,
                record.source_family,
                record.episode_id,
                record.seat,
                record.opponent_family,
            )
        ].append(record)

    episodes: list[_MetricEpisode] = []
    for key in sorted(grouped):
        episode_records = tuple(sorted(grouped[key], key=lambda record: record.step))
        turns = tuple(
            replay_metrics.extract_turn_metrics(
                record,
                (
                    episode_records[index + 1].observation
                    if index + 1 < len(episode_records)
                    and episode_records[index + 1].step == record.step + 1
                    else None
                ),
            )
            for index, record in enumerate(episode_records)
        )
        episodes.append(
            _MetricEpisode(
                records=episode_records,
                turns=turns,
                summary=replay_metrics.summarize_episode(turns),
            )
        )
    return episodes


def _optional_mean(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _sum_mappings(rows: Iterable[Mapping[str, float | int]]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        for key, value in row.items():
            totals[key] += float(value)
    return dict(sorted(totals.items()))


def _daily_rows(episodes: Sequence[_MetricEpisode]) -> list[dict[str, Any]]:
    daily: list[dict[str, Any]] = []
    for episode in episodes:
        by_day: defaultdict[int, list[tuple[DecisionRecord, TurnMetrics]]] = defaultdict(list)
        for record, turn in zip(episode.records, episode.turns):
            by_day[turn.day].append((record, turn))
        for day in sorted(by_day):
            paired = by_day[day]
            records = [record for record, _ in paired]
            turns = [turn for _, turn in paired]
            origins = {_source_group(record.action_origin) for record in records}
            sell_turns = [turn for turn in turns if turn.sell_quantity > 0]
            sell_deltas = [
                turn.observed_bank_delta
                for turn in sell_turns
                if turn.observed_bank_delta is not None
            ]
            daily.append(
                {
                    "source_group": next(iter(origins)) if len(origins) == 1 else "mixed",
                    "source_policy_id": turns[0].source_policy_id,
                    "source_family": turns[0].source_family,
                    "episode_id": turns[0].episode_id,
                    "seat": turns[0].seat,
                    "day": day,
                    "turn_count": len(turns),
                    "mean_money": _optional_mean(turn.money for turn in turns),
                    "end_money": turns[-1].money,
                    "mean_land_count": _optional_mean(turn.land_count for turn in turns),
                    "max_land_count": max(turn.land_count for turn in turns),
                    "mean_active_hands": _optional_mean(turn.active_hands for turn in turns),
                    "max_active_hands": max(turn.active_hands for turn in turns),
                    "mean_shed_units": _optional_mean(turn.shed_units for turn in turns),
                    "mean_carried_units": _optional_mean(turn.carried_units for turn in turns),
                    "mean_storage_utilization": _optional_mean(
                        turn.storage_utilization for turn in turns
                    ),
                    "storage_pressure_turns": sum(turn.storage_pressure for turn in turns),
                    "productive_actions": sum(turn.productive_actions for turn in turns),
                    "travel_actions": sum(turn.travel_actions for turn in turns),
                    "logistics_actions": sum(turn.logistics_actions for turn in turns),
                    "idle_actions": sum(turn.idle_actions for turn in turns),
                    "other_actions": sum(turn.other_actions for turn in turns),
                    "sell_quantity": sum(turn.sell_quantity for turn in turns),
                    "sell_turn_count": len(sell_turns),
                    "observed_sell_bank_delta_turn_count": len(sell_deltas),
                    "observed_bank_delta_on_sell_turns": (
                        sum(sell_deltas) if len(sell_deltas) == len(sell_turns) else None
                    ),
                    "crop_counts": _sum_mappings(turn.crop_counts for turn in turns),
                    "animal_counts": _sum_mappings(turn.animal_counts for turn in turns),
                    "market_order_counts": _sum_mappings(
                        turn.market_order_counts for turn in turns
                    ),
                    "current_prices": _sum_mappings(turn.current_prices for turn in turns),
                    "status": turns[-1].status,
                    "terminal_result": turns[-1].terminal_result,
                    "final_bank": turns[-1].final_bank,
                    "terminal_stranded_units": turns[-1].terminal_stranded_units,
                }
            )
    return sorted(
        daily,
        key=lambda row: (
            row["source_group"],
            row["source_family"],
            row["source_policy_id"],
            row["episode_id"],
            row["seat"],
            row["day"],
        ),
    )


def _episode_rows(episodes: Sequence[_MetricEpisode]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        summary = episode.summary
        origins = tuple(sorted({record.action_origin.value for record in episode.records}))
        groups = {_source_group(record.action_origin) for record in episode.records}
        row = asdict(summary)
        row.update(
            {
                "source_group": next(iter(groups)) if len(groups) == 1 else "mixed",
                "action_origins": origins,
                "hand_min": summary.hand_range[0],
                "hand_max": summary.hand_range[1],
                "final_8_action_cash_change": summary.final_8_action_cash_change,
                "final_22_action_cash_change": summary.final_22_action_cash_change,
                "final_48_action_cash_change": summary.final_48_action_cash_change,
            }
        )
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            row["source_group"],
            row["source_family"],
            row["source_policy_id"],
            row["episode_id"],
            row["seat"],
        ),
    )


def _source_comparison_rows(episodes: Sequence[_MetricEpisode]) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[EpisodeSummary]] = defaultdict(list)
    for episode in episodes:
        groups = {_source_group(record.action_origin) for record in episode.records}
        group = next(iter(groups)) if len(groups) == 1 else "mixed"
        grouped[group].append(episode.summary)
    rows: list[dict[str, Any]] = []
    for group in sorted(grouped):
        for comparison in replay_metrics.compare_sources(grouped[group]):
            rows.append({"source_group": group, **comparison})
    return sorted(rows, key=lambda row: (row["source_group"], row["source_family"]))


def _quantile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _jensen_shannon(left: Mapping[str, float], right: Mapping[str, float]) -> float | None:
    support = sorted(set(left) | set(right))
    left_total = sum(left.values())
    right_total = sum(right.values())
    if not support or left_total <= 0 or right_total <= 0:
        return None
    left_distribution = [left.get(key, 0.0) / left_total for key in support]
    right_distribution = [right.get(key, 0.0) / right_total for key in support]
    midpoint = [
        (left_value + right_value) / 2
        for left_value, right_value in zip(left_distribution, right_distribution)
    ]

    def divergence(distribution: Sequence[float], middle: Sequence[float]) -> float:
        return sum(
            value * log2(value / centre)
            for value, centre in zip(distribution, middle)
            if value > 0 and centre > 0
        )

    return sqrt(
        (
            divergence(left_distribution, midpoint)
            + divergence(right_distribution, midpoint)
        )
        / 2
    )


def _scalar_diagnostics(turns: Sequence[TurnMetrics]) -> dict[str, list[float]]:
    values: defaultdict[str, list[float]] = defaultdict(list)
    for turn in turns:
        values["day"].append(float(turn.day))
        values["hour"].append(float(turn.hour))
        values["land_count"].append(float(turn.land_count))
        values["hand_count"].append(float(turn.active_hands))
        if turn.money is not None:
            values["money"].append(turn.money)
        values["storage_load"].append(turn.shed_units + turn.carried_units)
        values["storage_utilization"].append(turn.storage_utilization)
        if turn.terminal_stranded_units is not None:
            values["terminal_stranded_units"].append(turn.terminal_stranded_units)
        for product, price in turn.current_prices.items():
            values[f"price:{product}"].append(price)
    return dict(values)


def _categorical_diagnostics(turns: Sequence[TurnMetrics]) -> dict[str, Counter[str]]:
    values: dict[str, Counter[str]] = {
        "crop_composition": Counter(),
        "animal_composition": Counter(),
        "action_family": Counter({category: 0 for category in ACTION_FAMILIES}),
        "market_operation": Counter({category: 0 for category in MARKET_OPERATIONS}),
        "terminal_state": Counter({"complete": 0, "incomplete": 0}),
        "crisis_state": Counter({"storage_pressure": 0, "terminal_stranding": 0}),
    }
    for turn in turns:
        if turn.crop_counts:
            values["crop_composition"].update(turn.crop_counts)
        else:
            values["crop_composition"]["__none__"] += 1
        if turn.animal_counts:
            values["animal_composition"].update(turn.animal_counts)
        else:
            values["animal_composition"]["__none__"] += 1
        values["action_family"].update(
            {
                "productive": turn.productive_actions,
                "travel": turn.travel_actions,
                "logistics": turn.logistics_actions,
                "idle": turn.idle_actions,
                "other": turn.other_actions,
            }
        )
        values["market_operation"].update(turn.market_order_counts)
        values["terminal_state"][turn.status] += 1
        if turn.storage_pressure:
            values["crisis_state"]["storage_pressure"] += 1
        if turn.terminal_stranded_units is not None and turn.terminal_stranded_units > 0:
            values["crisis_state"]["terminal_stranding"] += 1
    return values


def _coverage_rows(episodes: Sequence[_MetricEpisode]) -> list[dict[str, Any]]:
    turns_by_group: dict[str, list[TurnMetrics]] = {group: [] for group in SOURCE_GROUPS}
    for episode in episodes:
        for record, turn in zip(episode.records, episode.turns):
            turns_by_group[_source_group(record.action_origin)].append(turn)

    scalars = {group: _scalar_diagnostics(turns) for group, turns in turns_by_group.items()}
    categories = {
        group: _categorical_diagnostics(turns) for group, turns in turns_by_group.items()
    }
    scalar_names = sorted(
        {
            "day",
            "hour",
            "land_count",
            "hand_count",
            "money",
            "price:__none__",
            "storage_load",
            "storage_utilization",
            "terminal_stranded_units",
        }
        | {name for group in SOURCE_GROUPS for name in scalars[group]}
    )
    category_names = (
        "action_family",
        "animal_composition",
        "crisis_state",
        "crop_composition",
        "market_operation",
        "terminal_state",
    )

    rows: list[dict[str, Any]] = []
    base_group = "elite"
    for group in SOURCE_GROUPS:
        comparison_group = base_group
        for diagnostic in scalar_names:
            values = scalars[group].get(diagnostic, [])
            base_values = scalars[base_group].get(diagnostic, [])
            q25 = _quantile(values, 0.25)
            group_median = median(values) if values else None
            q75 = _quantile(values, 0.75)
            distance = None
            if values and base_values:
                base_q25 = _quantile(base_values, 0.25)
                base_q75 = _quantile(base_values, 0.75)
                base_median = median(base_values)
                scale = max(
                    (q75 or 0.0) - (q25 or 0.0),
                    (base_q75 or 0.0) - (base_q25 or 0.0),
                    1.0,
                )
                distance = (group_median - base_median) / scale
            rows.append(
                {
                    "source_group": group,
                    "comparison_group": comparison_group,
                    "diagnostic": diagnostic,
                    "diagnostic_type": "scalar",
                    "category": "",
                    "count": len(values),
                    "missing_count": max(0, len(turns_by_group[group]) - len(values)),
                    "minimum": min(values) if values else None,
                    "q25": q25,
                    "median": group_median,
                    "q75": q75,
                    "maximum": max(values) if values else None,
                    "distance_type": (
                        "standardized_median_difference" if distance is not None else ""
                    ),
                    "distance": distance,
                    "critical_zero_support": False,
                }
            )

        for diagnostic in category_names:
            counts = categories[group][diagnostic]
            base_counts = categories[base_group][diagnostic]
            distance = _jensen_shannon(base_counts, counts)
            category_support = sorted(set(counts) | set(base_counts)) or ["__none__"]
            for category in category_support:
                count = counts.get(category, 0)
                rows.append(
                    {
                        "source_group": group,
                        "comparison_group": comparison_group,
                        "diagnostic": diagnostic,
                        "diagnostic_type": "categorical",
                        "category": category,
                        "count": count,
                        "missing_count": 0,
                        "minimum": None,
                        "q25": None,
                        "median": None,
                        "q75": None,
                        "maximum": None,
                        "distance_type": "jensen_shannon" if distance is not None else "",
                        "distance": distance,
                        "critical_zero_support": (
                            (diagnostic, category) in CRITICAL_CATEGORIES and count == 0
                        ),
                    }
                )
    return sorted(
        rows,
        key=lambda row: (
            row["source_group"],
            row["diagnostic_type"],
            row["diagnostic"],
            row["category"],
        ),
    )


def _decision(
    section: str,
    turns_by_group: Mapping[str, int],
    coverage_rows: Sequence[Mapping[str, Any]],
    episodes: Sequence[_MetricEpisode],
) -> tuple[str, str]:
    complete_episode_counts: Counter[str] = Counter()
    for episode in episodes:
        groups = {_source_group(record.action_origin) for record in episode.records}
        if (
            len(groups) == 1
            and episode.summary.status == "complete"
            and episode.summary.turn_count == EXPECTED_ACTION_CALLS
        ):
            complete_episode_counts[next(iter(groups))] += 1
    has_pair = all(complete_episode_counts[group] > 0 for group in ("elite", "teacher"))
    if not has_pair:
        return "REJECT: insufficient compatible evidence", (
            "No complete compatible elite-versus-teacher episode pair is available."
        )

    if section == "Opponent and seat":
        group_coverage: dict[str, tuple[set[int], set[str]]] = {}
        for group in ("elite", "teacher"):
            group_episodes = [
                episode
                for episode in episodes
                if {_source_group(record.action_origin) for record in episode.records} == {group}
            ]
            group_coverage[group] = (
                {episode.summary.seat for episode in group_episodes},
                {episode.summary.opponent_family for episode in group_episodes},
            )
        if any(
            len(seats) < 2 or len(opponents) < 2
            for seats, opponents in group_coverage.values()
        ):
            return "REJECT: insufficient compatible evidence", (
                "Both seats and at least two opponent families are required for each source group."
            )

    section_diagnostics = {
        "Capital and expansion": {"land_count", "hand_count", "money", "market_operation"},
        "Portfolio and market": {"crop_composition", "animal_composition", "market_operation"},
        "Labor and routing": {"action_family", "hand_count", "market_operation"},
        "Storage and terminal": {"storage_load", "storage_utilization", "terminal_state"},
        "Opponent and seat": {"terminal_state"},
        "Coverage gap": {row["diagnostic"] for row in coverage_rows},
    }[section]
    relevant = [
        row
        for row in coverage_rows
        if row["source_group"] == "teacher" and row["diagnostic"] in section_diagnostics
    ]
    supported_groups = {
        group
        for group in ("elite", "teacher")
        if any(
            row["source_group"] == group
            and row["diagnostic"] in section_diagnostics
            and int(row["count"]) > 0
            for row in coverage_rows
        )
    }
    if supported_groups != {"elite", "teacher"}:
        return "REJECT: insufficient compatible evidence", (
            "The relevant diagnostics lack measured support in one or both source groups."
        )
    critical_gap = any(row["critical_zero_support"] for row in relevant)
    material_distance = any(
        row["distance"] is not None and abs(float(row["distance"])) >= 0.10
        for row in relevant
    )
    if critical_gap or material_distance:
        return "CHANGE", (
            "Measured coverage differs materially or a critical teacher action has zero support."
        )
    return (
        "KEEP",
        "No material measured difference is present in the available compatible evidence.",
    )


def _report(
    *,
    result: EdaBuildResult,
    turns_by_group: Mapping[str, int],
    compatibility_rows: Sequence[Mapping[str, str]],
    coverage_rows: Sequence[Mapping[str, Any]],
    episodes: Sequence[_MetricEpisode],
) -> str:
    sections = (
        "Capital and expansion",
        "Portfolio and market",
        "Labor and routing",
        "Storage and terminal",
        "Opponent and seat",
        "Coverage gap",
    )
    lines = [
        "# Elite Replay EDA",
        "",
        (
            "Generated deterministically from the attributed manifest, normalized "
            "decisions, and pinned-runtime compatibility report."
        ),
        "",
        "## Evidence accounting",
        "",
        f"- Manifest sources: {result.source_count}.",
        f"- Eligible public sources: {result.eligible_source_count}.",
        f"- Quarantined public sources: {result.quarantine_source_count}.",
        (
            f"- Compatible normalized turns: {result.compatible_turn_count} "
            f"(elite={turns_by_group.get('elite', 0)}, "
            f"teacher={turns_by_group.get('teacher', 0)}, "
            f"repaired={turns_by_group.get('repaired', 0)})."
        ),
        f"- Summarized episodes: {result.episode_count}.",
        (
            "- Notebook-authored descriptions are contextual evidence only. They are "
            "not counted as `1.29.3`-compatible executed measurements unless a "
            "normalized trajectory passes `elite_compatibility.csv`."
        ),
        (
            "- All manifest sources are listed in "
            "`replays/analysis/elite_compatibility.csv`; exclusions and stable "
            "reasons are listed in `replays/analysis/elite_quarantine.csv`."
        ),
        "",
        "## Interpretation boundary",
        "",
        (
            "The CSVs describe observed states, actions, and next-bank changes. They "
            "do not assign causal proceeds or costs to simultaneous actions. Empty "
            "measured tables mean the required normalized evidence was unavailable; "
            "notebook prose and embedded outputs are not silently substituted."
        ),
        "",
        "Coverage-table scalar distances are signed median differences divided by "
        "the larger source IQR (with a one-unit floor). Categorical distances are "
        "Jensen-Shannon distances after normalizing both sources on their common "
        "union support; no distance is emitted when either source has zero total support.",
        "",
    ]
    for section in sections:
        decision, explanation = _decision(section, turns_by_group, coverage_rows, episodes)
        if section in {"Capital and expansion", "Labor and routing"}:
            references = (
                "`elite_daily.csv`, `elite_episode_summary.csv`, and "
                "`elite_coverage_gap.csv`"
            )
        elif section == "Opponent and seat":
            references = "`elite_episode_summary.csv` and `elite_source_comparison.csv`"
        else:
            references = "`elite_source_comparison.csv` and `elite_coverage_gap.csv`"
        lines.extend(
            [
                f"## {section}",
                "",
                f"Evidence: {references}. {explanation}",
                "",
                f"Decision: {decision}",
                "",
            ]
        )

    reason_counts = Counter()
    for row in compatibility_rows:
        if row.get("eligible", "").lower() != "true":
            for reason in row.get("reason_codes", "").split(";"):
                if reason:
                    reason_counts[reason] += 1
    lines.extend(
        [
            "## Quarantine accounting",
            "",
            (
                "Stable reason counts: "
                + (
                    ", ".join(
                        f"`{reason}`={count}"
                        for reason, count in sorted(reason_counts.items())
                    )
                    or "none"
                )
                + "."
            ),
            "",
            "## Gate outcome",
            "",
            (
                (
                    "The EDA/data gate does not pass. BC collection remains blocked "
                    "until compatible elite and teacher evidence supports the required "
                    "strategy and coverage decisions."
                )
                if any(turns_by_group.get(group, 0) == 0 for group in ("elite", "teacher"))
                else (
                    "The descriptive comparison is populated, but BC collection still "
                    "requires human review of the compatibility, leakage, and "
                    "critical-action coverage gates."
                )
            ),
            "",
        ]
    )
    return "\n".join(lines)


def build_eda(
    *,
    manifest_path: Path,
    decisions_path: Path,
    output_dir: Path,
    report_path: Path,
) -> EdaBuildResult:
    """Build all tracked aggregate evidence without fabricating missing data."""
    artifacts = load_manifest(manifest_path)
    compatibility_path = output_dir / "elite_compatibility.csv"
    reported_compatibility_rows = _compatibility_rows(artifacts, compatibility_path)
    records, compatibility_rows = _bind_eligible_records(
        _load_decisions(decisions_path), artifacts, reported_compatibility_rows
    )
    quarantine_rows = [
        row for row in compatibility_rows if row.get("eligible", "").lower() != "true"
    ]
    _write_csv(compatibility_rows, REPORT_FIELDS, compatibility_path)
    _write_csv(quarantine_rows, REPORT_FIELDS, output_dir / "elite_quarantine.csv")
    episodes = _metric_episodes(records)
    daily_rows = _daily_rows(episodes)
    episode_rows = _episode_rows(episodes)
    source_rows = _source_comparison_rows(episodes)
    coverage_rows = _coverage_rows(episodes)

    _write_csv(daily_rows, DAILY_FIELDS, output_dir / "elite_daily.csv")
    _write_csv(episode_rows, EPISODE_FIELDS, output_dir / "elite_episode_summary.csv")
    _write_csv(
        source_rows,
        SOURCE_COMPARISON_FIELDS,
        output_dir / "elite_source_comparison.csv",
    )
    _write_csv(coverage_rows, COVERAGE_FIELDS, output_dir / "elite_coverage_gap.csv")

    eligible_public_ids = {
        row["source_policy_id"]
        for row in compatibility_rows
        if row.get("eligible", "").lower() == "true"
        and any(artifact.source_policy_id == row["source_policy_id"] for artifact in artifacts)
    }
    turns_by_group = Counter(_source_group(record.action_origin) for record in records)
    result = EdaBuildResult(
        source_count=len(artifacts),
        eligible_source_count=len(eligible_public_ids),
        quarantine_source_count=len(artifacts) - len(eligible_public_ids),
        compatible_turn_count=len(records),
        episode_count=len(episodes),
    )
    _atomic_write_text(
        report_path,
        _report(
            result=result,
            turns_by_group=turns_by_group,
            compatibility_rows=compatibility_rows,
            coverage_rows=coverage_rows,
            episodes=episodes,
        ),
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = build_eda(
        manifest_path=args.manifest,
        decisions_path=args.decisions,
        output_dir=args.output_dir,
        report_path=args.report,
    )
    print(
        f"sources={result.source_count} eligible={result.eligible_source_count} "
        f"quarantined={result.quarantine_source_count} turns={result.compatible_turn_count} "
        f"episodes={result.episode_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
