# RAG 계획 — 검색·답변 미구현

현재 구현은 적재까지다. FinalChunk가 BGE-M3 dense(1024, Cosine)·sparse vector로 dev Qdrant에 있고
payload는 FinalChunk.payload()(pblanc_id·source·parse_key·heading_path·pages·provenance)다. [Indexing 계약](../../contracts/schemas/document-indexing.contract.json)을 본다.

초기 baseline 계획: MySQL hard filter → 후보 pblanc_id → Qdrant payload filter(`pblanc_id` index) →
같은 BGE-M3로 만든 query vector 검색 → 근거 기반 답변. dense·sparse 결합(RRF 등)·Reranker·LangGraph는 실제 평가로 필요성이 확인된 후 정한다.
query embedding은 적재와 같은 embedding_key(모델·revision·설정)여야 하며 다른 key의 collection을 검색하지 않는다.

LLM 호출·답변 생성은 아직 하지 않는다. 날짜·상태 같은 정확한 조건은 MySQL이 결정한다.
[AI 경계 규칙](../rules/ai-boundary-rules.md)과 [제품 평가](../../evals/README.md)를 따른다.
