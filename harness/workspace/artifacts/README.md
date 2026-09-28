# 로컬 실행 산출물

이 README는 STATIC_DOCUMENTATION이며 tracking·format·link·Registry 검사를 유지한다.
실행 중 생성되는 하위 *.json / *.log는 GENERATED_ARTIFACT로 ignore하고 build 검증 입력에서 제외한다.
존재·공백·JSON format·Git 상태가 제품 Validation을 바꾸지 않는다. 생성 명령의 실패 exit는 계속 실패다.
사람이 읽는 결과·해석·작업 Report는 reports/의 GENERATED_REPORT에 기록한다. 생성물의 Git 추적은 필수가 아니다.
코드·Rule·설정·제어 입력을 Artifact로 숨기지 않는다. Artifact만 존재한다고 검토 완료로 간주하지 않는다.

Codex는 codex/<task-id>/, AGY는 agy/<review-id>/ 아래에 machine-readable evidence를 보관한다.
로그는 해당 작업의 logs/를 사용한다. Task마다 final validation·preservation을 구분하고 기존 원문을 overwrite하지 않는다.
공동 개발 보고서는 reports/development/, 독립 Review는 reports/agy/에 저장한다. checkpoints의 run/resume 구조는 유지한다.
이 README는 Agent 하위 경로로 옮기지 않는다. 과거 생성물의 이동은 cleanup manifest의 relocation mapping으로 추적한다.
