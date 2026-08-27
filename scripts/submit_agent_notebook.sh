#!/usr/bin/env bash
# Package an agent, push a Kaggle submission notebook, wait for it to finish,
# then submit submission.tar.gz from that kernel to Kaggriculture.
#
# Usage:
#   scripts/submit_agent_notebook.sh agents/task_teacher_v5 \
#     -m "task_teacher_v5: land-only NE BUY_LAND champion"
#
# Requires: kaggle CLI authenticated as the kernel owner (tuannm3812).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -x "$REPO_ROOT/.venv/bin/kaggle" ]]; then
  KAGGLE="$REPO_ROOT/.venv/bin/kaggle"
elif command -v kaggle >/dev/null 2>&1; then
  KAGGLE=kaggle
else
  echo "kaggle CLI not found." >&2
  exit 1
fi

AGENT_DIR=""
MESSAGE=""
PUBLIC=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message)
      MESSAGE="${2:?}"
      shift 2
      ;;
    --public)
      PUBLIC="--public"
      shift
      ;;
    -*)
      echo "Unknown flag: $1" >&2
      exit 1
      ;;
    *)
      if [[ -z "$AGENT_DIR" ]]; then
        AGENT_DIR="$1"
        shift
      else
        echo "Unexpected arg: $1" >&2
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$AGENT_DIR" || -z "$MESSAGE" ]]; then
  echo "Usage: $0 agents/<version> -m \"submission message\" [--public]" >&2
  exit 1
fi

AGENT_NAME="$(basename "$AGENT_DIR")"
KERNEL_DIR="$REPO_ROOT/notebooks/kernels/${AGENT_NAME}_submission"
NOTEBOOK="03_${AGENT_NAME}_submission.ipynb"
if [[ -n "$PUBLIC" ]]; then
  SLUG="kaggriculture-htdc"
else
  SLUG="kaggriculture-htdc-submission"
fi
KERNEL_ID="tuannm3812/$SLUG"

PY="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

echo "==> Package $AGENT_DIR"
"$PY" scripts/package_agent.py "$AGENT_DIR"

echo "==> Build submission notebook"
"$PY" scripts/build_agent_submission_notebook.py "$AGENT_DIR" ${PUBLIC}

echo "==> Push kernel $KERNEL_ID"
cp "$REPO_ROOT/notebooks/$NOTEBOOK" "$KERNEL_DIR/$NOTEBOOK"
PUSH_OUT="$("$KAGGLE" kernels push -p "$KERNEL_DIR" 2>&1)"
echo "$PUSH_OUT"
VERSION="$(echo "$PUSH_OUT" | sed -n 's/.*Kernel version \([0-9][0-9]*\) successfully pushed.*/\1/p' | head -1)"
if [[ -z "$VERSION" ]]; then
  echo "Could not parse kernel version from push output." >&2
  exit 1
fi

echo "==> Wait for kernel version $VERSION to finish"
STATUS=""
for _ in $(seq 1 60); do
  OUT="$("$KAGGLE" kernels status "$KERNEL_ID" 2>&1 || true)"
  echo "$OUT"
  if echo "$OUT" | grep -q 'KernelWorkerStatus.COMPLETE'; then
    STATUS=complete
    break
  fi
  if echo "$OUT" | grep -qE 'KernelWorkerStatus\.(ERROR|CANCELLED|FAILED)'; then
    echo "Kernel failed; dumping logs:" >&2
    "$KAGGLE" kernels logs "$KERNEL_ID" 2>&1 | tail -100 >&2 || true
    exit 1
  fi
  sleep 15
done

if [[ "$STATUS" != "complete" ]]; then
  echo "Timed out waiting for kernel $KERNEL_ID" >&2
  exit 1
fi

echo "==> Submit version $VERSION from $KERNEL_ID"
"$KAGGLE" competitions submit kaggriculture \
  -k "$KERNEL_ID" \
  -f submission.tar.gz \
  -v "$VERSION" \
  -m "$MESSAGE"

echo "==> Recent submissions"
"$KAGGLE" competitions submissions kaggriculture | head -10
