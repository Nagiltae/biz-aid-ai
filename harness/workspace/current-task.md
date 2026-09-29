# Current Task

## Goal / Context

2026-09-30 사용자 요청: Phase 3-C Corpus Parsing. 현재 enabled route(PDF / HWP / HWPX)의 전체 corpus를 production parsing pipeline으로
처리하고, 실행에서 드러난 반복적인 일반 parser bug만 최소 보정해 필요한 source만 재처리한 뒤 Phase 3 종료 가능 상태로 정리한다.

## Read First

[AGENTS](../../AGENTS.md) → [Source 규칙](../rules/data-source-rules.md)의 Phase 3 절 →
[Parsing Contract](../../contracts/schemas/document-parsing.contract.json)의 corpus_execution / routes / versioning → [Testing](../docs/testing.md).

## Scope / Acceptance

1. 기존 orchestration을 재사용하는 dev 전용 corpus runner: unique SHA, enabled format, SHA 순서, 순차, source별 timeout·실패 격리, 현재 parse_key skip, progress.
2. 실제 dev 실행: verified source → S3 GET/checksum → parser → DoclingDocument → S3 artifact → document_parse_results. prod 접근·삭제·덮어쓰기 금지.
3. 실패는 status·failure별로 묶어 여러 문서에서 반복되는 일반 bug만 1~3개 대표 문서로 고치고 영향받은 source만 재처리한다.
4. ZIP / XLSX / OTHER / UNKNOWN은 집계만 한다. 신규 parser, Phase 4 Chunking·Embedding·Qdrant·RAG는 시작하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-phase3-3c-corpus-parsing.md).
코드 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다. corpus 실행 자체가 통합 검증이다.
