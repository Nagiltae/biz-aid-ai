# Validation 정책

근거: PROJECT_DESIGN.md §37–41, 46 및 이번 요청의 현재 범위.
실제 검사를 수행한 항목만 PASS로 기록한다. 미구현을 통과로 계산하지 않는다.

## 실행 범위

| 진입점 | 현재 실제 검사 | 미구현 / 미측정 |
| --- | --- | --- |
| setup.sh | Bash·Git·Python >=3.11·Docker Compose >=2, Compose config와 mounts | Java·Node·DB·서비스 health, daemon 접근 |
| check-format.sh | UTF-8·LF·newline·공백·JSON indent·Git whitespace | 제품 언어 formatter |
| check-lint.sh | Python AST·Bash syntax·JSON key 중복·Shell 실행 권한 | 제품 lint, 정적 타입 검사 |
| check-contract.sh | 로컬 snapshot / report, 실제 sanitized API Fixture·mock HTTP·Raw / secret 보존 Contract tests | Live API 측정·공급자 전체 명세·제품 API·Qdrant 계약 |
| check-integration.sh | CLI snapshot → hash 확인 → 보고서 생성·검증, 실패 종료와 credential 없는 Probe CLI | Live HTTP·문서 본문 Parser·서비스 DB 경계 |
| check-git-tracked.sh | dev / CI ref·미추적 파일·금지 ignore·Profile Secret ignore / 추적 금지·example 추적·index 동기화·최종 status | Push·Merge 권한 강제 |
| check-comments.sh | Python tokenize / AST docstring·Bash comment의 한글 여부 | 주석 WHY의 적절성·누락은 AGY / 사용자 검토 |
| check-harness.sh | 문서 링크·Registry·Skill·명령·실제 module / Compose / CI·workspace·보고서·독립 Review 증거와 검토 범위 | AGY 독립 Architecture 판단·저자 신원 인증 |
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
고정된 사용자 제공 AGY 원문·검토 대상 checksum을 대조하며,
누락·변조·symlink·자기 Report·미지원 상태와 현재 Report의 검토 범위를 실패/대기로 검증한다.
보고서, 실제 validation 결과, Git Diff, 미추적 프로젝트 파일 없음이 이번 작업의 DoD다.

API 품질 Batch는 고정 5×20 계획·중복·MISSING/NULL/BLANK/INVALID·기간·확장자·부분 실패·재현/Raw checksum을 오프라인으로 검증한다.
명시적인 Negative Probe만 03 NODATA_ERROR를 EXPECTED_NO_DATA로 분류하고 Positive Probe / Batch의 같은 결과는 API_ERROR다.
Live Batch는 전체 Offline Validation PASS 이후 dev에서만 별도 실행한다. 제품·문서 Gate와 공식 정렬 보장 검증은 포함하지 않는다.

문서 Gate는 임시 파일 / mock stream으로 순차 100개 계획·HTTP 오류·Redirect·크기·형식·중복·checksum·Partial/Resume·Checkpoint·Secret 경계를 검사한다.
CI는 실제 파일 HTTP를 호출하지 않는다. Offline 전체 PASS 뒤 dev 다운로드를 별도 명령으로 수행한다.
SYNTHETIC_MOCK와 LIVE_HTTP Evidence를 구분하고 다운로드 성공을 본문 Parsing 성공으로 계산하지 않는다.
