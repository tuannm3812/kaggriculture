#!/usr/bin/env python3
"""Validate normalized public replay records and emit quarantine reports."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from kaggriculture_lib.replay_compat import (
    EXPECTED_ACTION_CALLS,
    PINNED_ENVIRONMENT_VERSION,
    validate_action_shape,
)
from kaggriculture_lib.replay_provenance import PublicArtifact, load_manifest
from kaggriculture_lib.replay_schema import DecisionRecord, read_decisions


REPORT_FIELDS = (
    "source_policy_id",
    "source_family",
    "episode_id",
    "declared_environment",
    "replay_environment",
    "status",
    "action_calls",
    "exception",
    "issue_codes",
    "final_bank_0",
    "final_bank_1",
    "action_sha256",
    "eligible",
    "reason_codes",
)


def _empty_row(artifact: PublicArtifact, reason_codes: Sequence[str]) -> dict[str, str]:
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
        "reason_codes": ";".join(reason_codes),
    }


def _recording_path(artifact: PublicArtifact, input_dir: Path) -> Path | None:
    if artifact.episode_id is None:
        return None
    candidates = (
        input_dir / f"{artifact.source_policy_id}.jsonl",
        input_dir / f"{artifact.source_policy_id.replace('/', '__')}.jsonl",
        input_dir / f"{artifact.episode_id}.jsonl",
        input_dir / f"{artifact.sha256}.jsonl",
    )
    return next((path for path in candidates if path.is_file()), None)


def _expected_hands(record: DecisionRecord) -> int | None:
    try:
        player = record.observation["player"]
        hands = record.observation["farms"][player]["hands"]
    except (KeyError, IndexError, TypeError):
        return None
    return len(hands) if isinstance(hands, (list, tuple)) else None


def _digest_actions(records: Sequence[DecisionRecord]) -> str:
    digest = sha256()
    for record in records:
        action = record.action
        value = {
            "farmer": list(action.farmer),
            "hands": [list(command) for command in action.hands],
            "market": [list(command) for command in action.market],
        }
        digest.update(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _evaluate_records(artifact: PublicArtifact, records: Sequence[DecisionRecord]) -> dict[str, str]:
    reasons: list[str] = []
    issue_codes: set[str] = set()
    environments = {record.environment_version for record in records}
    replay_environment = next(iter(environments)) if len(environments) == 1 else "mixed"

    if (
        artifact.declared_environment not in {PINNED_ENVIRONMENT_VERSION, "unknown"}
        or environments != {PINNED_ENVIRONMENT_VERSION}
    ):
        reasons.append("version_mismatch")

    identity_matches = all(
        record.source_policy_id == artifact.source_policy_id
        and record.source_family == artifact.source_family
        and record.episode_id == artifact.episode_id
        for record in records
    )
    seats = {record.seat for record in records}
    first_configuration = records[0].configuration if records else None
    first_opponent = records[0].opponent_family if records else None
    provenance_consistent = all(
        record.configuration == first_configuration
        and record.opponent_family == first_opponent
        and record.observation.get("player") == record.seat
        for record in records
    )
    if not records or not identity_matches or len(seats) != 1 or not provenance_consistent:
        reasons.append("unreproducible_source")

    complete_steps = [record.step for record in records] == list(range(EXPECTED_ACTION_CALLS))
    terminal_evidence = bool(
        records
        and records[-1].terminal_result
        and records[-1].final_banks is not None
    )
    incomplete = (
        len(records) != EXPECTED_ACTION_CALLS
        or not complete_steps
        or any(not record.completeness_ok for record in records)
        or not terminal_evidence
    )
    status = "INCOMPLETE" if incomplete else "DONE"
    if incomplete:
        reasons.append("incomplete_game")

    for record in records:
        expected_hands = _expected_hands(record)
        if expected_hands is None:
            issue_codes.add("unreadable_observation")
            continue
        issue_codes.update(issue.code for issue in validate_action_shape(record.action, expected_hands))
        if not record.compatibility_ok:
            issue_codes.add("compatibility_flag")
        if not record.legality_ok:
            issue_codes.add("legality_flag")
    if issue_codes:
        reasons.append("invalid_action")

    final_banks = next((record.final_banks for record in reversed(records) if record.final_banks is not None), None)
    eligible = not reasons
    return {
        "source_policy_id": artifact.source_policy_id,
        "source_family": artifact.source_family,
        "episode_id": artifact.episode_id or "",
        "declared_environment": artifact.declared_environment,
        "replay_environment": replay_environment,
        "status": status,
        "action_calls": str(len(records)),
        "exception": "",
        "issue_codes": ";".join(sorted(issue_codes)),
        "final_bank_0": "" if final_banks is None else str(final_banks[0]),
        "final_bank_1": "" if final_banks is None else str(final_banks[1]),
        "action_sha256": _digest_actions(records),
        "eligible": str(eligible).lower(),
        "reason_codes": ";".join(reasons),
    }


def _evaluate_artifact(artifact: PublicArtifact, input_dir: Path) -> dict[str, str]:
    initial_reasons: list[str] = []
    if artifact.declared_environment not in {PINNED_ENVIRONMENT_VERSION, "unknown"}:
        initial_reasons.append("version_mismatch")
    path = _recording_path(artifact, input_dir)
    if path is None:
        initial_reasons.append("missing_episode")
        return _empty_row(artifact, initial_reasons)
    try:
        records = list(read_decisions(path))
    except (OSError, ValueError) as error:
        row = _empty_row(artifact, [*initial_reasons, "unreproducible_source"])
        row["status"] = "ERROR"
        row["exception"] = f"{type(error).__name__}: {error}"
        return row
    return _evaluate_records(artifact, records)


def _write_rows(rows: Sequence[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=REPORT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quarantine", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    rows = [_evaluate_artifact(artifact, args.input) for artifact in load_manifest(args.manifest)]
    _write_rows(rows, args.output)
    _write_rows([row for row in rows if row["eligible"] != "true"], args.quarantine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
