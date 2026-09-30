# AI 경계

DB로 판단 가능한 날짜·지역·기업형태·지원분야·상태를 LLM 판단으로 대체하지 않는다.
중요 Claim에는 Evidence / Source를 연결한다.
근거 없는 지원 가능 여부 확정 금지. Qdrant 결과만으로 정확한 날짜·상태 확정 금지.
근거가 부족하면 확인 불가를 반환한다.

승인 범위: dev Qdrant의 FinalChunk dense·sparse 적재(Phase 4-B), read-only Retriever(dense·sparse·RRF hybrid, Phase 5),
근거 기반 답변 RAG v1(Hybrid top5 → LlmProvider → citation, Phase 6, dev·로컬 Ollama)과 MySQL 정형 후보로 제한한 RAG.
계속 금지: LangGraph·Reranker·LLM query rewrite·parent/neighbor expansion·지원 자격(eligibility) 판단·자연어→정형 조건 추출.
MySQL이 소유한 정형 조건(공고 lifecycle·분야·대상·소관기관·신청기간)은 의미 검색보다 먼저 적용해 후보 pblanc_id를 정한다.
Retriever는 정형 계층이 준 후보 scope 밖의 pblanc_id를 반환하지 않는다(Qdrant filter로 강제). LLM·Retriever가 제외된 공고를 되살리지 않는다.
정형 후보가 비면 query embedding·검색·LLM 생성을 하지 않고 즉시 NO_CANDIDATES로 끝낸다.
RAG 답변은 이번 요청에서 검색된 evidence 밖의 사실을 만들지 않는다. 근거가 없으면 확인 불가로 답한다.
Citation metadata(chunk_id·pblanc_id·page·source·provenance)는 LLM 출력을 믿지 않고 application이 검색된 SearchResult에서 resolve한다. LLM은 evidence id만 고른다.
LLM provider 교체는 RAG orchestration·prompt·retrieval 계약을 바꾸지 않는다. provider는 `rag.llm.LlmProvider` 경계만 구현한다.
Retriever는 적재와 같은 BgeM3Embedder(같은 embedding_key)로 query를 만들고, collection은 그 identity의 `collection_name`으로만 정하며, 기존 collection을 읽기만 한다.
LangSmith는 향후 Observability이며 지금 연동하지 않는다.
