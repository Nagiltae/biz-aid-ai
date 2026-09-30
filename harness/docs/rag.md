# RAG — 검색·근거 답변 v1 구현

적재: FinalChunk가 BGE-M3 dense(1024, Cosine)·sparse vector로 dev Qdrant에 있다([Indexing 계약](../../contracts/schemas/document-indexing.contract.json)).
검색: `retrieval/retriever.py`가 같은 BgeM3Embedder로 query를 만들어 현재 embedding_key collection을 dense·sparse·RRF hybrid로 읽는다([Retrieval 계약](../../contracts/schemas/document-retrieval.contract.json)).
Retrieval Evaluation(gold-v1, 12문항, top_k 5) 결과 baseline은 Hybrid RRF다(dense와 동률, sparse보다 우세).

답변 v1([RAG 계약](../../contracts/schemas/rag-answer.contract.json)): `rag/service.py`의 `RagService`가 Hybrid top5를 [E1]..[E5] context로 만들고
`rag/llm.py`의 `LlmProvider`(현재 `OllamaLlmProvider`)에 공통 prompt와 JSON schema를 보낸다. 모델은 answer·evidence_ids·insufficient_evidence만 돌려주고,
citation(chunk_id·pblanc_id·page·source·provenance)은 application이 이번 요청의 SearchResult에서 resolve한다. 유효 근거가 없으면 고정 확인 불가 문장을 돌려준다.
진입점은 dev CLI `scripts/run_rag_answer.py`다(FastAPI 서비스는 아직 없음).

다음 후보: provider 추가(Gemini), MySQL hard filter → 후보 pblanc_id → payload filter 결합, 표 직렬화 가독성 개선. Reranker·LangGraph는 평가로 필요성이 확인된 후 정한다.
지원 자격 판단은 하지 않는다. 날짜·상태 같은 정확한 조건은 MySQL이 결정한다. [AI 경계 규칙](../rules/ai-boundary-rules.md)과 [제품 평가](../../evals/README.md)를 따른다.
