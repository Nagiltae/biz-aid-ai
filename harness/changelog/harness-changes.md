# Harness 변경 이력

## 2026-09-30 — Phase 6 RAG Answer v1

사용자 승인으로 근거 기반 답변 v1을 추가한다: Hybrid top5 → evidence context → `LlmProvider`(Ollama qwen3.5:9b) → JSON 답 → application citation.
규칙 변경(보고): AI 경계의 "RAG·LLM·답변 생성 금지"를 dev RAG v1 승인으로 옮겼다. LangGraph·Reranker·query rewrite·expansion·자격 판단·MySQL 결합 금지는 유지한다.
AI 경계에 evidence 밖 사실 금지, application citation resolve, provider 교체 불변 규칙을 한 줄씩 추가하고 RAG 계약·test로 보호한다. Registry phase는 `phase6-rag-answer`다.
FastAPI(`ai/`)는 Registry상 미구현이라 만들지 않고 dev CLI를 진입점으로 두었다.
결과: [Phase 6 Report](../workspace/reports/development/2026-09-30-phase6-rag-answer.md). AGY 검토 pending.

## 2026-09-30 — Retrieval Evaluation (gold-v1)

동결 Gold 12문항으로 dense·sparse·hybrid(top_k 5)를 평가하는 `evals/retrieval/evaluate.py`를 추가했다(Gold hash 불일치 시 실행 거부).
evals README에 "Gold는 평가 대상 실행 전 확정·동결, 결과를 본 뒤 유리하게 수정 금지(새 버전으로만)" 규칙을 추가했다.
Retriever·embedding·collection·RRF 설정 변경 없음. 결과: [Evaluation Report](../workspace/reports/development/2026-09-30-retrieval-evaluation.md). AGY 검토 pending.

## 2026-09-30 — 100-source Retrieval dataset build

사용자 승인으로 기존 100-source parser corpus 중 이전 parse_key인 PDF·HWP 60건을 기존 corpus runner로 재parsing하고 100건을 dev Qdrant에 적재한다.
indexing용 얇은 bounded runner(`indexing/corpus.py`, `scripts/run_corpus_indexing.py`)를 추가했다: 명시 목록만, current PARSED gate 선행, resume, source 격리, source 경계 종료.
Source 규칙에 corpus indexing 한 줄을 추가했다. Parser·Chunker·Embedder·Qdrant schema 변경 없음.
결과: [Dataset Report](../workspace/reports/development/2026-09-30-dataset100-build.md). AGY 검토 pending.

## 2026-09-30 — Phase 5 Document Retrieval

사용자 승인으로 read-only Retriever(query embedding, dense·sparse·RRF hybrid)를 추가한다. Registry phase는 `phase5-document-retrieval`이다.
규칙 변경(보고): AI 경계의 "Retriever·query embedding 금지"를 승인 범위로 옮기고 RAG·LLM·LangGraph·Reranker·query rewrite·expansion·eligibility·답변 생성 금지는 유지했다.
AI 경계·파일 경계에 같은 embedder, identity 기반 collection, read-only 규칙을 한 줄씩 두고 test가 기계적으로 검사한다. Retrieval Contract를 추가했다.
결과: [Phase 5 Report](../workspace/reports/development/2026-09-30-phase5-document-retrieval.md). AGY 검토 pending.

## 2026-09-30 — Cleanup B-1: HWP converter identity 실패 격리

`chunking/source.current_parse_key`가 `HwpConversionError`를 `PipelineError("hwp_converter_identity_unavailable:<code>")`로 바꿔 CLI의 source 단위 격리에 포함한다.
Source 규칙에 'source 단위 실패는 PipelineError로만 격리하고 하위 예외는 단계 경계에서 변환한다' 한 줄을 추가했다. parse_key 규칙·converter 동작 변경 없음.

## 2026-09-30 — Pre AI Service Cleanup

Retriever 착수 전 정리. 기능·identity 변경 없음(parse_key·chunk_set_key·embedding_key 불변 확인).
Registry phase를 `phase4-document-indexing`으로 옮기고 setup 검사가 qdrant-client를 확인한다(parsing 전제 검사는 유지).
Parsing Contract의 `TABLE_QUALITY_FAILED` downstream 규칙이 Chunking Contract·구현과 충돌해, "표 구조로는 들어가지 않고 보존 text만 chunk"로 명확히 했다. 규칙 완화가 아니라 기존 구현 의미의 명시다.
파일 경계에 parsing ← chunking ← indexing 단방향 의존, Source 규칙에 artifact scope별 identity, DB 규칙에 Qdrant 파생 index 경계를 한 줄씩 추가했다.
완료된 Table Engine Evaluation 전제 문장(Phase 4 진입 금지)을 삭제했다. AGENTS·README·Architecture·RAG·Pipeline·infra·contracts 문서를 현재 구현에 맞췄다.
결과: [Cleanup Report](../workspace/reports/development/2026-09-30-pre-ai-service-cleanup.md). AGY 검토 pending.

