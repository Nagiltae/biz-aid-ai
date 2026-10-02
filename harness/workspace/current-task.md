# Current Task — V2 적재 결과 확인과 완전성 검증

## Goal / Context

2026-10-02 사용자 요청: V2 서비스 범위 데이터(2,541문서) 파싱·인덱싱 batch가 끝났다. 적재 결과를 읽기 전용으로 확인하고 입력 → 파싱 → 인덱싱 → Qdrant의 완전성을 대조한다.
V2 collection 전환(`QDRANT_COLLECTION_NAMESPACE`), `.env.dev` 읽기·수정, 재파싱·재인덱싱·point 삭제, V1 collection·V1 baseline 변경, 미지원 형식 작업, commit/push는 범위가 아니다.

## Current State Snapshot

- 완료: V1 E2E·고정 평가(10건 중 7 PASS), V2-0~V2-6 기능 구현, V2 데이터 파싱(COMPLETED, PARSED 2,534)·인덱싱(COMPLETED, 2,534문서·61,335 point, `final.ok=true`).
- 완료(이번 Task): 완전성 대조. 입력 2,541 = PARSED 2,534 + 제외 7, INDEXED 2,534 = Qdrant V2 문서 2,534, point 61,335 = 인덱싱 기록 61,335. V1 collection 3,849 point 그대로.
- 진행: 없음(실행 중인 batch 없음).
- 미검증: V2 collection 서비스 전환, React 화면에서 추천 흐름 완주, 실제 workflow의 LangSmith 기록, cases-v2 품질 평가, 제외 7문서 원인 분석·재처리.

## Read First

[AGENTS](../../AGENTS.md) → [Backlog](../docs/improvement-backlog.md)(IMP-006·007·010·018) → [V2-0 Report](reports/development/2026-10-01-v2-0-foundation.md) §4.

## Scope / Acceptance

1. 상태 조회·대조는 읽기 전용이다. state가 완료가 아니거나 `final.ok`가 false면 원인만 보고한다.
2. 문서 수와 point 수를 섞지 않고 단계별로 대조한다.
3. 실패·제외 문서는 원인별 분류만 하고 기존 Backlog ID에 Evidence로 남긴다.
4. 다음 단계: V2 collection 전환 → 화면 완주 + LangSmith 확인 → cases-v2 평가.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-v2-data-completeness.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
