# Spring Boot ↔ FastAPI — 연결 전

Spring Boot는 서비스 사실·후보 사업을, FastAPI는 질문 분석·근거 기반 답변을 담당한다.
FastAPI 쪽 내부 API는 [internal-api.contract.json](../schemas/internal-api.contract.json)에 정의돼 있다.
Spring 쪽 경계는 `backend/.../ai/AiGateway`다. 현재 구현(`UnconnectedAiGateway`)은 FastAPI를 호출하지 않고 `ai_service_not_connected`를 돌려준다.
자격 판정 요청 본문은 `AiDtos.CompanyProfileSnapshot`(FastAPI `company_profile`과 같은 snake_case 이름)으로 준비돼 있다.
연결 단계에서 timeout·오류 code 대응·citation 응답 매핑·서비스 간 인증을 확정한다. FastAPI ↔ Qdrant payload도 별도 계약으로 검증한다.
