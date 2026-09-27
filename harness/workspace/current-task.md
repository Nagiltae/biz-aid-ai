# Current Task

## Goal / Context

AGY Initial Harness Review의 MINOR Finding과 Harness 상태 전환을 정리한다.
현재 Phase는 phase0-preparation이며 이번 Task는 Harness Foundation 보완이다.
이 Task는 사용자의 2026-09-27 보완 요청으로 시작했다.
이전 Task 상태는 [보완 Report](reports/2026-09-27-codex-harness-fix-report.md)에 보존했다.
상태: 보완 구현·현재 적용 Validation 통과, 사용자 검토 대기.
Initial AGY Review: review_complete / PASS WITH FIXES.
이번 보완의 후속 AGY Review: pending. Human review: pending. Data Gate: pending.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[최초 Codex Report](reports/2026-09-27-codex-harness-report.md) →
[독립 Initial Review](reports/agy-initial-harness-review.md) →
[Workflow / Lifecycle](../docs/workflow.md).

## Allowed Scope / Requirements

M-1 Skill의 현재 하위 절차 필요성 명시, M-2 WHY / BOUNDARY / EXCEPTION / RISK 주석,
M-3 Checkpoint format·Resume·Recovery, M-5 Gate 계약 확장 절차,
current-task 전환·AGY Lifecycle·독립 Evidence 검증·관련 테스트·문서·Registry·Report.
Validation을 막는 IDE metadata는 좁은 ignore 정책으로 구분한다.

## Forbidden Scope / Non-goals

제품 기능·API Collector·Parser·DB·Migration·RAG·LangGraph·Indexing 구현 금지.
Gate go/drop 허용·API 환경변수 추정 금지.
Commit·Push·Merge·프로젝트 Branch 변경 금지.
최상위 설계·이전 Codex Report·독립 AGY Review 원문은 수정하지 않는다.

## Acceptance Criteria / Required Tests

현재 Review 결과를 독립 원문과 검토 대상 checksum으로 검증한다.
Codex Report·누락/변조/불일치 증거·미지원 상태는 Review 완료 근거로 거부한다.
이번 보완은 Initial Review의 승인 범위에 포함됐다고 기록하지 않는다.
제품 미구현 검증은 N/A, Human Review·Gate는 pending이다.

## Validation Command / Expected Report

check-format / lint / contract / integration / comments / harness / git-tracked / all.
[Final Report](reports/2026-09-27-codex-harness-fix-report.md).
다음 Task는 사용자 검토와 별도 승인 후에만 시작한다.

## 완료 / 남은 상태

M-1·M-2·M-3·M-5와 Task / Review Lifecycle을 보완했고 M-4의 명세 전 변수 추정은 보류했다.
39개 Unit / Contract / Harness와 4개 CLI Integration, check-all exit 0.
최상위 설계·이전 Codex / 독립 AGY 원문·.env.example·pending-only Gate 계약은 보존한다.
다음 작업은 보완 Report / Diff 검토이며 실제 API 명세·표본·분모·근거 기준은 미결정이다.
