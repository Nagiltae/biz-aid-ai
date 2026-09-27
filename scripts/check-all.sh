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
printf '\nN/A: product Unit/Component/E2E/AI Evaluation/Build; services and live data are unimplemented/unmeasured\n'
printf 'PENDING: Data Feasibility GO/DROP and human review; AGY evidence/scope status is reported by check-harness\n'
if [ "$failed" -ne 0 ]; then
  printf 'FAIL: one or more applicable validations failed\n' >&2
  exit 1
fi
printf 'PASS: all applicable Harness and local Phase 0 preparation validations\n'
