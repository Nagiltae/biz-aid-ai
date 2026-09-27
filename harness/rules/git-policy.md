# Git 정책

dev: 직접 개발. main: 최신 검증 완료 코드. op: 운영 배포 대상.
로컬 작업은 dev에서만 한다. CI는 dev Push의 ref를 확인한다.
Agent 임의 main / op merge·push·force push·branch 삭제는 금지한다.
Commit도 별도 요청이 없다면 만들지 않는다.

새 프로젝트 파일은 명시적인 경로로 git add하여 Diff로 검토 가능하게 한다.
index 기록이 권한 때문에 차단되면 정확한 git add 명령의 승인을 요청한다.
기존 사용자 수정 파일은 허락 없이 stage·되돌리지 않는다.
종료 전에 git status 및 check-git-tracked를 실행한다.
불필요한 .DS_Store, .env, payload, cache는 정책에 따라 ignore하며 결과물 문서는 숨기지 않는다.
