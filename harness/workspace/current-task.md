# Current Task — 미지원 첨부 형식 2단계: 이미지 OCR(PNG·JPEG)

## Goal / Context

2026-10-02 사용자 요청: PNG·JPEG 첨부를 IMAGE_OCR route로 읽는다. 근거: `2026-10-02-imp009-unsupported-formats.md`, `2026-10-02-unsupported-formats-foundation.md`.
사용자 승인·결정: 재분류 123행 적용(한 트랜잭션, 확인 불일치 시 ROLLBACK). PDF route의 고정 PP-OCRv5(한국어) 재사용, 새 모델·VLM 없음. 세로 타일 + 10~15% 겹침 + 중복 줄 제거, 타일 = page·bbox = 원본 좌표, 폭 축소 없음, 픽셀 상한 초과는 문서 단위 실패. 수용 기준은 PDF OCR 기존 기준, 미달은 OCR_REQUIRED(적재 안 함). parse_key는 IMAGE_OCR 전용 입력, 기존 parse_key 불변. document_role은 이번 단계부터 새 point payload에 기록(순위 미사용).
표본 외 전체 파싱·인덱싱, 다른 새 route 활성화, 기존 point 변경·재적재, 새 모델 다운로드, `.env.dev`, V1 collection·baseline, commit/push는 범위가 아니다.

## Next Steps

표본 확인 → (승인 후) 이미지 전체 파싱·인덱싱 → 3 DOCX·PPTX(ODT는 LibreOffice→DOCX) → 4 일반 ZIP(깊이 1) → 5 화면 완주 + cases-v2 기준점 → 6 XLSX → 7 옛 오피스.

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md) → [Pipeline](../docs/data-pipeline.md) → `contracts/schemas/document-parsing.contract.json`(routes·image_ocr·versioning) → `contracts/schemas/document-chunking.contract.json`.

## Scope / Acceptance

1. 재분류가 기대값과 같을 때만 COMMIT되고 전후 값이 기록된다.
2. IMAGE_OCR이 타일·겹침·중복 제거·원본 좌표 bbox·픽셀 상한·OCR_REQUIRED를 지키고, chunk provenance가 근거 위치를 잃지 않는다.
3. 기존 PDF·HWP·HWPX의 parse_key·chunk_set_key·embedding_key가 그대로다.
4. 표본 3개(포스터 2 + 긴 캡처 1)만 실행하고 전체 실행은 승인을 받는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-image-ocr-stage2.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
