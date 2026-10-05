#!/usr/bin/env bash
# BOUNDARY: 맥북에서 선택한 앱 이미지만 만든다. 서버 접속·운영 설정 열람·Git commit/push는 하지 않는다.
set -euo pipefail

usage() {
  echo '사용법: scripts/release.sh <새 태그> <frontend|backend|fastapi...> [--dry-run]' >&2
  exit 2
}
fail() { echo "FAIL: $*" >&2; exit 1; }

dry_run=false
arguments=()
for argument in "$@"; do
  case "$argument" in
    --dry-run) [[ "$dry_run" == false ]] || usage; dry_run=true ;;
    --*) usage ;;
    *) arguments+=("$argument") ;;
  esac
done
[[ ${arguments[1]+present} ]] || usage
tag="${arguments[0]}"
[[ "$tag" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,100}$ ]] || usage
services=()
selected_services=' '
for service in "${arguments[@]:1}"; do
  case "$service" in frontend|backend|fastapi) ;; *) usage ;; esac
  [[ "$selected_services" != *" $service "* ]] || usage
  selected_services+="$service "
  services+=("$service")
done
repository="${BIZAID_IMAGE_REPO:-nagt1997/bizaid}"
[[ "$repository" =~ ^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_.-]*$ ]] || usage
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
command -v git >/dev/null 2>&1 || fail 'Git이 없습니다.'
revision="$(git -C "$ROOT" rev-parse --verify HEAD 2>/dev/null)" || fail '커밋이 있는 Git 저장소에서 실행하세요.'

require_clean() {
  local changes current
  changes="$(git -C "$ROOT" status --porcelain --untracked-files=all)" || fail 'Git 상태를 확인하지 못했습니다.'
  [[ -z "$changes" ]] || fail '커밋하지 않은 변경이 있습니다. 먼저 검토·커밋하세요(dry-run도 같은 조건).'
  current="$(git -C "$ROOT" rev-parse --verify HEAD)" || fail 'Git 커밋을 확인하지 못했습니다.'
  [[ "$current" == "$revision" ]] || fail '릴리스 중 Git 커밋이 바뀌었습니다. push하지 않습니다.'
}
require_clean

build_arguments() {
  context="$ROOT"; file="$ROOT/backend/Dockerfile"
  if [[ "$service" == frontend ]]; then context="$ROOT/frontend"; file="$context/Dockerfile.prod"; fi
  if [[ "$service" == fastapi ]]; then file="$ROOT/data-pipeline/Dockerfile.prod"; fi
  build=(docker buildx build --platform linux/amd64 --load -f "$file" -t "$repository:$service-$tag"
         --label "org.opencontainers.image.revision=$revision" "$context")
}
print_command() { printf '%q ' "$@"; printf '\n'; }
server_steps() {
  echo '서버 .env.prod에서 선택한 서비스의 줄만 바꾸세요:'
  for service in "${services[@]}"; do
    case "$service" in
      frontend) echo "BIZAID_FRONTEND_TAG=$tag" ;;
      backend) echo "BIZAID_BACKEND_TAG=$tag" ;;
      fastapi) echo "BIZAID_FASTAPI_TAG=$tag" ;;
    esac
  done
  echo '서버에서 직접 실행:'
  echo 'prod config --quiet'
  echo "prod pull ${services[*]} && prod up -d --no-deps ${services[*]}"
  echo 'prod ps'
  echo 'scripts/smoke_prod.sh https://biz-aid.cloud'
}

if [[ "$dry_run" == true ]]; then
  echo "DRY-RUN: 커밋 $revision / 선택한 서비스 ${services[*]} / linux/amd64"
  echo '실행 시 Docker/buildx·비공개 저장소 로그인·기존 태그를 검사합니다. 지금은 Docker·registry에 접근하지 않습니다.'
  for service in "${services[@]}"; do build_arguments; print_command "${build[@]}"; done
  for service in "${services[@]}"; do print_command docker push "$repository:$service-$tag"; done
  echo '다음은 실제 릴리스 성공 후 적용할 서버 명령입니다. dry-run 결과로 배포하지 마세요.'
  server_steps
  exit 0
