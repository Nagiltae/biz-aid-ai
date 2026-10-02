# Current Task — 미지원 첨부 형식 4단계: 일반 ZIP

## Goal / Context

2026-10-02 사용자 요청: 일반 ZIP 첨부의 내부 파일을 각각 문서로 펼친다(깊이 1). 이번에는 구현·테스트·미리보기까지만 한다.
사용자 결정: 내부 파일 표 신설(migration, 한국어 COMMENT), data-source-rules ZIP 조항 변경, 압축 안 압축은 상태만, 이름은 UTF-8 플래그 없으면 CP949(실패 시 원래 byte), 내부 파일은 원본과 같은 S3 prefix·SHA key(덮어쓰기 금지), 공고 relation은 압축에서 상속, 처리 제외(Thumbs.db·빈·자리표시 txt·압축 안 압축·HWPML·XLSX·DOC·XLS·PPT)는 상태만, 단독 첨부와 같은 SHA는 연결만, 실제 PDF인 `.ai`는 PDF route, 파싱은 기존 route 그대로, document_role은 내부 파일명 기준.
근거: `2026-10-02-office-stage3.md`, `2026-10-02-imp009-unsupported-formats.md` §2, `2026-10-02-unsupported-formats-foundation.md`.
dev DB migration 적용, S3 업로드, 파싱·인덱싱 실행, 기존 point 변경, 변환 이미지 수정, natural.py·router 판단 로직 수정, `.env.dev`, V1 collection·baseline, commit/push는 범위가 아니다.

## Next Steps

미리보기 확인 → (승인 후) V10 적용 + 내부 파일 S3 저장 + 표본 파싱 → 전체 파싱·인덱싱 → 5 화면 완주 + cases-v2 기준점(IMP-024·025) → 6 XLSX(IMP-009 결정으로 의도적 제외 상태) → 7 옛 오피스(ODT 포함).

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md)(일반 ZIP) → [DB 규칙](../rules/database-rules.md) → `contracts/schemas/document-parsing.contract.json`(routes.ZIP·generic_zip) → `data-pipeline/pending-migrations/V10__document_archive_members.sql` → [Backlog](../docs/improvement-backlog.md)(IMP-009·026).

## Scope / Acceptance

1. V10은 승인 전이라 Flyway가 읽지 않는 `data-pipeline/pending-migrations/`에 둔다(check-all의 dev 준비가 `migrations/`를 dev DB에 적용하기 때문). DDL·COMMENT·CHECK는 테스트 전용 DB에서만 검증한다.
2. 기존 PDF·HWP·HWPX·IMAGE_OCR·DOCX·PPTX 원본의 parse_key·chunk_set_key·embedding_key가 그대로다.
3. 미리보기는 DB·S3에 쓰지 않는다. 형식·처리 여부·제외 사유·중복별 집계와 새 파싱 수·예상 시간을 보고하고 실행 승인을 받는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-generic-zip-stage4.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
