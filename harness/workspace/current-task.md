# Current Task

## Goal / Context

2026-09-28 사용자 승인: Phase 0 Document Download Gate.
api-quality-dev-20260928-01의 기존 동일 100 Item / printFlpthNm만 사용하는 dev 전용 제한된 도구를 구현·검증한다.
과거 Rebase 검증은 Report와 독립 AGY PASS에 보존됐다. 이번 Task의 AGY / Human Review는 pending이다.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[API 품질 Report](reports/2026-09-28-phase0-api-data-quality-report.md) →
[이전 Task / Rebase Report](reports/2026-09-28-post-rebase-merge-verification-report.md) →
[독립 Rebase Review](reports/agy-post-rebase-verification-review.md) →
[Pipeline](../docs/data-pipeline.md) → [Source 규칙](../rules/data-source-rules.md) →
[Skill](../skills/data-pipeline-change/SKILL.md) → [다운로드 계약](../../contracts/schemas/phase0-document-download.contract.json).

## Scope / Acceptance

순차 100 Primary Candidate 다운로드·원본 byte·SHA·형식 식별·실패 집계·Checkpoint / Resume·재현 가능한 Report.
새 API 수집·Supplementary 다운로드·본문 Parsing·OCR·DB·AI·GO/DROP·prod 실행은 범위 밖이다.
사용자 .env.dev / .env.prod를 수정하거나 stage·출력하지 않는다. API 인증정보를 문서 요청에 전달하지 않는다.
dev에서만 작업한다. Commit / Push / Merge / Rebase / Branch 변경은 하지 않는다.

## Validation / Reports

Offline 전체 PASS → dev 다운로드 → Gate / Task Report와 Git index 확정 → 최종 전체 Validation → tracked 파일 동결.
[Final Report](reports/2026-09-28-codex-document-download-gate-report.md).
Gate Report는 Task Report에서 연결하며 모든 실제 지표와 UNMEASURED·미확정·실패를 구분한다.
현재 구현·실행·Validation 상태의 최종 근거는 Final Report / 실행 로그다. 현재 Task 독립 Review / Human Review는 pending이다.
