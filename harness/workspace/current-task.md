# Current Task — 묶음3 서비스 관리

## Goal / Context

2026-10-04 사용자 요청(로컬 Claude CLI, 묶음1·2는 Codex): 서비스 관리 기능을 한 번에 끝까지 구현한다. 측정·비교 실험 없이 기능 완성이 목표다.
사용자 승인: 새 Flyway migration은 `migrations/`에 추가하고 dev DB에 적용한다(기존 migration 수정 금지).
범위: 1 회원 탈퇴 2 대화 삭제 3 로그인 시도 제한(계정·IP 5회/10분) 4 CI 초록 5 IMP-016·021·022·015·023·026 6 비밀번호 변경·지난 추천 목록·Swagger 7 문서·check-all·regression-set.
commit·push·브랜치 변경, `.env.dev`·secret 열람, 식별 key·vector·V1 변경, 운영 DB 접근은 범위가 아니다. Ollama 호출은 75초 기한·순차.

## Next Steps

AGY 독립 검토 → 사용자 commit(Report의 묶음별 파일 목록) → GitHub CI(validate·backend·frontend) 확인 → 5 화면 완주·cases-v2.

## Read First

[AGENTS](../../AGENTS.md) → [DB 규칙](../rules/database-rules.md) → `migrations/V12__account_management.sql` → Spring `auth`(AccountService·LoginThrottleService)·`common/maintenance` → [Backlog](../docs/improvement-backlog.md)(IMP-015·016·021·022·023·026).

## Scope / Acceptance

1. 탈퇴 뒤 서비스 데이터가 없고 활동 기록은 익명이며 이전 토큰은 즉시 401이다. 남의 대화 삭제는 404다.
2. 계정·IP 각각 5회 연속 실패 뒤 10분 동안 429 auth_login_locked, 성공 시 계정 횟수만 초기화. 이메일·IP 원문은 저장하지 않는다.
3. 정리 작업은 진행 중 workflow를 지우지 않는다. IMP-026은 기존 parse_key를 바꾸지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-04-bundle3-service.md). Spring·React·Python targeted tests, check-all 1회, regression-set 1회(bundle3-results.json). handoff는 harness/workspace/handoff/bundle3-handoff.md.
