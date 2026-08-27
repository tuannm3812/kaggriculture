import csv
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from kaggriculture_lib.replay_provenance import (
    PublicArtifact,
    load_manifest,
    write_manifest,
)
from kaggriculture_lib.replay_schema import (
    ActionOrigin,
    DecisionRecord,
    NormalizedAction,
    read_decisions,
    write_decisions,
)

from scripts.build_elite_eda import build_eda
from scripts.validate_public_replays import (
    REPORT_FIELDS,
    _evaluate_artifact,
)


@dataclass(frozen=True)
class FixtureDataset:
    manifest: Path
    decisions: Path


def _observation(*, money: float, hands: int, quadrants: tuple[str, ...], shed: int):
    return {
        "player": 0,
        "day": 0,
        "hour": 0,
        "farms": [
            {
                "money": money,
                "hands": [[0, 0]] * hands,
                "unlocked_quadrants": list(quadrants),
                "tiles": [[{"kind": "PLANT", "crop": "WHEAT"}]],
            },
            {
                "money": 80,
                "hands": [],
                "unlocked_quadrants": ["NW"],
                "tiles": [[{}]],
            },
        ],
        "market": {"prices": {"WHEAT": 25}, "inventory": {"WHEAT": 10_000}},
        "private": {"shed": {"WHEAT": shed}, "inventories": [{}] * (hands + 1)},
    }


def _records(
    *,
    episode_id: str,
    source_policy_id: str,
    source_family: str,
    origin: ActionOrigin,
    hands: int,
    quadrants: tuple[str, ...],
    market: tuple[tuple[str | int, ...], ...],
):
    rows = []
    for step in range(719):
        money = 100.0 + step
        rows.append(
            DecisionRecord(
                episode_id=episode_id,
                source_policy_id=source_policy_id,
                source_family=source_family,
                step=step,
                day=step // 24,
                hour=step % 24,
                seat=0,
                opponent_family="starter",
                environment_version="1.32.4",
                configuration={"shedCapacity": 100},
                observation=_observation(
                    money=money,
                    hands=hands,
                    quadrants=quadrants,
                    shed=10,
                ),
                action=NormalizedAction(
                    farmer=("PASS",),
                    hands=tuple(("PASS",) for _ in range(hands)),
                    market=market if step == 0 else (),
                ),
                action_origin=origin,
                original_action=None,
                repair_reason=None,
                terminal_result="win" if step == 718 else None,
                final_banks=(850.0, 90.0) if step == 718 else None,
                compatibility_ok=True,
                legality_ok=True,
                completeness_ok=True,
                duplicate=False,
            )
        )
    return rows


