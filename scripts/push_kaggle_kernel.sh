#!/usr/bin/env bash
# Push the platform smoke test notebook to its Kaggle kernel.
#
# Copies the source notebook (the single source of truth, in notebooks/)
# into its kernel-metadata.json folder under notebooks/kernels/, then runs
# `kaggle kernels push`. The copied .ipynb is gitignored and regenerated
# every run, so notebooks/ never has two versions to keep in sync by hand.
#
# Usage: scripts/push_kaggle_kernel.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTEBOOK="00_platform_smoke_test.ipynb"
KERNEL_DIR="$REPO_ROOT/notebooks/kernels/platform_smoke_test"

if command -v kaggle >/dev/null 2>&1; then
  KAGGLE=kaggle
elif [ -x "/Users/tuannm3812/Library/Python/3.9/bin/kaggle" ]; then
  KAGGLE="/Users/tuannm3812/Library/Python/3.9/bin/kaggle"
else
  echo "kaggle CLI not found on PATH or at the known local install path." >&2
  exit 1
fi

cp "$REPO_ROOT/notebooks/$NOTEBOOK" "$KERNEL_DIR/$NOTEBOOK"
"$KAGGLE" kernels push -p "$KERNEL_DIR"
