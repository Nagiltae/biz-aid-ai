# Current Task

## Goal / Context

2026-10-01 사용자 요청: V2-0 기반 작업. 기능 트랙(LLM 출력 계약 안정화, LangChain 최소 도입)과 데이터 트랙(서비스 대상 공고 범위 확정, V2 전용 Qdrant 적재 준비·시작)을 함께 준비한다.
기업정보 기반 개인화 검색은 다음 단계이며 이번 범위가 아니다.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [DB 규칙](../rules/database-rules.md) →
[Eligibility 계약](../../contracts/schemas/eligibility.contract.json) → [Indexing 계약](../../contracts/schemas/document-indexing.contract.json).

## Scope / Acceptance

1. 기업정보는 고정 field ID로 LLM과 주고받고, 허용 field ID·evidence 번호·분야·대상은 출력 schema enum으로 제한한다. application 재검증은 유지한다.
2. LangChain은 `rag/llm.py` LLM 호출 계층만. 후보 필터·검색·RRF·Qdrant 규칙·Citation·최종 상태는 기존 코드.
3. MySQL·S3는 전체 보관, V2 Qdrant는 CLOSED 제외 공고 문서만. V1 collection은 수정·추가 적재 금지. collection 전환은 설정으로.
4. Parser·Chunker·BGE-M3 방식, V1 baseline, API 계약, JWT, support_programs schema는 바꾸지 않는다.
5. 검증은 작게: targeted contract, E01~E03 1회 확인, V2 Smoke 소량. 반복 평가·전체 E2E·LangGraph·LangSmith·AWS 금지.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-v2-0-foundation.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
