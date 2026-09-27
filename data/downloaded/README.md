# downloaded 보존 정책

승인된 Phase 0 Document Download Gate의 원본 byte와 metadata/checksum을 보존한다.
README만 Git에 포함한다. 실제 데이터·credential은 commit하지 않는다.
원문 삭제·덮어쓰기를 하지 않는다. 다운로드 결과는 current-task의 Gate Report를 따른다. 문서 본문 Parsing은 구현하지 않았다.

`<run-id>/manifest.json` → `<pblancId>/document.bin` / metadata.json → summary-<순번>.json으로 연결한다.
부분 응답은 complete_body=false이며 전체 크기를 주장하지 않는다. 재개 전 모든 checksum을 확인한다.
기존 파일·같은 run-id를 overwrite하지 않는다. 고립 파일은 사람의 확인 전 재개하지 않는다.
