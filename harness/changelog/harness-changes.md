# Harness 변경 이력

## 2026-10-04 — 묶음5-1 공개 서비스 기능(Claude)

사용자 승인: 새 Flyway migration(V13)을 `migrations/`에 추가하고 dev DB에 적용. 기존 migration 수정 없음.
판정 출력 상한 1280→2560(eligibility 계약, Ollama·Bedrock 공통, 15개·75초·fail-closed 유지). Bedrock 120174 단일 판정 1회 확인.
기능: 비로그인 첫 화면 소개(/), 체험 계정(설정 on/off·IP별 생성 제한·합성 기업정보·수정/비밀번호/탈퇴 불가·24시간 뒤 매시 정리), 하루 AI 사용 제한(사용자 30·체험 합산 200, 429 고정 코드, 결과 없는 요청은 되돌림, GET /api/ai/usage), /privacy·/terms(초안, 사용자 검토 필요)와 가입 필수 동의 기록, 모든 화면 하단 데이터 출처·AI 참고용 안내.
DB: V13(users.account_type, user_consents, ai_usage_counters, activity_logs.action COMMENT에 TRIAL_START).
Harness: 사용자 지정 handoff `bundle5-1-handoff.md` non-gating 등록, 판정 1회 스크립트를 regression-set/run.py와 같은 STATIC_CONTROL로 등록, 화면·서버 약관 버전 일치 계약 검사 추가. 규칙 완화 없음.

## 2026-10-04 — 묶음4 Bedrock·V2 동결 시험·목록/표 context

사용자 승인으로 provider 경계에 Bedrock ConverseStream/forced tool JSON을 추가했다. 기본 Ollama·75초 기한·기존 판정 상한·fail-closed는 유지한다. credential chain만 사용하고 Compose 사용자 AWS 설정을 read-only로 제공한다. Registry/Compose 검증은 mount 경계와 신규 SDK 최소 의존성을 반영하며 키·자동 재시도는 추가하지 않는다.
cases-v2 20건은 실제 DB/Qdrant 근거로 실행 전에 동결한다. provider당1회 + 기존10질문 Bedrock1회만 실행한다. V1 baseline/collection·embedding/key는 불변. 목록 중복은 RRF 뒤 첫 결과 유지, 표는 context의 flat cell 표현만 바꾸며 구조를 추측하지 않는다. token/provider/model만 추적하고 prompt/개인정보는 보내지 않는다.
실측: Bedrock19/20, Ollama15PASS/3품질FAIL/2채점오류. 기존1280token 상한 때문에 Bedrock120174 fail-closed. 비교·비용 측정 한계와 후속 출력예산 결정을 Report에 기록한다. 현재 Task 독립 AGY 검토는 pending이며 과거 승인을 재사용하지 않는다. 사용자 지정 bundle4-handoff만 non-gating으로 추가했다.

## 2026-10-04 — 묶음3 서비스 관리(Claude)

사용자 승인: 새 Flyway migration을 `migrations/`에 추가하고 dev DB에 적용.
기능: 회원 탈퇴(POST /api/account/withdraw, 비밀번호 재확인, 서비스 데이터 즉시 삭제·활동 기록 익명화, 기존 Access·Refresh Token 즉시 무효), 대화 삭제(DELETE /api/conversations/{id}, 본인만), 로그인 시도 제한(계정·IP 각 5회 연속 실패 → 10분, 429 auth_login_locked, 성공 시 계정만 초기화), 비밀번호 변경(PUT /api/account/password, 다른 기기 로그아웃), 지난 맞춤 추천 목록(GET /api/ai/workflows), dev 전용 Swagger(springdoc 2.8.17).
DB: V12(login_throttles, activity_logs COMMENT — IMP-022). nginx는 X-Forwarded-For를 실제 접속 주소로 덮어쓰고 Spring은 forward-headers-strategy native.
정리: IMP-015(backend Flyway 11.20.3 고정), IMP-016·021(MaintenanceJob), IMP-023(AI 검색 경로 추적, prod 강제 off), IMP-026(config_identity_snapshots, 기존 key 278/278 동일).
CI: ci.yml에 backend(gradle test)·frontend(npm ci/typecheck/test/build) job 추가(validate job·필수 명령 그대로).
Harness: 사용자 지정 handoff `harness/workspace/handoff/bundle3-handoff.md`를 bundle1·2와 같이 non-gating 산출물로 등록(validate.py·.gitignore). 규칙 완화 없음.

## 2026-10-03 — 질문 지역 미반영 안내와 소관기관 대리 필터 측정

사용자 결정(나): 질문 지역은 기존 Natural Filter의 unapplied 상태를 유지하며 별도 추출 없이 추천 화면의 강조 안내로 보여 준다. 기업 지역 기준·중앙부처/매핑 없는 소관기관 포함·기업정보 수정 링크를 명시했다. 기업 지역이 적용되지 않은 경우 적용했다고 쓰지 않는다. frontend 테스트 2건 추가.
IMP-019 Remaining을 결정과 cases-v2/IMP-024 후속 비교로 갱신하고 IMP-005에 운영 Spring 이미지의 contracts 포함 경계를 기록했다. 소관기관 제외·검색 query·판정 prompt/규칙·embedding·identity는 변경하지 않았다.
이번 측정은 LLM 없는 read-only 표본 검토이며 V11은 pending SQL 미리보기만 수행한다. V11 적용은 별도 사용자 승인 전 금지다.

## 2026-10-03 — 맞춤 추천 기업 지역 조건(IMP-019 지역 부분)

**규칙 변경(사용자 결정)**: `ai-boundary-rules.md`의 "지역을 소관기관 Hard Filter로 쓰지 않는다"에 예외를 둔다. 저장된 기업 지역이 광역 표준명이면 다른 광역 지자체 소관 공고만 후보에서 뺀다(중앙부처·매핑 없는 소관기관 유지, fail-open). 질문 속 지역은 계속 unapplied다.
계약: 새 `contracts/schemas/company-region.contract.json`(광역 16개 표준명 — 전남광주통합특별시 하나, 별칭, 소관기관 매핑, 중앙부처 26개, fail-open·충돌 규칙). Spring·React·FastAPI가 이 파일 하나를 쓴다.
코드: FastAPI `candidates/region.py`, 후보 필터 `exclude_jurisdictions`, 적용 조건 기록, 정형 소관기관 조건과의 충돌(kind=region). Spring `RegionCatalog`(계약 읽기)·`@CompanyRegion` 검증·`GET /api/company/regions`. React 지역 선택·예전 값 안내·추천 화면 지역 충돌·적용 안내. compose backend에 `./contracts:/contracts:ro`, validator 갱신.
DB: V11(기존 지역 값 → 표준명, 맞지 않으면 NULL, COMMENT 변경)은 승인 전이라 `data-pipeline/pending-migrations/`에 둔다. 미리보기: 2건 변환, NULL 0건.
Backlog: IMP-019 부분 해결(질문 지역 충돌 처리·순위 반영은 남음), IMP-030 신규(여러 지역 대상 공고).

## 2026-10-03 — 맞춤 추천 판정 90초 시간 초과·과열 수정

