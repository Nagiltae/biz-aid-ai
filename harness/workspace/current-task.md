# 현재 Task

## 목표 / 승인 범위

상태 확인 주소 HEAD 허용(2026-10-06 사용자 승인). 운영에서 `GET /api/health`는 200인데 `HEAD /api/health`는 401이라 HEAD로만 확인하는 UptimeRobot 무료 플랜이 Down으로 본다.
backend SecurityConfig의 `/api/health` 공개 허용에 HEAD만 최소로 더한다. 다른 주소의 권한·보안 설정·앱 기능은 바꾸지 않는다.

## 상태

구현·backend 테스트 완료, 최종 check-all·사용자 검토 대기. 이전 운영 모니터링 current-task 원문은 Final Report 부록에 보존했다.

## Read First

AGENTS → Registry → workflow/git-policy → backend SecurityConfig·HealthController → [운영 설명서 §10](../../docs/deployment.md).

## Acceptance / Safety

- HEAD `/api/health`는 로그인 없이 200·본문 없음, GET은 그대로 200 `{"status":"ok"}`. 다른 HEAD 요청·주소의 권한은 그대로다.
- .env 파일 열람·출력 0. 운영 서버·AWS 접속 0. 새 패키지 0. commit/push 금지, 새 입력만 명시 staging.

## Validation

backend 테스트(gradle test) → check-all 1회.

## Expected Report

[Final Report](reports/development/2026-10-06-health-head.md)
