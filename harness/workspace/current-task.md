# Current Task

## Goal / Context

2026-09-30 사용자 요청: Improvement Backlog IMP-001 — chunk의 검색용 embedding_text에 공고명(MySQL support_programs.name)을 넣어
일반 heading("2. 지원 요건") evidence chunk가 같은 문서 안에서 밀리는 문제를 개선한다. 근거 본문(chunk text)과 RAG prompt는 바꾸지 않는다.

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md)의 Chunking 줄 → [Chunking 계약](../../contracts/schemas/document-chunking.contract.json) →
[Improvement Backlog](../docs/improvement-backlog.md).

## Scope / Acceptance

1. embedding_text = 공고명 + 기존 contextualize 결과. chunk text 불변. chunker_version 2로 chunk_set_key를 바꾼다.
2. 고정 100-source만 기존 indexing runner로 재적재하고 stale point가 남지 않는지 확인한다. re-parse·전체 corpus는 하지 않는다.
3. 확인은 Gold G01, "비즈플러스카드 지원요건" QA, 정상 QA 1건뿐이다. BGE-M3·RRF·top_k·Retriever·prompt는 바꾸지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-imp001-title-context.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
