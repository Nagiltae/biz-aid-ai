# parsed 보존 정책

Phase 3 승인 정책상 영구 parsed artifact는 S3, parse metadata는 MySQL이 소유한다. 이 디렉터리는 fixture·scratch·임시 처리 전용이며 영구 저장소가 아니다.
README만 Git에 포함한다. 실제 데이터·credential은 commit하지 않는다.
원문 삭제·덮어쓰기를 하지 않는다. 현재 실제 수집·다운로드·파싱 결과는 없다.
