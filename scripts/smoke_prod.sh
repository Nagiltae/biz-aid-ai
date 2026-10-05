#!/usr/bin/env bash
# 배포 후 최소 점검. 체험 계정 1개와 AI 질문 1개를 실제로 만든다(자동 재시도 없음).
set -euo pipefail
[[ $# == 1 ]] || { echo '사용법: smoke_prod.sh <https://서비스주소>' >&2; exit 2; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT/scripts/prod_smoke.py" "$1"
