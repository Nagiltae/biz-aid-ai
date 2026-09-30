# Current Task

## Goal / Context

2026-09-30 사용자 요청: 자연어 질문 → LLM 구조화 추출 → 허용 값 검증 → ProgramCandidateFilter → 기존 MySQL 후보 → scoped Hybrid RAG·citation.
LLM은 필터 입력 후보만 제안하고 SQL·후보 선택·날짜·검색 질의는 application이 정한다.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [RAG](../docs/rag.md) → [RAG 계약](../../contracts/schemas/rag-answer.contract.json) →
[Improvement Backlog](../docs/improvement-backlog.md).

## Scope / Acceptance

1. 추출 값은 활성 공고의 실제 category·target 값으로 검증하고, 목록 밖·지역·소관기관 조건은 적용하지 않고 unapplied로 보고한다.
2. "지금"은 application 날짜(Asia/Seoul 또는 --as-of)로 not_closed_on을 정한다. 날짜 미상 공고 규칙(IMP-011)은 바꾸지 않는다.
3. 추출 실패는 fallback 없이 실패한다. Retrieval·RAG prompt·citation·NO_CANDIDATES는 바꾸지 않는다.
4. 자격 판단·FastAPI·LangGraph·Query Rewrite·Gemini·re-index는 하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-phase6c-natural-filter.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
