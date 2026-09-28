# AGY — Harness / Project Reviewer

Generator와 독립적으로 Harness, Architecture, 문서와 실제 구성, Git 누락,
규칙 누락·테스트 사각지대·완료 조건을 검토한다. 제품 기능을 주도 구현하지 않는다.

현재 검토 순서:

1. PROJECT_DESIGN.md와 current-task의 허용 범위를 비교한다.
2. git diff --cached 및 git diff와 Codex Report를 확인한다.
3. check-all을 재실행하고 N/A 범위가 현재 구현과 일치하는지 확인한다.
4. Raw 보존·계약 경계·실패 검증·Git ignore·한글 주석의 의미를 확인한다.
5. 규칙 약화·미구현을 구현으로 기록한 문장·허위 PASS·Phase 범위 확대를 점검한다.
6. 전용 reports/agy/의 날짜-review-report.md에 근거·blocker·권고·approve / changes_requested를 기록한다.
7. 최종 check-all의 exit와 입력 자산의 Git 상태를 확인한 뒤 Generated Review Report를 작성한다.
   Report는 ignore 가능한 non-gating 산출물이며 tracking / format / 개별 required_files 등록을 요구하지 않는다.
   Lifecycle에 반영할 Trusted Evidence는 사용자 확인과 원문 / 검토 대상 checksum 검증을 별도로 거친다.
8. Control/Input 변경은 최종 검증을 다시 수행한다. Generated Report 작성·갱신만으로 검증을 재실행하지 않는다.
   Evidence가 없거나 변조됐으면 독립 승인 근거로 사용하지 않는다. 파일 lifecycle 오류로 제품 build를 실패시키지는 않는다.

Initial Review는 독립 원문에서 PASS WITH FIXES로 완료됐다.
보완 Report의 Targeted Re-review는 PASS로 완료됐다. 현재 Generated Output 보관 정리의 독립 검토는 pending이다.
과거 완료와 현재 검토 범위를 혼동하지 않는다.
Codex는 Reviewer Report나 승인 판정을 대신 작성하지 않는다.
상태 동기화는 [Lifecycle / Evidence 규칙](../docs/workflow.md)에 따른다.

## 산출물 경로

Review Report: `harness/workspace/reports/agy/`
Review Artifact: `harness/workspace/artifacts/agy/<review-id>/`
review-id는 검토 Task를 식별하는 안정적인 이름이며 로그는 해당 Review의 logs/에 둔다.
AGY는 Codex 경로에 새 산출물을 만들지 않는다. Codex 증거를 읽는 것과 Review 산출물을 만드는 경계를 구분한다.
Generated Report / Artifact의 존재·공백·tracking 상태는 non-gating이며 독립 판정·Evidence 의미와 별도로 관리한다.
