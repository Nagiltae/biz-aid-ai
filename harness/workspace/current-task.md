# Current Task — 미지원 첨부 형식 1단계: 공통 기반

## Goal / Context

2026-10-02 사용자 요청: 미지원 첨부 형식 지원의 공통 기반(형식 판별 세분화·파싱 Contract route 정의·출처 종류 설계·기존 행 재분류 미리보기)을 만든다.
근거: `reports/development/2026-10-02-imp009-unsupported-formats.md`. 실제 파싱·인덱싱·route 활성화·DB UPDATE·라이브러리 설치·변환 이미지 수정·기존 parse_key/chunk_set_key 변경·`.env.dev`·V1 collection/baseline·commit/push는 범위가 아니다.

사용자 확정: XLSX는 보이는 셀 5,000·파일 10MB·시트 20 상한(넘으면 자르지 않고 문서 단위 실패), 숨긴 시트 제외, 저장된 계산값 사용. 빈 신청 양식은 출처 종류만 기록하고 순위 반영은 cases-v2 뒤 결정. HWPML 보류(판별만). VLM 미도입.

## Next Steps

1 공통 기반(이번) → 2 이미지 OCR(PNG·JPEG) → 3 DOCX·PPTX(Docling XML 직접), ODT는 LibreOffice로 DOCX 변환 → 4 일반 ZIP(내부 파일을 각각 문서로, 깊이 1) → 5 화면 완주 + cases-v2 기준점 → 6 XLSX → 7 옛 오피스(DOC·XLS·PPT를 LibreOffice로 새 형식 변환).

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md) → [Pipeline](../docs/data-pipeline.md) → `contracts/schemas/document-parsing.contract.json`(routes) → `contracts/schemas/document-indexing.contract.json`(document_role).

## Scope / Acceptance

1. 기존 PDF·HWP·HWPX·XLSX 판별 결과와 parse_key·chunk_set_key·embedding_key가 바뀌지 않는다(테스트·실제 point 재계산).
2. 새 형식 route는 정의만 하고 모두 꺼져 있다. 출처 종류는 식별값 입력이 아니며 순위에 쓰지 않는다.
3. 기존 행 재분류는 미리보기·적용/되돌리기 계획만 남기고 사용자 승인을 받는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-unsupported-formats-foundation.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
