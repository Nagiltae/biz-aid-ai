# Current Task

## Goal / Context

2026-10-01 사용자 요청: Spring Boot ↔ FastAPI 실제 연결 + React AI E2E V1. 새 AI 기능이 아니라 이미 만든 React·Spring Boot·FastAPI를 하나의 서비스 흐름으로 연결한다.
React → Spring(`/api/ai/query`, `/api/programs/{id}/eligibility`) → HttpAiGateway → FastAPI(`/internal/v1/*`) → 기존 AI 서비스 → Spring → React.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [파일 경계](../rules/file-boundaries.md) →
[Spring ↔ FastAPI 경계](../../contracts/backend-ai/README.md) → [내부 API 계약](../../contracts/schemas/internal-api.contract.json) → [React ↔ Spring 계약](../../contracts/frontend-backend/README.md).

## Scope / Acceptance

1. Spring은 FastAPI 결과(목록 순위·답변·자격 상태·근거)를 재판단·재정렬하지 않고 계약 검증 후 전달한다. AI POST 자동 재시도 없음.
2. 성공한 AI 응답만 ASSISTANT 메시지로 저장한다(구조화 결과 포함). 실패 시 가짜 ASSISTANT 없음.
3. 서비스 간 인증은 공유 키(`INTERNAL_AI_API_KEY`). 내부 인증 실패는 사용자 401이 아니라 502 ai_service_auth_failed다.
4. FastAPI의 AI 로직(자연어 필터·검색·RRF·RAG prompt·Citation·EligibilityService·Parser·Chunker·Embedding·index)과 JWT·support_programs는 바꾸지 않는다.
5. FastAPI는 호스트 실행, Compose 통합은 IMP-017(사용자 결정).
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-ai-e2e-v1.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다. backend·frontend 테스트 명령은 [Testing](../docs/testing.md)에 있다.