원인(실측): 2번째 공고(PBLN_000000000123260) 판정에서 모델이 같은 criteria 13개를 반복 생성했다. 5,000 token 동안 끝나지 않았고 상한이 없었다(num_predict 327,680). 또 client timeout(300초)이 stream 읽기 사이 대기라서, Spring이 90초에 포기한 뒤에도 FastAPI·Ollama가 18분 넘게 20,905 token을 생성했다(팬 과열).
수정: LLM 호출에 전체 기한 75초를 둔다(계약 internal-api `llm_call`, stream으로 받다가 넘으면 연결을 닫아 Ollama도 멈춤, `llm_timeout`→503). num_ctx 32768을 명시했다(실행 중인 값과 같아 재적재 없음). 자격 판정에는 criteria maxItems 12·num_predict 1,024를 두고, 상한에 닿은 출력은 판정하지 않고 `eligibility_output_limit_reached`로 실패시킨다(계약 eligibility `criterion_output`). OLLAMA_TIMEOUT_SECONDS는 기한을 줄이기만 한다(.env.dev.example 75).
prompt·판정 규칙·Top 3 순위·식별값은 바꾸지 않았다. Backlog IMP-029(일부 공고 criteria 과다·반복) 신규.

## 2026-10-03 — AI 검색 화면: 대기 안내와 최근 질문 우선 표시

사용자 요청: 검색 입력칸 아래에 "답변까지 시간이 걸릴 수 있다"는 안내를 추가했다. 대화 기록은 "질문 + 답변" 묶음 단위로 최근 묶음이 맨 위에 오게 바꿨다(묶음 안은 질문 → 답변). 진행 중 표시·오류·첫 응답도 기록 위에 둔다. `AiSearchPage.tsx`, `styles.css`, 테스트 1개 추가. 서버 API·저장 순서는 그대로다.

## 2026-10-03 — Compose frontend가 backend와 함께 재시작

IMP-017 적용 중 backend 컨테이너가 새 IP로 다시 만들어진 뒤 nginx가 예전 IP로 보내 로그인이 502가 됐다. `frontend.depends_on.backend.restart: true`로 backend 재시작·재생성 때 frontend도 다시 시작하고, validator에 같은 검사를 추가했다. 규칙 변경 없음.

## 2026-10-03 — IMP-017 FastAPI Compose 통합(+IMP-005)

사용자 결정: FastAPI를 질문 처리 전용 이미지로 Compose app profile에 넣고 `scripts/dev.sh`로 개발 환경 전체를 다룬다. 파싱·인덱싱은 host.
**규칙 변경(사용자 결정)**: Qdrant 주소는 loopback에 더해 Compose 서비스 `http://qdrant:6333`만 허용한다(`qdrant_store.qdrant_url`, 계약 `document-indexing.qdrant.server`). 다른 원격 주소는 계속 거부한다.
**식별값 계산 변경(구현 중 결정, 보고)**: `embedding_identity`의 torch·transformers 버전에서 PEP 440 local label(`+cpu`)을 뺀다(계약 `identity.runtime_version_rule`). 이미지가 CUDA 없는 `torch==2.14.0+cpu`를 써도 기존 embedding_key(`228acdd12220`)가 같다. host 값에는 label이 없어 기존 key 279/279가 그대로다.
IMP-005: 계약에 `expected_scope_manifest_sha256`(chunking·embedding)을 추가하고, 질문 서버는 BGE-M3 범위만 검증한다(배치는 전체 검증 그대로).
코드·파일: `requirements-api.txt` 분리(`requirements.txt`가 포함), `data-pipeline/Dockerfile`·`.dockerignore`, `parsing/__init__.py` 지연 import(질문 경로에서 boto3 제거), compose `fastapi` 서비스·qdrant app profile·backend `COMPOSE_AI_BASE_URL`, `scripts/dev.sh`.
Harness: validator의 compose 경계 검사를 강화했다(fastapi mount 읽기 전용·주소·포트 loopback·backend 주소). Registry에 compose 서비스·실행 파일을 등록했다. IMP-005·IMP-017 RESOLVED.
검증: host와 컨테이너의 검색 순위(3질문×3모드 상위 10)와 API 응답 body가 같다. 이미지 1.91GB, 비밀값 노출 0.

## 2026-10-03 — IMP-028 후속: 짧은 안내문 5원본 복원

삭제한 45원본 중 공고 본문 성격의 짧은 안내문 5원본(60 point)을 보관된 파싱 결과로 재적재(재파싱 없음). 복원 point 60/60이 삭제 전과 같은 ID·hash. 기존 point·V1 변경 0. V2 2,776원본·64,041 point. 제외 목록 40·재적재 목록 130 갱신. 보고서의 "10 point 이하 14개"를 12개로 정정. 규칙 변경 없음.

## 2026-10-03 — IMP-028 처리: ZIP 내부 참고자료 45원본의 V2 point 삭제

사용자 결정(선택지 a): 참고·해설서·가이드·매뉴얼·분류 성격 45원본의 V2 point 9,449개를 source_sha256 필터로만 삭제. MySQL 파싱 결과·S3 artifact 보관, V1 미접촉. REFERENCE 판정은 하지 않음.
확인: 남은 V2 63,981 point·V1 3,849 point hash 변경 0, point 없는 공고 0, V2 2,771원본. 삭제 목록·재적재 제외 목록·되돌리기 명령을 IMP-028·Report §11에 기록. Master Guide §1·README 갱신. 규칙 변경 없음.

## 2026-10-03 — 일반 ZIP 범위 B 전체 실행 + document_role 규칙 개정

사용자 결정: 범위 B(FORM은 보관만). document_role 계약 개정: "제출서류"를 단독 FORM 단서에서 빼고 `qualified_cues`(+목록·체크리스트 → LIST, +안내·기준 → BODY) 추가, FORM 단서 결과보고서·상세서·조사서·프로필 추가(평가표 제외). 판정 코드·테스트 갱신. 식별값 입력 아님(267/267 동일). 기존 point payload는 고치지 않음.
실행: FORM이 아닌 187원본 파싱(AWS 만료로 96에서 멈춘 뒤 같은 run-id로 재개, 170 PARSED·17 OCR_REQUIRED·실패 0) → V2에 신규 11,891 point. 기존 V2 61,539·V1 3,849 point hash 변경 0. V2 2,816문서·73,430 point.
Backlog: IMP-009 결정·Evidence, IMP-027(지침 단서), IMP-028(대형 참고자료가 공고 근거를 차지, 결정 대기). Master Guide §1·README 갱신.

## 2026-10-02 — 일반 ZIP 승인 실행: V10 적용·내부 파일 S3 저장·표본 파싱

V10을 공통 `migrations/`로 옮겨(보관 폴더 삭제) dev·test에 적용, COMMENT 검사 통과, Spring backend Flyway(11.7.2) validate 통과. Registry·계약·테스트 경로 갱신.
V2 범위 117압축 `--execute`: DB 639행, S3 새 object 510(덮어쓰기 0), 미리보기와 같음. 표본 7원본 파싱(DB·S3 저장, Qdrant 적재 없음).
document_role 확인(무작위 30 + 집중 16), 규칙 개선은 제안만(변경 없음). 전체 범위 A/B는 사용자 결정 대기. 규칙 변경 없음.

## 2026-10-02 — 미지원 첨부 형식 4단계: 일반 ZIP(구현·미리보기)