def _write_compatibility(
    path: Path,
    artifacts: list[PublicArtifact],
    decisions: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=REPORT_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        for artifact in artifacts:
            writer.writerow(_evaluate_artifact(artifact, decisions))


def _fixture_dataset(tmp_path: Path) -> FixtureDataset:
    artifacts = [
        PublicArtifact(
            source_policy_id="public/elite",
            source_family="elite-family",
            owner="public",
            notebook_url="https://www.kaggle.com/code/public/elite",
            episode_id="elite-1",
            retrieved_at="2026-08-02T00:00:00+00:00",
            sha256="1" * 64,
            declared_environment="1.32.4",
        ),
        PublicArtifact(
            source_policy_id="public/missing",
            source_family="missing-family",
            owner="public",
            notebook_url="https://www.kaggle.com/code/public/missing",
            episode_id="missing-1",
            retrieved_at="2026-08-02T00:00:00+00:00",
            sha256="2" * 64,
            declared_environment="unknown",
        ),
        PublicArtifact(
            source_policy_id="public/versioned",
            source_family="versioned-family",
            owner="public",
            notebook_url="https://www.kaggle.com/code/public/versioned",
            episode_id=None,
            retrieved_at="2026-08-02T00:00:00+00:00",
            sha256="3" * 64,
            declared_environment="1.32.2",
        ),
    ]
    manifest = tmp_path / "manifest.json"
    decisions = tmp_path / "normalized"
    write_manifest(artifacts, manifest)
    write_decisions(
        _records(
            episode_id="elite-1",
            source_policy_id="public/elite",
            source_family="elite-family",
            origin=ActionOrigin.PUBLIC_ORIGINAL,
            hands=1,
            quadrants=("NW", "NE"),
            market=(("BUY_LAND",),),
        ),
        decisions / "public__elite.jsonl",
    )
    write_decisions(
        _records(
            episode_id="teacher-1",
            source_policy_id="task_teacher_v2",
            source_family="task-teacher-v2",
            origin=ActionOrigin.TEACHER,
            hands=0,
            quadrants=("NW",),
            market=(("HIRE",),),
        ),
        decisions / "teacher.jsonl",
    )
    return FixtureDataset(manifest=manifest, decisions=decisions)


def test_build_eda_outputs_are_deterministic_and_decision_complete(tmp_path: Path):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"
    report_path = tmp_path / "report.md"
    _write_compatibility(
        output_dir / "elite_compatibility.csv",
        load_manifest(fixture_dataset.manifest),
        fixture_dataset.decisions,
    )

    result = build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=output_dir,
        report_path=report_path,
    )
    first_bytes = {
        path.name: path.read_bytes()
        for path in sorted(output_dir.glob("elite_*.csv"))
    }
    first_report = report_path.read_bytes()
    second = build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=output_dir,
        report_path=report_path,
    )

    assert result.source_count == 3
    assert second == result
    assert first_bytes == {
        path.name: path.read_bytes()
        for path in sorted(output_dir.glob("elite_*.csv"))
    }
    assert first_report == report_path.read_bytes()
    for name in (
        "elite_daily.csv",
        "elite_episode_summary.csv",
        "elite_source_comparison.csv",
        "elite_coverage_gap.csv",
        "elite_compatibility.csv",
        "elite_quarantine.csv",
    ):
        assert (output_dir / name).exists()

    report = report_path.read_text(encoding="utf-8")
    for section in (
        "Capital and expansion",
        "Portfolio and market",
        "Labor and routing",
        "Storage and terminal",
        "Opponent and seat",
        "Coverage gap",
    ):
        assert f"## {section}" in report
    assert "Decision: KEEP" in report
    assert "Decision: CHANGE" in report
    assert "Decision: REJECT" in report
    assert "REJECT: insufficient compatible evidence" in report


def test_build_eda_quarantines_manifest_sources_when_compatibility_is_absent(tmp_path: Path):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"

    result = build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=output_dir,
        report_path=tmp_path / "report.md",
    )

    assert result.eligible_source_count == 0
    with (output_dir / "elite_quarantine.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 3
    assert {row["reason_codes"] for row in rows} == {"missing_compatibility_report"}

    with (output_dir / "elite_coverage_gap.csv").open(newline="", encoding="utf-8") as source:
        coverage = list(csv.DictReader(source))
    elite_diagnostics = {row["diagnostic"] for row in coverage if row["source_group"] == "elite"}
    assert {"crop_composition", "animal_composition", "price:__none__"} <= elite_diagnostics


def test_coverage_gap_records_zero_support_critical_actions(tmp_path: Path):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"
    _write_compatibility(
        output_dir / "elite_compatibility.csv",
        load_manifest(fixture_dataset.manifest),
        fixture_dataset.decisions,
    )
    build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=output_dir,
        report_path=tmp_path / "report.md",
    )

    with (output_dir / "elite_coverage_gap.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    teacher_buy_land = next(
        row
        for row in rows
        if row["source_group"] == "teacher"
        and row["diagnostic"] == "market_operation"
        and row["category"] == "BUY_LAND"
    )
    assert teacher_buy_land["count"] == "0"
    assert teacher_buy_land["critical_zero_support"] == "true"
    assert teacher_buy_land["distance_type"] == "jensen_shannon"
    assert teacher_buy_land["distance"] == "1.000000"

    teacher_land = next(
        row
        for row in rows
        if row["source_group"] == "teacher"
        and row["diagnostic"] == "land_count"
    )
    assert teacher_land["count"] == "719"
    assert teacher_land["median"] == "1.000000"
    assert teacher_land["distance_type"] == "standardized_median_difference"
    assert teacher_land["distance"] == "-1.000000"


