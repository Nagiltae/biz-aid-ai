# Current Task

## Goal / Context

2026-09-28 사용자 승인: Phase 2 Full Document Acquisition.
dev MySQL의 검증된 1,554개 support_programs만 Source로 사용해 공식 문서 후보의 원본 byte와 provenance metadata를 수집한다.
Phase 1B API FULL을 재실행하지 않으며 기존 구조화 데이터·Raw·fingerprint·lifecycle·V1/V2를 보존한다.

## Read First

[AGENTS](../../AGENTS.md) → [Workflow](../docs/workflow.md) → [Source 규칙](../rules/data-source-rules.md) →
[파일 경계](../rules/file-boundaries.md) → [DB 규칙](../rules/database-rules.md) →
[Pipeline](../docs/data-pipeline.md) → [Skill](../skills/data-pipeline-change/SKILL.md) →
[Document Contract](../../contracts/schemas/document-acquisition.contract.json).

## Scope / Acceptance

PRINT_CANDIDATE / ATTACHMENT_CANDIDATE는 원본 field provenance이며 본공고/부속 의미 확정이 아니다.
순차 요청·자동 retry 0·redirect 3·100 MiB·timeout 15초의 로컬 안전 경계와 원본 overwrite 금지를 적용한다.
공개 문서 요청에 인증정보를 전달하지 않는다. 실제 signature/container로 형식을 관찰하고 HTML 오류 응답은 실패로 보존한다.
동일 URL은 한 번 요청하고 동일 SHA binary는 한 번 저장하되 모든 pblancId/source field/token 관계는 DB에 남긴다.
중단 run은 검증된 relation에서 resume한다. 이전 실패는 같은 run에서 자동 재시도하지 않고 새 run에서만 다시 시도한다.
Offline/Contract → Integration → Preliminary Validation → dev Live → Integrity/Quality → Final Validation → Codex Report 순서다.
AGY 독립 Review / Human Review는 pending이다. Parsing·OCR·Chunking·AI·prod·DB reset·구조화 Source 변경은 범위 밖이다.

## Validation / Reports

[Final Report](reports/codex/2026-09-28-phase2-document-acquisition.md).
Artifact는 artifacts/codex/phase2-document-acquisition/에 기록한다. Binary는 ignored `data/downloaded/`에 보존한다.
Control/Input STRICT / Generated Output NON-GATING을 유지하고 최종 검증 뒤 Report 때문에 재검증하지 않는다.
