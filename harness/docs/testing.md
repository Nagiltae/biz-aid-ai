# Validation 정책

처음 보는 용어의 한국어 뜻은 [용어집](glossary-ko.md)을, 프로젝트 전체 흐름은 [PROJECT_MASTER_GUIDE](../../PROJECT_MASTER_GUIDE.md)를 본다.

근거: 현재 production code·Contract·Task 범위. PROJECT_DESIGN.md §37–41, 46은 최초 검증 목표다.
실제 검사를 수행한 항목만 PASS로 기록한다. 미구현을 통과로 계산하지 않는다.

## 실행 범위

| 진입점 | 현재 실제 검사 | 미구현 / 미측정 |
| --- | --- | --- |
| setup.sh | Bash·Git·Python >=3.11·Docker Compose >=2, Compose config와 mounts, Python/DB/Parser/Qdrant client 전제 | Java·Node build, 서비스 health, Live Qdrant·LLM 호출 |
| check-format.sh | Control/Input의 UTF-8·LF·newline·공백·JSON indent·Git whitespace | 제품 언어 formatter |
| check-lint.sh | Python AST·Bash syntax·JSON key 중복·Shell 실행 권한 | 제품 lint, 정적 타입 검사 |
| check-contract.sh | Phase 0부터 RAG·Eligibility·내부 API·V1 baseline helper까지 offline Contract tests | Live API·AWS·실제 Qdrant·LLM·Browser 호출 |
| check-integration.sh | 로컬 CLI와 dev/test MySQL의 구조화 적재·문서 metadata·parse persistence | Live upstream HTTP·AWS·실제 Parser model·서비스 E2E |
| check-git-tracked.sh | dev / CI ref·미추적 파일·금지 ignore·Profile Secret ignore / 추적 금지·example 추적·index 동기화·최종 status | Push·Merge 권한 강제 |
| check-comments.sh | Python tokenize / AST docstring·Bash comment의 한글 여부 | 주석 WHY의 적절성·누락은 AGY / 사용자 검토 |
| check-harness.sh | 정적 문서 링크·Registry·Skill·명령·실제 module / Compose / CI·Workspace 제어·Review metadata | AGY 독립 Architecture 판단·저자 신원 인증 |
| check-all.sh | 위 Harness·Python Contract·MySQL Integration 검사 전부 실행, 적용 범위 요약 | Backend/Frontend 별도 build·test, Browser E2E, Live AI Eval |
| (서비스 V1) backend | `docker run --rm -v "$PWD/backend":/app -v bizaid-gradle-cache:/home/gradle/.gradle -w /app gradle:8.14-jdk21 gradle test` — H2 격리 DB의 인증·기업정보·QueryDSL 검색·대화·활동 기록과 가짜 FastAPI(JDK HttpServer)로 AI 결과 전달·저장·제한시간·내부 인증 오류 | check-all에 포함되지 않음. 실제 MySQL은 Compose E2E로 확인 |
| (서비스 V1) frontend | `cd frontend && npm ci && npm run typecheck && npm test && npm run build` — 인증 routing·목록·기업정보 저장·SEARCH_LIST 카드·DOCUMENT_QA 근거·자격 판정 상태 | check-all에 포함되지 않음 |

0 = 해당 진입점의 **현재 명시된 범위** 통과, 1 = 실패, 2 = CLI 사용 오류.
check-all은 모든 적용 검사를 실행한 후 하나라도 실패하면 1을 반환한다.
각 진입점에서 실행하지 않은 Live·서비스 build·E2E·AI Eval은 N/A로 출력하며 성공 건수에 넣지 않는다.
새 실행 코드·제품 module·service가 생기면 Registry와 검증을 함께 갱신해야 한다.
현재 Registry 밖의 실행 코드·workflow·module은 Harness drift로 실패한다.

개발 중 검증은 결함을 재현·확인할 수 있는 가장 작은 충분 범위(smallest sufficient scope)로 한다.
전체 corpus / full evaluation은 production 최종 승인 직전 명시적으로 필요할 때만 실행한다.
검증만을 위한 별도 기능 개발은 기존 Harness로 해결할 수 없을 때만 한다.

## 테스트 단계와 DoD

