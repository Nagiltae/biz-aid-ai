# Current Task

## Goal / Context

2026-09-30 사용자 요청: RAG Answer Generation v1. 질문 → 기존 Hybrid Retriever(top_k 5) → evidence context → 교체 가능한 LlmProvider(Ollama qwen3.5:9b)
→ 근거 답변 + application citation을 구현한다. Retriever·embedding·collection·RRF·top_k는 바꾸지 않는다.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [RAG](../docs/rag.md) → [RAG 계약](../../contracts/schemas/rag-answer.contract.json) →
[Retrieval 계약](../../contracts/schemas/document-retrieval.contract.json) → [Testing](../docs/testing.md).

## Scope / Acceptance

1. RAG는 `retrieval.Retriever`를 그대로 쓰고 LLM은 `LlmProvider` 경계로만 호출한다. prompt는 provider 공통 하나다.
2. LLM은 evidence id만 고르고 citation metadata는 application이 검색 결과에서 resolve한다. 유효 근거가 없으면 확인 불가로 답한다.
3. 검증은 targeted test와 실제 Qwen smoke 최대 3문항이다. Gemini·MySQL 결합·자격 판단·LangGraph·전체 Gold 생성 평가는 하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-phase6-rag-answer.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
