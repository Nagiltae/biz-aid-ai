#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for command in bash git python3 docker; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'FAIL: required command missing: %s\n' "$command" >&2
    exit 1
  fi
done
exec python3 -B "$SCRIPT_DIR/lib/validate.py" setup
