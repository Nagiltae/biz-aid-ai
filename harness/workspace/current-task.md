# Current Task

## Goal / Context

2026-10-01 사용자 요청: IMP-014 — 지원사업 목록 검색(SEARCH_LIST)이 같은 공고의 여러 문서 조각 때문에 서로 다른 공고를 충분히 보여주지 못하는 문제를 고친다.
출력 단위(공고)에 맞춰 공고별 최고 조각으로 순위를 매기고 서로 다른 공고를 최대 5개 돌려준다.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → [RAG](../docs/rag.md) → [RAG 계약](../../contracts/schemas/rag-answer.contract.json)의 discovery 절 →
[Improvement Backlog](../docs/improvement-backlog.md)의 IMP-014.

## Scope / Acceptance

1. 목록은 공고 단위이며 같은 공고의 조각이 목록 자리를 독점하지 않는다. 중복 0, 후보 범위 밖 0, LLM 호출은 조건 추출 1회다.
2. BGE-M3·dense/sparse·RRF(k=60)·collection·index·DOCUMENT_QA hybrid top5는 바꾸지 않는다. 공고별 검색 반복·전체 후보 검색은 하지 않는다.
3. 범위 밖이거나 검색 근거가 없는 공고로 목록을 채우지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-imp014-discovery-diversity.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
