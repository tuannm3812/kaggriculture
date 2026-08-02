from dataclasses import replace
from pathlib import Path
import re

import pytest

from kaggriculture_lib.replay_schema import (
    ActionOrigin,
    DecisionRecord,
    NormalizedAction,
    normalize_action,
    read_decisions,
    write_decisions,
)


@pytest.fixture
def sample_record() -> DecisionRecord:
    return DecisionRecord(
        episode_id="89256171",
        source_policy_id="prvsiyan/frontier-v12",
        source_family="radiant-89256171",
        step=25,
        day=1,
        hour=1,
        seat=0,
        opponent_family="baseline",
        environment_version="1.32.2",
        configuration={"seed": 7, "board": ["north", "south"]},
        observation={"bank": 12.5, "field": {"crop": "MELON"}},
        action=NormalizedAction(("PLANT", "MELON"), (("MOVE", "N"),), (("SELL", "MILK", 4),)),
        action_origin=ActionOrigin.PUBLIC_ORIGINAL,
        original_action=None,
        repair_reason=None,
        terminal_result="win",
        final_banks=(21.0, 19.5),
        compatibility_ok=True,
        legality_ok=True,
        completeness_ok=True,
        duplicate=False,
    )


def test_normalize_action_preserves_order_and_quantities():
    raw = {
        "farmer": ["PLANT", "MELON"],
        "hands": [["MOVE", "N"], ["PASS"]],
        "market": [["SELL", "MILK", 4], ["HIRE"]],
    }
    normalized = normalize_action(raw)
    assert normalized.farmer == ("PLANT", "MELON")
    assert normalized.hands == (("MOVE", "N"), ("PASS",))
    assert normalized.market == (("SELL", "MILK", 4), ("HIRE",))


def test_repaired_record_keeps_original_and_reason(sample_record):
    repaired = replace(
        sample_record,
        action_origin=ActionOrigin.PUBLIC_REPAIRED,
        original_action=sample_record.action,
        action=NormalizedAction(("PASS",), (), ()),
        repair_reason="seed unavailable",
    )
    assert repaired.original_action != repaired.action
    assert repaired.repair_reason == "seed unavailable"


def test_jsonl_round_trip_is_lossless(tmp_path: Path, sample_record):
    path = tmp_path / "decisions.jsonl"
    write_decisions([sample_record], path)
    assert list(read_decisions(path)) == [sample_record]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"step": 24}, "step must equal day * 24 + hour"),
        ({"seat": 2}, "seat must be 0 or 1"),
        ({"final_banks": (1.0, float("inf"))}, "final_banks must be finite"),
    ],
)
def test_record_rejects_invalid_contract_values(sample_record, changes, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        replace(sample_record, **changes)


def test_record_rejects_repair_fields_for_original_action(sample_record):
    with pytest.raises(ValueError, match="repair fields are only allowed"):
        replace(sample_record, repair_reason="unnecessary")


def test_read_decisions_reports_malformed_row_with_path_and_line(tmp_path: Path, sample_record):
    path = tmp_path / "decisions.jsonl"
    write_decisions([sample_record], path)
    with path.open("a", encoding="utf-8") as destination:
        destination.write("not json\n")
    with pytest.raises(ValueError, match=rf"{path}:2: malformed JSON"):
        list(read_decisions(path))


def test_read_decisions_reports_schema_error_with_path_and_line(tmp_path: Path):
    path = tmp_path / "decisions.jsonl"
    path.write_text('{"episode_id": "one"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=rf"{path}:1: schema violation"):
        list(read_decisions(path))
