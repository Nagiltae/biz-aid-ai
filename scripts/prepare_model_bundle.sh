#!/usr/bin/env bash
# 질문 서버용 고정 BGE-M3 모델·tokenizer를 포장한다. S3 업로드는 이 스크립트에서 하지 않는다.
set -euo pipefail
[[ $# == 2 ]] || { echo '사용법: prepare_model_bundle.sh <artifact 디렉터리> <새 출력.tar.gz>' >&2; exit 2; }
[[ ! -e "$2" ]] || { echo '기존 bundle은 덮어쓰지 않습니다.' >&2; exit 1; }
# WHY: macOS의 AppleDouble 메타데이터는 서버 입력이 아니므로 압축에 넣지 않는다.
COPYFILE_DISABLE=1 tar -czf "$2" -C "$1" BAAI--bge-m3-embedding BAAI--bge-m3
echo '모델 bundle 준비 완료. 사용자 승인 후 AWS S3 경유로 서버에 옮기고 SHA-256을 대조하세요.'
