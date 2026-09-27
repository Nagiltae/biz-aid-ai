# 작업 절차와 Human Review

1. PROJECT_DESIGN.md → AGENTS.md → current-task.md 순으로 범위를 확인한다.
2. Registry에서 필요한 Context / Rules / Skills를 읽는다.
3. 충돌·큰 기술 변경·규칙 완화는 구현 전에 보고한다.
4. dev에서 허용된 변경을 작성하고 관련 Unit / Contract / Integration을 검증한다.
5. check-all 결과와 실패 원인을 External Memory에 기록한다.
6. 실행 결과를 확인하고 Codex Final Report를 작성한다.
7. 신규 파일과 이번 Task에서 수정한 파일을 명시적 경로로 Git index에 반영하고 최종 check-all과 Git 상태를 확인한다.
   기존의 관련 없는 사용자 변경은 stage하거나 되돌리지 않는다.
8. AGY가 별도 Reviewer Report를 작성한다. Codex가 대신 승인하지 않는다.
9. 사용자가 Git Diff / Report를 확인한 뒤 다음 Task·Push·main / op 승격을 결정한다.

CI는 dev Push에 현재 적용 검증을 실행한다. 원격 실행 여부는 로컬 실행과 구분한다.
현재 운영 배포 workflow는 없다. 미래 자동 배포 trigger는 op Merge로 유지한다.

## Static Harness / Dynamic Workspace / Artifact

- `required_files`는 정적 규칙·계약·실행 구조와 current-task, 기존 Workspace README의 개별 필수 목록이다.
  이 영역의 새 파일·누락은 기존처럼 Registry Drift로 실패한다.
- `dynamic_paths`는 `harness/workspace/reports/*.md`, `harness/workspace/checkpoints/*.md`다.
  바로 아래 Markdown 일반 파일만 허용하며 symlink·실행 권한·하위 디렉터리·실행 코드는 금지한다.
  Git 추적과 ignore 금지를 check-harness / check-git-tracked에서 확인한다.
  개별 Report·Checkpoint를 required_files에 추가하지 않는다. 기존 고정 README는 required_files에 유지한다.
- artifacts의 재생성 log / JSON과 data 원문은 기존 ignore 정책을 따른다.
  코드·규칙·최종 해석 Markdown Report를 Artifact 영역에 숨기지 않는다.

일반 Report의 안전한 존재는 Trusted Review Evidence 승인이 아니다.
특정 Report를 실제 Lifecycle Evidence로 쓸 때만 사용자 확인된 ACCEPTED_AGY_REVIEWS 기준과
원문 checksum·검토 대상 checksum·관계·판정을 검증한다. 파일 추가만으로 Review 상태를 바꾸지 않는다.

## 최종 Validation 순서

작업 → Test / Validation → 결과 확인 → Final Report → 최종 Git index 구성 → check-all PASS → 추적 파일 변경 금지.
최종 실행 전 format / lint / contract / integration / comments / harness / git-tracked를 각각 실행한다.
이후 git status, git diff --cached --stat, git diff --cached --check,
git ls-files --others --exclude-standard로 최종 상태를 확인한다.
최종 Validation 이후 추적 파일이나 새 프로젝트 파일이 바뀌면 기존 결과는 Final 결과가 아니다.
Git 상태를 다시 구성하고 최종 Validation을 재실행한다. Report는 최종 실행 전 작성하며,
작성 시점에 실제 실행한 결과와 이후 최종 실행 절차를 구분한다. 동결 후 결과는 ignored 실행 로그와 최종 응답으로 전달한다.

## current-task 상태 전환

`current-task.md`는 승인된 현재 Task 하나를 나타낸다. Phase 전체를 자동 진행하는 큐가 아니다.

| 시점 | 기록과 전환 |
| --- | --- |
| 새 Task 승인 / 시작 | 이전 current-task 내용과 완료·미완료 항목을 Report에 보존한 뒤 목표·범위·Acceptance·Read First·Validation·Expected Report로 교체 |
| 작업 진행 | current-task의 진행 상태를 갱신하고 장시간 작업은 [Checkpoint 규칙](../workspace/checkpoints/README.md)에 따라 기록 |
| 작업 종료 | Final Report에 변경 목록·실행 결과·남은 문제를 기록하고 current-task를 검토 대기 상태로 유지 |
| 다음 Task 승인 | 이전 Final Report·Review·최신 checkpoint를 링크하고 Registry의 report를 새 Task 보고서로 교체 |

