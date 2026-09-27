# Codex Harness Fix Report — 2026-09-27

범위: Initial Harness Review 보완. 제품 기능·실제 Data Gate 측정은 수행하지 않았다.
진행 상태: 보완 구현·현재 적용 Validation 통과, 사용자 검토 대기.
독립 Initial Review: PASS WITH FIXES / review_complete.
이번 보완의 후속 AGY Review·Human Review·Data Gate: pending.

## 1. AGY Finding별 처리 결과

| Finding | 수용 / 미수용 | 처리 결과와 이유 |
| --- | --- | --- |
| M-1 Skill 구조 | 수용 | 5개 Skill에 추가 workflow/reference 불필요를 명시. data-pipeline-change는 기존 측정 절차만 유지. Architecture에 Target / 현재 구조 구분 |
| M-2 WHY 주석 | 수용 | Compose 권한·ignore 경계·Registry drift·AGENTS 크기·독립 증거·Raw hash·출력 충돌의 이유를 한글로 보강 |
| M-3 Checkpoint | 수용 | 최소 Format과 생성·갱신·완료·Stage 집계·Resume / Recovery 정의. 실제 Collector나 수집 checkpoint 생성 없음 |
| M-4 환경변수 준비 | 조건부 수용 / 명세 전 변수 추가 미수용 | .env.example은 원문 유지. 공식 명세와 API Contract 확정 후 별도 Task에서 변수 추가. 추정 이름을 추가하지 않으라는 사용자 지시 적용 |
| M-5 Gate 확장 | 수용 / 현재 go/drop 허용 미수용 | pending-only 계약 유지. 측정 → Evidence → Human Review → Contract Task → Tests / Validation → 기록 절차 문서화 |
| I-1 개발 방식 baseline | 정보 확인 / 수치 생성 보류 | 실제 독립 Review를 증거로 보존한다. 비교 Task·측정값이 없어 성공률·시간·token·비용 개선값을 만들지 않음 |
| I-2 Docker smoke ignore | 현 정책 수용 / CI smoke 추가 보류 | 재생성 JSON/log는 ignore, 해석은 추적 Report. 이번 Task에서 새로운 CI Docker 실행을 추가하지 않음 |
| I-3 과거 API 확인 재현 | 수용 / 과거 서술을 측정으로 재사용하지 않음 | 설계 원문 보존. 실제 endpoint·응답 증거는 다음 Gate Task의 선행 조건 |
| I-4 current-task 전환 | 수용 | 사용자 요청으로 이전 Task 상태를 이 Report에 보존하고 current-task를 보완 Task로 교체 |
| 추가: AGY 상태 전환 | 수용 | pending / review_complete Lifecycle, 고정된 독립 원문·검토 대상 checksum과 현재 Task의 Report 연결 검증 |

CRITICAL / MAJOR Finding은 없었다. 모든 MINOR의 현재 범위 보완을 수용했다.
미수용·보류한 것은 추정 환경변수·즉시 Gate 확장·새 CI 실행·측정 없는 평가 수치다.

## 2. 생성 파일

- [2026-09-27-codex-harness-fix-report.md](2026-09-27-codex-harness-fix-report.md): 이번 보완·검증·이전 Task를 보존하는 Final Report.
- 기존 [agy-initial-harness-review.md](agy-initial-harness-review.md)는 사용자 / AGY 제공 파일이며
  Codex가 생성·수정하지 않았다. Registry 등록과 Git 추적만 추가한다.
- 추가 workflow/reference·빈 디렉터리·제품 파일 생성 없음.
- 재생성 가능한 Validation·Git Diff log는 artifacts/에 저장하고 Git에서는 제외한다.

## 3. 수정 파일

이번 요청 시작 시 Git index / working tree를 기준으로 다음 25개 파일을 수정했다.
최초 commit이 없으므로 최종 cached Diff에서는 이 파일들이 신규 A로 표시된다.

