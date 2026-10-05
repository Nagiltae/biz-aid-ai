#!/usr/bin/env bash
# WHY: allowlist 방식이라 소스·Harness·Secret·데이터가 새로 늘어도 배포 묶음에 섞이지 않는다.
set -euo pipefail
[[ $# == 1 && ! -e "$1" ]] || { echo '사용법: make_deploy_bundle.sh <새 출력.tar.gz>' >&2; exit 2; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# WHY: macOS의 AppleDouble 메타데이터는 서버 입력이 아니므로 압축에 넣지 않는다.
COPYFILE_DISABLE=1 tar -czf "$1" -C "$ROOT" docker-compose.prod.yml docker-compose.restore.yml Caddyfile .env.prod.example scripts/deploy.sh scripts/smoke_prod.sh scripts/prod_smoke.py scripts/restore_deploy_data.sh scripts/restore_deploy_data.py docs/deployment.md
echo '서버 실행 묶음 생성 완료(코드 저장소·Secret·데이터 제외).'
