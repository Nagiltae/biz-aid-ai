#!/usr/bin/env bash
# 비밀값을 읽거나 echo하지 않는다. Compose/일회성 client가 서버 process 환경으로 받는다.
set -euo pipefail
[[ $# -ge 2 ]] || { echo '사용법: restore_deploy_data.sh <programs|qdrant|models|models-check|certs> <디렉터리> [--model-path <빈 모델 경로>]' >&2; exit 2; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# WHY: 동일 서버에서 두 복원 실행이 빈 목적지 검사를 동시에 통과하지 않게 한다.
exec flock --nonblock "$ROOT/.restore.lock" python3 "$ROOT/scripts/restore_deploy_data.py" "$@"
