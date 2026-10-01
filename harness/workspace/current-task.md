# Current Task

## Goal / Context

2026-10-01 사용자 요청: V2-4 최종 추천 결과 조립. React 구현 전에 workflow가 COMPLETED일 때 클라이언트가 받을 final_result 계약을 고정한다.
새 LLM 호출·검색 재정렬(IMP-019)·prompt 튜닝·React·LangSmith·IMP-021은 이번 범위가 아니다. V2 collection batch는 건드리지 않는다.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [파일 경계](../rules/file-boundaries.md) →
[Spring ↔ FastAPI 경계](../../contracts/backend-ai/README.md) → [내부 API 계약](../../contracts/schemas/internal-api.contract.json) → [화면 API](../../contracts/frontend-backend/README.md).

## Scope / Acceptance

1. COMPLETED일 때만 final_result(recommended·excluded·unresolved)를 만든다. 물을 수 있는 부족 정보가 남으면 WAITING_FOR_USER를 유지한다.
2. 분류는 기존 판정 상태로만 한다(ELIGIBLE → 추천, INELIGIBLE → 제외, 근거 부족·판정 실패 → 판단 불가). 새 점수·LLM 판단 없음.
3. 묶음 안 순서는 검색 순위 그대로다. 이유·근거는 그 공고 판정의 조건과 검증된 Citation만 쓴다.
4. 추천 0건도 정상 결과다. 기존 V1/V2 API는 회귀하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-v2-4-final-result.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
