# Current Task

## Goal / Context

2026-10-01 사용자 요청: V1 AI 평가 기준선 고정. 새 AI 기능이나 품질 개선 없이 현재 production
SEARCH_LIST·DOCUMENT_QA·Eligibility를 동일한 작은 시험으로 1회 측정해 V2 변경 전 비교점을 남긴다.

## Read First

[AGENTS](../../AGENTS.md) → [RAG](../docs/rag.md) → [Testing](../docs/testing.md) →
[제품 평가](../../evals/README.md) → [Improvement Backlog](../docs/improvement-backlog.md).

## Scope / Acceptance

1. `evals/v1_baseline/cases-v1.json` 10건(검색 4·QA 3·자격 3)을 sha256으로 동결한다.
2. 자연어 문장 전체가 아니라 공고·근거·Citation·핵심 사실·자격 상태와 핵심 조건을 판정한다.
3. 실제 dev V1 실행은 1회만 하며 문제를 발견해도 production Prompt·검색·RAG·판정 코드를 고치지 않는다.
4. 실패는 결과와 Backlog에 남기고 V2는 가능한 한 동일 baseline으로 비교한다. 기준 변경은 새 version이다.
5. LangSmith·LangChain·LangGraph·Bedrock·Gemini와 독립 Review는 이번 범위가 아니다.

## Result / Validation

- 1회 실행: 10건 시도, 7 PASS / 3 FAIL. SEARCH_LIST 4/4, DOCUMENT_QA 2/3, Eligibility 1/3.
- QA·Eligibility citation의 다른 공고 혼입 0. 검색 중복·MySQL 후보 범위 밖 결과 0.
- [Final Report](reports/development/2026-10-01-v1-ai-baseline.md)
- 작은 Contract test 후 `./scripts/check-all.sh`를 마지막 1회 실행한다.

AGY 독립 Review는 사용자 요청에 따라 이번 Task에서 수행하지 않는다.
