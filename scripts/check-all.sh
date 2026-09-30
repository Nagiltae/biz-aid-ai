#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
failed=0
for check in setup check-format check-lint check-contract check-integration check-git-tracked check-comments check-harness; do
  printf '\nRUN: %s.sh\n' "$check"
  if ! "$SCRIPT_DIR/$check.sh"; then
    failed=1
  fi
done
printf '\nN/A: Backend/Frontend build, Browser E2E, Live external services and V1 AI baseline rerun; run separately\n'
printf 'PENDING: current-task human review; AGY evidence/scope status is reported by check-harness\n'
if [ "$failed" -ne 0 ]; then
  printf 'FAIL: one or more applicable validations failed\n' >&2
  exit 1
fi
printf 'PASS: all applicable Harness, offline Contract and MySQL integration validations\n'