## 2026-09-30 — Phase 4-B Document Indexing

FinalChunk → BGE-M3 dense·sparse → dev Qdrant 적재를 추가한다. 가중치는 기존 모델 artifact 체계에 scope embedding으로 등록해 parse_key·chunk identity가 바뀌지 않는다.
Indexing 계약, Source 규칙 3줄, Compose dev-vector Qdrant(loopback 검증)를 추가한다.
규칙 변경: AI 경계의 'Qdrant Indexing 금지'와 파일 경계의 'Embedding/Qdrant module 범위 밖'을 승인된 dev Indexing 범위로 좁혔다. Retriever·RAG·LLM·LangGraph 금지는 유지한다.
결과: [Phase 4-B Report](../workspace/reports/development/2026-09-30-phase4b-document-indexing.md). AGY 검토 pending.

## 2026-09-28 — Phase 1B dev FULL Structured Sync

사용자 승인으로 첫 페이지의 실행 시점 totalCount 기반 전체 pagination과 페이지별 Raw snapshot / hash 재검증을 추가한다.
ID / count / 완전성 / normalization 검증이 끝나기 전에 DB mutation을 시작하지 않는다.
기존 모델·fingerprint·lifecycle·Flyway V1/V2를 재사용하고 DB-only atomic transaction / 협력적 시간 예산을 적용한다.
첫 Live FULL과 현재 dev 실행은 soft-delete 후보 DRY-RUN만 허용하며 실제 삭제 경로는 차단한다.
장기 FULL 안전 규칙을 Source / Pipeline / Skill / Contract에 기록하고 mock API + 실제 test DB 회귀로 연결한다.
과거 AGY 승인은 보존하며 이번 Task 독립 Review는 pending이다. Generated 산출물은 non-gating이다.
결과: [Phase 1B Report](../workspace/reports/codex/2026-09-28-phase1b-full-sync.md).

## 2026-09-27 — 최초 기반 구축

- 원인: 설계만 있고 Context·Registry·검증·External Memory가 없었다.
- 범위: Phase 0 준비에 필요한 Harness와 로컬 파일 도구·계약·테스트·CI.
- 전체 서비스·DB·Pipeline·RAG를 만들지 않도록 실제 구현 목록을 Registry로 고정한다.
- 미구현 제품 검증은 N/A로 공개한다. Gate 통과와 AGY 승인은 독립 상태로 둔다.
- Raw byte 보존과 hash 검증, 미측정 보고서 계약으로 다음 데이터 실험의 증거를 준비한다.
- 규칙 완화·삭제 없음. 최상위 설계 수정 없음.
- 실행 결과: [Codex Report](../workspace/reports/codex/2026-09-27-codex-harness-report.md).
- AGY 검토: pending.

## 2026-09-27 — AGY Initial Review 보완

- 근거: [독립 AGY Initial Review](../workspace/reports/agy/agy-initial-harness-review.md), PASS WITH FIXES.
- M-1: 불필요한 workflow/reference는 생성하지 않고 Target와 현재 Skill 구조를 명시.
- M-2: Compose·ignore·Registry·Context 크기·Review 증거·Raw 무결성·출력 충돌의 WHY 주석 보강.
- M-3 / I-4: Checkpoint Format·복원과 current-task 교체·이전 상태 보존 절차 정의.
- M-4: 공식 명세 전 환경변수 추정 없음. .env.example 보존.
- M-5: pending-only Gate 계약은 유지하고 측정·Human Review 후 확장 Task 절차만 정의.
- 사용자 요청에 따라 pending 고정 검사를 Evidence 검증이 필요한 review_complete 전환으로 교체.
  독립 원문·검토 대상 hash는 고정하며 자기 Report를 Evidence로 사용할 수 없도록 검증.
