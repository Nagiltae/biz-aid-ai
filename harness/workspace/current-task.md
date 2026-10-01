# Current Task

## Goal / Context

2026-10-01 사용자 요청: V2-2 Top 3 지원사업 자격 판정. V2-1 개인화 검색 Top 3 각각에 기존 단일 공고 자격 판정을 연결한다.
추가 질문·재판정·LangGraph·React V2는 이번 범위가 아니다. V2 collection batch는 별도로 실행 중이며 건드리지 않는다.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [파일 경계](../rules/file-boundaries.md) →
[Spring ↔ FastAPI 경계](../../contracts/backend-ai/README.md) → [내부 API 계약](../../contracts/schemas/internal-api.contract.json) → [Eligibility 계약](../../contracts/schemas/eligibility.contract.json).

## Scope / Acceptance

1. 검색 Top 3 순서대로 공고마다 기존 `EligibilityService.evaluate`를 호출한다. 판정 엔진을 복제하지 않는다.
2. 공고별 근거 범위를 격리하고, 한 공고 실패는 그 공고만 FAILED + 오류 코드로 남긴다(UNKNOWN·성공으로 바꾸지 않음).
3. Spring은 저장된 기업정보만 snapshot으로 보내고 없는 값은 만들지 않는다. FastAPI는 users·companies를 읽지 않는다.
4. 조합은 FastAPI 서비스가 소유하고 클라이언트가 공고별로 AI 흐름을 조립하지 않는다. V1 API는 바꾸지 않는다.
5. Spring 제한시간을 몰래 늘리지 않고 큐를 만들지 않는다. 초과하면 측정·기록한다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-v2-2-top3-eligibility.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
