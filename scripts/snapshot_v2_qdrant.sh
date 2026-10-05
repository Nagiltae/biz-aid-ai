#!/usr/bin/env bash
# 명시한 V2 collection snapshot만 생성·다운로드한다. point·vector는 변경하지 않는다.
set -euo pipefail
if [[ $# != 3 || "$2" != bizaid_v2_* ]]; then
  echo '사용법: snapshot_v2_qdrant.sh <Qdrant URL> <bizaid_v2_... collection> <새 출력.snapshot>' >&2
  exit 2
fi
[[ ! -e "$3" ]] || { echo '기존 snapshot은 덮어쓰지 않습니다.' >&2; exit 1; }
reply=$(curl --fail --silent --show-error --max-time 180 -X POST "$1/collections/$2/snapshots")
name=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])' <<< "$reply")
curl --fail --silent --show-error --max-time 300 "$1/collections/$2/snapshots/$name" -o "$3"
echo 'V2 snapshot 다운로드 완료.'
