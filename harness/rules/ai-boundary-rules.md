# AI 경계

DB로 판단 가능한 날짜·지역·기업형태·지원분야·상태를 LLM 판단으로 대체하지 않는다.
중요 Claim에는 Evidence / Source를 연결한다.
근거 없는 지원 가능 여부 확정 금지. Qdrant 결과만으로 정확한 날짜·상태 확정 금지.
근거가 부족하면 확인 불가를 반환한다.

승인 범위: dev Qdrant의 FinalChunk dense·sparse 적재(Phase 4-B), read-only Retriever(dense·sparse·RRF hybrid, Phase 5),
근거 기반 답변 RAG v1(Hybrid top5 → LlmProvider → citation, Phase 6, dev·로컬 Ollama)과 MySQL 정형 후보로 제한한 RAG.
자연어 질문에서 정형 후보 조건을 LLM으로 추출하는 것도 승인됐다(`candidates/natural.py`). 추출은 필터 입력 후보일 뿐 SQL·후보 선택·날짜를 정하지 않는다.
단일 공고 자격 사전 판단(Eligibility v1: 공고 1개 + 기업 Profile snapshot, `eligibility/`)이 승인됐다.
계속 금지: Reranker·LLM query rewrite·parent/neighbor expansion·추천 점수·적합도 순위.
LangGraph는 V2-3 추천 흐름(`workflow/recommendation.py`)의 단계·분기만 소유한다. 검색·RRF·Citation·판정 규칙·최종 상태는 기존 서비스를 노드에서 호출하며 다시 만들지 않는다. 한 단계(한 HTTP 요청)에서 비싼 공고 판정 LLM 호출은 최대 1건이다. 여러 공고 판정은 V2-2부터 개인화 검색 Top 3에 한해 승인됐다(전체 후보 일괄 LLM 판정은 금지).
최종 추천 결과(V2-4 final_result)는 LLM을 다시 부르지 않고 기존 판정 상태를 코드로 나눈다(ELIGIBLE → 추천, INELIGIBLE → 제외, 그 밖·판정 실패 → 판단 불가). 순서는 검색 순위 그대로이며, 이유·근거는 그 공고 판정에 이미 있는 조건과 검증된 Citation만 쓴다. 추천할 공고가 없으면 빈 추천 목록이 정상 결과다.
여러 공고 판정도 공고마다 기존 단일 공고 판정을 따로 실행해 근거 범위를 공고별로 격리한다. 한 공고의 실패는 그 공고에만 명시적 실패 상태·코드로 남기고 다른 공고 결과나 UNKNOWN·성공으로 바꾸지 않는다.
AI 계층은 자격 판단에 기업 Profile snapshot을 입력으로 받을 뿐 기업 정보의 저장·source of truth를 소유하지 않는다. Spring은 저장된 값만 snapshot에 넣고 저장되지 않은 값(신용점수·체납·인증 등)에 기본값을 만들지 않는다.
서비스 계층(Spring)은 AI 결과(목록·순위·답변·자격 상태·근거)를 재판단·재정렬하거나 만들지 않고 계약 검증 후 전달만 한다. 계약을 어긴 응답은 고쳐 쓰지 않고 거부한다.
AI POST 요청(검색·자격 판정)은 자동 재시도하지 않는다(LLM 중복 실행·메시지 이중 저장 방지). AI 호출이 실패하면 가짜 ASSISTANT 메시지를 저장하지 않고, 자연어 답이 없는 목록 결과에 답변 문장을 지어 넣지 않는다.
자격 판단은 제공된 기업 사실과 정확히 그 대상 공고에서 검색된 evidence 둘 다에 근거해야 한다.
기업 사실이 없으면 LLM이 추론하지 않고 UNKNOWN / NEEDS_MORE_INFO로 둔다(값 없는 필드로 낸 MET·NOT_MET은 application이 UNKNOWN으로 되돌린다).
최종 자격 상태는 검증된 criterion 결과로 application이 계산하며 모델이 덮어쓸 수 없다.
LLM이 추출한 정형 조건은 SQL 실행 전에 application의 허용 canonical 값(활성 공고의 실제 DB 값)으로 검증한다. 허용 값 밖은 적용하지 않고 unapplied로 드러낸다.
처리할 수 없거나 모호한 hard 조건(예: 질문 속 지역)을 다른 정형 field(예: 소관기관 jurisdiction_name)로 바꿔 적용하지 않는다(질문 속 지역은 unapplied).
예외(2026-10-03 사용자 결정, IMP-019): 저장된 기업정보의 지역이 광역 지자체 표준명이면 기업 지역과 다른 광역 지자체가 소관기관인 공고만 후보에서 뺀다. 중앙부처·공공기관·매핑에 없는 소관기관은 남긴다(fail-open). 표준명·소관기관 매핑은 `contracts/schemas/company-region.contract.json`에만 둔다.
저장된 기업정보는 LLM이 해석하지 않는다. 의미가 확실하고 사용자가 승인한 매핑(`candidates/personalized.py`, `candidates/region.py`)만 일반 코드로 검색조건이 되고, 나머지(업력·휴업·표준명이 아닌 예전 지역 값 등)는 unapplied로 드러낸다. 질문 조건과 겹치지 않으면 완화하지 않고 충돌 상태로 돌려준다(지원대상 kind=target, 정형 소관기관 조건과 기업 지역 kind=region).
"현재·지금" 같은 상대 시간은 LLM이 만든 날짜가 아니라 application 시간(Asia/Seoul 날짜 또는 명시한 as_of)으로 해석한다.
LLM이 제안한 hard filter는 질문 원문에 근거가 있고 application이 검증한 경우에만 후보 선택에 영향을 준다. 근거 없는 제안은 진단(discarded)으로만 남긴다.
지원사업 찾기·목록 요청(SEARCH_LIST)은 문서 QA 생성을 강제하지 않고 MySQL의 공고 정형 정보를 목록으로 돌려준다(답변 생성 LLM 미사용).
지원사업 목록 검색은 문서 조각 순위가 아니라 공고 단위 결과를 돌려준다. 고정된 작은 조각 절단 때문에 같은 공고의 여러 조각이 목록 자리를 독점하게 하지 않는다(공고별 최고 조각으로 순위를 매김).
목록 다양성을 채우려고 후보 범위 밖 공고나 의미 검색 근거가 없는 공고를 임의로 넣지 않는다. 근거가 있는 공고가 적으면 적게 돌려준다.
MySQL이 소유한 정형 조건(공고 lifecycle·분야·대상·소관기관·신청기간)은 의미 검색보다 먼저 적용해 후보 pblanc_id를 정한다.
Retriever는 정형 계층이 준 후보 scope 밖의 pblanc_id를 반환하지 않는다(Qdrant filter로 강제). LLM·Retriever가 제외된 공고를 되살리지 않는다.
정형 후보가 비면 query embedding·검색·LLM 생성을 하지 않고 즉시 NO_CANDIDATES로 끝낸다.
RAG 답변은 이번 요청에서 검색된 evidence 밖의 사실을 만들지 않는다. 근거가 없으면 확인 불가로 답한다.
Citation metadata(chunk_id·pblanc_id·page·source·provenance)는 LLM 출력을 믿지 않고 application이 검색된 SearchResult에서 resolve한다. LLM은 evidence id만 고른다.
LLM provider 교체는 RAG orchestration·prompt·retrieval 계약을 바꾸지 않는다. provider는 `rag.llm.LlmProvider` 경계만 구현한다.
LangChain은 이 LLM 호출 계층(`rag/llm.py`: prompt 구성·모델 호출·구조화 출력)만 소유한다. 후보 필터·Retriever·RRF·Qdrant 규칙·Citation 연결·자격 최종 상태는 소유하지 않는다.
허용값이 정해진 LLM 출력(분야·대상, 기업정보 field ID, evidence 번호)은 생성 단계에서 요청별 허용값 목록(enum)으로 제한하고, application 검증도 그대로 유지한다(이중 방어). 기업정보는 사람이 읽는 이름 대신 고정 field ID로 주고받는다.
Retriever는 적재와 같은 BgeM3Embedder(같은 embedding_key)로 query를 만들고, collection은 그 identity의 `collection_name`으로만 정하며, 기존 collection을 읽기만 한다.
LangSmith 실행 추적은 설정(`BIZAID_TRACING_ENABLED`)으로 켤 때만, `observability/tracing.py`가 정한 단계를 명시적으로 기록한다. LangChain/LangGraph 자동 추적은 쓰지 않으며 workflow 실행 중에는 강제로 끈다.
외부 추적에는 단계 이름·시간·상태·개수·오류 코드·공개 공고 ID·field ID만 보낸다. 질문·기업정보·임시 답변 값·문서 원문·검색 조각·prompt·모델 응답·비밀값·예외 메시지 원문은 보내지 않는다(형식 검사로 이중 차단).
추적 식별값은 사용자·기업과 무관한 무작위 값(trace_key)이다. 추적 생성·전송 실패는 무시하고 AI 흐름을 멈추거나 바꾸지 않는다.
