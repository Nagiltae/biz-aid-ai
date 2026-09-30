# RAG — 검색·근거 답변 v1 구현

처음 보는 용어의 한국어 뜻은 [용어집](glossary-ko.md)을, 프로젝트 전체 흐름은 [PROJECT_MASTER_GUIDE](../../PROJECT_MASTER_GUIDE.md)를 본다.

적재: FinalChunk가 BGE-M3 dense(1024, Cosine)·sparse vector로 dev Qdrant에 있다([Indexing 계약](../../contracts/schemas/document-indexing.contract.json)).
검색: `retrieval/retriever.py`가 같은 BgeM3Embedder로 query를 만들어 현재 embedding_key collection을 dense·sparse·RRF hybrid로 읽는다([Retrieval 계약](../../contracts/schemas/document-retrieval.contract.json)).
Retrieval Evaluation(gold-v1, 12문항, top_k 5) 결과 baseline은 Hybrid RRF다(dense와 동률, sparse보다 우세).

답변 v1([RAG 계약](../../contracts/schemas/rag-answer.contract.json)): `rag/service.py`의 `RagService`가 Hybrid top5를 [E1]..[E5] context로 만들고
`rag/llm.py`의 `LlmProvider`(현재 `OllamaLlmProvider`)에 공통 prompt와 JSON schema를 보낸다. 모델은 answer·evidence_ids·insufficient_evidence만 돌려주고,
citation(chunk_id·pblanc_id·page·source·provenance)은 application이 이번 요청의 SearchResult에서 resolve한다. 유효 근거가 없으면 고정 확인 불가 문장을 돌려준다.
진입점은 dev CLI `scripts/run_rag_answer.py`다(FastAPI 서비스는 아직 없음).
CLI는 먼저 `candidates.ProgramCandidateService`로 MySQL 후보 pblanc_id(활성 공고 + 선택 필터 category·target·jurisdiction·not_closed_on)를 정하고,
`RagService.answer(query, candidate_pblanc_ids=...)`가 Retriever에 scope를 넘긴다(Qdrant MatchAny). 후보가 없으면 검색·LLM 없이 NO_CANDIDATES다.
`--natural-filter`는 `candidates.natural.NaturalLanguageFilterService`가 같은 LlmProvider로 category·target·현재 모집 요청·unapplied 조건을 뽑고,
활성 공고의 실제 값으로 검증한 뒤 ProgramCandidateFilter를 만든다. 지역·소관기관은 자연어로 적용하지 않고 unapplied로 남기며, 검색 질의는 원문 그대로다.
같은 추출 호출이 request_mode(SEARCH_LIST·DOCUMENT_QA)를 낸다. SEARCH_LIST는 `candidates/discovery.py`가 `Retriever.search_programs`로 의미·단어 검색마다 공고별 최고 조각 하나(Qdrant group 검색)를 받아
공고 순위를 기존 RRF(k=60)로 합치고 상위 5개 공고의 MySQL 정형 정보를 돌려준다(답변 생성 LLM 없음, IMP-014). DOCUMENT_QA는 기존 RagService 그대로다. hard filter는 질문 근거가 있을 때만 적용한다.

Eligibility v1(`eligibility/`, [계약](../../contracts/schemas/eligibility.contract.json)): 공고 1개 + 기업 Profile snapshot → 고정 질의로 그 공고만 hybrid top5 →
LLM criterion(MET·NOT_MET·UNKNOWN, evidence id, profile field) → application 검증·최종 상태(ELIGIBLE·INELIGIBLE·NEEDS_MORE_INFO·INSUFFICIENT_EVIDENCE)·citation.

내부 HTTP API([계약](../../contracts/schemas/internal-api.contract.json)): `scripts/run_api.py`로 127.0.0.1:8000에 띄우며 /internal/v1/query·/internal/v1/eligibility가
CLI와 같은 `ServiceRuntime`을 호출한다.

다음 후보: provider 추가(Gemini), 표 직렬화 가독성 개선. Reranker·LangGraph는 평가로 필요성이 확인된 후 정한다.
지원 자격 판단은 하지 않는다. 날짜·상태 같은 정확한 조건은 MySQL이 결정한다. [AI 경계 규칙](../rules/ai-boundary-rules.md)과 [제품 평가](../../evals/README.md)를 따른다.

V1 종료 기준선은 `evals/v1_baseline/cases-v1.json` 10건이다. 최초 1회 결과는 검색 4/4, DOCUMENT_QA 2/3,
Eligibility 1/3으로 전체 7/10 PASS였다. QA 1건은 12개월 조건을 빠뜨렸고 Eligibility 2건은 model field 이름이 계약과 달라
application 검증에서 실패했다. 생산 route를 고치지 않은 현재 상태이며 V2 provider·prompt·retrieval 변경은 같은 baseline으로 비교한다.
