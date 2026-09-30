# RAG 계획 — 검색 구현, 답변 미구현

적재: FinalChunk가 BGE-M3 dense(1024, Cosine)·sparse vector로 dev Qdrant에 있고 payload는 FinalChunk.payload()다([Indexing 계약](../../contracts/schemas/document-indexing.contract.json)).
검색: `retrieval/retriever.py`가 같은 BgeM3Embedder로 query dense·sparse를 만들고 현재 embedding_key collection을 dense·sparse·RRF hybrid로 읽는다([Retrieval 계약](../../contracts/schemas/document-retrieval.contract.json)).
SearchResult는 rank·score·chunk_id·pblanc_id·title·text·heading_path·source·pages·provenance와 mode별 순위·점수를 가진다.

다음 계획: Gold 평가로 mode·top_k·fusion을 정한 뒤 MySQL hard filter → 후보 pblanc_id → Qdrant payload filter → 근거 기반 답변.
Reranker·parent/neighbor expansion·LangGraph는 평가로 필요성이 확인된 후 정한다. top_k 기본값은 dev 편의값이다.

LLM 호출·답변 생성·지원 자격 판단은 아직 하지 않는다. 날짜·상태 같은 정확한 조건은 MySQL이 결정한다.
[AI 경계 규칙](../rules/ai-boundary-rules.md)과 [제품 평가](../../evals/README.md)를 따른다.