check-all은 Harness와 Python Unit / Contract / MySQL Integration을 실행한다. Backend·Frontend test/build와 실제 서비스 E2E·AI baseline은 별도 승인 실행으로 기록한다.
API Probe는 별도의 명시적인 Local 명령이며 CI에서 실제 요청을 강제하지 않는다.
Probe의 credential_missing 종료 코드 3은 NOT_RUN이며 PASS로 계산하지 않는다.
Profile 격리·fallback 금지·OS 우선·셸 비실행·secret 비노출·prod OS 주입은 임시 합성 설정만 사용한다.
사용자 .env.dev / .env.prod를 fixture로 복사하지 않는다. Offline PASS 이후 현재 dev Live만 명시적으로 실행한다.
제품 Level 1–7(Format / Lint / Unit / Component / Contract / Integration / E2E / AI Eval)은 진입점별로 분리한다.
React→Spring, Spring→FastAPI/MySQL, FastAPI→Qdrant 경계는 V1 E2E에서 확인했고, V1 AI baseline 10건은 별도 명시 실행이다.
Live 결과를 check-all의 offline PASS로 대체하거나 반대로 과거 Live Evidence를 현재 실행 결과로 재사용하지 않는다.

AGY는 주석 의미·Architecture·테스트 사각지대·적용 제외 타당성을 독립 검토한다.
Codex 검증 통과는 AGY 승인 또는 Phase 0 GO를 뜻하지 않는다.
Review Lifecycle은 [workflow.md](workflow.md)의 pending / review_complete를 따른다.
사용자 확인된 AGY 참조·상태는 제어 입력으로 검증해 자기 승인·미지원 metadata는 실패시킨다.
원문·검토 대상의 누락·checksum 불일치·symlink는 non-gating integrity 상태로 표시하며 독립 승인 근거로 인정하지 않는다.
제품 검증 통과와 Report file lifecycle을 분리한다. 입력 자산의 Git Diff·미추적 파일 없음, 실제 실행 결과와 Generated Report 제공이 DoD다.

API 품질 Batch는 고정 5×20 계획·중복·MISSING/NULL/BLANK/INVALID·기간·확장자·부분 실패·재현/Raw checksum을 오프라인으로 검증한다.
명시적인 Negative Probe만 03 NODATA_ERROR를 EXPECTED_NO_DATA로 분류하고 Positive Probe / Batch의 같은 결과는 API_ERROR다.
Live Batch는 전체 Offline Validation PASS 이후 dev에서만 별도 실행한다. 제품·문서 Gate와 공식 정렬 보장 검증은 포함하지 않는다.

문서 Gate는 임시 파일 / mock stream으로 순차 100개 계획·HTTP 오류·Redirect·크기·형식·중복·checksum·Partial/Resume·Checkpoint·Secret 경계를 검사한다.
CI는 실제 파일 HTTP를 호출하지 않는다. Offline 전체 PASS 뒤 dev 다운로드를 별도 명령으로 수행한다.
SYNTHETIC_MOCK와 LIVE_HTTP Evidence를 구분하고 다운로드 성공을 본문 Parsing 성공으로 계산하지 않는다.

## Phase 1A 검증

`.venv`에 `data-pipeline/requirements.txt`를 설치한다. 기존 shell 진입점은 이 Python을 사용한다.
Unit / Contract는 제품 package를 import하고 Fixture / mock만 사용한다.
Integration은 Compose dev MySQL + 공통 Flyway를 실제 준비하며 `biz_aid_test`에서 fixture SQL을 실행한다.
DB가 없거나 migration이 실패하면 FAIL이며 SQLite / skip으로 대체하지 않는다.
CI는 외부 API key 없이 합성 100건을 검증한다. 실제 Pilot은 동일 Raw 100건을 dev DB에 적재하는 별도 CLI다.
최종 Control/Input / index를 확정하고 check-all을 실행한 뒤 Generated Report를 작성한다. 기존 Phase 0 검증도 계속 실행한다.

환경 정책 회귀는 Profile 격리·generic/이전 설정 fallback 금지·Process 우선·필수 DB 설정·Secret 비노출·3306 경계를 검사한다.
실제 Integration은 Host 3306과 MySQL 내부 @@port=3306을 확인한다. CI는 공개 합성 DB 값을 Process Environment에 주입하며 사용자 Secret 파일을 만들지 않는다.

## Database COMMENT 검증

