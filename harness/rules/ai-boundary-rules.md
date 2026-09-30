# AI 경계

DB로 판단 가능한 날짜·지역·기업형태·지원분야·상태를 LLM 판단으로 대체하지 않는다.
중요 Claim에는 Evidence / Source를 연결한다.
근거 없는 지원 가능 여부 확정 금지. Qdrant 결과만으로 정확한 날짜·상태 확정 금지.
근거가 부족하면 확인 불가를 반환한다.

승인 범위: dev Qdrant의 FinalChunk dense·sparse 적재(Phase 4-B), read-only Retriever(dense·sparse·RRF hybrid, Phase 5),
근거 기반 답변 RAG v1(Hybrid top5 → LlmProvider → citation, Phase 6, dev·로컬 Ollama).
계속 금지: LangGraph·Reranker·LLM query rewrite·parent/neighbor expansion·지원 자격(eligibility) 판단·MySQL 조건 결합.
RAG 답변은 이번 요청에서 검색된 evidence 밖의 사실을 만들지 않는다. 근거가 없으면 확인 불가로 답한다.
Citation metadata(chunk_id·pblanc_id·page·source·provenance)는 LLM 출력을 믿지 않고 application이 검색된 SearchResult에서 resolve한다. LLM은 evidence id만 고른다.
LLM provider 교체는 RAG orchestration·prompt·retrieval 계약을 바꾸지 않는다. provider는 `rag.llm.LlmProvider` 경계만 구현한다.
Retriever는 적재와 같은 BgeM3Embedder(같은 embedding_key)로 query를 만들고, collection은 그 identity의 `collection_name`으로만 정하며, 기존 collection을 읽기만 한다.
LangSmith는 향후 Observability이며 지금 연동하지 않는다.