- Initial Review는 과거 Foundation 대상이다. 이번 보완의 후속 Review·Human Review·Data Gate는 pending.
- IDE가 생성한 로컬 .idea metadata만 제외하고 같은 경로의 코드·문서 숨김은 거부.
- 제품 기능·추정 upstream·기술 도입·Git 승격 없음.
- 결과: [보완 Report](../workspace/reports/codex/2026-09-27-codex-harness-fix-report.md).

## 2026-09-27 — Dynamic Workspace Registry Drift 수정

- 재현: clean dev에서 AGY Targeted Re-review 파일만 unregistered로 check-harness / check-all이 실패했다.
- 원인: 정적 Harness 구조와 계속 생성되는 External Memory에 같은 개별 등록 의무를 적용했다.
- required_files는 정적 필수 목록, dynamic_paths는 바로 아래 reports / checkpoints Markdown 경계로 분리한다.
  기존 Workspace README는 정적 필수 파일로 유지하고 새 기록은 Git 추적·ignore·일반 파일·symlink·실행 권한을 검사한다.
- 일반 Report 허용과 Trusted Evidence를 분리한다. 사용자 제공 Targeted Re-review PASS의 원문·검토 대상 hash만 별도 등록한다.
  현재 수정 Task의 Review·Human Review·Data Gate는 pending이다. AGY 원문·과거 Report는 수정하지 않는다.
- 실제 파일을 복사하는 fixture와 동적 기록·정적 drift·숨김·자기 승인 방지 회귀를 추가한다.
- Final Report → 최종 Git 상태 구성 → check-all → 동결 순서를 명시한다. 이후 변경 시 기존 Final 결과는 무효다.
- 결과: [수정 Report](../workspace/reports/codex/2026-09-27-codex-dynamic-workspace-fix-report.md).

## 2026-09-27 — 기업마당 Request / Sample Contract와 최소 Probe

- 근거: 사용자가 확인한 공식 GET Endpoint·query 정보와 제공한 실제 sanitized 10건 Sample.
- 관찰 Raw 계약·Fixture checksum·nullable / 비정형 / HTML / @ / unknown field 보존 Tests를 추가한다.
- 세 BIZINFO 환경변수를 명시하며 실제 key와 Live 응답은 Git에 넣지 않는다.
  사용자 제공 sanitized Fixture만 Source 규칙의 명시적인 추적 예외로 둔다.
- 최대 4요청의 명시적인 Local Probe만 허용한다. CI는 Fixture·mock HTTP·키 없는 CLI를 실행한다.
  Compose의 네트워크·read-only 경계, Raw hash / overwrite, pending-only Gate는 유지한다.
- 현재 key가 없어 Live NOT_RUN이며 최근 100건 Rule·정렬 / ID 보장은 미확정이다.
- 현재 Report로 Task를 전환하며 과거 독립 Evidence는 보존하고 현재 Review는 pending으로 구분한다.
- 결과: [API Contract / Probe Report](../workspace/reports/codex/2026-09-27-codex-bizinfo-contract-probe-report.md).

## 2026-09-28 — Profile 격리와 dev Live Probe

- 사용자 승인 dev / prod만 필수 CLI로 선택하며 Branch / APP_PROFILE 자동 선택·Profile / legacy .env fallback을 금지한다.
- 사용자 Secret 파일은 수정·삭제·stage하지 않는다. 기존 ignore는 유지하고 Secret 추적 / example 숨김 / ignore 누락 회귀를 추가한다.
- OS 우선·셸 비실행·선택 파일만 read·prod runtime 주입·NOT_RUN / key 비노출을 합성 오프라인 Test로 검증한다.
- 오프라인 전체 PASS 후 dev 4요청: 두 페이지 10건씩 / totalCount=1514 / 중복 없음 / 관찰 내림차순, 알려진 ID 1건 일치.
- Synthetic ID는 03 NODATA_ERROR / items={}를 관찰해 기존 Probe exit 1을 보존했다. 오류를 가짜 PASS로 바꾸지 않는다.
- Raw 네 개의 byte / checksum을 검증했다. prod 실제 읽기·Live 호출, 100건 본 수집·제품 기능·Gate 판단 없음.
- 최근 100건 Rule과 공식 정렬 보장은 미확정이며 현재 독립 Review / Human Review는 pending이다.
- 결과: [Profile / dev Live Report](../workspace/reports/codex/2026-09-28-codex-bizinfo-profile-live-probe-report.md).

## 2026-09-28 — Phase 0 API 품질 Task

