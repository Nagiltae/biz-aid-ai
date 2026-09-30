# Current Task

## Goal / Context

2026-10-01 사용자 요청: React + Spring Boot 서비스 V1. 실제 사용자 기능 단위로 React 화면 → Spring API → MySQL을 함께 구현한다.
Spring ↔ FastAPI 실제 연결은 이번 범위가 아니다. AI 검색·자격 판정은 Spring 경계(AiGateway)와 React 결과 UI까지만 준비한다.

## Read First

[AGENTS](../../AGENTS.md) → [파일 경계](../rules/file-boundaries.md) → [DB 규칙](../rules/database-rules.md) → [주석 정책](../rules/code-comment-policy.md) →
[React ↔ Spring 계약](../../contracts/frontend-backend/README.md) → [Spring ↔ FastAPI 경계](../../contracts/backend-ai/README.md).

## Scope / Acceptance

1. Spring: 회원가입·로그인·로그아웃·현재 사용자·토큰 재발급(JWT), 기업정보 등록·조회·수정, 지원사업 목록(QueryDSL)·상세, 대화·메시지 저장·조회, AI 검색·자격 판정 API 경계.
2. React: 로그인·회원가입, 기업정보, 지원사업 목록·필터·상세, AI 검색, 자격 판정 결과, 근거 표시, loading·empty·error 상태.
3. DB: 공통 Flyway V6(한국어 COMMENT). support_programs는 조회 전용. MyBatis 없음(JPA + QueryDSL).
4. Compose `app` profile로 MySQL + Spring + React 실행. 기존 dev-db·dev-vector 흐름 유지.
5. FastAPI·ServiceRuntime·Retriever·RAG·EligibilityService·Qdrant·Parser·Chunker·Embedding은 수정하지 않는다. 가짜 AI 결과를 만들지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-service-v1-react-spring.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다. backend·frontend 테스트 명령은 [Testing](../docs/testing.md)에 있다.
