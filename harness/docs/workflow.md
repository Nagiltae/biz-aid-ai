# 작업 절차와 Human Review

1. AGENTS.md → current-task.md → Registry와 관련 Rule / Skill / Contract 순으로 범위를 확인한다. 현재 구현은 production code·Harness·PROJECT_MASTER_GUIDE를 기준으로 하고 PROJECT_DESIGN.md는 최초 목표와 배경으로 읽는다.
2. Registry에서 필요한 Context / Rules / Skills를 읽는다.
3. 충돌·큰 기술 변경·규칙 완화는 구현 전에 보고한다.
4. dev에서 허용된 변경을 작성하고 관련 Unit / Contract / Integration을 검증한다.
5. 신규·수정 Control/Input 자산만 명시적 경로로 Git index에 반영한다. 관련 없는 사용자 변경은 보존한다.
6. 최종 check-all의 exit result와 Git 상태를 확인한다. 실패는 이후 생성물로 덮어 성공 처리하지 않는다.
7. 실제 결과를 Generated Report / Artifact에 기록한다. 생성물 작성·갱신 때문에 검증을 다시 실행하지 않는다.
8. AGY가 독립 검토하고 별도 Generated Review Report를 작성한다. 개발 Producer가 대신 승인하지 않는다.
9. 사용자가 Git Diff / Report를 확인한 뒤 다음 Task·Push·main / prod 승격을 결정한다.

CI는 dev Push에 현재 적용 검증을 실행한다. 원격 실행 여부는 로컬 실행과 구분한다.
현재 운영 배포 workflow는 없다. 미래 자동 배포 trigger는 prod Merge로 유지한다.

## Workspace Control/Input / Generated Output(관리 문서와 생성 산출물 구분)

고정 입력은 current-task와 재사용 실행 코드 regression-set/run.py, artifacts/README.md·checkpoints/README.md다.
Registry.workspace_static_files는 이 anchor의 역할을 선언하고 required_files는 개별 strict 구조를 관리한다.

