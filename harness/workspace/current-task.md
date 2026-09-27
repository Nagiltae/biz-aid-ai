# Current Task

## Goal / Context

Static Harness와 Dynamic Workspace의 Registry Drift 책임을 분리한다.
현재 Phase는 phase0-preparation이며 사용자의 2026-09-27 Debugging 요청으로 시작했다.
Rollback 이후 clean dev에서 check-harness / check-all의 동일 실패를 재현했다.
이전 Task 전체는 [이번 Report](reports/2026-09-27-codex-dynamic-workspace-fix-report.md)에 보존한다.
보완 Report의 독립 AGY Targeted Re-review: review_complete / PASS.
현재 수정 Task의 독립 Review·Human Review·Data Gate: pending.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[Registry](../registry.json) → [Workflow](../docs/workflow.md) →
[Debugging](../skills/debugging/SKILL.md) → [AGY Fix Review](reports/agy-harness-fix-review.md).

## Allowed Scope / Forbidden Scope

Registry·validate.py·Harness 회귀 테스트, 필요한 최소 Workflow / Reviewer / Checkpoint 안내·Changelog·External Memory.
제품 기능·API 수집·Parser·DB·RAG·LangGraph·Indexing·추정 API 환경변수·Gate go/drop 구현 금지.
Commit·Push·Merge·프로젝트 Branch 변경 금지. 설계·AGY 원문·과거 Codex Report·Raw / Contract 정책은 보존한다.

## Acceptance / Validation / Expected Report

새 추적 Report·Checkpoint는 개별 등록 없이 통과하고 코드·symlink·Untracked·ignore는 실패한다.
정적 Registry·Skill / Rule·AGENTS Routing·독립 Evidence / checksum·자기 승인 방지는 유지한다.
format / lint / contract / integration / comments / harness / git-tracked / all을 실제 실행한다.
[Final Report](reports/2026-09-27-codex-dynamic-workspace-fix-report.md).
Final Report와 Git index 구성 후 최종 check-all을 실행한다. 이후 추적 파일 변경 시 재검증한다.
상태: 정책 수정·53개 Contract / Harness와 4개 Integration·Report 작성 전 check-all 통과.
Final Report를 완성했으며 최종 Git index 구성 후 검증과 Git 확인을 수행한다. 최종 종료 코드는 Report의 로그와 최종 응답을 따른다.
다음 Task는 별도 사용자 승인 후에만 시작한다.