사용자 승인에 따라 명시적 Negative Probe의 EXPECTED_NO_DATA를 실제 API 오류와 분리했다.
기본 정렬 선두 100건의 dev 전용 5×20 Batch / Raw 재현 분석 / 품질 계약 / 오프라인 회귀를 추가했다.
전체 Collector·다운로드·DB·AI는 추가하지 않고 pending-only Gate / Trusted AGY Evidence / Secret 정책을 유지한다.
실제 실행 결과와 변경 이유는 current-task의 Final Report에 기록한다.

## 2026-09-28 — 제한된 Document Download Gate

사용자가 동일 API 표본 100개의 Primary Candidate 다운로드를 승인했다. 별도 dev 도구·로컬 안전 계약·mock 회귀를 추가한다.
Static Registry에는 코드 / 계약 / Test만 등록하며 Report / Checkpoint는 기존 Dynamic 정책으로 추적한다.
API / prod Secret / Supplementary / Parser / GO-DROP·독립 Review Guardrail은 유지한다.
체크포인트는 결과별 원문 checksum에서 재개하며 과거 AGY PASS를 이번 Task 승인으로 재사용하지 않는다.

## 2026-09-28 Phase 1A 사용자 승인

구조화 데이터 제품 Pilot / dev MySQL / 공통 Flyway를 사용자 승인으로 추가했다.
Static Registry에 제품·migration·tests를 등록하고 Dynamic Report 규칙과 AGY 독립 Evidence 검증은 보존한다.
setup / CI는 Python 제품 dependency, integration은 실제 dev MySQL을 검증한다. 기존 phase0 네트워크·mount 경계는 그대로다.
기존 DB 없음 문구만 실제 구현 범위로 동기화한다. 이번 Task Review는 pending이며 이전 AGY PASS를 재사용하지 않는다.

## 2026-09-28 — Profile / Dev MySQL 포트 정책 정리

사용자 최종 정책에 따라 dev / prod 설정을 각 Profile 파일로 통일하고 Dev Host MySQL을 3306으로 전환했다.
Secret 생성과 별도 DB 설정 fallback을 제거했으며 기존 계정·volume·Pilot·Flyway 계보를 보존한다.
정적 Registry / Dynamic Report / AGY 독립 검토 규칙은 유지한다. 새 회귀와 최종 검증을 별도로 기록한다.
결과: [환경 정책 Report](../workspace/reports/codex/2026-09-28-codex-env-port-policy-report.md).

## 2026-09-28 — 사용자 credential 재검증과 Database COMMENT 정책

사용자 변경 credential을 유지하고 root 준비 연결을 실제 인증에 성공한 로컬 TCP로 명시했다. 계정·비밀번호는 변경하지 않는다.
적용된 V1을 보존하는 신규 V2로 application Table / Column COMMENT만 추가한다.
DB 규칙·Migration Skill·Testing 문서를 연결하고 실제 dev/test schema 전체의 COMMENT 누락·placeholder를 Integration / check-all에서 실패시킨다.
새 업무 테이블도 자동 탐색하며 Flyway 내부 테이블만 제외한다. COMMENT 외 정의와 기존 Pilot 100건 보존을 검증한다.
사용자 승인으로 example credential placeholder만 비웠으며 Secret 파일과 과거 Report는 보존한다.
현재 독립 Review는 pending이다. 결과: [Database COMMENT Report](../workspace/reports/codex/2026-09-28-codex-database-comments-report.md).

## 2026-09-28 — Workspace output lifecycle / Validation boundary

사용자 승인으로 workspace 전체를 Inventory하고 current-task 1개·정적 README 2개와 실행 산출물을 분리한다.
Report/Checkpoint Markdown과 Artifact JSON/log는 non-gating이며 미추적·ignore·공백·존재·index 상태로 build를 실패시키지 않는다.
format/lint/comments·Git diff·Registry/links의 공유 파일 목록을 바꾸고 Control/Input strict 검증과 command 실패 전파를 유지한다.
AGY 참조와 자기 승인 방지는 strict metadata로 보존하며 원문 checksum / 누락은 별도 non-gating 신뢰 상태로 표시한다.
committed 원문은 보존하고 HEAD에 없는 staged 생성 Report 7개는 로컬 파일을 유지한 채 index만 제거한다.
최종 검증 뒤 새 Generated Report를 작성하며 생성물만 추가됐을 때 재검증하지 않는다. Phase 1A 제품·Migration·Secret은 변경하지 않는다.
결과: [Workspace lifecycle Report](../workspace/reports/codex/2026-09-28-codex-workspace-lifecycle-report.md).

## 2026-09-28 — Generated Output Producer / Task별 보관

