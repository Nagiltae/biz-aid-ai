# Validation 정책

근거: PROJECT_DESIGN.md §37–41, 46 및 이번 요청의 현재 범위.
실제 검사를 수행한 항목만 PASS로 기록한다. 미구현을 통과로 계산하지 않는다.

## 실행 범위

| 진입점 | 현재 실제 검사 | 미구현 / 미측정 |
| --- | --- | --- |
| setup.sh | Bash·Git·Python >=3.11·Docker Compose >=2, Compose config와 mounts | Java·Node·DB·서비스 health, daemon 접근 |
| check-format.sh | Control/Input의 UTF-8·LF·newline·공백·JSON indent·Git whitespace | 제품 언어 formatter |
| check-lint.sh | Python AST·Bash syntax·JSON key 중복·Shell 실행 권한 | 제품 lint, 정적 타입 검사 |
| check-contract.sh | 로컬 snapshot / report, 실제 sanitized API Fixture·mock HTTP·Raw / secret 보존 Contract tests | Live API 측정·공급자 전체 명세·제품 API·Qdrant 계약 |
| check-integration.sh | CLI snapshot → hash 확인 → 보고서 생성·검증, 실패 종료와 credential 없는 Probe CLI | Live HTTP·문서 본문 Parser·서비스 DB 경계 |
| check-git-tracked.sh | dev / CI ref·미추적 파일·금지 ignore·Profile Secret ignore / 추적 금지·example 추적·index 동기화·최종 status | Push·Merge 권한 강제 |
| check-comments.sh | Python tokenize / AST docstring·Bash comment의 한글 여부 | 주석 WHY의 적절성·누락은 AGY / 사용자 검토 |
| check-harness.sh | 정적 문서 링크·Registry·Skill·명령·실제 module / Compose / CI·Workspace 제어·Review metadata | AGY 독립 Architecture 판단·저자 신원 인증 |
| check-all.sh | 위 검사 전부 실행, 전체 적용 범위 요약 | 제품 Unit·Component·E2E·AI Eval·Build |

0 = 해당 진입점의 **현재 명시된 범위** 통과, 1 = 실패, 2 = CLI 사용 오류.
check-all은 모든 적용 검사를 실행한 후 하나라도 실패하면 1을 반환한다.
제품 검증은 `N/A: 미구현`으로 출력하며 성공 건수에 넣지 않는다.
새 실행 코드·제품 module·service가 생기면 Registry와 검증을 함께 갱신해야 한다.
현재 Registry 밖의 실행 코드·workflow·module은 Harness drift로 실패한다.

## 테스트 단계와 DoD

지금은 로컬 도구 Unit / Contract / Integration을 실행한다.
API Probe는 별도의 명시적인 Local 명령이며 CI에서 실제 요청을 강제하지 않는다.
Probe의 credential_missing 종료 코드 3은 NOT_RUN이며 PASS로 계산하지 않는다.
Profile 격리·fallback 금지·OS 우선·셸 비실행·secret 비노출·prod OS 주입은 임시 합성 설정만 사용한다.
사용자 .env.dev / .env.prod를 fixture로 복사하지 않는다. Offline PASS 이후 현재 dev Live만 명시적으로 실행한다.
제품 Level 1–7(Format / Lint / Unit / Component / Contract / Integration / E2E / AI Eval)과
React→Spring, Spring→FastAPI/MySQL, FastAPI→Qdrant, Pipeline→실 API/Parser 경계는 향후 필수다.
AI Eval은 dev small / main medium / scheduled 또는 release full로 구분할 계획이다.
현재 제품·LLM·gold 데이터가 없어 AI 성능 수치와 비용을 만들지 않는다.

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

Producer 경로 회귀는 reports/codex·reports/agy와 Agent/Task별 Artifact의 non-gating 경계를 검사한다.
Registry/Agent 지침이 반대 Producer 경로로 설정되거나 현재 Codex Task Report가 AGY 경로를 가리키면 FAIL이다.
산출물 디렉터리나 파일이 없어도 통과한다. static anchor·제품 공백/untracked 검사는 그대로 유지한다.
