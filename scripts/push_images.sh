#!/usr/bin/env bash
# BOUNDARY: 이번 검증은 --build-only. 실제 push는 사용자가 Docker login 뒤 명시 실행한다.
set -euo pipefail
[[ $# -ge 2 ]] || { echo '사용법: push_images.sh <Docker Hub 사용자/저장소> <태그> [--build-only] [--platform linux/amd64|linux/arm64]' >&2; exit 2; }
[[ "$1" =~ ^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_.-]*$ && "$2" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,100}$ ]] || { echo '저장소/태그 형식 오류' >&2; exit 2; }
repository="$1"; tag="$2"; platform=linux/amd64; build_only=false
shift 2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-only) build_only=true; shift ;;
    --platform)
      [[ $# -ge 2 && ( "$2" == linux/amd64 || "$2" == linux/arm64 ) ]] || { echo '지원 플랫폼: linux/amd64 또는 linux/arm64' >&2; exit 2; }
      platform="$2"; shift 2 ;;
    *) echo '알 수 없는 옵션' >&2; exit 2 ;;
  esac
done
# BOUNDARY: 서버 CPU와 같은 단일 플랫폼만 만든다. 기본값은 실제 Ubuntu x86_64 서버다.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for service in frontend backend fastapi; do
  context="$ROOT"; file="$ROOT/backend/Dockerfile"
  if [[ "$service" == frontend ]]; then context="$ROOT/frontend"; file="$context/Dockerfile.prod"; fi
  if [[ "$service" == fastapi ]]; then file="$ROOT/data-pipeline/Dockerfile.prod"; fi
  docker buildx build --platform "$platform" --load -f "$file" -t "$repository:$service-$tag" "$context"
done
for service in frontend backend fastapi; do
  actual="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$repository:$service-$tag")"
  [[ "$actual" == "$platform" ]] || { echo '빌드된 이미지 플랫폼 불일치' >&2; exit 1; }
  docker image inspect --format '{{.Os}}/{{.Architecture}} {{.Size}} bytes' "$repository:$service-$tag"
done
if [[ "$build_only" == false ]]; then
  for service in frontend backend fastapi; do docker push "$repository:$service-$tag"; done
fi