- [.gitignore](../../../.gitignore)
- [AGENTS.md](../../../AGENTS.md)
- [README.md](../../../README.md)
- [contracts/README.md](../../../contracts/README.md)
- [harness/agents/agy-reviewer.md](../../../harness/agents/agy-reviewer.md)
- [harness/agents/codex-developer.md](../../../harness/agents/codex-developer.md)
- [harness/changelog/harness-changes.md](../../../harness/changelog/harness-changes.md)
- [harness/docs/architecture.md](../../../harness/docs/architecture.md)
- [harness/docs/testing.md](../../../harness/docs/testing.md)
- [harness/docs/workflow.md](../../../harness/docs/workflow.md)
- [harness/registry.json](../../../harness/registry.json)
- [harness/skills/api-contract-change/SKILL.md](../../../harness/skills/api-contract-change/SKILL.md)
- [harness/skills/data-pipeline-change/SKILL.md](../../../harness/skills/data-pipeline-change/SKILL.md)
- [harness/skills/database-migration/SKILL.md](../../../harness/skills/database-migration/SKILL.md)
- [harness/skills/debugging/SKILL.md](../../../harness/skills/debugging/SKILL.md)
- [harness/skills/feature-development/SKILL.md](../../../harness/skills/feature-development/SKILL.md)
- [harness/skills/rag-change/SKILL.md](../../../harness/skills/rag-change/SKILL.md)
- [harness/workspace/checkpoints/README.md](../../../harness/workspace/checkpoints/README.md)
- [harness/workspace/current-task.md](../../../harness/workspace/current-task.md)
- [scripts/check-all.sh](../../../scripts/check-all.sh)
- [scripts/lib/validate.py](../../../scripts/lib/validate.py)
- [scripts/phase0.py](../../../scripts/phase0.py)
- [tests/README.md](../../../tests/README.md)
- [tests/contract/test_harness_policy.py](../../../tests/contract/test_harness_policy.py)
- [tests/contract/test_phase0.py](../../../tests/contract/test_phase0.py)

| 변경 범위 | 이유 |
| --- | --- |
| scripts/phase0.py | Raw·checksum·시각·overwrite의 기존 설계 이유 설명. 동작 변경 없음 |
| scripts/lib/validate.py | WHY 주석, 독립 Review Lifecycle·Evidence / 범위·current-task 연결 검증 |
| scripts/check-all.sh | 오래된 AGY pending 고정 출력 제거, 실제 상태는 check-harness 결과로 안내 |
| .gitignore | 작업 중 IDE가 생성한 .idea metadata를 제외. 문서·코드 숨김은 verifier가 거부 |
| AGENTS / README / Architecture / Agent docs | 현재 Review 결과·Target 구조·routing·후속 pending 상태 동기화 |
| Workflow / Checkpoint / contracts README | 상태 전환·복원·계약 확장의 실행 가능한 절차 정의 |
| 6개 SKILL.md | 별도 하위 문서가 필요한 경우와 필요하지 않은 경우를 명확히 표시 |
| Registry / Changelog | 활성 Task·보고서·독립 Review 증거와 승인된 변경 이유 등록 |
| tests / 테스트 README | Lifecycle 공격·변조·scope mismatch·IDE 숨김 회귀 및 go/drop 거부 검증 |

## 4. 삭제 파일

없음. 기존 원문·Review·데이터·IDE metadata를 삭제하거나 덮어쓰지 않았다.
최상위 설계, 이전 Codex Report, AGY Review, .env.example, Gate 계약은 원문을 보존한다.

## 5. 주석 보강 위치와 이유