사용자 승인으로 Report / Artifact 전체 Inventory와 정적·실행·accepted·과거 Evidence 참조 그래프를 만든다.
원문을 보존해 Codex/AGY 전용 디렉터리와 Task별 Artifact로 옮기며 참조 없는 superseded 중간 로그만 명시적으로 정리한다.
accepted review는 경로만 갱신하며 hash·verdict·상태를 바꾸지 않는다. historical Report 내부는 relocation mapping으로 보완한다.
Registry / Agent 지침에 Producer 출력 경로를 고정하고 current-task·static anchor strict / generated non-gating 경계는 유지한다.
기존 도구와 제품 CLI의 입출력 참조만 이동 위치로 갱신한다. 제품 데이터 처리·DB·Migration·checkpoint·Secret 변경은 없다.
결과: [Output cleanup Report](../workspace/reports/codex/2026-09-28-workspace-output-cleanup.md).

## 2026-09-28 — Phase 2 Full Document Acquisition

사용자 승인으로 검증된 Phase 1B dev DB를 Source로 전체 문서 후보의 원본 byte와 provenance metadata를 수집한다.
V1/V2를 보존한 신규 V3, 제품 documents package, 얇은 CLI, 품질 계약과 offline/MySQL 회귀를 정적 Registry에 추가한다.
공개 요청에는 인증정보를 전달하지 않으며 순차 요청·자동 retry 0·redirect/size/timeout·HTML 거부·exclusive 저장을 적용한다.
URL/SHA dedupe 뒤에도 모든 pblancId/source field/token relation을 보존한다. Parser/OCR/AI와 prod는 범위 밖이며 현재 Review는 pending이다.

## 2026-09-29 — Phase 2.5 S3 Document Storage

사용자 승인으로 Phase 2의 3,231개 고유 binary를 고정 dev S3의 content-addressed object와 연결한다.
수동 구현의 metadata-link PUT 가능성, MySQL rowcount 재실행 의존, cached HEAD-only 검증, write smoke를 제거했다.
V4는 검증된 S3 위치 metadata만 추가하고 legacy `storage_path`와 로컬 1.6GB corpus를 보존한다.
로컬 SHA/S3 HEAD checksum 전수 검증 뒤 3,288 relation을 원자적으로 연결하고 실제 S3 byte로 Phase 2 run을 재검증한다.
prod/upstream HTTP/Parser/S3 삭제는 수행하지 않으며 AGY 독립 Review와 로컬 삭제 사용자 승인은 pending이다.

## 2026-09-29 — Claude Development Producer

기존 Repository-native Harness를 유지하면서 Codex와 Claude를 같은 Task를 이어서 수행하는 개발 Producer로 등록한다.
Task Evidence는 공동 development 경로에 두고 Agent handoff에 Registry·current-task 변경을 요구하지 않는다.
AGY 독립 Reviewer identity와 전용 Evidence 경계는 별도로 고정한다.
CLAUDE.md는 AGENTS/current-task/Registry로 연결하는 bootstrap만 유지하며 Rule/Skill/Docs를 복제하지 않는다.
과거 Codex/AGY Report와 accepted review checksum은 변경하지 않으며 제품·S3·DB 동작도 변경하지 않는다.

## 2026-09-29 — Phase 3 Document Parsing 시작

사용자 승인으로 Phase를 phase3-document-parsing으로 전환하고 Parsing Contract와 Source 규칙 Phase 3 절을 추가한다.
공통 구조화 표현은 DoclingDocument이며 PDF=Docling, HWP=HWP→PDF→Docling, HWPX=HwpxDoclingAdapter 방향을 기록한다.
route는 detected_format만 따르고 parse_key 버전 규칙·container/XML 안전 한도·빈 text 비성공 Gate를 Contract와 Test로 고정한다.
validator의 phase 목록을 DATABASE_PHASES 하나로 합쳐 Phase 2.5에서 integration dev MySQL 준비가 빠졌던 누락을 함께 바로잡는다.
docling-core·defusedxml을 pin한다. Docling 변환기·HWP 변환기·결과 영속화·OCR은 아직 도입하지 않았으며 AGY Review는 pending이다.

## 2026-09-29 — Phase 3 3-A 보정

