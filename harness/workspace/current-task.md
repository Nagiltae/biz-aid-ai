# Current Task

## Goal / Context

2026-09-30 사용자 요청: 기존 100-source parser 검증 corpus를 Retrieval Evaluation용 dataset으로 완성한다.
이전 parse_key인 PDF·HWP 60건을 현재 parser로 재parsing하고, 100건 전체를 Chunking → BGE-M3 dense·sparse → dev Qdrant로 적재한다.
기존 Parser·Chunker·Embedder·Indexer를 그대로 쓰는 bounded data processing이며 background run 하나로 순차 실행한다.

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md)의 corpus 실행 줄 → [Pipeline](../docs/data-pipeline.md) → [Indexing 계약](../../contracts/schemas/document-indexing.contract.json).

## Scope / Acceptance

1. target은 기존 run(`corpus-20260930-01`)의 정확한 100 unique source(PDF 45·HWP 42·HWPX 13)이고, 재parsing은 current PARSED가 없는 PDF·HWP 60건뿐이다.
2. PHASE A(60 재parsing)가 60/60 PARSED이고 100/100 current PARSED gate를 통과해야 PHASE B(100 indexing)를 시작한다. 두 phase는 동시에 돌지 않는다.
3. 최종: 100 source indexing 성공, 실패 0, 현재 embedding_key collection 하나, point 중복 없음, pblanc_id·provenance 존재.
4. 전체 2,926 corpus·Parser/Chunker/BGE-M3/Qdrant schema/Retriever 변경·Gold·Retrieval Evaluation·RAG는 하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-dataset100-build.md).
새 runner 코드 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
