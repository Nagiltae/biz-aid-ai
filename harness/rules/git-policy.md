# Git 정책

dev: 직접 개발. main: 최신 검증 완료 코드. op: 운영 배포 대상.
로컬 작업은 dev에서만 한다. CI는 dev Push의 ref를 확인한다.
Agent 임의 main / op merge·push·force push·branch 삭제는 금지한다.
Commit도 별도 요청이 없다면 만들지 않는다.

새 Control/Input 파일은 명시적인 경로로 git add하여 Diff로 검토 가능하게 한다.
index 기록이 권한 때문에 차단되면 정확한 git add 명령의 승인을 요청한다.
기존 사용자 수정 파일은 허락 없이 stage·되돌리지 않는다.
종료 전에 git status 및 check-git-tracked를 실행한다.
Secret·payload·cache와 Generated Workspace Output은 정책에 따라 ignore한다.
current-task·정적 Workspace README·제품·규칙·검증 입력을 ignore로 숨기지 않는다.
Generated Report / Checkpoint / Artifact는 tracking·staging 필수 대상이 아니다. 존재·format·Git 상태로 build를 실패시키지 않는다.
committed 생성물은 보존하며 강제 untrack / history rewrite하지 않는다. HEAD에 없는 staged 생성물은 승인된 Task에서 index만 제거하고 로컬 원문을 보존한다.
최종 검증 뒤 생성물만 추가·갱신한 경우 재검증은 필요 없다. Control/Input 변경은 재검증한다.