사용자 결정: 일반 ZIP 내부 파일을 각각 문서로(깊이 1), 내부 파일 표 신설, 이름 UTF-8/CP949/원래 byte, 원본과 같은 S3 key(덮어쓰기 금지), 공고 relation 상속, 처리 제외·단독 첨부 중복은 상태만, 기존 route로 파싱, document_role은 내부 파일명.
**규칙 변경**: `data-source-rules.md` 일반 ZIP 조항을 "Contract 전까지 POLICY_PENDING 보존"에서 위 결정의 구체 규칙으로 바꿨다(압축 자체는 계속 POLICY_PENDING).
DB: V10 `document_archive_members`(한국어 COMMENT·CHECK 7). check-all이 공통 `migrations/`를 dev DB에 적용하므로 승인 전에는 `data-pipeline/pending-migrations/`에 보관(`migrations/README.md`). 검증은 테스트 DB에서 표를 만들고 지우는 방식.
코드: `documents/archive.py`(펼치기·분류·저장·기록), `scripts/run_archive_extraction.py`, `S3DocumentStore.put_bytes`, 파싱 입력·공고 상속·V2 범위에 STORED 내부 파일 포함(표가 없으면 동작 불변). 계약 `generic_zip`, ZIP `extraction_enabled: true`.
검증: 기존 V2 221·V1 46원본 key 불변. 미리보기(쓰기 없음) V2 117압축 → 내부 639, 처리 대상 고유 510. Backlog IMP-009 결정(XLSX·DOC·XLS·PPT 의도적 제외), IMP-026 신규. README V2 상태 갱신.

## 2026-10-02 — DOCX·PPTX 전체 실행(PPTX 위치 단위 수정 포함)

PPTX 슬라이드 크기·bbox를 EMU에서 pt로 환산(`parsing/office.py`), 계약 office·chunking provenance 설명과 단위 test 추가. 위치는 식별값 입력이 아니며 기존 route key 불변.
V2 범위 단독 DOCX 6·PPTX 1 파싱·적재(7 PARSED·7 INDEXED·58 point). 기존 V2 61,481·V1 3,849 point hash 변경 0. V2 61,539 point·2,646 원본, 범위 1,372공고 전부 point 보유. Master Guide §1 갱신. 규칙 변경 없음.

## 2026-10-02 — 미지원 첨부 형식 3단계: DOCX·PPTX

사용자 결정: 단독 DOCX·PPTX를 Docling으로 직접 읽는다(VLM 없음). docling-slim format-docx·format-pptx extra 추가 승인(기존 버전 불변). ODT는 기존 변환 이미지 변경이 HWP parse_key를 바꾸므로 7단계로 연기. 압축 안 DOCX·PPTX는 4단계.
의존성: requirements에 extra와 python-docx==1.2.0·python-pptx==1.0.2·xlsxwriter==3.2.9 고정(설치 전후 pip freeze 비교: 이 3개만 추가). 계약 `dependencies.docling.pin`과 test 기대값 갱신.
코드: `parsing/office.py`(LibreOffice 렌더링을 끈 Word·PowerPoint backend 하위 class, `bizaid__office` 위치 meta, 서식 정보 제거), router 분기(page 없는 문서 단위 Gate), `parse_identity` route 전용 입력(office_parser_version·office_config_sha256·python-docx/pptx 버전 + docling_version), chunk provenance에 block_order·heading_path·slide.
계약: DOCX·PPTX `enabled: true`, `office` 설정, `route_parse_key_inputs`·route_scope, 실패 코드 office_*, ODT 연기 이유를 pending_decisions에. chunking provenance 설명.
검증: 기존 PDF·HWP·HWPX 155원본과 IMAGE_OCR 105원본의 parse_key·chunk_set_key·embedding_key 불변. Backlog IMP-024(질문 유형 LLM 단독 판단)·IMP-025(공고 선택 단계 없음) 신규. 규칙 변경 없음.

## 2026-10-02 — 미지원 첨부 형식 2단계: 이미지 OCR(PNG·JPEG)

사용자 승인: 재분류 123관계를 한 트랜잭션으로 적용(확인 일치 → COMMIT, 로그 `artifacts/development/unsupported-formats-foundation/reclassify_apply_log.json`).
코드: `parsing/image_ocr.py`(PDF route의 고정 PP-OCRv5 재사용, 세로 타일·겹침·중복 줄 제거, page = 타일·bbox = 원본 px, 픽셀 상한 초과 실패), router IMAGE_OCR 분기, `parse_identity`에 route 전용 입력(IMAGE_OCR만 image_ocr_version·image_ocr_config_sha256, OCR 두 모델 hash), chunk payload `document_role`(값이 있을 때만).
계약: document-parsing PNG·JPEG `enabled: true`, `image_ocr` 설정(타일 2,000px·겹침 0.12·픽셀 40M·신뢰도 0.0), `route_parse_key_inputs`, 경고 IMAGE_OCR_APPLIED, 실패 코드 image_*. document-chunking `final_chunk_fields`에 document_role, 이미지 provenance 설명. 다른 새 route는 그대로 꺼져 있다.
검증: 실제 point 155원본의 parse_key·chunk_set_key·embedding_key 불변 재확인. 규칙 변경 없음.

## 2026-10-02 — 미지원 첨부 형식 1단계: 공통 기반

사용자 확정 순서: 공통 기반 → 이미지 OCR → DOCX·PPTX(ODT는 LibreOffice→DOCX) → 일반 ZIP(깊이 1) → 화면 완주·cases-v2 기준점 → XLSX → 옛 오피스. HWPML 보류, VLM 미도입.
코드: `documents/formats.py` 판별 세분화(OLE 디렉터리 읽기를 `_cfb`로 분리, HWP 판정 그대로), `indexing/document_role.py`(출처 종류 판정, 순위 미사용, 아직 payload에 연결하지 않음).
계약: document-parsing 새 route 정의(전부 enabled false), XLSX 상한·실패 코드, ZIP은 일반 압축만, pending_decisions 갱신. document-acquisition 형식 목록 확장. document-indexing에 `document_role`(식별값 입력 밖).
규칙 변경(보고): data-source-rules의 ZIP 문단을 세분화 판별·route 비활성·재분류 승인 규칙으로 교체. data-pipeline 문서 동기화. 테스트: 새 판별·출처 종류 테스트 추가, 파싱 테스트의 형식 목록·route 기대값을 새 계약에 맞춤(Phase 2.5 기준 집계는 과거 기록이라 그대로 두고 형식 포함 관계로 검사).
DB·Qdrant·S3 변경 없음. 기존 행 재분류는 미리보기·계획만(`artifacts/development/unsupported-formats-foundation/`).

## 2026-10-02 — 미지원 첨부 형식(IMP-009) 읽기 전용 조사

규칙·코드·DB 변경 없음. 전체 corpus의 ZIP·OTHER·XLSX·UNKNOWN 305개 원본(로컬 보존본, SHA 확인)과 일반 압축 내부 728개를 실체·분포·내용 가치·기술 조건으로 조사하고 IMP-009 Evidence에 요약했다. current-task를 조사 Task와 다음 단계(공통 기반 → XLSX → DOCX·PPTX → 옛 오피스 → 일반 ZIP → 이미지)로 갱신했다.
결과: Report `2026-10-02-imp009-unsupported-formats.md`(Generated Output).

## 2026-10-02 — AI 검색 화면의 기업정보 입력 안내

사용자 요청: 기업정보가 없어도 AI 검색 화면에는 들어가되, 검색칸·검색 버튼(·예시·새 대화)은 비활성으로 두고 기업정보 입력 안내와 "기업정보 입력하기" 버튼(등록 화면으로 이동)를 보여 준다. `/ai`의 등록 화면 강제 이동과 메뉴 잠금을 없앴다. 미등록 상태에서는 대화 목록·AI 요청을 보내지 않는다. 로그인 직후 미등록이면 등록 화면으로 가는 동작은 유지(LoginPage의 "이미 로그인" 이동도 기업정보 미등록이면 `/company`로 가게 해 이동 경합을 없앰). 서버 차단은 그대로. 규칙 변경 없음.