fi

command -v docker >/dev/null 2>&1 || fail 'Docker가 없습니다. Docker Desktop을 설치·실행하세요.'
docker info >/dev/null 2>&1 || fail 'Docker Desktop에 연결하지 못했습니다. Docker Desktop을 실행하세요.'
docker buildx version >/dev/null 2>&1 || fail 'Docker buildx가 없습니다. Docker Desktop의 buildx를 확인하세요.'
release_tmp="$(mktemp -d "${TMPDIR:-/tmp}/bizaid-release.XXXXXX")"
trap 'rm -rf "$release_tmp"' EXIT

# WHY: 비공개 저장소의 기존 이미지 조회로 로그인·접근 권한을 확인한다. 인증 파일·토큰은 직접 읽지 않는다.
auth_image="$repository:backend-${BIZAID_BACKEND_TAG:-20261005-03}"
docker buildx imagetools inspect "$auth_image" >"$release_tmp/registry.log" 2>&1 ||
  fail 'Docker Hub 비공개 저장소 접근 확인 실패. docker login과 BIZAID_BACKEND_TAG의 기존 태그를 확인하세요(원문 출력 안 함).'

require_absent() {
  local reference="$repository:$service-$tag"
  if LC_ALL=C docker buildx imagetools inspect "$reference" >"$release_tmp/registry.log" 2>&1; then
    fail "이미 존재하는 태그라 덮어쓰지 않습니다: $reference"
  fi
  # BOUNDARY: 인증·연결 오류는 태그가 없다는 근거가 아니다. 명시적인 manifest 부재만 허용한다.
  if grep -Eiq 'unauthorized|denied|forbidden|authorization|credential|timeout|lookup|dial tcp|TLS|x509|429|too many requests' "$release_tmp/registry.log"; then
    fail "태그 조회 실패: $reference. docker login·권한·네트워크를 확인하세요(원문 출력 안 함)."
  fi
  if ! grep -Eiq 'manifest unknown|no such manifest|^(ERROR: )?[^[:space:]]+: not found$' "$release_tmp/registry.log"; then
    fail "태그 부재를 확인할 수 없어 중단합니다: $reference (원문 출력 안 함)."
  fi
}
for service in "${services[@]}"; do require_absent; done

for service in "${services[@]}"; do
  require_clean
  build_arguments
  print_command "${build[@]}"
  "${build[@]}" >"$release_tmp/build.log" 2>&1 || fail "빌드 실패: $service (원문 출력 안 함)."
  actual="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$repository:$service-$tag" 2>/dev/null)" || fail "이미지 확인 실패: $service"
  [[ "$actual" == linux/amd64 ]] || fail "이미지 플랫폼 불일치: $service"
  labeled="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$repository:$service-$tag" 2>/dev/null)" || fail "이미지 커밋 라벨 확인 실패: $service"
  [[ "$labeled" == "$revision" ]] || fail "이미지 커밋 라벨 불일치: $service"
done
require_clean
# WHY: 오래 걸린 빌드 사이에 다른 릴리스가 같은 태그를 올렸을 수 있어 push 전에 다시 확인한다.
for service in "${services[@]}"; do require_absent; done
for service in "${services[@]}"; do
  require_clean
  require_absent
  print_command docker push "$repository:$service-$tag"
  docker push "$repository:$service-$tag" >"$release_tmp/push.log" 2>&1 ||
    fail "push 실패: $service. 앞서 올라간 이미지는 보존하며 자동 재시도하지 않습니다(원문 출력 안 함)."
done
echo "PASS: 선택한 서비스 ${services[*]} / 태그 $tag / 커밋 $revision"
server_steps
