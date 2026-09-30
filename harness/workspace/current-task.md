# Current Task

## Goal / Context

2026-09-30 사용자 요청: FastAPI Internal API v1. 이미 구현된 자연어 query(SEARCH_LIST·DOCUMENT_QA)와 단일 공고 Eligibility를
서비스 계층(Spring Boot)이 호출할 내부 HTTP API로 얇게 노출한다. 판단 로직은 기존 서비스에 둔다.

## Read First

[AGENTS](../../AGENTS.md) → [파일 경계](../rules/file-boundaries.md) → [내부 API 계약](../../contracts/schemas/internal-api.contract.json) →
[RAG 계약](../../contracts/schemas/rag-answer.contract.json) → [Eligibility 계약](../../contracts/schemas/eligibility.contract.json).

## Scope / Acceptance

1. handler는 검증·ServiceRuntime 호출·직렬화만 한다. CLI와 API는 같은 runtime을 쓴다.
2. provider·DB pool·Qdrant client는 lifespan에서 한 번, BGE-M3는 첫 사용 때 한 번 만든다. 판단 결과는 HTTP 200이다.
3. Spring Boot·React·인증·CORS·LangGraph·Gemini·Profile 저장·re-index는 하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-internal-api-v1.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