| 파일 / 함수 | 설명한 WHY / BOUNDARY / EXCEPTION / RISK |
| --- | --- |
| validate.py / ACCEPTED_AGY_REVIEWS | 사용자가 전달·확인한 독립 원문만 고정 기준으로 삼아 자기 Report를 승인 증거로 쓰지 못하게 함 |
| validate.py / compose | 로컬 Batch의 외부 호출·내부 쓰기 차단, repository read-only와 결과 쓰기 경계 |
| validate.py / allowed_ignored | IDE·credential·payload·재생성 결과는 제외하되 코드·규칙·해석 Report는 추적 |
| validate.py / review_status | 이름·COMPLETE 문구로 저자를 증명할 수 없어 원문과 검토 대상 hash를 대조, 이전 Review를 현재 변경 승인으로 재사용하지 않음 |
| validate.py / harness_check | Registry 밖 파일의 검증 누락 방지, 활성 Report 연결, AGENTS가 거대한 설명서가 되는 것을 방지 |
| phase0.py / validate_metadata | 미확인 API 수집 시각을 파일 보존 시각으로 대체하지 않음 |
| phase0.py / verify_snapshot | 파싱 가능 여부와 무관하게 byte 변경은 재현 근거 손실이므로 크기·hash를 함께 확인 |
| phase0.py / write_json, snapshot | 출력 충돌은 실패, metadata 저장 실패 시 이미 보존한 Raw는 복구 근거로 남김 |
| phase0.py / validate_report | 보고서 형식 검증과 Human Gate 판단의 책임 분리 |

주석 수를 DoD나 품질 점수로 쓰지 않는다. 코드 동작 번역 주석을 추가하지 않았다.

## 6. Checkpoint 설계

[Checkpoint 규칙](../checkpoints/README.md)에 run_id, task, started_at, updated_at, total_target,
completed_count, failed_count, failed_items, current_stage, last_processed_item, next_action,
resume_command, notes 및 status를 정의했다.
순번별 Markdown을 보존하고 성공·실패 item을 중복 없이 현재 Stage 단위로 집계한다.
입력·원문 checksum·마지막 확정 item을 대조한 후 현재 구현된 안전한 명령으로만 재개한다.
완료는 Final Report 보존과 추가 동작 없음이며, 실패 측정이나 Data Gate GO를 대신하지 않는다.
예시는 합성 Format이며 실제 수집 증거가 아니다.

## 7. Gate Contract 전환 절차

[Contracts](../../../contracts/README.md): 실제 측정 완료 → Evidence 검토 → Human Review →
승인된 별도 Contract Task → gate_decisions·필드·호환성 정의 → 정상/오류 Tests →
Contract / Integration / Harness / check-all → Report / Changelog / Diff.
현재 gate_decisions=["pending"]을 유지한다. Codex 자동 GO/DROP은 금지한다.

## 8. current-task 전환 절차

[Workflow](../../docs/workflow.md): 새 Task 승인 → 이전 내용을 Report에 보존 → current-task 교체 →
진행 상태 / Checkpoint → Final Report → 검토 대기 → 다음 Task 승인.
Expected Report는 단일 Final Report 링크이며 Registry.report와 일치해야 한다.
이번 보완 요청으로 Task를 전환했고 이전 상태는 아래 §10에 보존했다.
사용자 확인 전 API 수집 Task로 자동 전환하지 않는다.

## 9. AGY Review Lifecycle 설계

- 상태: pending / review_complete. 완료와 판정은 별개다.
- 권한: AGY / 사용자가 판단, Codex는 사용자에게서 확인한 독립 Evidence에 맞는 동기화만 수행.
- Evidence: 사용자가 이번 요청에서 제공·확인한 AGY Initial 원문과 이전 Codex 검토 대상의 SHA-256을
  ACCEPTED_AGY_REVIEWS에 고정했다. Registry 경로·자기 checksum만 바꿔서는 통과하지 않는다.
- 검증: 미지원 상태·누락·변조·symlink·자기 Report·current-task / Registry report mismatch를 거부.
- 결과: Initial은 PASS WITH FIXES / review_complete. 이번 보완은 검토 대상이 달라 후속 Review pending.
- Human Review: 독립 원문·수정 처리·검증·Git Diff를 비교해 다음 Task 여부를 사용자가 결정.
- 한계: hash는 원문 무결성 확인이며 서명에 의한 저자 인증은 아니다.
  사용자 제공·확인과 변경 내역 검토가 현재 신뢰 기준이다. 새 외부 인증 기술은 도입하지 않는다.
