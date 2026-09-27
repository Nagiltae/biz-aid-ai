# Harness 변경 이력

## 2026-09-27 — 최초 기반 구축

- 원인: 설계만 있고 Context·Registry·검증·External Memory가 없었다.
- 범위: Phase 0 준비에 필요한 Harness와 로컬 파일 도구·계약·테스트·CI.
- 전체 서비스·DB·Pipeline·RAG를 만들지 않도록 실제 구현 목록을 Registry로 고정한다.
- 미구현 제품 검증은 N/A로 공개한다. Gate 통과와 AGY 승인은 독립 상태로 둔다.
- Raw byte 보존과 hash 검증, 미측정 보고서 계약으로 다음 데이터 실험의 증거를 준비한다.
- 규칙 완화·삭제 없음. 최상위 설계 수정 없음.
- 실행 결과: [Codex Report](../workspace/reports/2026-09-27-codex-harness-report.md).
- AGY 검토: pending.

## 2026-09-27 — AGY Initial Review 보완

- 근거: [독립 AGY Initial Review](../workspace/reports/agy-initial-harness-review.md), PASS WITH FIXES.
- M-1: 불필요한 workflow/reference는 생성하지 않고 Target와 현재 Skill 구조를 명시.
- M-2: Compose·ignore·Registry·Context 크기·Review 증거·Raw 무결성·출력 충돌의 WHY 주석 보강.
- M-3 / I-4: Checkpoint Format·복원과 current-task 교체·이전 상태 보존 절차 정의.
- M-4: 공식 명세 전 환경변수 추정 없음. .env.example 보존.
- M-5: pending-only Gate 계약은 유지하고 측정·Human Review 후 확장 Task 절차만 정의.
- 사용자 요청에 따라 pending 고정 검사를 Evidence 검증이 필요한 review_complete 전환으로 교체.
  독립 원문·검토 대상 hash는 고정하며 자기 Report를 Evidence로 사용할 수 없도록 검증.
- Initial Review는 과거 Foundation 대상이다. 이번 보완의 후속 Review·Human Review·Data Gate는 pending.
- IDE가 생성한 로컬 .idea metadata만 제외하고 같은 경로의 코드·문서 숨김은 거부.
- 제품 기능·추정 upstream·기술 도입·Git 승격 없음.
- 결과: [보완 Report](../workspace/reports/2026-09-27-codex-harness-fix-report.md).

## 2026-09-27 — Dynamic Workspace Registry Drift 수정

- 재현: clean dev에서 AGY Targeted Re-review 파일만 unregistered로 check-harness / check-all이 실패했다.
- 원인: 정적 Harness 구조와 계속 생성되는 External Memory에 같은 개별 등록 의무를 적용했다.
- required_files는 정적 필수 목록, dynamic_paths는 바로 아래 reports / checkpoints Markdown 경계로 분리한다.
  기존 Workspace README는 정적 필수 파일로 유지하고 새 기록은 Git 추적·ignore·일반 파일·symlink·실행 권한을 검사한다.
- 일반 Report 허용과 Trusted Evidence를 분리한다. 사용자 제공 Targeted Re-review PASS의 원문·검토 대상 hash만 별도 등록한다.
  현재 수정 Task의 Review·Human Review·Data Gate는 pending이다. AGY 원문·과거 Report는 수정하지 않는다.
- 실제 파일을 복사하는 fixture와 동적 기록·정적 drift·숨김·자기 승인 방지 회귀를 추가한다.
- Final Report → 최종 Git 상태 구성 → check-all → 동결 순서를 명시한다. 이후 변경 시 기존 Final 결과는 무효다.
- 결과: [수정 Report](../workspace/reports/2026-09-27-codex-dynamic-workspace-fix-report.md).
