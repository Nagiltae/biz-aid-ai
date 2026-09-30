# AI 경계

DB로 판단 가능한 날짜·지역·기업형태·지원분야·상태를 LLM 판단으로 대체하지 않는다.
중요 Claim에는 Evidence / Source를 연결한다.
근거 없는 지원 가능 여부 확정 금지. Qdrant 결과만으로 정확한 날짜·상태 확정 금지.
근거가 부족하면 확인 불가를 반환한다.

승인 범위: dev Qdrant의 FinalChunk dense·sparse 적재(Phase 4-B)와 read-only Retriever(query embedding, dense·sparse·RRF hybrid 검색, Phase 5).
계속 금지: RAG·LLM·LangGraph·Reranker·LLM query rewrite·parent/neighbor expansion·지원 자격(eligibility) 판단·답변 생성.
Retriever는 적재와 같은 BgeM3Embedder(같은 embedding_key)로 query를 만들고, collection은 그 identity의 `collection_name`으로만 정하며, 기존 collection을 읽기만 한다.
LangSmith는 향후 Observability이며 지금 연동하지 않는다.
