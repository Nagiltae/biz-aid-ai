#!/usr/bin/env bash
# 개발 환경(MySQL·Qdrant·FastAPI·Spring·React)을 명령 하나로 다룬다. Ollama는 host에서 따로 실행한다.
# 내부는 기존 방식대로 docker compose --env-file .env.dev --profile app 이다. .env.dev 내용은 출력하지 않는다.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICES="mysql qdrant fastapi backend frontend"

usage() {
  cat <<'EOF'
사용법: scripts/dev.sh <명령> [서비스]
  up                 전체 개발 환경 시작(이미지가 없을 때만 빌드)
  down               전체 중지·컨테이너 제거(데이터 volume은 지우지 않음)
  restart <서비스>   서비스 다시 시작
  logs <서비스>      서비스 로그 보기(최근 200줄부터 계속)
  status             서비스 상태
  build <서비스>     이미지 다시 빌드(의존성을 바꿨을 때만)
서비스: mysql qdrant fastapi backend frontend
EOF
}

compose() {
  # BOUNDARY: 다른 .env 파일을 자동으로 읽지 않고 dev Profile 파일만 쓴다(check-all의 compose 검사와 같은 방식).
  COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file "$ROOT/.env.dev" --profile app -f "$ROOT/docker-compose.yml" "$@"
}

require_service() {
  if [[ -z "${1:-}" || " $SERVICES " != *" $1 "* ]]; then
    echo "서비스 이름이 필요합니다: $SERVICES" >&2
    exit 2
  fi
}

if [[ ! -f "$ROOT/.env.dev" ]]; then
  echo ".env.dev가 없습니다. .env.example을 참고해 저장소 루트에 만드세요." >&2
  exit 1
fi
# 모델 artifact는 process environment로만 받는다. 없으면 기본 cache 경로를 쓴다(이미지에는 넣지 않음).
export BIZAID_DOCLING_ARTIFACTS_PATH="${BIZAID_DOCLING_ARTIFACTS_PATH:-$HOME/.cache/biz-aid/docling-artifacts}"

command="${1:-}"
case "$command" in
  up)
    if [[ ! -d "$BIZAID_DOCLING_ARTIFACTS_PATH/BAAI--bge-m3-embedding" ]]; then
      echo "BGE-M3 모델 artifact가 없습니다: $BIZAID_DOCLING_ARTIFACTS_PATH (scripts/provision_docling_artifacts.py 참고)" >&2
      exit 1
    fi
    # BOUNDARY: profile이 없는 phase0(Phase 0 증거 도구)까지 올라오지 않게 개발 서비스 이름을 명시한다.
    compose up -d $SERVICES
    if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
      echo "주의: host Ollama(127.0.0.1:11434)에 연결되지 않습니다. 질문 처리 전에 Ollama를 실행하세요." >&2
    fi
    compose ps $SERVICES
    ;;
  down)
    compose down
    ;;
  restart)
    require_service "${2:-}"
    compose restart "$2"
    ;;
  logs)
    require_service "${2:-}"
    compose logs --tail 200 -f "$2"
    ;;
  status)
    compose ps $SERVICES
    ;;
  build)
    require_service "${2:-}"
    if [[ "$2" == "mysql" || "$2" == "qdrant" ]]; then
      echo "$2는 공개 이미지를 그대로 쓰므로 빌드하지 않습니다." >&2
      exit 2
    fi
    compose build "$2"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