| 분류 | 현재 경계 | Validation / Git |
| --- | --- | --- |
| STATIC_CONTROL | harness/workspace/current-task.md, artifacts/development/regression-set/run.py | format·tracking·link/scope·Registry strict |
| STATIC_DOCUMENTATION | artifacts/README.md, checkpoints/README.md | format·tracking·links·Registry strict |
| GENERATED_REPORT | reports/**/*.md | non-gating, 신규 파일 ignore |
| GENERATED_CHECKPOINT | checkpoints/**/*.md 중 고정 README 제외 | non-gating, 신규 파일 ignore |
| GENERATED_ARTIFACT | artifacts/**/*.json / **/*.log, OS .DS_Store | non-gating, ignore |

생성물의 존재·부재·format·trailing whitespace·untracked·ignored·unstaged·index 미등록은
제품 Validation의 PASS/FAIL에 영향을 주지 않는다. 검증 명령 자체의 실패 exit는 그대로 실패다.
기존 committed Report / Checkpoint는 삭제·강제 untrack·history rewrite하지 않는다.
HEAD에 없는 staged 생성물은 사용자 승인 범위에서 index만 제거하고 로컬 원문을 보존한다.
새 산출물은 Git 추적을 요구하지 않으며 공유·보존은 사용자 관리 작업이다.

workspace 전체를 제외하지 않는다. .py/.sh/SQL/설정 등 코드와 미분류 입력은 생성물로 인정하지 않으며
제품·Rule·Skill·CI·정적 문서를 ignore로 숨기면 실패한다. 정적 template / 새 입력을 도입하면 anchor와 Registry를 명시한다.
생성물 symlink·실행 권한·내용은 build에서 따라가거나 실행하지 않는다. 신뢰 근거로 쓸 때는 별도 안전·무결성 확인이 필요하다.

### Task 역할별 보관

Codex와 Claude의 공동 Task Report는 reports/development/, 개발 Artifact는 artifacts/development/<task-id>/에 작성한다.
AGY Review는 reports/agy/, Review Artifact는 artifacts/agy/<review-id>/에 둔다.
두 개발 Producer는 같은 Report를 이어서 갱신하며 handoff 때문에 Registry·current-task·Harness 설정을 바꾸지 않는다.
contributors / finalized_by는 작업 이력일 뿐 Review 권한이 아니다. 안정적인 Task 이름과 실행별 run-id를 구분한다.
Registry.task_output_paths와 Agent 지침은 정적 계약으로 검증하며 출력 디렉터리·파일의 존재는 요구하지 않는다.
역사적인 root 경로도 기존 Generated 분류를 유지하지만 새 산출물의 기본 위치로 사용하지 않는다.

보관 정리는 Inventory / Reference Graph → KEEP·MOVE·DELETE·UNCLASSIFIED 판정 → 명시적 파일 목록으로 수행한다.
Final Report·Review·Validation·Preservation·accepted evidence·live 참조는 보존한다.
참조 없는 중간 산출물만 Final Evidence로 완전히 대체됐고 Phase audit에 필요하지 않을 때 삭제한다.
producer를 확인할 수 없는 파일은 보존하고 사용자 판단을 받는다. checkpoints는 별도 run/resume 영역이다.
tracked historical Report는 git mv, ignored 파일은 filesystem move로 원문을 그대로 옮긴다.
static 참조와 accepted mapping의 경로만 갱신하며 checksum·verdict·승인 상태는 바꾸지 않는다.
과거 Generated Report 내부 링크는 수정하지 않고 cleanup manifest의 old/new relocation mapping으로 해석한다.
cleanup manifest / reference graph의 역사적 Codex 경로는 보존하며 새 Task 산출물은 공동 development 경로를 사용한다.

## Improvement Backlog

기능 진행을 위해 관찰된 non-blocking 문제를 의도적으로 미루면 [Improvement Backlog](improvement-backlog.md)에 Evidence와 Revisit trigger를 기록한다.
기록 전에 같은 문제가 있는지 확인하고, 있으면 새 ID 대신 Evidence·Revisit만 갱신한다. 정상적인 다음 기능이나 근거 없는 아이디어는 넣지 않는다.
해결하면 삭제하지 않고 RESOLVED와 근거 report를, 시도 후 가치가 없으면 DROPPED와 이유를 남긴다.

## 최종 Validation 순서

작업 → Control/Input·Git index 확정 → Test / 최종 check-all → 실제 exit 결과 확인 → Generated Report / Artifact → AGY / 사용자 검토.
최종 실행에는 format / lint / contract / integration / comments / harness / git-tracked를 각각 실행한다.
git status, git diff --cached --stat와 입력 자산의 Git whitespace / untracked 경계를 확인한다.
원시 git diff --check는 역사적인 Generated Report 공백을 표시할 수 있으므로 그 전체 결과를 build 승인으로 사용하지 않는다.
check-format이 생성물을 제외한 입력 자산의 Git diff를 검사한다.

최종 Validation 이후 **Control/Input**이 바뀌면 결과를 최종 근거로 재사용하지 않고 검증을 다시 실행한다.
Generated Output만 작성·갱신됐으면 기존 제품 검증 결과는 유효하다. Report를 고치기 위한 재검증 순환을 만들지 않는다.
Report에는 실제 실행 결과를 쓰며 미래 실행이나 Mock을 실제 PASS / Live Evidence로 기록하지 않는다.

## current-task 상태 전환

`current-task.md`는 승인된 현재 Task 하나를 나타낸다. Phase 전체를 자동 진행하는 큐가 아니다.

| 시점 | 기록과 전환 |
| --- | --- |
| 새 Task 승인 / 시작 | 이전 current-task 내용과 완료·미완료 항목을 Report에 보존한 뒤 목표·범위·Acceptance·Read First·Validation·Expected Report로 교체 |
| 작업 진행 | current-task의 진행 상태를 갱신하고 장시간 작업은 [Checkpoint 규칙](../workspace/checkpoints/README.md)에 따라 기록 |
| 작업 종료 | current-task를 검토 대기 상태로 확정하고 검증한 뒤 Generated Report에 결과 기록. 생성물만 추가되면 재검증 없음 |
| 다음 Task 승인 | 이전 Final Report·Review·최신 checkpoint를 링크하고 Registry의 report를 새 Task 보고서로 교체 |

개발 Producer가 작업 구현 상태를 갱신할 수 있으나 Human Review 승인·다음 Task 승인·AGY 판정을 만들 수 없다.
Expected Report는 [Final Report]라는 label의 로컬 Markdown 링크 하나로 지정하고 Registry.report와 일치시킨다.
check-harness는 이 참조의 경로와 Registry 일치를 검사한다. Report 파일의 존재·내용·추적 상태를 요구하지 않는다.
진행 중 Session 교체는 current-task와 최신 checkpoint에서 재개한다.
Codex ↔ Claude handoff도 같은 복원 절차를 사용하며 제어 파일의 Producer identity를 전환하지 않는다.
Task 전환은 현재 사용자의 요청과 저장된 Report로 확인하며 Agent 내부 Memory만으로 결정하지 않는다.
Task 교체 전 상태는 해당 새 Task의 Final Report에 보존한다.

## AGY Review Lifecycle / Evidence(독립 검토 절차와 근거)

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

AGY / 사용자가 판정과 완료를 결정한다. 개발 Producer는 명시된 독립 Evidence에 맞는 상태 동기화만 수행한다.
Codex·Claude 작업 Report나 Reviewer / COMPLETE 문구만으로 상태를 전환하지 않는다.

현재 사용자가 제공·확인한 [Initial Review](../workspace/reports/agy/agy-initial-harness-review.md)와
[Targeted Re-review](../workspace/reports/agy/agy-harness-fix-review.md)를
`scripts/lib/validate.py`의 ACCEPTED_AGY_REVIEWS에 원문 SHA-256·검토 대상 Report SHA-256·결과로 고정했다.
check-harness는 lifecycle 상태·사용자 확인된 Evidence 참조를 제어 입력으로 검증한다.
자기 Report나 미승인 Evidence 경로로 review_complete를 선언하면 실패한다.
원문 / 검토 대상의 존재·symlink·byte checksum은 별도의 **non-gating integrity 상태**로 표시한다.
VERIFIED / UNAVAILABLE / MISMATCH / UNSAFE를 구분하며 미검증 근거로 현재 Review를 complete 처리하지 않는다.
checksum 불일치나 Report format/Git 상태는 제품 build를 실패시키지 않으며, 사람의 Review 승인을 대신하지도 않는다.
새 증거 기준은 사용자 승인 Task에서만 추가하며 개발 Producer가 Review 원문을 작성·편집해 등록하지 않는다.

Hash는 원문 무결성을 확인하며 저자의 신원을 서명으로 인증하지는 않는다.
현재 독립성의 근거는 사용자에게서 전달된 AGY 원문과 사용자 확인, 변경 내역의 Human Review다.
서명·외부 인증 시스템은 도입하지 않는다.

Initial Review 결과는 **PASS WITH FIXES**이며 이전 Foundation Report에 한정한다.
Targeted Re-review는 보완 Report에 대한 **PASS**로 완료됐다. 최신 Evidence는 이 독립 원문이다.
Registry.report의 현재 Task Report는 검토 대상이 달라 CURRENT REPORT REVIEW가 pending이다.
보완 구현과 check-all 통과만으로 과거 결과를 바꾸거나 현재 Task / Human Review를 승인하지 않는다.
Human Review는 AGY 원문·활성 개발 Producer Report·최종 Validation·Git Diff를 대조해 다음 Task를 판단한다.

사용자 지정 `harness/workspace/handoff/bundle1-handoff.md`는 동일 Task 실행 상태를 이어가는 non-gating checkpoint다. 반면 `artifacts/development/regression-set/run.py`는 재사용 실행 입력으로 strict 등록하며 JSON/log 실행 결과와 구분한다.
