# Validation 정책

근거: PROJECT_DESIGN.md §37–41, 46 및 이번 요청의 현재 범위.
실제 검사를 수행한 항목만 PASS로 기록한다. 미구현을 통과로 계산하지 않는다.

## 실행 범위

| 진입점 | 현재 실제 검사 | 미구현 / 미측정 |
| --- | --- | --- |
| setup.sh | Bash·Git·Python >=3.11·Docker Compose >=2, Compose config와 mounts | Java·Node·DB·서비스 health, daemon 접근 |
| check-format.sh | UTF-8·LF·newline·공백·JSON indent·Git whitespace | 제품 언어 formatter |
| check-lint.sh | Python AST·Bash syntax·JSON key 중복·Shell 실행 권한 | 제품 lint, 정적 타입 검사 |
| check-contract.sh | 로컬 snapshot / report 계약, 정상·오류 입력 unit / contract tests | 실제 기업마당·제품 API·Qdrant 계약 |
| check-integration.sh | CLI snapshot → hash 확인 → 보고서 생성·검증, 실패 종료 확인 | 실 API·다운로드·Parser·서비스 DB 경계 |
| check-git-tracked.sh | dev / CI ref·미추적 파일·금지 ignore·index와 작업 파일 동기화·최종 status | Push·Merge 권한 강제 |
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
