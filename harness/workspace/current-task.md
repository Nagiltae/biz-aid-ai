# Current Task

## Goal / Context

2026-09-30 사용자 요청: MySQL deterministic candidate filtering + pblanc_id-scoped RAG.
정형 조건 → MySQL 후보 pblanc_id → 기존 Hybrid Retriever를 후보로 제한 → 기존 RAG → 근거 답변·citation을 연결한다.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [DB 규칙](../rules/database-rules.md) → [RAG](../docs/rag.md) →
[RAG 계약](../../contracts/schemas/rag-answer.contract.json) → [Improvement Backlog](../docs/improvement-backlog.md).

## Scope / Acceptance

1. 후보는 실제 V1 column(source_active·source_deleted·category·target·jurisdiction_name·파생 신청기간)만 쓰고 자유 텍스트를 해석하지 않는다.
2. Retriever는 Qdrant filter로 후보 scope를 강제하고 scoring·top_k·RRF·collection은 바꾸지 않는다. 빈 후보는 검색·LLM 없이 끝낸다.
3. 자연어 조건 추출·자격 판단·FastAPI·LangGraph·Gemini·re-index는 하지 않는다. IMP-008 상태를 갱신한다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-phase6b-candidate-scoped-rag.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
