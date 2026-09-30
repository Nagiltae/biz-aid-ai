# Current Task

## Goal / Context

2026-10-01 사용자 요청: V1 코드 마감. 새 기능이 아니라 V2 전에 V1 코드를 장기적으로 관리 가능한 구조로 정리한다.
Spring 도메인 중심 구조, dev/prod profile 분리, MySQL 사용자 활동 기록, Backlog 단계 분류와 V1 기준선을 막는 문제만 최소 수정.

## Read First

[AGENTS](../../AGENTS.md) → [파일 경계](../rules/file-boundaries.md) → [Safety](../rules/safety.md) → [DB 규칙](../rules/database-rules.md) →
[Improvement Backlog](../docs/improvement-backlog.md)의 단계 분류.

## Scope / Acceptance

1. React API·FastAPI Contract·SEARCH_LIST·DOCUMENT_QA·자격 판정·Qdrant·Parser·Chunker·Embedding·JWT 정책·messages AI 결과 구조는 바꾸지 않는다.
2. Spring은 도메인 중심 + 내부 계층, 의존 한 방향. 완전한 DDD 패턴은 들이지 않는다.
3. prod profile에 비밀값·로컬 기본값을 두지 않는다. 개발 Compose 흐름은 유지한다.
4. activity_logs에 비밀번호·토큰·키·질문/답변 전문을 저장하지 않는다.
5. 실제 AI E2E는 1회. 평가·재인덱싱·AWS·FastAPI Compose 통합은 하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-v1-code-closing.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다. backend·frontend 테스트 명령은 [Testing](../docs/testing.md)에 있다.