사용자 검토로 3-A 상태를 implementation complete / local validation PASS / AGY·human review pending으로 정정한다.
Contract에 unique content SHA와 source relation count 기준을 분리하고, HWPX 품질 검증 pending 항목,
HWP 변환기 UNDECIDED, S3 artifact + MySQL metadata 저장 정책, Generic ZIP member provenance 요건과 docling-core 사용 이유를 고정한다.
PROJECT_DESIGN §20의 `data/parsed/` 보존 표현이 승인 정책과 충돌함을 기록한다. 새 route·S3 PUT·migration은 추가하지 않았다.

## 2026-09-29 — Phase 3-A DONE / 3-B Docling PDF route

3-A는 AGY Review·Status Semantics Re-review·Human Review PASS로 DONE이며 current-task와 3-B Report에 기록한다. 3-A Report 원문은 변경하지 않는다.
3-B는 PDF route를 기존 router 안에서 Docling DocumentConverter(do_ocr=false)로 활성화하고 HWP가 재사용할 `convert_pdf` 경계를 둔다.
`docling` meta 패키지는 OCR engine을 포함하므로 PDF 전용 `docling-slim[convert-core,format-pdf,models-local]==2.130.0`과
TableFormer용 `docling-ibm-models[opencv-python-headless]==4.0.3`을 pin한다. docling-core 2.99.0과 호환을 resolver·pip check로 확인했다.
parse_key에 docling-slim·docling-parse·docling-ibm-models 버전과 PDF pipeline 설정 hash를 추가하고 failure_code 목록을 Contract에 등록한다.
setup은 Phase 3에서 Docling import·lzma·OCR engine 부재를 검사한다. 로컬 `.venv`는 lzma가 있는 별도 CPython 3.11.16 빌드로 재생성했다.

## 2026-09-29 — Phase 3-B 보정: 표 cell 탈락 관찰·offline 모델

Docling 표 cell 탈락(docling-ibm-models MatchingPostProcessor WARNING)을 conversion 범위 logger filter로 warning에 노출한다. 새 status는 만들지 않는다.
PARSED는 실행·재적재·text 양 Gate 통과이며 의미·표 완전성 보장이 아님을 Contract에 명시한다. 표 설정 ACCURATE + cell matching을 명시값으로 고정한다.
모델은 명시적 artifact 경로의 고정 snapshot만 쓰고 manifest hash를 parse_key에 넣는다. test runtime 다운로드를 금지하고 validator는 HF offline으로 실행한다.
setup은 lzma와 artifact 부재를 fail-fast로 보고한다. CI artifact 공급은 후속 Infra Task이며 그 전까지 CI Phase 3 setup은 실패한다.

## 2026-09-29 — Phase 3-B AGY B-1: CI Docling artifact 공급

AGY 3-B Review(CONDITIONAL PASS)의 B-1을 해결한다. 모델은 Git에 넣지 않고 모델 identity만으로 만든 key의 Actions cache로 공급한다.
cache miss일 때만 `provision --allow-network`가 Contract의 resolved commit으로 staging에 받고 manifest 검증 후 이동한다.
hit·miss 모두 verify한 뒤 setup·check-all을 HF_HUB_OFFLINE=1로 실행한다. manifest는 Contract 파일 목록 기준이며 기대값과 달라도 변환 전 실패한다.

## 2026-09-29 — Phase 3-B DONE / 3-B.1 등록

3-B는 Human Review PASS로 DONE이다. AGY B-1은 remote CI cache-miss 경로 SUCCESS로 closed됐다.
TableFormer 표 cell 손실은 warning으로 관찰 가능해졌을 뿐 해결되지 않았다. 다음 작업은 HWP가 아니라
3-B.1 Table Engine Evaluation / Replacement이며 current-task와 Registry report를 새 Task로 교체한다. 구현은 시작하지 않았다.

## 2026-09-29 — Phase 3-B.1 PDF Table Engine Evaluation 착수

TableFormer 표 cell 손실의 근본 해결을 위해 primary table engine을 corpus evidence로 다시 결정하는 평가 Task를 시작한다.
Source 규칙에 PDF Table Engine 절(Docling 문서 parser 유지, DoclingDocument 수렴, evidence 없는 교체 금지, 재시도 fallback 불인정,
Phase 4 gate, 분리된 benchmark 환경·명시 모델, 산출물 ignored 경로)을 추가하고 Contract에 table_engine 절을 둔다.
benchmark 코드는 `evals/table_engine/`, corpus는 SHA 고정 manifest로 추적한다. production route는 바꾸지 않는다.

## 2026-09-29 — Phase 3-B.2 PP-TableMagic Production Suitability Gate