## 2026-10-02 — 맞춤 추천 화면의 기업정보 입력 안내

사용자 요청: 기업정보가 없으면 맞춤 추천 화면에서 기업정보 입력을 안내한다. `RequireCompany`에 notice 방식을 추가해 `/recommend`는 등록 화면으로 보내는 대신 화면 안에 안내와 [기업정보 입력하기]를 보여 주고, 맞춤 추천 메뉴는 잠그지 않는다. AI 검색은 기존대로 메뉴 잠금·등록 화면 이동. 서버 차단(company_not_registered)은 그대로다. 규칙 변경 없음.

## 2026-10-02 — 기업정보 필수·내 기업정보 화면 개편

사용자 결정: 로그인 뒤 기업정보가 없으면 등록 화면으로 보내고 AI 검색·맞춤 추천은 등록 뒤에만 쓴다(지원사업 목록·상세는 공개 유지). 기업 규모는 선택 상자(소상공인·중소기업·중견기업·모름). 내 기업정보는 보기 화면 + [수정] 버튼, 메뉴는 계정 영역으로 이동.
React: `useMyCompany`·`RequireCompany`, 로그인 직후 기업정보 확인, 보기/수정 모드, 메뉴 잠금. Spring: `CompanyService.requireRegistered`를 대화·AI 검색 진입점에 적용, `CompanyRequest.companySize` 허용값 검사. 화면 API 계약 갱신. 규칙 변경 없음.
결과: [Report](../workspace/reports/development/2026-10-02-company-required.md).

## 2026-10-02 — 회원가입 50초 지연 수정

원인: `AuthService.signup` 트랜잭션이 커밋 전 새 users 행을 잠근 상태에서 `ActivityLogService`가 REQUIRES_NEW(다른 연결)로 `activity_logs`(users FK)를 저장해 MySQL 잠금 대기 50초 후 실패했다(가입 SIGNUP 기록 유실).
수정: `ActivityLogService.success`는 진행 중 트랜잭션이 있으면 커밋 뒤(`afterCommit`)에 기록한다. 실패 기록은 기존대로 즉시 별도 트랜잭션. `ActivityLogTest`가 H2에 V8과 같은 외래키를 걸어 수정 전 실패를 재현하고 수정 후 통과한다. 실측 50.2초 → 0.06~0.3초. 규칙 변경 없음.
결과: [Report](../workspace/reports/development/2026-10-02-signup-latency-fix.md).

## 2026-10-02 — V2 적재 결과 확인과 완전성 검증

규칙 변경 없음. V2 데이터 batch 결과를 읽기 전용으로 대조했다(2,541 → PARSED 2,534 → INDEXED 2,534 → Qdrant 2,534문서·61,335 point, final.ok=true, V1 3,849 유지). 제외 7문서와 마감 공고 point를 기존 Backlog IMP-006·007·010·018 Evidence로 기록하고, Master Guide §1·README 상태를 실제 값으로 갱신했다.
결과: [Report](../workspace/reports/development/2026-10-02-v2-data-completeness.md). AGY 검토 pending.

## 2026-10-02 — 운영 배포 브랜치 이름 op → prod

사용자 결정: 브랜치는 dev(개발) → main(최신 검증) → prod(운영 배포)로 쓴다. Registry `branches.deployment`, validator 기대값, Harness policy test, Git 정책·Workflow·PROJECT_DESIGN의 `op`(배포 workflow 예시 `deploy-op.yml` 포함)를 `prod`로 바꿨다. Git 정책에 prod 브랜치와 실행 환경 profile(`prod`)이 별개라는 문장을 추가했다.
AGY 초기 Review 원문(`harness/workspace/reports/agy/`)과 Codex 과거 Report는 당시 기록이라 수정하지 않았다. 원격·로컬 브랜치 생성은 하지 않았다.

## 2026-10-01 — Claude 실행 환경별 역할 분리(사용자 결정)

규칙 추가(보고): 같은 `CLAUDE.md`를 읽는 로컬 Claude CLI와 클라우드 세션의 역할을 나눴다. 로컬 CLI는 기존 개발 Producer `claude`로 프롬프트를 받아 개발만 한다. 클라우드 세션(`CLAUDE_CODE_REMOTE=true`)은 개발·리뷰를 하지 않고 GitHub 읽기와 사용자와의 대화만 하며, 파일 수정·삭제·git add·commit·push 등 모든 변경은 예외 없이 사용자 허락을 받는다.
이유: 클라우드 세션이 자동 stop hook의 커밋·푸시 요구를 승인으로 오인해 허락 전에 push한 일이 있었다. 승인 규칙을 `CLAUDE.md`에 그대로 쓰면 개발을 맡은 로컬 CLI까지 매 수정마다 승인을 받게 되므로, `.claude/settings.json` SessionStart hook이 클라우드 세션에서만 [역할 문서](../agents/claude-cloud-advisor.md)를 주입한다. 별도 실행 스크립트는 만들지 않았다.
Registry: `agents`·`required_files`에 새 파일 2개 등록. 개발 Producer·독립 Reviewer(AGY) 정의와 Gate는 바꾸지 않았다.

## 2026-10-01 — Codex 인수인계 문서 검토·보완(Claude)

규칙 변경 없음. 문서 정정만 했다: observability.md(삭제 완료된 `biz_aid` 프로젝트를 "사용자 결정"으로 남긴 문장, 진단 연결과 개인정보 검증 근거 구분, 실제 workflow 추적 미검증 명시), Master Guide(V1과 V2 차이 표, 기획 배경 사용자 작성 칸, LangSmith 진단/실제 추적 상태 구분), current-task(검토 Task·확인한 batch 구조·AWS 만료 위험), Codex 인수인계 Report·checkpoint의 "인덱싱 재개/중단" 지침 정정.
결과: [Report](../workspace/reports/development/2026-10-01-handoff-review.md). AGY 검토 pending.

## 2026-10-01 — 프로젝트 인수인계 문서 정합성

production code·V2-0~V2-6 Report·checkpoint·실행 상태를 대조해 README, Master Guide, Architecture, RAG/Observability, 서비스별 실행 문서와 current-task를 현재 상태로 맞췄다. V2 기능 구현 완료와 전체 데이터 검증 완료, 파싱과 Qdrant indexing, 진단 trace와 전체 workflow 추적을 구분한다.
V1 기준선·V1 collection은 동결 상태를 유지하고, 다음 작업을 V2 파싱 완료 확인 → 별도 collection indexing·완전성 검증 → 전환 → V2 평가로 명시했다. 규칙·Gate는 완화하지 않았고 제품 코드는 변경하지 않았다.

## 2026-10-01 — V2-6 LangSmith 선택적 실행 추적