- 새 Review 증거 기준 추가와 재검토 주기 시작은 사용자 승인 Task에서만 수행한다.
  Codex가 AGY 원문이나 결과를 만들어 등록할 수 없다.

## 10. 이전 current-task 보존

아래는 보완 요청 시작 직전의 전체 Task 기록이다.
과거 pending·27/4개 테스트 수는 당시 상태이며 최신 결과는 이 Report의 §13을 따른다.
문서 링크의 상대 경로는 당시 current-task 위치 기준으로 보존했다.

```markdown
# Current Task

## Goal / Context

Harness Engineering 기반과 Phase 0 Data Feasibility Gate 최소 환경 구축.
PROJECT_DESIGN.md가 최상위 설계다. 실제 Gate 측정은 다음 별도 작업이다.
상태: 준비 범위 구현·로컬 검증 통과, 사용자 검토 대기.
AGY: pending. Human review: pending. Data Feasibility Gate: pending.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) → [Architecture](../docs/architecture.md) →
[Git 정책](../rules/git-policy.md) → 작업별 Skill.

## Allowed Scope / Requirements

Harness docs·agents·skills·rules·registry·workspace·evals·changelog,
contracts, scripts, tests, evals, infra, CI, Compose Phase 0 Batch, data 저장 정책.
한글 설명성 주석, 실제 실패를 반환하는 검증, 원문 보존,
생성/수정/삭제 목록과 이유 및 validation 증거를 남긴다.

## Forbidden Scope / Non-goals

React·Spring Boot·FastAPI 기능, 전체 Data Pipeline, DB·Migration,
RAG·LangGraph·Indexing·회원·운영 배포, 임의 Push·Merge·branch 삭제.
API 100건 수집·Parser 선택·GO / DROP 판단을 이번에 수행하지 않는다.

## Acceptance Criteria / Required Tests

문서 Registry와 실행 파일 일치, 로컬 원문 무결성과 보고서 계약의 정상/오류 검증,
CLI Integration, Git 추적·ignore·CI·주석·Harness drift 검사.
제품 미구현 검증과 AGY 미실행 상태를 명시한다.

## Validation Command / Expected Report

`./scripts/setup.sh`, `./scripts/check-all.sh`.
[Codex 작업 Report](reports/2026-09-27-codex-harness-report.md).
검증 결과·남은 문제·다음 작업은 보고서에 동기화한다.

## 완료 내용 / 남은 문제 / 다음 작업

Harness Registry·문서·규칙·6개 Skill·9개 Validation 진입점·dev CI,
로컬 Raw snapshot / report 도구와 Compose Batch를 구축했다.
check-all 통과, Unit / Contract / Harness 27개와 CLI Integration 4개 통과.
실제 데이터 100건·다운로드·Parsing·RAG 가치·자동화는 미측정이다.
AGY 검토 후 실제 명세·응답과 주요 field·분모·표본·근거 위치 기준을 확정한다.
```

## 11. 추가 / 수정한 Tests

- tests/contract/test_harness_policy.py: 독립 Initial 증거 정상 인정과 현재 보완 pending,
  새 주기 pending, 상태/증거 불일치, 미지원 상태, 증거 없음, Codex 자기 Report,
  원문 누락·위조·검토 대상 변조·외부 symlink, 과거 Report 연결, IDE 문서·코드 숨김.
- tests/contract/test_phase0.py: 준비 단계 Gate 거부를 go와 drop 양쪽으로 검증.
- 기존 원문 byte·checksum·overwrite와 CLI Integration을 그대로 재실행한다.
- 실제 API·Parser·제품·DB·LLM·RAG 테스트는 이번 대상이 아니다.

## 12. 실행한 Validation

아래 명령을 로컬에서 각각 실제 실행했고 check-all로 전체 적용 범위를 다시 검증했다.
초기 check-format은 IDE가 새로 생성한 .idea/biz-aid-ai.iml의 newline 형식 때문에 exit 1이었다.
이 파일은 제품 파일이 아니라 로컬 IDE metadata이므로 ignore를 추가하고,
같은 경로에 코드·Report가 숨겨지면 실패하는 테스트를 추가했다.

