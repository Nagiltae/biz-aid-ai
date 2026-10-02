# Current Task — 미지원 첨부 형식 3단계: DOCX·PPTX

## Goal / Context

2026-10-02 사용자 요청: 단독 첨부 DOCX·PPTX를 Docling으로 XML을 직접 읽는다(DOCLING_DOCX·DOCLING_PPTX, VLM 없음).
사용자 결정: docling-slim format-docx·format-pptx extra를 버전 고정으로 추가(기존 패키지 버전 불변). ODT는 7단계로 연기(변환 이미지를 고치면 HWP_PDF_DOCLING parse_key가 바뀐다). 압축 안 DOCX·PPTX는 4단계.
근거: `2026-10-02-image-ocr-stage2.md` §9, `2026-10-02-unsupported-formats-foundation.md`, `2026-10-02-imp009-unsupported-formats.md`.
표본 외 전체 파싱·인덱싱, ODT·XLSX·옛 오피스·일반 ZIP route 활성화, 변환 이미지 수정, 기존 point 변경·재적재, 기존 패키지 버전 변경, natural.py·router 판단 로직 수정, `.env.dev`, V1 collection·baseline, commit/push는 범위가 아니다.

## Next Steps

표본 확인 → (승인 후) DOCX·PPTX 전체 파싱·인덱싱 → 4 일반 ZIP(깊이 1, 압축 안 DOCX·PPTX 포함) → 5 화면 완주 + cases-v2 기준점(IMP-024·025 비교 포함) → 6 XLSX → 7 옛 오피스(ODT 포함).

## Read First

[AGENTS](../../AGENTS.md) → [Pipeline](../docs/data-pipeline.md) → `contracts/schemas/document-parsing.contract.json`(routes·office·versioning) → `contracts/schemas/document-chunking.contract.json`(provenance) → [Backlog](../docs/improvement-backlog.md)(IMP-009·024·025).

## Scope / Acceptance

1. 의존성 추가 뒤에도 기존 point(PDF·HWP·HWPX 155원본, IMAGE_OCR 105원본)의 parse_key·chunk_set_key·embedding_key가 그대로다.
2. DOCX는 가짜 page 없이 문서 순서·제목 경로, PPTX는 슬라이드 번호가 `bizaid__office` meta와 chunk provenance에 남는다. 품질 기준은 문서 단위 글자 Gate.
3. 표본 3개만 실행하고 전체 실행은 승인을 받는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-office-stage3.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