FastAPI `observability/tracing.py`: 설정(`BIZAID_TRACING_ENABLED`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` 기본 biz-aid)으로 켜는 RunTree 직접 기록. workflow 요청 = 최상위 실행, 하위 personalized_search·natural_filter·mysql_candidates·qdrant_search·eligibility·apply_answers·final_result. 값은 요약 함수 + 형식 검사(이중), SDK 런타임/환경변수 자동 첨부 off, workflow 실행 중 LangChain/LangGraph 자동 추적 강제 off(`tracing_context(enabled=False)`), 실패 무시.
State에 `trace_key`(무작위, thread_id) 추가(선택 필드, schema_version 유지). requirements에 langsmith==0.14.2 명시(기존 간접 의존성과 같은 버전). `.env.dev.example` 변수 4개.
규칙 변경(보고): AI 경계의 "LangSmith 지금 연동하지 않는다"를 선택적 추적·외부 전송 금지 항목·무작위 식별값·장애 무시 규칙 3줄로 교체. 내부 API 계약에 tracing 절.
운영 사고(보고): 첫 실제 진단을 이름 `biz_aid`로 보내 LangSmith가 같은 이름의 새 프로젝트를 자동 생성했다(실제 프로젝트 이름은 `biz-aid`, ID 928ce4c3…). 진단 기록 2건만 있으며 삭제는 사용자 결정. 기본 이름을 `biz-aid`로 고친 뒤 재진단해 기존 프로젝트 저장을 확인했다.
결과: [Report](../workspace/reports/development/2026-10-01-v2-6-langsmith-tracing.md). AGY 검토 pending.

## 2026-10-01 — V2-5 React V2 맞춤 추천 화면

React `/recommend/:workflowId?`(`features/recommend/`): 질문 → Top 3 → 공고별 판정(서버 CONTINUE마다 한 요청씩) → 부족 정보 입력 → answers → 재판정 → finalResult. 주소 기반 복원(GET만), 요청 잠금, 실패·409 자동 재시도 없음. V1 client·인증·근거 표시·CSS 재사용.
Spring: WorkflowResponse에 `pendingPblancIds`(State pending 그대로, 진행 표시용) 추가. nginx `/api/` `proxy_read_timeout 120s`(기본 60초가 Spring AI 90초보다 짧았음, Spring 값 변경 없음).
규칙 변경(보고): 파일 경계에 React workflow 요청 1개·복원은 GET만·자동 재시도 없음, proxy 응답 대기 > Spring AI 제한시간 2줄 추가. 계약 frontend-backend 갱신.
결과: [Report](../workspace/reports/development/2026-10-01-v2-5-react-recommend.md). AGY 검토 pending.

## 2026-10-01 — V2-4 최종 추천 결과 조립

FastAPI `workflow/recommendation.py`: COMPLETED 전이 때만 `build_final_result`로 final_result(recommended·excluded·unresolved·counts·disclaimer)를 만든다. 기존 판정 상태 → 묶음 표, 검색 순위 유지, 이유는 기존 조건(MET·NOT_MET·UNKNOWN)과 evidence_id, 근거는 같은 공고의 검증된 Citation만(섞이면 실패). LLM 추가 호출 없음. State schema_version 2(1은 그대로 진행 가능).
Spring: `AiDtos.FinalResult` 등, `HttpAiGateway.checkFinalResult`(COMPLETED에만 존재, 묶음별 상태, 순위 순서, 판정 공고 전체·개수, 근거 격리, 이유 근거 존재), 응답 `finalResult`.
규칙 변경(보고): AI 경계에 최종 결과 조립 원칙 1줄 추가(기존 "추천 점수·적합도 순위 금지"와 중복되지 않는 범위). 계약 3개 갱신.
테스트 보강: Spring 기존 테스트의 activity_logs·companies 조회에 target_type·사용자 조건을 추가(새 테스트와 id가 겹쳐 2건이 잡히던 순서 의존성 제거, assertion 약화 아님).
결과: [Report](../workspace/reports/development/2026-10-01-v2-4-final-result.md). AGY 검토 pending.
검증 실행 수정: `scripts/lib/validate.py`의 `run()`이 git을 터미널(TTY)에 직접 출력해 `git diff --check`가 pager(less)를 열고 `(END)`에서 멈췄다. 검증 하위 프로세스에 `GIT_PAGER=cat`만 추가했다(검사 내용·판정 기준 변경 없음). PTY 재현 → 수정 후 check-all exit 0.

## 2026-10-01 — V2-3 LangGraph 상태 기반 추천 흐름

FastAPI `workflow/recommendation.py`(LangGraph): route → search / evaluate_next(판정 1건) → aggregate / apply_answers. `/internal/v2/workflows/{start,advance}`는 받은 State로 한 단계만 실행한다. requirements에 langgraph==1.2.12(langgraph-sdk 의존성으로 websockets 17.1 → 16.1.1, pip check 정상).
Spring: V9 `ai_workflows`(state_json JSON, status·current_step, version, step_started_at), `RecommendationWorkflowService`(단계 점유 + 낙관적 잠금, 트랜잭션 밖 AI 호출), `/api/ai/workflows` 시작·조회·continue·answers. 임시 기업정보는 state_json에만 둔다.
IMP-020 RESOLVED(시작 14.7초, 판정 1건 39.4초, Spring 제한시간 변경 없음). 새 Backlog IMP-021.
규칙 변경(보고): AI 경계 "계속 금지"에서 LangGraph를 빼고 추천 흐름 단계·분기 소유로 범위를 정함(한 단계 판정 최대 1건). 파일 경계(State 저장은 Spring의 MySQL ai_workflows, FastAPI 비접근, 별도 저장소 금지, 클라이언트 분기 결정 금지), DB 규칙(V9, 임시/영구 기업정보 구분, 상태 column 복사), AGENTS 현황 문구.
결과: [Report](../workspace/reports/development/2026-10-01-v2-3-langgraph-workflow.md). AGY 검토 pending.

## 2026-10-01 — V2-2 Top 3 지원사업 자격 판정

FastAPI `eligibility/top_programs.py`가 개인화 검색 Top 3 → 공고별 기존 `EligibilityService.evaluate`를 순서대로 조합한다(`POST /internal/v2/personalized-eligibility`). 공고별 결과는 COMPLETED(기존 판정 결과) 또는 FAILED(고정 오류 코드)다.
Spring `POST /api/ai/personalized-eligibility`는 V1 단일 판정과 같은 snapshot 매핑으로 저장된 기업정보만 보내고, 판정 순서·공고별 상태·근거 범위를 검증한다(기존 판정 검증을 공통 메서드로 재사용).
규칙 변경(보고): AI 경계의 "여러 공고 일괄 판정 금지"를 "개인화 검색 Top 3에 한해 승인, 전체 후보 일괄 LLM 판정 금지"로 좁혔다(사용자 요청). 공고별 근거·실패 격리, 저장되지 않은 기업정보 기본값 금지, 클라이언트가 AI 흐름을 조립하지 않음(파일 경계)을 추가했다. 새 Backlog IMP-020(전체 응답 161초 > Spring 90초).
결과: [Report](../workspace/reports/development/2026-10-01-v2-2-top3-eligibility.md). AGY 검토 pending.

## 2026-10-01 — V2-1 기업정보 기반 개인화 검색

Spring `POST /api/ai/personalized-search` → 로그인 사용자 기업정보 4개 값 snapshot → FastAPI `POST /internal/v2/personalized-search` → 기업정보 코드 매핑 + 기존 Natural Filter 결합 → CLOSED 제외 MySQL 후보 → 기존 공고 단위 검색 Top 3.
사용자 결정: 기업규모 소상공인 → 지원대상 {소상공인, 중소기업}, 중소기업 → {중소기업}, 인증 대상 제외. 폐업만 COMPANY_CLOSED, 휴업·업력·지역은 unapplied. 질문 대상과 기업규모 대상이 겹치지 않으면 CONDITION_CONFLICT.
`ProgramCandidateFilter.exclude_closed_on`(CLOSED만 제외), `ProgramDiscoveryService.discover(limit)`를 추가했다. V1 query 경로·검색 알고리즘·DB schema는 바꾸지 않았다.
규칙 변경(보고, 완화 없음): AI 경계(저장된 기업정보는 LLM 해석 금지·승인 매핑만·unapplied·충돌 미완화), 파일 경계(FastAPI는 Spring 소유 서비스 데이터를 읽지 않음), DB 규칙(V2 적재 전 V1 collection 확인은 품질 평가 아님). 새 Backlog IMP-019.
결과: [Report](../workspace/reports/development/2026-10-01-v2-1-personalized-search.md). AGY 검토 pending.

## 2026-10-01 — V2-0 기반 작업(출력 계약 안정화·LangChain 최소 도입·V2 서비스 범위 적재)

자격 판정은 기업정보를 고정 field ID(기본 field 이름, 추가 사실 extra_N)로 주고, 요청마다 허용 field ID·evidence 번호를 출력 schema enum으로 제한한다. 결과는 원래 이름으로 되돌려 API 의미를 유지한다. 자연어 필터 분야·대상과 RAG evidence 번호도 enum으로 제한했다. application 재검증은 그대로다.
`rag/llm.py`의 Ollama provider 내부를 LangChain(ChatPromptTemplate + ChatOllama)으로 바꿨다. LlmProvider 경계·LlmRequest/LlmResponse는 그대로다. requirements에 langchain-core·langchain-ollama를 고정했다.
Qdrant collection namespace(`QDRANT_COLLECTION_NAMESPACE`, 비면 V1)를 추가했다. 적재 경로는 namespace 필수라 V1 collection에 쓸 수 없고, V1 baseline evaluator는 V1 collection으로 고정했다. 적재 최종 확인은 "collection 하나뿐" 대신 "대상 collection 존재"로 바꿨다.
`indexing/service_scope.py`(+ `scripts/run_v2_service_scope.py`)가 CLOSED가 아닌 활성 공고의 검증 원본 문서를 고르고, 기존 parsing·indexing runner로 V2 collection batch를 돌린다(`--collection-namespace v2 --parsed-only`).
규칙 변경(보고, 완화 없음): AI 경계(허용값 enum + 재검증, LangChain 소유 범위), DB 규칙(보관과 서비스 검색 범위 구분, V1 collection 동결, 설정 전환). 새 Backlog IMP-018, IMP-003 Evidence 추가.
결과: [Report](../workspace/reports/development/2026-10-01-v2-0-foundation.md). AGY 검토 pending.

## 2026-10-01 — V1 Finalization

production code·Harness·PROJECT_MASTER_GUIDE를 현재 상태의 기준으로 명시하고 PROJECT_DESIGN은 최초 목표와 배경으로 구분했다.
FastAPI 연동 전, RAG 미구현, 후보 제한 향후 계획처럼 남아 있던 상태 문구를 실제 V1 구조로 갱신했다. 별도 최상위 `ai/` 금지는 유지하되 Registry key를 `forbidden_top_level_modules`로 바꿔 AI 기능 미구현으로 오해되지 않게 했다.
check-all의 검증 범위 표시는 offline Contract·MySQL Integration과 별도 Backend/Frontend·Browser E2E·Live AI Eval을 구분하도록 수정했다. 검사 항목과 강도는 줄이지 않았다.
V1 AI frozen baseline 10건(7 PASS / 3 FAIL)은 변경하거나 재실행하지 않았다. 결과: [Report](../workspace/reports/development/2026-10-01-v1-finalization.md). AGY 검토는 이번 Task 범위 밖이다.

## 2026-10-01 — V1 코드 마감

Spring을 도메인 중심 package + 내부 계층(presentation·application·domain·infrastructure)으로 정리하고 역방향 의존(도메인·서비스 → HTTP DTO)을 없앴다. API·React·FastAPI 계약과 DB 의미는 바꾸지 않았다.
설정을 application.yml(공통, 기본 dev)·application-dev.yml·application-prod.yml(주소 기본값 없음, DB TLS, Secure Cookie 고정)로 나눴다. Compose는 SPRING_PROFILES_ACTIVE=dev.
V8 activity_logs(회원가입·로그인 성공/실패·로그아웃·기업정보·대화 생성·AI 검색·자격 판정)를 추가했다. ActivityLogService를 서비스에서 명시 호출하고 REQUIRES_NEW로 저장한다.
IMP-013 RESOLVED(평가 근거를 source+chunk_index로 판정), Backlog를 V1/V2/운영/장기로 분류했다.
규칙 변경(보고, 완화 없음): 파일 경계(Spring 도메인·계층 배치와 의존 방향, common 범위, DDD 패턴 비도입), Safety(profile 파일 비밀값 금지, activity_logs 민감정보 금지), DB 규칙(MySQL 사용 범위, V8). 새 contract test 1개(profile 규칙), 기존 평가 test fixture에 IMP-013 경우 추가.
결과: [Report](../workspace/reports/development/2026-10-01-v1-code-closing.md). AGY 검토 pending.

## 2026-10-01 — Spring Boot ↔ FastAPI 연결 + React AI E2E V1

`UnconnectedAiGateway`를 `HttpAiGateway`(동기 RestClient, 연결 3s·응답 90s 환경설정, 자동 재시도 없음)로 바꿨다. Spring은 FastAPI 결과를 계약 검증 후 그대로 전달하고, 성공한 AI 응답만 ASSISTANT 메시지(V7 `ai_result_type`·`ai_result_json`)로 저장한다.
FastAPI `/internal/v1/*`에 공유 키 서비스 간 인증(`X-Internal-Api-Key`, `INTERNAL_AI_API_KEY`, 키 없으면 503 fail closed)을 추가했다. `/health`는 열어 둔다. AI 판단 로직·검색·prompt는 바꾸지 않았다.
사용자 결정: 공유 키 방식, FastAPI는 호스트 실행 + Compose backend가 host.docker.internal로 호출(Compose 통합은 IMP-017).
규칙 변경(보고, 완화 없음): AI 경계(재판단·재정렬 금지, 자동 재시도 금지, 실패 시 가짜 ASSISTANT 금지), 파일 경계(React는 AI 포함 Spring만 호출, HttpAiGateway 한 곳, 내부 인증 실패는 사용자 인증 실패 아님), Safety(JWT_SECRET·INTERNAL_AI_API_KEY 환경변수), DB 규칙(V7).
결과: [Report](../workspace/reports/development/2026-10-01-ai-e2e-v1.md). AGY 검토 pending.

## 2026-10-01 — React + Spring Boot 서비스 V1

`backend/`(Spring Boot 3.5, Java 21: JWT 인증·기업정보·지원사업 조회·대화·AI 경계)와 `frontend/`(React 19 + Vite + TanStack Query)를 추가했다. Spring ↔ FastAPI 실제 연결은 하지 않았다(AiGateway 미연결 구현).
사용자 결정: 인증은 JWT(Access 15분 메모리, Refresh 14일 HttpOnly Cookie·DB 해시·rotation), 사용자 1명당 기업 1개, 기업정보는 `companies` 한 테이블(신용점수·체납 등은 판정 요청 때만), Compose `app` profile이 기존 dev MySQL을 재사용, DB 접근은 MyBatis 대신 JPA + QueryDSL.
공통 Flyway에 V6(users·refresh_tokens·companies·conversations·messages, 한국어 COMMENT)을 추가했고 Spring도 같은 history를 쓴다. support_programs는 조회 전용 매핑이다.
규칙 변경(보고): 파일 경계(React는 Spring만 호출, Spring은 서비스 데이터 기준 시스템, support_programs 조회 전용, backend/·frontend/ 허용, FastAPI 연결은 명시 승인 후), DB 규칙(JPA/QueryDSL·공통 Flyway 계보), 주석 정책(핵심 로직의 한국어 무엇/왜, Java·TS·CSS 주석 검사), AI 경계(서비스 계층은 AI 결과를 만들거나 고치지 않음).
validator: check-comments가 Java·TS(TSX)·CSS 주석을 검사하고, Compose 검사가 app profile(mysql 공유·backend/frontend loopback·공통 migrations mount)을 확인하며, backend/frontend build 산출물(build·.gradle·node_modules·dist)만 ignore를 허용한다. Registry의 미구현 module은 `ai`만 남았다.
IMP-015·IMP-016 추가. 결과: [Report](../workspace/reports/development/2026-10-01-service-v1-react-spring.md). AGY 검토 pending.

## 2026-10-01 — IMP-014 목록 검색 공고 다양성

SEARCH_LIST 순위 단위를 조각에서 공고로 바꿨다. `Retriever.search_programs`가 의미·단어 검색마다 공고별 최고 조각 하나(Qdrant group 검색)를 받고 기존 RRF로 공고 순위를 합친다.
RAG 계약 discovery 절(fetch_chunks → group_limit_per_mode 50, 공고 단위 규칙, 채우기 금지)과 AI 경계 2줄(공고 단위 결과·조각 독점 금지, 범위 밖·근거 없는 공고로 채우지 않음)을 갱신했다.
BGE-M3·dense/sparse·RRF·collection·index·DOCUMENT_QA top5는 바꾸지 않았다. IMP-014 RESOLVED.
결과: [Report](../workspace/reports/development/2026-10-01-imp014-discovery-diversity.md). AGY 검토 pending.

## 2026-09-30 — 문서 한국어화와 PROJECT_MASTER_GUIDE

루트에 `PROJECT_MASTER_GUIDE.md`(시작부터 현재까지 전체 설명·기술 선택·실험·실패·용어 사전·면접 답변)와 `harness/docs/glossary-ko.md`를 추가했다.
Harness 문서의 영어 제목에 한글 뜻을 덧붙이고, observability의 "RAG 없음" 서술을 현재 상태로 고쳤다. anchor로 쓰이는 제목과 validator가 검사하는 문구는 유지했다.
주석 정책 규칙에 "사람이 읽는 문서" 절(한국어 우선, 식별자 불변, 검사 문구 유지, 마스터 가이드 갱신)을 추가했다. 코드·Contract·API 동작 변경 없음. Registry에는 새 문서 경로 두 줄만 등록했다.

## 2026-09-30 — FastAPI Internal API v1

`biz_aid_pipeline/api/`(FastAPI): /health, /internal/v1/query, /internal/v1/eligibility. CLI와 API는 같은 `runtime.ServiceRuntime`을 호출하고, lifespan에서 한 번 만든 자원을 재사용한다.
파일 경계의 "FastAPI 없음"을 내부 API 위치로 바꾸고 4줄을 추가했다: 서비스 계층 전용·브라우저 직접 의존 금지, thin handler, 무거운 자원 요청별 재생성 금지, 판단 결과는 HTTP 오류가 아님.
작은 내부 API 계약을 추가하고 requirements에 fastapi·uvicorn을 추가했다. 판단 로직 변경 없음. IMP-014 추가.
결과: [Report](../workspace/reports/development/2026-09-30-internal-api-v1.md). AGY 검토 pending.

## 2026-09-30 — Single-program Eligibility v1

`eligibility/`: CompanyProfileSnapshot(저장 없음) + 대상 공고 1개 → 고정 질의 scope 검색 → LLM criterion → application 검증·최종 상태·citation. 작은 Eligibility 계약을 추가했다.
규칙 변경(보고): AI 경계의 "지원 자격 판단 금지"를 단일 공고 v1 승인으로 옮기고, 여러 공고 판정·추천 점수 금지를 명시했다. Profile snapshot 소비·대상 공고 근거·모름은 UNKNOWN·상태는 application 계산 4줄을 추가했다.
Retrieval·RAG prompt·index 변경 없음. IMP-003 evidence 갱신.
결과: [Report](../workspace/reports/development/2026-09-30-eligibility-v1.md). AGY 검토 pending.

## 2026-09-30 — IMP-001 공고명 검색 context

FinalChunk.embedding_text 첫 줄에 공고명(support_programs.name)을 넣고 chunk text는 그대로 둔다. content_key에 공고명을 넣어 같은 입력만 vector를 공유한다.
Chunking 계약 chunker_version 2(embedding_context), Source 규칙에 검색 전용 context·identity 반영 2줄을 추가했다. 고정 100-source를 기존 runner로 재적재했다.
BGE-M3·RRF·top_k·Retriever·RAG prompt 변경 없음. IMP-001 RESOLVED, IMP-013 추가.
결과: [Report](../workspace/reports/development/2026-09-30-imp001-title-context.md). AGY 검토 pending.

## 2026-09-30 — Discovery list + hard filter grounding

자연어 추출 호출이 request_mode(SEARCH_LIST·DOCUMENT_QA)를 함께 낸다. SEARCH_LIST는 후보 scope hybrid 검색을 공고 단위로 중복 제거해 MySQL 정형 정보 목록을 돌려준다(답변 LLM 없음).
LLM hard filter는 질문 원문 근거(허용 값 표현·모집 계열 표현)가 있을 때만 적용한다. AI 경계에 목록 응답·근거 있는 hard filter·공고 단위 중복 제거 3줄을 추가했다.
RAG prompt·citation·retrieval baseline 변경 없음. IMP-012 RESOLVED, IMP-001 evidence 갱신.
결과: [Report](../workspace/reports/development/2026-09-30-phase6d-discovery-list.md). AGY 검토 pending.

## 2026-09-30 — Natural-language candidate filter

자연어 질문 → 같은 LlmProvider 구조화 추출(category·target·현재 모집 요청·unapplied) → 활성 공고 실제 값 검증 → ProgramCandidateFilter → 기존 scoped RAG.
규칙 변경(보고): AI 경계의 "자연어→정형 조건 추출 금지"를 해제하고 허용 값 검증·다른 field 오매핑 금지·상대 시간은 application 시간 규칙을 추가했다.
jurisdiction은 지역명과 겹쳐 자연어로 적용하지 않는다. Retrieval·RAG prompt·citation 변경 없음. Backlog IMP-012 추가, IMP-003·IMP-011 evidence 갱신.
결과: [Report](../workspace/reports/development/2026-09-30-phase6c-natural-filter.md). AGY 검토 pending.

## 2026-09-30 — Candidate-scoped RAG (MySQL 정형 후보 → pblanc_id scope)

`candidates/`(support_programs read-only)가 활성 공고 + category·target·jurisdiction·not_closed_on으로 후보 pblanc_id를 정하고, Retriever가 Qdrant MatchAny로 scope를 강제한다.
빈 후보는 검색·LLM 없이 NO_CANDIDATES다. AI 경계에 정형 조건 선적용·scope 밖 반환 금지·빈 후보 short-circuit 3줄을 추가하고 "MySQL 조건 결합 금지"를 해제했다(자격 판단·자연어 조건 추출 금지는 유지).
Retrieval scoring·prompt·provider·citation 변경 없음. IMP-008 RESOLVED, IMP-011 추가.
결과: [Report](../workspace/reports/development/2026-09-30-phase6b-candidate-scoped-rag.md). AGY 검토 pending.

## 2026-09-30 — Improvement Backlog

관찰됐지만 blocker가 아니어서 의도적으로 미룬 개선을 기록하는 `harness/docs/improvement-backlog.md`를 추가했다(IMP-001~010, 최근 Retrieval·RAG 4건 + 과거 phase에서 복원한 6건).
운영 규칙은 Workflow의 Improvement Backlog 절, 진입 링크는 AGENTS 한 줄이다. 제품 코드 변경 없음.

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
- M-4: 공식 명세 전 환경변수 추정 없음. .env.dev.example 보존.
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

## 2026-10-01 — V1 AI Evaluation Baseline

V1 종료 상태를 V2 변경과 같은 조건으로 비교하도록 SEARCH_LIST 4건·DOCUMENT_QA 3건·Eligibility 3건을
`evals/v1_baseline/cases-v1.json`에 두고 sha256으로 동결했다. 문장 전체 대신 공고 ID·후보 범위·문서 SHA와 조각 순번·Citation·핵심 사실·자격 상태를 판정한다.
기존 case와 기대값은 수정하지 않고 기준 변경은 새 version으로 만든다. 실제 Ollama·dev MySQL·dev Qdrant 1회 실행은 check-all 밖에서 수행하며 응답 시간은 합격 조건이 아니다.

## 2026-10-03 — 지역 마무리 및 IMP-029

- 사용자 V11 적용 승인과 whitespace/prefix 경계 수용을 기록하고 common Flyway로 이동한다. 질문 지역 unapplied와 후보 소관기관 필터 유지 결정을 구분한다.
- IMP-019/030 측정 Evidence와 IMP-031 신청 가능 지역 추출·IMP-032 원본 소관 불일치 후속을 기록한다.
- IMP-029 사용자 범위 축소: 비교 실험을 생략하고 prompt의 서류/절차/작성 항목 제외·중복 금지·관련 조건 묶기와 상한15개/1280token을 적용한다. 75초 기한·fail-closed·공고별 근거 격리·기존 identity는 보존한다. 같은 입력 workflow1회 후 check-all1회; 결과는 Task Report에 기록한다.
- 실제 workflow1회에서 117611 상한 실패는 해소됐으나 123260은 근거ID 검증 실패다. 성공으로 숨기지 않고 IMP-029 OPEN/부분 해결을 보존한다. 모든 HTTP 단계는90초 미만이었다.

## 2026-10-03 묶음1 품질

사용자 승인: FORM 근거 제외·내부 지급규정 role 정정·근접 RRF 지역 가산·규칙 우선 질문 모드·공고 선택을 계약에 기록한다. V1 baseline/identity/vector/MySQL 지역 필터는 유지한다. 고정질문 runner는 strict 입력, 사용자 지정 handoff는 좁은 checkpoint 예외다. 실제 결과는 묶음1 Report에 기록하며 AGY 승인으로 취급하지 않는다.

## 2026-10-04 묶음2 지역·데이터 정리

기업 지역 제목/소관 규칙과 named QA 예외를 계약·FastAPI·Spring·React에 공유했다. 명시 신청기간 파생 보강·원문 보존, snapshot 후 V2 마감 정리, 신규 문서 admission을 추가했다. 제품 key/vector/V1과 비밀값 불변. 사용자 지정 bundle2 handoff만 non-gating 경계에 추가했다. 최종 검증 결과는 개발 Report에 실제 exit로 기록한다.

## 2026-10-04 묶음5-2 배포 전 마무리

- 사용자 승인으로 명시 운영 질문 서버만 원격 DB/TLS·고정 검색 collection을 허용한다. 수집·적재 dev guard는 보존한다.
- 운영 외부 추적/Swagger 차단, IP 신뢰는 Caddy와 전용 nginx 경계로 제한한다.
- 기존 usage counter를 전체 하루300회/IP별 가입5개에 재사용한다. 공고 영역/V2 snapshot만 이사하며 개인정보 영역은 제외한다.
- 공공누리 제3유형 확인·Bedrock 국외 처리·문의처를 안내하고 약관/동의 버전을 2026-10-04.2로 함께 올린다.
- 운영 Compose/리허설/배포 smoke 및 narrow bundle5-2 handoff 생성물 예외를 등록한다. 미측정 결과는 PASS로 기록하지 않는다.

- V14는 기존 type/key/data를 보존하고 usage counter 새 key와 동의 버전 개정 번호의 DB COMMENT만 동기화한다. V1~V13은 불변이다.

- 묶음5-2 최종 계약 검사에서 dev 입력 필드 오류 suffix 회귀3건을 발견해, 상세 오류 제거를 명시 prod 응답에만 적용했다. 기존 dev 계약 assertion은 그대로 유지하며 prod의 field/detail 비노출 검사를 보강했다.
- 최종 코드 점검에서 S3Config에 잘못 중복 추가된 DB 전용 설정 helper를 제거해 기존 dev-only S3 경계를 복원하고, 운영 DB 예외가 S3로 확산되지 않는 검사를 추가했다. 운영 예외를 계약 scope/architecture에도 명시했다.

## 2026-10-04 묶음5-2 마무리 수정

사용자 결정으로 계정 하루10회·실제IP 합산30회를 적용한다. 기존 원자적 store와 해시만 재사용하고 거절/실패 때 모든 예약을 보상한다. 한국 날짜7일 정리와 V15 COMMENT, 문서 버전2026-10-04.3을 동기화한다. 일반 input 전체폭/버튼 세로배치의 공통 CSS 원인을 수정하고 기업 매출은 표시만 쉼표·한글로 보강한다. 이전Report·migrationV1~V14는 보존하며 실제Bedrock은 호출하지 않는다.

## 2026-10-05 — 묶음6-0 배포 준비물

- 사용자결정:ARM t4g.large/Ubuntu24.04,RDS MySQL8.4,단일비공개Hub3태그,pull전용서버bundle. 명시build override와안전복원·설명서/Contract를등록한다.
- 개발Compose/dev.sh/기존migration·vector·V1/V2원본은보존한다. 실제push/AWS생성/S3업로드/Bedrock은미실행이다.
- handoff/bundle6-0-handoff.md만동적산출물로등록한다. Generated출력으로제품입력을숨기지않고기존gate를유지한다.

## 2026-10-05 묶음6-0 추가 지시 — 실제 운영 서버 반영

- 사용자 확정 Ubuntu24.04 x86_64/8GB+swap2GB,시드니 EC2/RDS/S3를운영설명서·공개예시에반영한다. Bedrock만서울global profile유지.
- 운영image 기본amd64, build --platform옵션·image검증, 전달prefix deploy/<태그>/ 및시드니CA/VERIFY_IDENTITY. 개발Compose/dev.sh/profile·기존data02·migration불변.
- 개인정보시드니저장/Bedrock다국가처리·실제저장항목을안내하고서버/화면동의버전2026-10-05.1로동기화한다. 과거동의불변/신규가입·체험버전기록을검사하며법률검토는남긴다.

## 2026-10-05 묶음6-2 — 개발 설정 견본 이름 정리

- 사용자 요청으로 개발 견본 이름을 `.env.dev.example`로 바꾼다. 견본은 실행 설정으로 읽히지 않으며 안내·문서·Git 제외 예외·Registry·검사 기준의 이름만 맞춘다.
- 견본 내용과 `.env.prod.example`, 실제 설정 파일, 서비스 코드·Compose 설정을 보존한다. 실제 설정값 열람·서비스 재시작·commit·push는 하지 않는다.
- 과거 보고서는 유지한다. 보고서 밖 검사 산출물(JSON·로그)의 이름 문자열은 사용자 지정 전체 변경 범위에 따라 교체하며 과거 검사 결과를 이번 통과 근거로 사용하지 않는다.
- 전체 검사는 실제 설정 읽기와 DB 준비가 포함되어 이번 사용자 제한에 따라 실행하지 않는다. 실제 설정을 열지 않는 정적 검사와 Git 제외·이력·기존 검사 회귀만 확인한다.
