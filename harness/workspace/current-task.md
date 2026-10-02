# Current Task — 회원가입 응답 지연 원인 파악과 수정

## Goal / Context

2026-10-02 사용자 요청: React에서 회원가입 응답이 매우 느린 원인을 찾고, 사용자가 고른 추천 방법(성공 활동 기록을 본 트랜잭션 커밋 뒤에 저장)으로 고친다.
인증 방식·DB 스키마·migration·다른 기능 변경은 범위가 아니다. 직전 Task(V2 적재 완전성 검증)의 결과는 `2026-10-02-v2-data-completeness.md`에 있다.

## Current State Snapshot

- 원인: 가입 트랜잭션이 커밋 전 새 users 행을 잠근 채 별도 트랜잭션으로 activity_logs(users FK)를 저장 → MySQL 잠금 대기 50초 후 실패 → 그 뒤 가입 커밋.
- 수정: `ActivityLogService.success`를 커밋 뒤 기록으로 변경. 실패 기록은 즉시 별도 트랜잭션 그대로.
- 결과: 실제 가입 50.2초 → 0.06~0.3초, backend 로그의 잠금 대기·기록 실패 0.
- V2 데이터: 적재·완전성 검증 완료(전환 전). 다음 단계는 V2 collection 전환 → 화면 완주 + LangSmith 확인 → cases-v2 평가.

## Read First

[AGENTS](../../AGENTS.md) → [DB 규칙](../rules/database-rules.md) → [Testing](../docs/testing.md).

## Scope / Acceptance

1. 원인을 측정과 로그로 확인하고, 테스트가 수정 전 실패·수정 후 통과한다.
2. 실패 기록(로그인 실패 등)은 본 트랜잭션이 되돌려져도 계속 남는다.
3. Spring 테스트·check-all이 통과한다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-signup-latency-fix.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