@pytest.mark.parametrize(
    ("changes", "expected_reason"),
    [
        ({"source_family": "wrong-family"}, "unreproducible_source"),
        ({"episode_id": "wrong-episode"}, "unreproducible_source"),
        ({"compatibility_ok": False}, "invalid_action"),
        ({"duplicate": True}, "duplicate_record"),
        (
            {
                "action": NormalizedAction(
                    farmer=("PASS",),
                    hands=(("PASS",),),
                    market=(("HIRE",),),
                )
            },
            "action_digest_mismatch",
        ),
    ],
)
def test_build_eda_rechecks_public_decisions_against_compatibility_report(
    tmp_path: Path,
    changes,
    expected_reason: str,
):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"
    artifacts = load_manifest(fixture_dataset.manifest)
    _write_compatibility(
        output_dir / "elite_compatibility.csv",
        artifacts,
        fixture_dataset.decisions,
    )
    elite_path = fixture_dataset.decisions / "public__elite.jsonl"
    elite_records = list(read_decisions(elite_path))
    elite_records[0] = replace(elite_records[0], **changes)
    write_decisions(elite_records, elite_path)

    result = build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=output_dir,
        report_path=tmp_path / "report.md",
    )

    assert result.eligible_source_count == 0
    with (output_dir / "elite_quarantine.csv").open(newline="", encoding="utf-8") as source:
        rows = {row["source_policy_id"]: row for row in csv.DictReader(source)}
    assert expected_reason in rows["public/elite"]["reason_codes"].split(";")


def test_build_eda_rejects_stale_or_identity_mismatched_compatibility_rows(tmp_path: Path):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"
    artifacts = load_manifest(fixture_dataset.manifest)
    compatibility_path = output_dir / "elite_compatibility.csv"
    _write_compatibility(compatibility_path, artifacts, fixture_dataset.decisions)
    with compatibility_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    stale = dict(rows[0])
    stale["source_policy_id"] = "stale/source"
    rows.append(stale)
    with compatibility_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=REPORT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="not present in manifest"):
        build_eda(
            manifest_path=fixture_dataset.manifest,
            decisions_path=fixture_dataset.decisions,
            output_dir=output_dir,
            report_path=tmp_path / "report.md",
        )


def test_build_eda_rejects_compatibility_identity_mismatch(tmp_path: Path):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"
    artifacts = load_manifest(fixture_dataset.manifest)
    compatibility_path = output_dir / "elite_compatibility.csv"
    _write_compatibility(compatibility_path, artifacts, fixture_dataset.decisions)
    with compatibility_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    rows[0]["source_family"] = "wrong-family"
    with compatibility_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=REPORT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="manifest identity mismatch"):
        build_eda(
            manifest_path=fixture_dataset.manifest,
            decisions_path=fixture_dataset.decisions,
            output_dir=output_dir,
            report_path=tmp_path / "report.md",
        )


def test_build_eda_excludes_unrelated_or_incomplete_teacher_trajectories(tmp_path: Path):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"
    artifacts = load_manifest(fixture_dataset.manifest)
    _write_compatibility(
        output_dir / "elite_compatibility.csv",
        artifacts,
        fixture_dataset.decisions,
    )
    teacher_path = fixture_dataset.decisions / "teacher.jsonl"
    teacher_records = list(read_decisions(teacher_path))
    unrelated = [
        replace(
            record,
            episode_id="other-teacher-1",
            source_policy_id="other_teacher",
            source_family="other-teacher",
        )
        for record in teacher_records
    ]
    write_decisions(unrelated, fixture_dataset.decisions / "other-teacher.jsonl")
    write_decisions(
        [replace(teacher_records[0], episode_id="incomplete-teacher")],
        fixture_dataset.decisions / "incomplete-teacher.jsonl",
    )

    result = build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=output_dir,
        report_path=tmp_path / "report.md",
    )

    assert result.compatible_turn_count == 1438
    with (output_dir / "elite_daily.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert {row["source_policy_id"] for row in rows} == {"public/elite", "task_teacher_v2"}


def test_build_eda_rejects_decisions_without_a_complete_teacher_episode(tmp_path: Path):
    fixture_dataset = _fixture_dataset(tmp_path)
    output_dir = tmp_path / "analysis"
    artifacts = load_manifest(fixture_dataset.manifest)
    _write_compatibility(
        output_dir / "elite_compatibility.csv",
        artifacts,
        fixture_dataset.decisions,
    )
    teacher_path = fixture_dataset.decisions / "teacher.jsonl"
    teacher_records = list(read_decisions(teacher_path))
    teacher_path.unlink()
    write_decisions(
        teacher_records[:1],
        fixture_dataset.decisions / "incomplete-teacher.jsonl",
    )

    result = build_eda(
        manifest_path=fixture_dataset.manifest,
        decisions_path=fixture_dataset.decisions,
        output_dir=output_dir,
        report_path=tmp_path / "report.md",
    )

    assert result.compatible_turn_count == 719
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert report.count("Decision: REJECT: insufficient compatible evidence") == 6
