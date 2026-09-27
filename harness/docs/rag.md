# RAG 계획 — 현재 미구현

MySQL hard filter → 후보 pblanc_id → Qdrant metadata filter →
dense retrieval → 근거 기반 답변을 초기 baseline으로 검토한다.
Sparse/BM25·RRF·Reranker·LangGraph는 실제 평가로 필요성이 확인된 후 검토한다.

Phase 0에서는 API보다 공고문에 상세 조건이 있는지와 근거 위치를 추적할 수 있는지 평가한다.
LLM을 호출하거나 embedding·chunk·index를 만들지 않는다.
RAG 가치가 입증되지 않았으면 GO를 선언하지 않는다.
[AI 경계 규칙](../rules/ai-boundary-rules.md)과 [제품 평가](../../evals/README.md)를 따른다.
