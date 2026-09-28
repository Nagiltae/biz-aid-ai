# Current Task

## Goal / Context

2026-09-29 사용자 승인: Phase 3 Document Parsing. S3의 검증된 원본 문서를 후속 Chunking이 직접 소비할
DoclingDocument와 추적 metadata로 변환한다. PDF는 Docling, HWP는 HWP → PDF → Docling, HWPX는 native XML을
HwpxDoclingAdapter로 DoclingDocument에 옮긴다. 별도 canonical document tree는 만들지 않는다.
입력은 Phase 2.5의 unique content SHA 3,231개(parse 단위)이며 relation 3,288개는 provenance로만 센다. route는 `detected_format`만 따른다.
이전 Task: [Claude Producer Report](reports/development/2026-09-29-claude-producer-harness.md),
[AGY Handoff Review](reports/agy/2026-09-29-same-task-handoff-review.md).

## Read First

[AGENTS](../../AGENTS.md) → [Workflow](../docs/workflow.md) → [Source 규칙](../rules/data-source-rules.md) →
[파일 경계](../rules/file-boundaries.md) → [Pipeline](../docs/data-pipeline.md) →
[Parsing Contract](../../contracts/schemas/document-parsing.contract.json) → [Testing](../docs/testing.md).

## Scope / Acceptance

현재 sub-step 3-A: Contract + 최소 vertical slice(HWPX → HwpxDoclingAdapter → DoclingDocument, 공통 router·정규화·문서 Gate).
3-A 상태: implementation complete / local validation PASS / AGY independent review pending / human review pending.
AGY와 사용자 Review가 끝난 뒤에만 3-A를 DONE으로 전환하며 그 전에는 3-B(PDF route)를 시작하지 않는다.
HWPX 표본 실행 성공은 execution evidence이며 Heading·Paragraph·List·Table·Reading Order·Source Location 품질 검증은 pending이다.
PDF / HWP route는 ROUTE_NOT_ENABLED다. HWP→PDF 변환기는 후보 LibreOffice + H2Orestart, 결정 UNDECIDED(HWP 15건 Pilot 후 확정)다.
XLSX / ZIP / OTHER / UNKNOWN은 POLICY_PENDING이며 원본을 보존한다. Generic ZIP은 member provenance Contract 전까지 전개하지 않는다.
Parsed artifact는 S3, parse 상태·provenance·pointer·parser metadata는 MySQL, 로컬은 fixture/scratch/임시 처리만이다.
저장 구현(S3 PUT·신규 migration), Pilot, Full Parse, 대량 S3 GET/PUT은 후속 sub-step에서 사용자 확인 후 진행한다.
OCR·Chunking·Embedding·Qdrant·RAG·LLM, 재다운로드·재업로드·S3/로컬 원본 삭제·prod는 범위 밖이다.
AGY 독립 Review / Human Review는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-09-29-phase3-document-parsing.md).
Artifact가 필요하면 artifacts/development/phase3-document-parsing/에 기록한다.
Control/Input STRICT / Generated Output NON-GATING을 유지하고 최종 검증 뒤 Report 때문에 재검증하지 않는다.