Codex가 작업 구현 상태를 갱신할 수 있으나 Human Review 승인·다음 Task 승인·AGY 판정을 만들 수 없다.
Expected Report는 [Final Report]라는 label의 로컬 Markdown 링크 하나로 지정하고 Registry.report와 일치시킨다.
check-harness는 이 연결을 검사해 과거 Report를 현재 Task의 Review 대상으로 잘못 사용하는 것을 막는다.
진행 중 Session 교체는 current-task와 최신 checkpoint에서 재개한다.
Task 전환은 현재 사용자의 요청과 저장된 Report로 확인하며 Agent 내부 Memory만으로 결정하지 않는다.
Task 교체 전 상태는 해당 새 Task의 Final Report에 보존한다.

## AGY Review Lifecycle / Evidence

상태는 `pending`과 `review_complete` 두 가지다.
`registry.json.agy_review`는 가장 최근에 수신한 독립 Review의 상태,
`agy_review_evidence`는 그 원문 경로다.
Review 완료는 승인 판정이 아니다. PASS / PASS WITH FIXES / FAIL은 독립 원문의 결과로 별도 보존한다.

| 상태 / 전환 | 권한과 필요한 Evidence |
| --- | --- |
| pending | 해당 Review를 아직 받지 않은 상태. evidence=null |
| pending → review_complete | AGY가 작성하고 사용자가 독립 결과로 확인한 Report가 필요 |
| 새 검토 주기 → pending | 사용자가 새 검토 범위를 승인한 Task에서 전환. 기존 Review 원문·결과는 보존 |
| review_complete 갱신 | 새로운 독립 Report를 AGY / 사용자가 확인한 뒤 별도 Task에서 증거 기준을 추가 |

AGY / 사용자가 판정과 완료를 결정한다. Codex는 명시된 독립 Evidence에 맞는 상태 동기화만 수행한다.
Codex 작업 Report나 Reviewer / COMPLETE 문구만으로 상태를 전환하지 않는다.

현재 사용자가 제공·확인한 [Initial Review](../workspace/reports/agy-initial-harness-review.md)와
[Targeted Re-review](../workspace/reports/agy-harness-fix-review.md)를
`scripts/lib/validate.py`의 ACCEPTED_AGY_REVIEWS에 원문 SHA-256·검토 대상 Report SHA-256·결과로 고정했다.
check-harness는 Evidence 경로가 그 기준에 있는지, 원문과 검토 대상이 안전한 Git 추적 Dynamic Workspace 파일인지,
symlink가 아닌지, byte가 기준과 일치하는지를 검사한다.
Registry 값이나 자기 Report의 hash만 변경해서는 통과할 수 없다.
새 증거 기준은 사용자 승인 Task에서만 추가하며 Codex가 Review 원문을 작성·편집해 등록하지 않는다.

Hash는 원문 무결성을 확인하며 저자의 신원을 서명으로 인증하지는 않는다.
현재 독립성의 근거는 사용자에게서 전달된 AGY 원문과 사용자 확인, 변경 내역의 Human Review다.
서명·외부 인증 시스템은 도입하지 않는다.

Initial Review 결과는 **PASS WITH FIXES**이며 이전 Foundation Report에 한정한다.
Targeted Re-review는 보완 Report에 대한 **PASS**로 완료됐다. 최신 Evidence는 이 독립 원문이다.
현재 Dynamic Workspace 수정 Report는 검토 대상이 달라 CURRENT REPORT REVIEW가 pending이다.
보완 구현과 check-all 통과만으로 과거 결과를 바꾸거나 현재 Task / Human Review를 승인하지 않는다.
Human Review는 AGY 원문·Codex Report·최종 Validation·Git Diff를 대조해 다음 Task를 판단한다.
