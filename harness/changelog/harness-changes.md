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
