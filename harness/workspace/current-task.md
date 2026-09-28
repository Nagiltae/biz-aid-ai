# Current Task

## Goal / Context

2026-09-28 사용자 승인: Phase 1B Full Structured Data Sync.
Phase 1A 제품 구조를 재사용하며 dev API 전체 pagination·Raw 보존·완전성·정규화·MySQL 적재를 검증한다.
이전 current-task 원문은 artifacts/codex/phase1b-full-sync/repository-before.json과 이번 Final Report에 보존한다.

## Read First

[AGENTS](../../AGENTS.md) → [Workflow](../docs/workflow.md) → [Source 규칙](../rules/data-source-rules.md) →
[Pipeline](../docs/data-pipeline.md) → [Skill](../skills/data-pipeline-change/SKILL.md) →
[FULL Contract](../../contracts/schemas/full-structured-sync.contract.json) → [Git 정책](../rules/git-policy.md).

## Scope / Acceptance

실행 첫 totalCount를 고정하고 모든 Raw/checksum·Page·유효 ID unique·count 일치를 DB mutation 전에 검증한다.
오류·중복·count 변화·불완전 FULL은 FAIL이며 reconciliation 금지다. SAMPLE/PARTIAL absence도 삭제 근거가 아니다.
첫 Live FULL은 soft-delete 후보 DRY_RUN만 계산한다. 실제 soft-delete/physical DELETE·prod·증분 조회는 금지한다.
제품 Source Model/Normalizer/payload/fingerprint/lifecycle·V1/V2·COMMENT·Secret을 재설계하지 않는다.
API 수집/검증/정규화 뒤 DB-only atomic transaction, 제한된 시간 budget·DB lock·rollback·readback을 확인한다.
Unit/Contract·Integration·Full Validation → Live FULL → Live 검증 → Final Validation → Codex Report 순서다.
AGY 독립 Review / Human Review는 pending이다. 문서 제품화·Parser·AI·새 schema·Git history 변경은 범위 밖이다.

## Validation / Reports

[Final Report](reports/codex/2026-09-28-phase1b-full-sync.md).
Artifact는 artifacts/codex/phase1b-full-sync/에 기록한다. 기존 Control/Input STRICT / Generated Output NON-GATING을 유지한다.
최종 검증 후 Report 때문에 재검증하지 않는다. 실제 soft-delete는 별도 승인 Task와 새 성공 FULL 검토가 필요하다.
