# Current Task

## Goal / Context

2026-09-30 사용자 요청: Phase 4-B Document Indexing. Phase 4-A FinalChunk를 BAAI/bge-m3 dense·sparse vector로 만들어
dev Qdrant에 적재한다. Parser·Chunker 로직은 수정하지 않는다. Retriever·query embedding·RRF·Reranker·LangGraph·LLM은 이번 범위가 아니다.

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md)의 Chunking·Indexing 줄 →
[Indexing 계약](../../contracts/schemas/document-indexing.contract.json) → [Chunking 계약](../../contracts/schemas/document-chunking.contract.json) →
[Parsing 계약](../../contracts/schemas/document-parsing.contract.json)의 model_artifacts → [Testing](../docs/testing.md).

## Scope / Acceptance

1. Embedding 모델·tokenizer는 chunking과 같은 BAAI/bge-m3 revision이며 가중치는 기존 artifact 체계(scope embedding)에서만 읽는다. parse_key·chunk identity는 바뀌지 않는다.
2. dense(1024, Cosine)와 sparse를 batch로 만들고 입력을 자르지 않는다. 같은 content_key는 한 번만 embedding한다.
3. Qdrant point id는 chunk_id, payload는 FinalChunk.payload()+embedding_key다. collection은 embedding_key별이며 schema 불일치는 실패한다.
4. 재실행은 point를 늘리지 않는다. 실제 확인은 Phase 4-A와 같은 3개 source(PDF·HWP·HWPX)로만 하고 전체 corpus indexing은 시작하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-phase4b-document-indexing.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
