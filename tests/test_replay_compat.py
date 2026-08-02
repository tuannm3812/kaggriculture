import csv
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

import pytest

from kaggriculture_lib.replay_provenance import PublicArtifact, write_manifest
from kaggriculture_lib.replay_compat import (
    run_tape_compatibility,
    validate_action_shape,
)
from kaggriculture_lib.replay_schema import (
    ActionOrigin,
    DecisionRecord,
    NormalizedAction,
    write_decisions,
)


def _artifact(*, episode_id="episode-1", declared_environment="1.29.3"):
    return PublicArtifact(
        source_policy_id="owner/policy",
        source_family="family",
        owner="owner",
        notebook_url="https://example.test/policy",
        episode_id=episode_id,
        retrieved_at="2026-08-02T00:00:00+00:00",
        sha256="a" * 64,
        declared_environment=declared_environment,
    )


def _pass_record(step, *, legality_ok=True, environment_version="1.29.3"):
    return DecisionRecord(
        episode_id="episode-1",
        source_policy_id="owner/policy",
        source_family="family",
        step=step,
        day=step // 24,
        hour=step % 24,
        seat=0,
        opponent_family="starter",
        environment_version=environment_version,
        configuration={"seed": 31},
        observation={"farms": [{"hands": []}, {"hands": []}], "player": 0},
        action=NormalizedAction(("PASS",), (), ()),
        action_origin=ActionOrigin.PUBLIC_ORIGINAL,
        original_action=None,
        repair_reason=None,
        terminal_result="win" if step == 718 else None,
        final_banks=(2100.0, 1900.0) if step == 718 else None,
        compatibility_ok=True,
        legality_ok=legality_ok,
        completeness_ok=True,
        duplicate=False,
    )


def test_shape_validator_rejects_wrong_hand_count():
    action = NormalizedAction(("PASS",), (("PASS",),), ())
    issues = validate_action_shape(action, expected_hands=0)
    assert [issue.code for issue in issues] == ["hand_count_mismatch"]


def test_shape_validator_rejects_more_than_ten_market_orders():
    action = NormalizedAction(("PASS",), (), tuple(("HIRE",) for _ in range(11)))
    issues = validate_action_shape(action, expected_hands=0)
    assert "market_order_limit" in {issue.code for issue in issues}


def test_pass_tape_completes_both_seats_under_pinned_runtime():
    def pass_policy(obs, config=None):
        hands = len(obs["farms"][obs["player"]]["hands"])
        return {"farmer": ["PASS"], "hands": [["PASS"]] * hands, "market": []}

    reports = [run_tape_compatibility(pass_policy, seed=31, seat=seat) for seat in (0, 1)]
    assert all(report.environment_version == "1.29.3" for report in reports)
    assert all(report.status == "DONE" for report in reports)
    assert all(report.action_calls == 719 for report in reports)


def test_runtime_rejects_boolean_seat():
    with pytest.raises(ValueError, match="seat"):
        run_tape_compatibility(lambda obs: {}, seed=31, seat=False)


def test_runtime_reports_environment_construction_failure(monkeypatch):
    def fail_construction(*args, **kwargs):
        raise RuntimeError("environment unavailable")

    monkeypatch.setattr("kaggriculture_lib.replay_compat.make", fail_construction)

    report = run_tape_compatibility(lambda obs: {}, seed=31, seat=0)

    assert report.status == "ERROR"
    assert report.action_calls == 0
    assert report.exception == "RuntimeError: environment unavailable"
    assert report.issues == ()
    assert report.final_banks is None
    assert report.state_rewards is None
    assert report.score is None
    assert report.action_sha256 == sha256(b"").hexdigest()
    assert report.eligible is False


def test_validation_cli_quarantines_manifest_entry_without_episode(tmp_path):
    from scripts.validate_public_replays import main

    manifest = tmp_path / "manifest.json"
    input_dir = tmp_path / "normalized"
    compatibility = tmp_path / "compatibility.csv"
    quarantine = tmp_path / "quarantine.csv"
    input_dir.mkdir()
    write_manifest(
        [_artifact(episode_id=None)],
        manifest,
    )

    assert main(
        [
            "--manifest",
            str(manifest),
            "--input",
            str(input_dir),
            "--output",
            str(compatibility),
            "--quarantine",
            str(quarantine),
        ]
    ) == 0

    with compatibility.open(newline="", encoding="utf-8") as source:
        compatibility_rows = list(csv.DictReader(source))
    with quarantine.open(newline="", encoding="utf-8") as source:
        quarantine_rows = list(csv.DictReader(source))
    assert compatibility_rows[0]["eligible"] == "false"
    assert quarantine_rows[0]["reason_codes"] == "missing_episode"


def test_validation_cli_admits_complete_pinned_decision_tape(tmp_path):
    from scripts.validate_public_replays import main

    manifest = tmp_path / "manifest.json"
    input_dir = tmp_path / "normalized"
    compatibility = tmp_path / "compatibility.csv"
    quarantine = tmp_path / "quarantine.csv"
    write_manifest([_artifact()], manifest)
    write_decisions((_pass_record(step) for step in range(719)), input_dir / "episode-1.jsonl")

    assert main(
        [
            "--manifest",
            str(manifest),
            "--input",
            str(input_dir),
            "--output",
            str(compatibility),
            "--quarantine",
            str(quarantine),
        ]
    ) == 0

    with compatibility.open(newline="", encoding="utf-8") as source:
        row = next(csv.DictReader(source))
    with quarantine.open(newline="", encoding="utf-8") as source:
        quarantine_rows = list(csv.DictReader(source))
    assert row["eligible"] == "true"
    assert row["status"] == "DONE"
    assert row["action_calls"] == "719"
    assert row["final_bank_0"] == "2100.0"
    assert len(row["action_sha256"]) == 64
    assert quarantine_rows == []


def test_record_evaluation_requires_terminal_evidence():
    from scripts.validate_public_replays import _evaluate_records

    records = [_pass_record(step) for step in range(719)]
    records[-1] = replace(records[-1], terminal_result=None, final_banks=None)
    row = _evaluate_records(_artifact(), records)
    assert row["eligible"] == "false"
    assert "incomplete_game" in row["reason_codes"].split(";")


def test_record_evaluation_rejects_spliced_episode_provenance():
    from scripts.validate_public_replays import _evaluate_records

    records = [_pass_record(step) for step in range(719)]
    records[300] = replace(
        records[300],
        opponent_family="different-opponent",
        configuration={"seed": 99},
        observation={"farms": [{"hands": []}, {"hands": []}], "player": 1},
    )
    row = _evaluate_records(_artifact(), records)
    assert row["eligible"] == "false"
    assert "unreproducible_source" in row["reason_codes"].split(";")


def test_validation_cli_runs_directly_from_repository_root():
    repository_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "scripts/validate_public_replays.py", "--help"],
        cwd=repository_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