check-integration / check-all은 실제 dev/test application DB의 information_schema.tables / columns를 조회한다.
BASE TABLE 전체를 탐색해 Flyway 내부 테이블만 제외하며, 신규 업무 테이블/컬럼도 자동 포함한다.
Table / Column COMMENT의 빈 값·TODO/TBD·이름 반복·단독 "데이터"/"값"·한국어 설명 부재는 실패한다.
품질 함수의 Unit/Contract는 mock metadata를 사용하며 DB 연결을 하지 않는다.
Integration은 별도 test DB의 빈 합성 테이블에서 COMMENT 누락·placeholder 실패와 신규 Table 탐색을 재현하고 finally에서 해당 fixture만 제거한다.
동일 DB의 빈 fixture에 V1→V2를 적용해 COMMENT 외 column definition / 키 / 제약 보존도 검사한다.
Flyway 소유권·적용 migration 불변·단위와 lifecycle 설명의 독립 검토는 [DB 규칙](../rules/database-rules.md)을 따른다.
규칙 검사만으로 설명 의미가 정확하다고 주장하지 않는다. prod / Live API는 실행하지 않는다.

## Workspace lifecycle 회귀

current-task와 artifacts/checkpoints의 고정 README는 format·tracking·links·Registry strict 입력이다.
reports/**/*.md, checkpoint Markdown(고정 README 제외), artifacts/**/*.json / **/*.log는 non-gating 출력이다.
format/lint/comments 파일 목록, Git whitespace·untracked/index 동기화·ignore 경계, Harness 파일/링크 검사는 같은 분류를 사용한다.
이미 추적된 historical 생성물도 검사 대상에서 제외하지만 삭제·강제 untrack·원문 수정하지 않는다.

격리 Git fixture로 untracked/ignored/unstaged/trailing whitespace·malformed Artifact·출력 없음·검증 후 Report 생성을 PASS로 확인한다.
current-task/정적 README/Rule/제품의 공백·링크 오류, static ignore·untracked·Registry Drift·코드 숨김은 FAIL을 유지한다.
Generated Output만 변경됐으면 기존 Validation은 유효하며 Control/Input 변경은 재검증한다.
출력 파일 형식과 무관하게 실제 검증 command exit 1은 check-all exit 1로 전파한다.

Producer 경로 회귀는 reports/development·reports/agy와 Task별 Artifact의 non-gating 경계를 검사한다.
Codex·Claude 지침의 공동 경로 불일치, current-task의 Agent 전용 Report 지정, 개발 Report의 Review Evidence 사용은 FAIL이다.
Agent handoff checkpoint를 추가하거나 공동 Report를 이어서 갱신해도 Registry 변경 없이 Harness가 통과해야 한다.
산출물 디렉터리나 파일이 없어도 통과한다. static anchor·제품 공백/untracked 검사는 그대로 유지한다.

## Phase 1B FULL 검증

Unit/Contract는 mock API의 여러 Page·마지막 partial/exact Page·중복/invalid ID·오류/빈 Page·count 변화/불일치·Raw/metadata 변조·overwrite·Secret 경계를 검증한다.
Integration은 동일 product orchestration을 mock HTTP와 실제 test MySQL에 연결해 FULL INSERT·동일 rerun NOOP·REACTIVATE·DRY_RUN 후보·SAMPLE/PARTIAL·transaction budget rollback을 검증한다.
기존 성공 FULL APPLY는 controlled test DB에서만 유지한다. dev APPLY와 첫 Live 실제 soft-delete는 거부한다.
CI는 Live API를 호출하지 않는다. 전체 Offline Validation 후 별도 dev collect, Live Raw/DB 대조 후 새 최종 Validation과 Codex Report를 기록한다.

## Phase 2 Document Acquisition 검증

Unit/Contract는 provenance 추출, URL/SHA dedupe, PDF/HWP/HWPX/UNKNOWN, HTML/HTTP/network/redirect/size,
retry 0, overwrite 거부와 false PASS를 mock/temp file로 검증한다. Integration은 실제 test MySQL의 V3에
relation 보존, checksum readback, partial/resume, rerun 성공 재사용, 실패 새 run 재요청과 품질 Gate를 검증한다.
CI는 문서 Live HTTP를 호출하지 않는다. Preliminary Validation 이후에만 dev 전체 acquisition을 실행하고
DB relation과 binary checksum을 다시 읽어 확인한 뒤 Final Validation을 실행한다.

## Phase 2.5 S3 저장 검증

Contract는 SHA key, 조건부 PUT, 412 race, HEAD checksum, 실제 GET SHA, overwrite 금지와 metadata all-or-none을 mock S3로 검증한다.
metadata-link 테스트는 누락 object에서 PUT 없이 실패하고 전체 검증 후에만 DB update 경계로 진입함을 확인한다.
Integration은 실제 test MySQL V4와 S3 readback을 모사하며 live AWS나 upstream HTTP를 호출하지 않는다.
dev 별도 검증에서 로컬 3,231 SHA와 S3 HEAD checksum을 대조하고 DB 3,288 relation readback 후 기존 Phase 2 run을 S3 byte로 재검증한다.

## Phase 3 Parsing 검증

Contract 테스트는 합성 HWPX container로 detected-format route, 비활성 route 상태, 입력 SHA/크기 불일치 거부,
DoclingDocument JSON 재적재·표 병합·section 순서·글상자/중첩 표·정규화와 orig 보존, 빈 text의 비성공 상태,
경로 탈출·중복·압축비·해제 크기·DTD/entity·암호화·손상 XML/ZIP 거부와 parse_key 버전 규칙을 검증한다.
Contract의 unique content SHA / source relation 기준 분리와 합계, 미결정 route의 비활성 상태도 검사한다.
실제 corpus·AWS S3·Docling PDF 변환·HWP 변환·HWPX 구조 품질은 아직 검증 대상이 아니며 PASS로 계산하지 않는다.

`test_document_parsing_pdf.py`는 결정론적 합성 PDF로 text PDF → PARSED와 JSON 재적재, image-only PDF → OCR_REQUIRED,
손상 PDF와 Docling 부분 성공 → PARSE_FAILED(등록된 failure_code), detected_format이 PDF일 때만 PDF handler 호출,
integrity 오류의 선행, OCR 비활성, parse_key의 Docling 배포·설정 추적을 검증한다.
표 cell 탈락 warning 노출·전역 logging 불변, upstream 탈락 문구 drift, 명시적 표 설정, artifact 경로 fail-fast·manifest identity도 검증한다.
test runtime은 모델을 다운로드하지 않는다. validator는 HF_HUB_OFFLINE=1로 실행하고 `BIZAID_DOCLING_ARTIFACTS_PATH`에 준비된 artifact가 없으면 setup이 FAIL이다.
CI는 모델 identity 기반 key의 Actions cache를 복원하고 miss일 때만 명시적 provisioning step에서 네트워크를 쓴다.
cache hit·miss와 무관하게 manifest identity를 verify한 뒤 setup·check-all을 HF_HUB_OFFLINE=1로 실행한다. PDF test skip은 없다.
`test_docling_provisioning.py`는 cache key의 identity 한정 변화, resolved commit 다운로드, staging 원자성, 손상·중단 거부, CI step 순서·network 경계를 검증한다.
프로젝트 인터프리터 요구사항은 stdlib `lzma`를 포함한 Python 3.11이다. setup은 lzma 부재를 Docling PDF prerequisite 미충족으로 보고한다.

## Phase 3-B.1 표 engine 평가

`test_table_engine_eval.py`는 critical token 분류, HTML span grid, 1:1 표 매칭, GT 비교(완전·미검출·cell 탈락·병합 cell),
두 engine family 이상의 consensus, Camelot lattice span 복원, corpus SHA·provenance 고정과 Contract의 table_engine 규칙을 합성 데이터로 검증한다.
실제 benchmark 실행은 저장소 밖 benchmark venv·모델에서 명시적으로 하며 CI와 check-all은 engine·모델을 실행하지 않는다.

## Phase 3-B.2 PP-TableMagic 적합성

`test_table_engine_eval.py`는 PP 행 규칙·HTML 행별 cell 수, 검출 경계 grid의 span 증명과 충돌 보고, 구조 bbox 긴 변 정규화 보정,
Contract의 suitability_gate·table_quality 규칙을 검증한다. `test_harness_policy.py`는 IntelliJ introspection cache
`.idea/dataSources/**/storage_v2/**/*.meta`만 허용하고 다른 확장자·위치·실행 파일은 계속 FAIL임을 검증한다.
PP 진단(`pp_diagnostics.py`)은 benchmark venv에서 명시적으로 실행하며 check-all은 engine·모델을 실행하지 않는다.

## Phase 3-B.3 PDF Hybrid Parsing 검증

평가 테스트(`test_table_engine_eval.py`)와 production 테스트(`test_document_parsing*.py`)를 파일로 구분한다.
평가 테스트는 겹친 검출 box 정규화, 실패 표 text의 읽기 순서 재조립, 겹친 PP 영역을 고르지 않고 합친 FAILED 영역으로 보존하는 조립 규칙,
visual 품질 Gate(빈 출력·반복·원문에 없는 한자 출력·native grounding·human pending)를 검증한다.
PaddleOCR-VL pilot의 호출별 120초 상한은 무기한 평가 실행을 막는 local safety boundary이며 production threshold가 아니다.
Chart·Spotting 출력 schema와 의미 정확성은 evidence 없이 강제하지 않고 review bundle에서 사람이 원본 crop과 대조한다.
`test_production_route_is_unchanged_by_evaluation`은 Contract primary·표 설정·PDF route가 그대로이고
제품 parsing 코드가 evals·paddle·camelot을 import하지 않음을 확인한다. PaddleOCR-VL과 조립 pilot은 check-all에서 실행하지 않는다.

## Phase 3-B.4 Hybrid Review Closure(표 조립 검토 마무리)

조립 회귀는 손실·겹침·footnote·표/그림 충돌 사례와 정상 표 문서를 포함한 최대 5문서 targeted 범위에서 쪽 단위로 baseline Docling 대비 잃은 글자(`lost_vs_baseline`)를 센다. 문서 합계는 한 쪽의 손실을 다른 쪽의 개선이 가릴 수 있어 판정에 쓰지 않는다.
평가 테스트는 교체된 표의 footnote 자식 보존, VALID 표 cell 밖 단어 보존, 부분 겹침 판정, 쪽 단위 손실 계산, review flag가 판정을 대신하지 않음을 검증한다.
`evals/table_engine/review.py`는 기존 산출물로 사람 검토 entry point를 만들며 모델·parser를 다시 실행하지 않고 어떤 항목도 PASS로 기록하지 않는다.

## Phase 3-B.5 PP Production Integration(PP 표 엔진 운영 적용)

PDF route Contract test는 합성 PDF로 PP 표가 TABLE_VALID TableItem과 provenance로 조립되는지, 실패 표가 구조 없이 native text로 남는지,
표 engine 오류가 fallback 없이 PARSE_FAILED인지, Docling 표 구조가 꺼지고 PP 설정에 OCR이 없는지 확인한다. PP 모델은 Docling layout과 같은 고정 artifact 경로에서만 읽는다.
실제 문서 확인은 check-all 밖의 targeted regression(최대 5문서)으로만 하며 결과는 ignored `data/parsed/`에 둔다.

## Phase 3-B.6 HWP → PDF Route(HWP를 PDF로 변환해 처리)

HWP route Contract test는 docker 호출을 대체해 변환 성공 시 `parse_pdf` 재사용·원본 SHA provenance·derivation·임시 디렉터리 삭제를,
변환 실패·timeout·이미지 identity 불일치가 fallback 없이 CONVERSION_FAILED인지, Dockerfile이 Contract의 hash·base digest·H2Orestart SHA와 같은지 확인한다.
실제 변환은 check-all 밖에서 HWP 최대 3개의 targeted 확인으로만 하며 check-all은 변환 이미지를 요구하지 않는다.

## Phase 3-B.7 OCR_REQUIRED OCR(글자 없는 문서의 문자 인식)

PDF Contract test는 합성 image-only PDF 1쪽에 실제 OCR을 돌려 글자가 없으면 OCR_REQUIRED + OCR_TEXT_INSUFFICIENT인지 확인하고,
OCR 결과를 대체한 test로 PARSED 조립·읽기 순서·`bizaid__ocr` provenance, OCR engine 오류의 PARSE_FAILED, text PDF에서 OCR 미호출을 확인한다.
실제 OCR_REQUIRED 문서 확인은 check-all 밖에서 최대 3문서로만 한다.

부분 scan PDF는 text page와 image page를 합친 2-page fixture로 검증한다. OCR mock은 image page만 선택되는지, native page text가 한 번만
남는지, OCR text·provenance·JSON round-trip과 기존 PP table route가 유지되는지를 확인한다. 일반 text PDF는 계속 OCR 호출 0회다.

## Phase 3 Parse persistence(파싱 결과 저장)

Contract test는 parsed S3 key 결정성, conditional PUT·checksum·full readback 및 verify 실패 시 repository 미호출을 검사한다.
MySQL integration은 작은 기존 ParseResult fixture로 V5 metadata·JSON reload, 동일 source SHA·parse_key 재사용과 S3 실패 시 row 부재를
검사한다. 실제 AWS, parser model 반복 실행, 전체 corpus와 Markdown artifact는 사용하지 않는다.

## Phase 3 Parse orchestration(파싱 실행 흐름)

Contract test는 단일 SHA source lookup → S3 read → parser → persistence 호출 순서와 CLI의 명시적 SHA 입력을 검사한다.
Bounded batch test는 1~3개 unique SHA 제한, 결정적 순차 순서, source별 실패 격리와 INSERTED/REUSED 집계를 검사한다.
MySQL integration은 같은 source를 두 번 실행해 persistence가 INSERTED → REUSED를 반환하는지 확인한다.
S3 read 실패 case는 parser와 persistence가 모두 호출되지 않아야 한다. fake S3와 작은 ParseResult를 사용하며 실제 모델 반복 실행은 없다.
실제 dev smoke는 사용자가 명시적으로 승인한 경우에만 최대 3개 source로 제한하고 prod·자동 source discovery·전체 corpus 실행은 금지한다.

## Phase 3-B.12 HWPX 구조·provenance

HWPX Contract test는 합성 header.xml로 OUTLINE·내장 개요 스타일 heading, 사용자 정의 스타일 비heading, NUMBER/BULLET list group,
머리말 furniture·각주, cell 안 heading 무시와 RichTableCell, 중첩 표 구조 보존과 글자 1회 계수, `bizaid__hwpx` provenance, page/bbox 미생성을 확인한다.
실제 HWPX 확인은 check-all 밖에서 최대 3문서로만 한다.

## Phase 3-B.13 Parser Hardening(파서 안정화)

parse_key test는 HWPX adapter·PDF 표 설정·HWP 변환기·normalizer 변경이 각각 의존 route key만 바꾸는지 확인한다.
PDF test는 PP 영역에 걸친 native item의 영역 밖 단어 보존과 중복 제거, OCR page의 furniture 제거, 같은 행 anchor, OCR 부족 page의 warning 유지와 문서 status를 확인한다.
실제 문서 점검은 check-all 밖에서 format별 최대 2개, 총 6개로만 한다.

## Phase 3-C Corpus Parsing(100건 일괄 파싱)

corpus runner test는 enabled format unique SHA 선택·SHA 순서, 현재 parse_key 결과 skip, source 실패 격리와 연속 환경 실패 시 중단을 확인한다.
실제 통합 검증은 dev corpus 실행 자체이며 check-all에 넣지 않는다.
OCR page 선택 test는 native 글자만 있는 low-text page를 OCR하지 않고, 글자 없는 page와 raster image가 있는 page만 OCR하는지 확인한다.

## Phase 4-A Document Chunking(문서 조각 생성)

Chunking test는 합성 DoclingDocument로 meta 비노출, VALID 표·보존된 FAILED 표 text 포함, heading 문맥, 공고 relation별 FinalChunk와 content_key 공유,
여러 page provenance, chunk_id 결정성, tokenizer·max_tokens·정책·parse_key에 따른 identity 변화, parse identity의 artifact scope 분리를 확인한다. 실제 문서 확인은 check-all 밖에서 format별 1개로만 한다.

## Phase 4-B Document Indexing(검색용 벡터 적재)

Indexing test는 embedding 모델·tokenizer 정렬, embedding 가중치의 artifact scope 분리, embedding_key 변화, sparse 집계 규칙을 확인하고
in-memory Qdrant와 가짜 embedder로 point id·payload 보존, content_key 재사용, 재실행 idempotency, stale 정리, schema·모델 불일치 실패를 확인한다.
실제 BGE-M3 추론과 dev Qdrant 적재는 check-all 밖에서 format별 1개로만 확인한다.

## Phase 5 Document Retrieval(근거 검색)

Retrieval test는 in-memory Qdrant와 가짜 embedder로 collection이 embedding identity에서 정해지는지, 세 mode 결과 field가 payload와 같은지,
검색 전후 point·collection이 변하지 않는지, 다른 identity의 collection이 없으면 만들지 않고 실패하는지 확인한다.
RRF 순위·동점 결정성과, `retrieval/` 코드가 적재·변환 경로를 호출하거나 별도 모델을 import하지 않는지를 AST로 확인한다.
실제 BGE-M3 query와 dev Qdrant 검색은 check-all 밖에서 소수 질문 smoke로만 확인하며 검색 품질 수치를 결론내리지 않는다.

## Phase 6 RAG Answer(근거 기반 답변·후보 제한·자격 판정·내부 API)

RAG test는 가짜 Retriever·가짜 LlmProvider로 hybrid top5 호출, evidence id → SearchResult citation 매핑, prompt에 식별자·provenance가 없는지,
context에 없는 evidence id가 citation이 되지 않는지, 근거 부족·근거 id 없는 답이 고정 확인 불가 문장으로 바뀌는지 확인한다.
실제 Ollama 모델 호출은 check-all 밖에서 소수 Gold 질문 smoke로만 확인한다.
후보 test는 in-memory SQLite의 V1 subset 표로 정형 필터·lifecycle 제외·기간 판정 불가 보존을, Retriever test는 in-memory Qdrant에서 후보 scope 밖 공고가 세 mode 모두에 없는지와 빈 scope의 embedding 생략을,
RAG test는 빈 후보의 NO_CANDIDATES(검색·LLM 미호출)와 scope 위반 거부를 확인한다. 실제 MySQL·Qdrant·LLM 경로는 check-all 밖 smoke로 확인한다.
자연어 필터 test는 가짜 LlmProvider로 허용 값 검증(DB 활성 값 domain, 목록 밖 값 미적용), "지금"의 application 날짜 변환, 지역의 jurisdiction 오매핑 금지, 추출 실패 시 fallback 없는 실패를 확인한다.
목록·분기 test는 in-memory Qdrant로 조각 순위 A,A,B,A,C,D,E가 공고 A~E 한 칸씩이 되는지와 후보 범위 밖 제외를, 가짜 Retriever·SQLite 표로 MySQL 정형 정보·scope 위반·중복 거부·빈 후보 미검색을, router test로 SEARCH_LIST가 답변 LLM 없이 목록을, DOCUMENT_QA가 기존 RagService를 쓰는지 확인한다.
hard filter grounding test는 질문에 없는 category·currently_open·자유 문구가 후보 조건이 되지 않는지 확인한다.
Eligibility test는 가짜 Retriever·LlmProvider로 전부 MET→ELIGIBLE(고정 질의·단일 공고 scope·citation), 값 없는 필드→UNKNOWN·NEEDS_MORE_INFO(추측 MET 되돌림),
NOT_MET→INELIGIBLE, 잘못된 evidence id·다른 공고 evidence·모르는 profile field·허용 밖 result·비활성 공고 거부를 확인한다.
내부 API test는 FastAPI TestClient와 가짜 runtime으로 /health, query의 SEARCH_LIST·DOCUMENT_QA 직렬화(판단 결과 200), eligibility status 무변경,
요청 검증 422·company_profile 422·비활성 공고 404 매핑과 lifespan 종료 시 자원 정리를 확인한다. 실제 서버 HTTP smoke는 check-all 밖에서 한다.

## V1 AI 평가 기준선

`evals/v1_baseline/cases-v1.json` 10건은 V1 종료 시점의 SEARCH_LIST 4건·DOCUMENT_QA 3건·Eligibility 3건을 같은 조건으로 비교하는 작은 기준선이다.
기존 사례와 기대값은 `cases-v1.frozen.json`의 sha256으로 고정하며 결과를 보고 수정하지 않는다. 기준 변경은 기존 파일을 덮지 않고 새 version으로 만든다.
답변 문장 전체 exact match 대신 공고 ID·순위·후보 범위, `(source_sha256, chunk_index)` 근거, citation, 핵심 사실, 자격 상태·핵심 criterion을 판정한다.
응답 시간은 환경 의존 참고값이며 PASS/FAIL에 쓰지 않는다. 실제 Ollama·dev MySQL·dev Qdrant 실행은 check-all 밖에서 명시적으로 1회 수행하고,
고정 fixture hash·판정 helper만 Contract test로 검사한다. 품질 실패를 고치기 위한 prompt tuning이나 반복 LLM 평가는 이 기준선 작업에 포함하지 않는다.
