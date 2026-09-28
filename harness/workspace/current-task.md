# Current Task

## Goal / Context

2026-09-29 사용자 승인: Phase 3 Document Parsing. S3의 검증된 원본 문서를 후속 Chunking이 직접 소비할
DoclingDocument와 추적 metadata로 변환한다. PDF는 Docling, HWP는 HWP → PDF → Docling, HWPX는 native XML을
HwpxDoclingAdapter로 DoclingDocument에 옮긴다. 별도 canonical document tree는 만들지 않는다.
입력은 Phase 2.5의 unique content SHA 3,231개(parse 단위)이며 relation 3,288개는 provenance로만 센다. route는 `detected_format`만 따른다.

3-A(Contract + HWPX slice)는 DONE이다. implementation PASS, local check-all PASS,
[AGY Review](reports/agy/2026-09-29-phase3-document-parsing-3a-review.md) PASS,
[Status Semantics Re-review](reports/agy/2026-09-29-phase3-document-parsing-3a-status-addendum.md) PASS,
2026-09-29 Human Review PASS. 3-A 결과는 [3-A Report](reports/development/2026-09-29-phase3-document-parsing.md)에 보존한다.

## Read First

[AGENTS](../../AGENTS.md) → [Workflow](../docs/workflow.md) → [Source 규칙](../rules/data-source-rules.md) →
[파일 경계](../rules/file-boundaries.md) → [Pipeline](../docs/data-pipeline.md) →
[Parsing Contract](../../contracts/schemas/document-parsing.contract.json) → [Testing](../docs/testing.md).

## Scope / Acceptance

현재 sub-step 3-B: Docling PDF route. PDF byte → integrity 확인 → Docling DocumentConverter(do_ocr=false) → DoclingDocument →
normalize_document → apply_gate → ParseResult. 기존 router·ParseResult·Gate를 재사용하고 별도 PDF parser·문서 tree는 만들지 않는다.
native text 부족 PDF는 OCR_REQUIRED이며 PARSE_FAILED가 아니다. OCR engine은 설치·구현하지 않는다.
3-B 보정: Docling 표 cell 탈락을 warning evidence로 노출하고 PARSED가 표 완전성을 뜻하지 않음을 Contract에 명시한다.
표 설정은 A/B evidence 없이 바꾸지 않는다. 모델은 명시적 artifact 경로의 고정 snapshot만 쓰며 test runtime 다운로드는 금지다.
AGY 3-B Review CONDITIONAL PASS의 B-1(CI artifact 공급)은 Actions cache + 명시적 provisioning + identity verify로 로컬에서 해결했다.
3-B 상태: implementation complete / local validation PASS / AGY conditional issue addressed locally / remote CI verification pending / human review pending.
Pending: remote CI 실행 확인, 전체 실행 전 동시성·메모리 정책, OCR_REQUIRED 1쪽·picture 0 문서 3건의 원인.
HWP→PDF 변환기는 UNDECIDED(HWP 15건 Pilot 후 확정)이며 이후 같은 `convert_pdf` 경계를 재사용한다.
HWPX는 3-A 동작을 유지한다. XLSX / ZIP / OTHER / UNKNOWN은 POLICY_PENDING이다.
Parsed artifact 저장(S3 PUT·신규 migration), Pilot, Full Parse, 대량 S3 GET/PUT은 후속 sub-step이다.
OCR·Chunking·Embedding·Qdrant·RAG·LLM, 재다운로드·재업로드·S3/로컬 원본 삭제·prod는 범위 밖이다.

## Validation / Reports

[Final Report](reports/development/2026-09-29-phase3-3b-docling-pdf.md).
Artifact가 필요하면 artifacts/development/phase3-document-parsing/에 기록한다.
Control/Input STRICT / Generated Output NON-GATING을 유지하고 최종 검증 뒤 Report 때문에 재검증하지 않는다.
