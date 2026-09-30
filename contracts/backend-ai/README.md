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