| 실제 명령 | 결과 |
| --- | --- |
| ./scripts/check-format.sh | 최종 PASS / exit 0 |
| ./scripts/check-lint.sh | PASS / exit 0 |
| ./scripts/check-contract.sh | PASS / exit 0, 39 tests |
| ./scripts/check-integration.sh | PASS / exit 0, 4 tests |
| ./scripts/check-comments.sh | PASS / exit 0, 26개 한글 설명성 주석 확인 |
| ./scripts/check-harness.sh | PASS / exit 0, 독립 증거와 현재 Report 범위 검사 |
| ./scripts/check-git-tracked.sh | PASS / exit 0 |
| ./scripts/check-all.sh | PASS / exit 0, setup 포함 모든 현재 적용 검사 |
| skill-creator quick_validate.py | 6개 Skill 모두 Skill is valid |
| git status | dev, No commits yet, 모든 프로젝트 파일 index에 반영 |
| git diff --cached --stat | 총 69개 staged 경로 |
| git diff --cached | 전체 Diff 확인·로컬 log 보존, Task의 코드 Diff 별도 확인 |
| git ls-files --others --exclude-standard | 출력 없음 / 프로젝트 Untracked 0개 |
| 보존 파일 SHA-256 비교 | 설계·이전 Codex Report·AGY 원문·.env.example 모두 시작 시 byte와 일치 |

전체 적용 Validation 로그: harness/workspace/artifacts/2026-09-27-harness-fix-check-all.log.
전체 cached Diff: harness/workspace/artifacts/2026-09-27-harness-fix-cached-diff.log.
구현 시점의 기존 index 대비 변경 Diff: harness/workspace/artifacts/2026-09-27-harness-fix-incremental.log.
원격 GitHub Actions·AGY 후속 검토·제품 / 실제 데이터 검증은 실행하지 않았다.

## 13. Validation 결과

39개 Unit / Contract / Harness와 4개 CLI Integration이 통과했다.
Lifecycle·증거·현재 Task scope의 정상/실패 사례를 실제 격리 Git 저장소에서 검증했다.
Initial Review는 review_complete / pass_with_fixes이며 검토 대상은 이전 Foundation Report다.
현재 보완 Report의 후속 AGY Review·Human Review·Data Gate는 pending이다.
제품 API·실 API 수집·다운로드·Parser·DB·E2E·AI Evaluation·Build는 N/A이며 PASS로 계산하지 않았다.
초기 IDE format 실패는 로컬 metadata 정책으로 해결했으며 최종 Validation에 남은 실패는 없다.
Gate 계약의 pending-only 제약과 환경변수 무추정 정책은 유지했다.

## 14. 남아 있는 미결정 사항

공식 API endpoint·인증·응답 envelope·pagination·field mapping,
주요 field와 Null/blank/invalid 정의, 각 성공률의 분모, 최근 100건 선택,
HWP/HWPX 근거 위치·표 품질 기준은 이전 기록대로 미결정이다.
이번 보완으로 실제 수집·Parsing·RAG 가치·자동화가 검증된 것은 아니다.
AGY 후속 검토와 사용자 판단, 다음 Phase 0 Task 승인이 필요하다.

## 15. 다음 검토와 Git 상태

이번 Task는 dev에서만 수행한다. Commit·Push·Merge·프로젝트 Branch 변경 없음.
AGY가 보완 결과와 Evidence / 상태 전환 범위를 검토하고 사용자가 Diff로 다음 Task를 판단한다.
최종 프로젝트 Untracked 0개, 새 Report 1개와 사용자 제공 AGY Review 1개를 Git 추적에 추가했다.
이전 67개 경로와 합쳐 총 69개 staged 경로이며, 이번 Task는 기존 파일 25개를 수정했다.
프로젝트 Branch는 dev이며 Commit·Push·Merge·Branch 변경 없음.
Git index 반영은 파일시스템 .git 읽기 전용 제약으로 승인된 git add 권한을 사용했다.
