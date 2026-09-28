# Current Task

## Goal / Context

2026-09-29 사용자 승인: Phase 2.5 S3 Document Storage + Local Pipeline Execution.
Phase 2의 3,231개 고유 binary와 3,288개 provenance relation을 기존 S3 object에 연결한다.
S3 object는 HEAD checksum과 실제 byte readback으로 검증하며 기존 로컬 corpus는 AGY와 사용자 승인 전까지 보존한다.

## Read First

[AGENTS](../../AGENTS.md) → [Workflow](../docs/workflow.md) → [Source 규칙](../rules/data-source-rules.md) →
[파일 경계](../rules/file-boundaries.md) → [DB 규칙](../rules/database-rules.md) →
[Pipeline](../docs/data-pipeline.md) → [Skill](../skills/data-pipeline-change/SKILL.md) →
[Document Contract](../../contracts/schemas/document-acquisition.contract.json), [DB 규칙](../rules/database-rules.md).

## Scope / Acceptance

고정 region/bucket/prefix와 SHA 기반 key를 사용하고 ETag를 SHA로 해석하지 않는다.
기존 object는 HEAD `ChecksumSHA256` 검증 후 재사용하며 metadata 연결 단계의 PUT/DELETE/Copy/multipart는 금지한다.
모든 3,231개 object가 검증된 뒤 3,288개 relation을 단일 DB transaction으로 연결하고 실제 byte readback으로 Phase 2 run을 재검증한다.
`storage_path`는 이번 단계에서 legacy 로컬 경로를 유지하며 `s3_*`가 검증된 영구 저장 위치다.
AGY 독립 Review / Human Review는 pending이다. 로컬 삭제·Parser·upstream HTTP·prod는 범위 밖이다.

## Validation / Reports

[Final Report](reports/codex/2026-09-29-phase2-5-s3-storage.md).
Artifact는 artifacts/codex/phase2-5-s3-storage/에 기록한다. 로컬 Binary는 ignored `data/downloaded/`에 보존한다.
Control/Input STRICT / Generated Output NON-GATING을 유지하고 최종 검증 뒤 Report 때문에 재검증하지 않는다.
