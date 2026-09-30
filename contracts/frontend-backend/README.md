# React ↔ Spring Boot — 서비스 V1

React는 Spring Boot `/api`만 호출하며 DB와 FastAPI에 직접 접근하지 않는다.
로컬에서는 Vite proxy(개발) 또는 nginx(Compose)로 같은 origin처럼 호출해 CORS를 열지 않는다.

## 인증(JWT)

- Access Token: 15분, 응답 본문 `accessToken`으로만 전달. React 메모리에만 두고 `Authorization: Bearer`로 보낸다.
- Refresh Token: 14일, `bizaid_refresh` HttpOnly·SameSite=Strict·Path=/api/auth Cookie. DB에는 SHA-256 해시만 저장하고 재발급마다 교체(rotation)한다.
- 401을 받으면 React는 `/api/auth/refresh`를 한 번 호출하고 성공 시 원 요청을 한 번 재시도한다. 실패하면 로그인 화면으로 보낸다.

## Endpoint

| Method | Path | 인증 | 역할 |
| --- | --- | --- | --- |
| POST | /api/auth/signup · /login · /refresh · /logout | 없음(refresh·logout은 Cookie) | 가입·로그인·재발급·로그아웃 |
| GET | /api/auth/me | 필요 | 현재 사용자 |
| GET | /api/programs | 없음 | 지원사업 목록(keyword·category·target·jurisdiction·status·page·size) |
| GET | /api/programs/filter-options | 없음 | 필터 선택지(활성 공고의 실제 값) |
| GET | /api/programs/{pblancId} | 없음 | 지원사업 상세 |
| GET · POST · PUT | /api/company | 필요 | 내 기업정보 조회·등록·수정 |
| POST · GET | /api/conversations | 필요 | 대화 생성·목록 |
| GET · POST | /api/conversations/{id}/messages | 필요 | 메시지 조회·사용자 메시지 저장 |
| POST | /api/ai/query | 필요 | AI 검색·질문 `{query, conversationId?}` → `{conversationId, userMessage, assistantMessage, result}` |
| POST | /api/programs/{pblancId}/eligibility | 필요 | 지원 자격 판정 `{creditScore?, taxDelinquent?, additionalFacts?}`(일시 정보, 저장 안 함) |

## 응답과 오류

정상 응답은 wrapper 없이 DTO를 그대로 돌려준다. 목록은 `{items, page, size, totalElements, totalPages}`(page는 0부터)다.
오류는 항상 `{"error": {"code", "message", "fieldErrors"?}}`다. React는 code로 분기하고 message를 보여 준다.
대표 code: validation_failed(400), auth_required·auth_invalid_credentials·auth_refresh_invalid(401), company_not_registered·program_not_found·conversation_not_found(404), company_already_registered·auth_email_taken(409), ai_service_unavailable(503)·ai_service_timeout(504)·ai_service_auth_failed·ai_response_invalid·ai_service_error(502).
AI 결과(`result`)는 FastAPI 값을 camelCase로 옮긴 것이다. SEARCH_LIST는 `programs`(FastAPI 순위 그대로), DOCUMENT_QA는 `answer`·`citations`다. 메시지 조회의 ASSISTANT 메시지는 `resultType`·`result`로 같은 화면을 복원한다.
날짜만 의미하는 값(신청기간·개업일)은 `YYYY-MM-DD`, 시각(createdAt·updatedAt)은 UTC ISO-8601(`Z`)이다. 모집 상태는 Asia/Seoul 오늘 날짜로 계산한다.
