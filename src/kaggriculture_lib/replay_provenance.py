"""Immutable provenance records for approved public replay artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from json import dump, load
from pathlib import Path
from string import hexdigits
from typing import Sequence


@dataclass(frozen=True)
class PublicArtifact:
    """Attribution and byte identity for one public notebook or replay artifact."""

    source_policy_id: str
    source_family: str
    owner: str
    notebook_url: str
    episode_id: str | None
    retrieved_at: str
    sha256: str
    declared_environment: str

    def __post_init__(self) -> None:
        required = {
            "source_policy_id": self.source_policy_id,
            "source_family": self.source_family,
            "owner": self.owner,
            "notebook_url": self.notebook_url,
            "retrieved_at": self.retrieved_at,
            "declared_environment": self.declared_environment,
        }
        for name, value in required.items():
            if not value:
                raise ValueError(f"{name} must be non-empty")
        if len(self.sha256) != 64 or any(char not in hexdigits for char in self.sha256.lower()):
            raise ValueError("sha256 must contain 64 hexadecimal characters")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of *path* without decoding its bytes."""
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_unique(records: Sequence[PublicArtifact]) -> None:
    policy_ids: set[str] = set()
    artifact_ids: set[tuple[str, str]] = set()
    for record in records:
        if record.source_policy_id in policy_ids:
            raise ValueError(f"duplicate source_policy_id: {record.source_policy_id}")
        artifact_id = (record.sha256, record.source_policy_id)
        if artifact_id in artifact_ids:
            raise ValueError(f"duplicate artifact record: {artifact_id}")
        policy_ids.add(record.source_policy_id)
        artifact_ids.add(artifact_id)


def load_manifest(path: Path) -> list[PublicArtifact]:
    """Load a manifest and verify that its policy identifiers are unique."""
    with path.open(encoding="utf-8") as manifest:
        entries = load(manifest)
    if not isinstance(entries, list):
        raise ValueError("manifest must be a JSON array")
    records = [PublicArtifact(**entry) for entry in entries]
    _validate_unique(records)
    return records


def write_manifest(records: Sequence[PublicArtifact], path: Path) -> None:
    """Write records in stable policy-ID order as canonical pretty JSON."""
    _validate_unique(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_records = sorted(records, key=lambda record: record.source_policy_id)
    with path.open("w", encoding="utf-8") as manifest:
        dump([asdict(record) for record in ordered_records], manifest, indent=2, sort_keys=True)
        manifest.write("\n")
