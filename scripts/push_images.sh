#!/usr/bin/env bash
# BOUNDARY: 이번 검증은 --build-only. 실제 push는 사용자가 Docker login 뒤 명시 실행한다.
set -euo pipefail
[[ $# == 2 || ( $# == 3 && "$3" == --build-only ) ]] || { echo '사용법: push_images.sh <Docker Hub 사용자/저장소> <태그> [--build-only]' >&2; exit 2; }
[[ "$1" =~ ^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_.-]*$ && "$2" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,100}$ ]] || { echo '저장소/태그 형식 오류' >&2; exit 2; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for service in frontend backend fastapi; do
  context="$ROOT"; file="$ROOT/backend/Dockerfile"
  if [[ "$service" == frontend ]]; then context="$ROOT/frontend"; file="$context/Dockerfile.prod"; fi
  if [[ "$service" == fastapi ]]; then file="$ROOT/data-pipeline/Dockerfile.prod"; fi
  docker buildx build --platform linux/arm64 --load -f "$file" -t "$1:$service-$2" "$context"
done
for service in frontend backend fastapi; do
  docker image inspect --format '{{.Os}}/{{.Architecture}} {{.Size}} bytes' "$1:$service-$2"
done
if [[ "${3:-}" != --build-only ]]; then
  for service in frontend backend fastapi; do docker push "$1:$service-$2"; done
fi