PP-TableMagic을 표 검출·구조 owner로 쓰는 후보 구조를 Contract table_engine.suitability_gate에 기록하고
Docling bbox gate는 귀속 측정용으로만 둔다. table_quality(TABLE_VALID / TABLE_QUALITY_FAILED)는 ParseStatus를 늘리지 않으며
증명되지 않은 cell 매핑은 조용한 fallback이 아닌 품질 실패이고 TABLE_QUALITY_FAILED 표는 Chunking·indexing에 들어가지 않는다.
IntelliJ DB introspection cache(`.idea/dataSources/**/storage_v2/**/*.meta`, 비실행)만 좁게 ignore 허용하고 regression test를 추가한다.

## 2026-09-29 — Phase 3-B.3 PDF Hybrid Parsing Validation

Contract table_quality에 failed_table_policy(구조 미생성·bbox native text 무손실 보존·provenance·자동 fallback 없음)를,
visual_pilot(평가 전용 PaddleOCR-VL, informative 후보만, provenance 필드, 모델 파생 evidence, VISUAL_VALID / VISUAL_QUALITY_FAILED)을 추가한다.
Source 규칙 PDF Table Engine 절에 두 줄을 더하고 production route 불변 테스트를 둔다. visual pilot은 호출별 120초 local safety
boundary와 재개 가능한 결과 기록을 사용하고, 검증되지 않은 출력 schema·semantic threshold는 강제하지 않는다. production parser와 ParseStatus는 바꾸지 않는다.
조립 pilot에서 겹친 PP 영역이 먼저 넣은 표를 지우는 손실이 관찰되어 failed_table_policy에 overlapping_regions(선택하지 않고 합친 영역을 FAILED native text로 보존)를,
visual quality_rule에 한국어 원문에 없는 한자 출력(평가 후보)을 추가한다.

## 2026-09-29 — Phase 3-B.4 Hybrid Review Closure

corpus 32문서 조립에서 쪽 단위 손실을 재자 문서 합계에 가려진 손실이 드러났다(교체된 표의 caption·footnote 삭제, VALID 표 cell 밖 단어, 일부만 겹친 text 삭제).
Contract table_engine에 assembly_rule을, Source 규칙에 한 줄을 추가하고 regression test를 둔다. 사람 검토 entry point(review.py)를 추가한다. production route와 ParseStatus는 바꾸지 않는다.
검증 범위 원칙(smallest sufficient scope, full corpus는 최종 승인 직전 명시 요청 시, 검증 전용 기능은 기존 Harness로 불가할 때만)을 Testing 실행 범위에 추가한다.

## 2026-09-29 — Phase 3-B.5 PP Production Integration

사용자 결정으로 PDF production 표 engine을 PP-TableMagic으로 전환한다. Contract routes.PDF에 table_engine 설정을 두고 Docling 표 구조(TableFormer)를 끈다.
PP 모델 6개를 Docling layout과 같은 artifact identity·CI cache에 넣고 TableFormer 가중치는 목록에서 뺀다. parse_key에 paddlepaddle·paddlex 버전을 넣는다.
TableFormer cell drop warning을 PDF_TABLE_* warning으로 바꾸고 pp_table_engine_error 실패 코드를 등록한다. visual_pilot에 production 보류 상태를 적는다.
Source 규칙·Pipeline 문서·setup 검사(PP 설치 확인, paddleocr 미설치)를 맞춘다.
CI(Linux x86_64)에서 PaddleX 기본 oneDNN 경로가 Paddle 3.3.1 PIR NotImplementedError를 내 routes.PDF.table_engine에 runtime_environment(oneDNN off)와 cpu_kernel_rule을 추가하고,
native text가 부족한 PDF는 PP 없이 OCR_REQUIRED로 남기는 ocr_required_rule을 둔다.

## 2026-09-29 — Phase 3-B.6 HWP → PDF Route

사용자 승인으로 HWP 변환기를 LibreOffice headless + H2Orestart 전용 Docker 이미지로 정하고(host 설치 없음) HWP route를 활성화한다.
Contract routes.HWP에 이미지 identity·실행 조건·provenance 규칙, CONVERSION_FAILED 실패 코드를 두고 Source 규칙·Pipeline·infra README·Testing을 맞춘다. HWPX route는 바꾸지 않는다.

## 2026-09-29 — Phase 3-B.7 OCR_REQUIRED OCR

