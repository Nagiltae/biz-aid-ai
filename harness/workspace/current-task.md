# Current Task

## Goal / Context

2026-09-29 사용자 승인: Phase 3-B.6 HWP → PDF Route. HWP를 전용 Docker 변환기(LibreOffice headless + H2Orestart, host 설치 없음)로
PDF로 바꾼 뒤 production PDF parser(`parse_pdf`: Docling backbone + PP-TableMagic)를 그대로 재사용한다. 최종 표현은 DoclingDocument다.
HWPX는 기존 native `HwpxDoclingAdapter`를 유지한다. PDF/PP 평가는 다시 하지 않는다.

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md)의 Phase 3 절 →
[Parsing Contract](../../contracts/schemas/document-parsing.contract.json)의 routes.HWP / routes.PDF → [Testing](../docs/testing.md).

## Scope / Acceptance

1. HWP 원본 → 임시 디렉터리 → 전용 Docker 변환 → PDF byte → `parse_pdf` → DoclingDocument. 임시 파일은 끝나면 지우고 PDF는 저장하지 않는다.
2. provenance의 source는 원본 HWP SHA이고 중간 PDF의 SHA·크기·변환기 identity만 기록한다. 변환 실패는 CONVERSION_FAILED이며 fallback이 없다.
3. 이미지형 변환 PDF는 기존 PDF OCR_REQUIRED 흐름을 그대로 탄다.
4. 실제 확인은 HWP 최대 3개로 한다. HWP corpus 실행·benchmark·새 평가 도구는 만들지 않는다.
OCR 구현, 전체 corpus parsing, Phase 4 Chunking·Embedding·Qdrant는 시작하지 않는다. AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-29-phase3-3b6-hwp-pdf-route.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다. check-all에 실제 HWP 변환을 넣지 않는다.
