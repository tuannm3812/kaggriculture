from datetime import datetime, timezone
from pathlib import Path

import pytest

from kaggriculture_lib.replay_provenance import (
    PublicArtifact,
    load_manifest,
    sha256_file,
    write_manifest,
)


def test_sha256_file_is_content_addressed(tmp_path: Path):
    source = tmp_path / "source.ipynb"
    source.write_bytes(b"public notebook bytes")
    assert sha256_file(source) == "5eb611ebdfd3dcc277d94d8e7684a4592caad2f5de7c9fb443f94e468385b5ce"


def test_manifest_round_trip_is_sorted_and_lossless(tmp_path: Path):
    fetched = datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc)
    records = [
        PublicArtifact(
            source_policy_id="prvsiyan/frontier-v12",
            source_family="radiant-89256171",
            owner="prvsiyan",
            notebook_url="https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-lab-high-score-visuals",
            episode_id="89256171",
            retrieved_at=fetched.isoformat(),
            sha256="a" * 64,
            declared_environment="1.32.2",
        )
    ]
    path = tmp_path / "manifest.json"
    write_manifest(records, path)
    assert load_manifest(path) == records


def test_artifact_rejects_missing_attribution():
    with pytest.raises(ValueError, match="owner"):
        PublicArtifact(
            source_policy_id="x",
            source_family="family",
            owner="",
            notebook_url="https://www.kaggle.com/code/a/b",
            episode_id=None,
            retrieved_at="2026-08-02T07:00:00+00:00",
            sha256="a" * 64,
            declared_environment="unknown",
        )
