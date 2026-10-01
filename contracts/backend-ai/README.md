# Spring Boot ↔ FastAPI — AI E2E V1

Spring Boot는 서비스 사실·후보 사업을, FastAPI는 질문 분석·근거 기반 답변을 담당한다.
FastAPI 내부 API는 [internal-api.contract.json](../schemas/internal-api.contract.json)에 정의돼 있고 Spring은 이 계약을 그대로 쓴다.

- 호출 위치: `backend/.../ai/HttpAiGateway`(AiGateway 구현) 한 곳. 동기 RestClient(JDK HttpClient).
- 서비스 간 인증: 헤더 `X-Internal-Api-Key` = 환경변수 `INTERNAL_AI_API_KEY`(Spring·FastAPI 같은 값). 키가 없는 FastAPI는 `/internal/v1/*`를 503으로 거부한다. `/health`는 열려 있다.
- 제한시간: 연결 `AI_CONNECT_TIMEOUT`(기본 3s), 응답 `AI_RESPONSE_TIMEOUT`(기본 90s). 자동 재시도 없음.
- 이름 규칙: FastAPI JSON snake_case ↔ Spring DTO camelCase를 전용 ObjectMapper가 기계적으로 바꾼다. 의미·값은 그대로다. `natural_filter`는 원본 구조(JsonNode)로 전달한다.
- 응답 검증(고치지 않고 거부): query는 request_mode ∈ {SEARCH_LIST, DOCUMENT_QA}·status 존재·programs 공고 ID 중복 없음, eligibility는 status ∈ 4개 값·요청 공고 ID 일치·모든 근거가 대상 공고.
- 오류 변환

| FastAPI / 전송 결과 | Spring 오류 |
| --- | --- |
| 연결 실패(서버 없음·연결 제한시간) | 503 ai_service_unavailable |
| 응답 제한시간 초과 | 504 ai_service_timeout |
| 401·403 internal_auth_failed, 503 internal_auth_not_configured | 502 ai_service_auth_failed(사용자 로그인 오류 아님) |
| 404 eligibility_program_not_found_or_inactive | 404 program_not_found |
| 502(LLM 출력 계약 위반), Spring 응답 검증 실패 | 502 ai_response_invalid |
| 503(LLM·DB·Qdrant 접속 실패) | 503 ai_service_unavailable |
| 그 밖의 4xx·5xx | 502 ai_service_error |

NO_CANDIDATES·NO_INDEXED_PROGRAMS·INSUFFICIENT_EVIDENCE·NEEDS_MORE_INFO·INELIGIBLE는 오류가 아니라 200 정상 결과로 전달한다.

## V2 개인화 검색

- Spring `POST /api/ai/personalized-search {query}` → 로그인 사용자의 저장된 기업정보에서 `company_size`·`business_status`·`region`·`business_start_date`만 snapshot으로 → FastAPI `POST /internal/v2/personalized-search`.
- FastAPI는 users·companies를 읽지 않는다. 기업정보 → 검색조건은 승인된 코드 매핑(`candidates/personalized.py`)만 쓰고 LLM은 질문 조건만 추출한다.
- 응답: status(LISTED·NO_CANDIDATES·NO_INDEXED_PROGRAMS·COMPANY_CLOSED·CONDITION_CONFLICT), candidate_count, programs(최대 3, 순위 그대로), applied_conditions, unapplied_conditions. Spring은 status·Top 3·중복 없음만 검증하고 고치지 않는다.
- V1 `/internal/v1/query`·`/api/ai/query` 동작은 바뀌지 않았다.
- V2 Top 3 자격 판정: Spring `POST /api/ai/personalized-eligibility {query}` → 판정용 기업정보 snapshot(V1 단일 판정과 같은 매핑, 저장된 값만) → FastAPI `POST /internal/v2/personalized-eligibility`. FastAPI가 검색 Top 3 → 공고별 기존 판정을 순서대로 조합하고, Spring은 판정 순서·공고별 상태(COMPLETED/FAILED)·공고별 근거 범위를 검증만 한다. 현재 전체 응답이 Spring 응답 제한시간(90s)을 넘을 수 있다(IMP-020).
- V2-3 추천 흐름(LangGraph): Spring `POST /api/ai/workflows`(시작) · `GET /api/ai/workflows/{id}`(조회, FastAPI 호출 없음) · `POST /api/ai/workflows/{id}/continue`(다음 단계) · `POST /api/ai/workflows/{id}/answers`(부족 정보). Spring이 State JSON을 MySQL `ai_workflows`에 저장·복원하고, FastAPI `/internal/v2/workflows/{start,advance}`는 받은 State로 한 단계만 실행한다(판정 최대 1건). 동시 진행은 단계 점유 + version으로 막는다.
- V2-4 최종 결과: COMPLETED State의 `final_result`는 FastAPI가 기존 판정 결과로 조립한다(새 LLM 호출 없음, 검색 순위 유지, 공고별 Citation 재사용). Spring은 묶음별 허용 상태·순위 순서·판정한 공고 전체 포함·개수·근거 격리·이유가 가리키는 근거 존재만 검증하고 고치지 않는다(어기면 502 ai_response_invalid, State 저장 안 함).
