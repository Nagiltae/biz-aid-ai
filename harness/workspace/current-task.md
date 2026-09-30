# Current Task

## Goal / Context

2026-09-30 사용자 요청: AI 서비스 개발(Retriever) 착수 전 기반 정리·전체 리뷰·Harness 안정화.
새 기능은 추가하지 않는다. 정상 동작하는 Parser·Chunking·Embedding·Qdrant 경로를 재설계하지 않는다.

## Read First

[AGENTS](../../AGENTS.md) → [Architecture](../docs/architecture.md) → [Pipeline](../docs/data-pipeline.md)의 Identity 요약 →
[파일 경계](../rules/file-boundaries.md) → [AI 경계](../rules/ai-boundary-rules.md) → [Testing](../docs/testing.md).

## Scope / Acceptance

1. 호출처가 없음을 확인한 dead code·unused import만 삭제한다. 애매한 후보는 보고서에 보류로 남긴다.
2. 문서·Rule·Contract·Registry를 실제 구현 상태에 맞추고, 반복 실수를 막는 규칙만 최소 추가한다.
3. parse_key·chunk_set_key·embedding_key와 artifact scope, Qdrant schema 규칙은 바뀌지 않아야 한다.
4. 실제 확인은 기존 parsed source 1개의 Chunking → Indexing smoke로 한정한다. Retriever·RAG·LangGraph·LLM·corpus 실행은 하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-30-pre-ai-service-cleanup.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
