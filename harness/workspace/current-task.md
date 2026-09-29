# Current Task

## Goal / Context

2026-09-29 사용자 결정: PP-TableMagic을 PDF production table engine으로 쓴다. Phase 3-B.5 PP Production Integration은
3-B.3·3-B.4에서 검증한 PP pipeline을 production PDF parser에 통합하고 Docling TableFormer 표 route를 PP 기반 route로 전환한다.
Docling은 document backbone(layout·읽기 순서)으로 남고 최종 표현은 DoclingDocument다. PaddleOCR-VL visual 해석은 보류다.

기준 evidence: [3-B.4 Report](reports/development/2026-09-29-phase3-3b4-review-closure.md)와 최신 checkpoint.
PP 엔진 선정 benchmark·대규모 human review·VL 재실행은 하지 않는다.

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md)의 PDF Table Engine 절 →
[Parsing Contract](../../contracts/schemas/document-parsing.contract.json)의 routes.PDF.table_engine / table_engine → [Testing](../docs/testing.md).

## Scope / Acceptance

1. production parsing package에 PP 모델 적재, 표 검출·구조, native text 매핑, 표 품질 Gate, 실패 표 text 보존, DoclingDocument 조립,
   provenance, 오류 처리만 둔다. benchmark·review UI·GT·visual 평가 기능은 가져오지 않는다.
2. TABLE_VALID만 TableItem이다. TABLE_QUALITY_FAILED·겹친 PP 영역은 구조 없이 native text + provenance로 보존한다. 다른 표 parser로 fallback하지 않는다.
3. 확인은 최대 5문서 targeted regression으로만 한다. 전체 corpus 재실행·PP/VL 재benchmark는 하지 않는다.
HWP, OCR fallback, Phase 4 Chunking·Embedding·Qdrant, persistence 확장은 시작하지 않는다. AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-29-phase3-3b5-pp-production.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다. check-all에 대규모 PDF 평가를 넣지 않는다.
