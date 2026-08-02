"""Hash approved public notebooks and write their attributable manifest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from kaggriculture_lib.replay_provenance import PublicArtifact, sha256_file, write_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True, help="local JSON artifact specification")
    parser.add_argument("--output", type=Path, required=True, help="tracked manifest JSON output path")
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="OWNER/SLUG=PATH",
        help="override an artifact raw_path from the local specification",
    )
    return parser.parse_args()


def artifact_overrides(values: list[str]) -> dict[str, Path]:
    """Parse policy-ID-to-local-path overrides supplied on the command line."""
    overrides: dict[str, Path] = {}
    for value in values:
        policy_id, separator, raw_path = value.partition("=")
        if not separator or not policy_id or not raw_path:
            raise ValueError("--artifact must use OWNER/SLUG=PATH")
        if policy_id in overrides:
            raise ValueError(f"duplicate --artifact policy ID: {policy_id}")
        overrides[policy_id] = Path(raw_path)
    return overrides


def main() -> None:
    args = parse_args()
    overrides = artifact_overrides(args.artifact)
    with args.spec.open(encoding="utf-8") as specification:
        entries = json.load(specification)
    if not isinstance(entries, list):
        raise ValueError("artifact specification must be a JSON array")

    retrieved_at = datetime.now(timezone.utc).isoformat()
    records = []
    for entry in entries:
        policy_id = entry["source_policy_id"]
        raw_path = overrides.get(policy_id, Path(entry["raw_path"]))
        records.append(
            PublicArtifact(
                source_policy_id=policy_id,
                source_family=entry["source_family"],
                owner=entry["owner"],
                notebook_url=entry["notebook_url"],
                episode_id=entry.get("episode_id"),
                retrieved_at=retrieved_at,
                sha256=sha256_file(raw_path),
                declared_environment=entry["declared_environment"],
            )
        )
    write_manifest(records, args.output)


if __name__ == "__main__":
    main()
