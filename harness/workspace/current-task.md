# Current Task

## Goal / Context

2026-09-28 사용자 승인: Generated Output의 Producer별 보관·참조·정리.
Control/Input STRICT / Generated Output NON-GATING 정책은 유지한다. Validation Boundary를 다시 설계하지 않는다.
이전 Workspace lifecycle Task의 current-task 원문은 inventory-before.json과 이번 Final Report에 보존한다.

## Read First

[AGENTS](../../AGENTS.md) → [Workflow](../docs/workflow.md) → [Git 정책](../rules/git-policy.md) →
[Registry](../registry.json) → [Testing](../docs/testing.md) → [feature-development](../skills/feature-development/SKILL.md).

## Scope / Acceptance

reports/codex·reports/agy와 artifacts/codex/<task-id>·artifacts/agy/<review-id>로 생성물을 분리한다.
Inventory / Reference Graph로 KEEP·MOVE·DELETE·UNCLASSIFIED를 판정하고 원문 byte·accepted checksum·판정을 보존한다.
static/live 경로 참조와 도구의 출력 경로만 갱신한다. 제품 정규화·DB logic·Pilot·Secret·Migration은 변경하지 않는다.
current-task·정적 README 두 개는 strict, checkpoint 파일·run/resume 구조는 그대로 유지한다.
독립 Review / Human Review는 pending이다. 이전 AGY 승인 결과를 이번 작업 승인으로 재사용하지 않는다.

## Validation / Reports

정적 입력 / index 확정 → 실제 전체 Validation → Generated Report 작성 → AGY / 사용자 검토.
[Final Report](reports/codex/2026-09-28-workspace-output-cleanup.md).
Manifest / Reference Graph / 최종 실행 Evidence는 artifacts/codex/workspace-output-cleanup/에 보관한다.
Report 생성만으로 재검증하지 않는다. static/input 변경은 최종 Validation을 다시 수행한다.