OCR_REQUIRED PDF에만 PaddleX PP-OCRv5(mobile det + 한국어 rec) OCR을 추가한다. Contract routes.PDF.ocr, 모델 2개의 artifact identity, PDF_OCR_APPLIED /
OCR_TEXT_INSUFFICIENT warning, ocr_engine_error 실패 코드를 두고 out_of_scope에서 OCR을 뺀다. provisioning은 없는 모델 폴더만 받도록 바꾼다. Source 규칙·Pipeline·Testing을 맞춘다.

## 2026-09-29 — Phase 3-B.8 page-selective OCR

문서 평균이 scan page를 숨기지 않도록 PDF page마다 native text를 독립 판정한다. 선택한 page만 기존 PP-OCRv5 text layer로
교체하며 충분한 page는 native text를 유지한다. OCR 부족 page는 다른 page의 text 양과 무관하게 OCR_REQUIRED로 남긴다.

## 2026-09-29 — Phase 3-B.9 Parse persistence

PARSED DoclingDocument를 source SHA·parse_key 주소의 immutable S3 JSON으로 저장하고, checksum·실제 byte 검증 후 V5 MySQL
metadata를 확정한다. 동일 key는 재사용하고 새 parse_key는 별도 결과로 보존하며 비성공 결과는 artifact를 만들지 않는다.

## 2026-09-29 — Phase 3-B.10 Single-source parse orchestration

verified `document_sources`의 unique content SHA 하나를 S3 readback → 기존 parser → 기존 persistence로 연결하는 dev-only CLI를 추가한다.
relation metadata가 충돌하면 중단하고, 재실행은 persistence의 source SHA·parse_key idempotency를 그대로 사용한다. 암묵적 batch와 실제 AWS 검증은 포함하지 않는다.

## 2026-09-29 — Phase 3-B.11 Bounded parse orchestration

기존 single-source orchestration을 호출자 명시 SHA 1~3개의 결정적 순차 batch로 감쌌다. source 자동 탐색과 병렬 처리를 두지 않고,
source별 실패를 격리해 INSERTED/REUSED/실패를 집계하며 재실행은 기존 persistence idempotency를 그대로 사용한다.

## 2026-09-29 — Phase 3-B.12 HWPX 구조·provenance

HwpxDoclingAdapter가 header.xml의 명시 선언으로 heading·list·각주·머리말을 만들고, 목록·중첩 표가 있는 cell을 RichTableCell로 보존하며 모든 item에 `bizaid__hwpx` provenance를 남긴다.
Contract routes.HWPX에 structure_rules·provenance·quality_status를, versioning.adapter_version을 2로, HWPX_STYLE_HEADER_MISSING warning을 둔다. Source 규칙·Pipeline·Testing을 맞춘다.

## 2026-09-30 — Phase 3-B.13 Parser Hardening

parse identity를 route 의존 범위로 나누고(`adapter_version` → HWPX 전용 `hwpx_adapter_version`, Contract versioning.route_scope), 조립의 단어 소유 규칙,
OCR page furniture 제거, 같은 행 anchor, OCR 부족 page의 status 규칙을 Contract·Source 규칙·Testing에 반영한다. 3-B.8의 "부족 page 하나면 문서 OCR_REQUIRED"는 실제 문서 근거로 바꾼다.

## 2026-09-30 — Phase 3-C Corpus Parsing

기존 orchestrate_source를 재사용하는 dev 전용 corpus runner(`parsing/corpus.py`, `scripts/run_corpus_parsing.py`)를 추가한다. 자식 process 하나로 순차 실행하고
source별 timeout·실패 격리·현재 parse_key skip·연속 환경 실패 중단·progress 파일을 둔다. Contract `corpus_execution`과 Source 규칙에 corpus 실행 규칙을 둔다.
corpus 100건 실행에서 native text만 있는 low-text page의 native가 OCR로 교체되는 반복 문제(27건, 77쪽)를 확인해 OCR page 선택에 raster image 조건을 두고, runner에 --max-completed·source 경계 종료·--sources-file 재처리를 둔다.

## 2026-09-30 — Phase 4-A Document Chunking

DoclingDocument → HybridChunker(BGE-M3 tokenizer) → BizAidChunkEnricher → FinalChunk를 추가하고 `document-chunking.contract.json`을 둔다. docling-core를 `[chunking]` extra로 고정하고
BGE-M3 tokenizer 파일을 기존 모델 artifact에 `scope=chunking`으로 등록한다. parse identity는 parsing scope 파일로만 계산해 기존 parse_key를 유지한다. Source 규칙·Pipeline·Testing을 맞춘다.
