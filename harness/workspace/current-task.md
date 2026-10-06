# 현재 Task

## 목표 / 승인 범위

운영 모니터링(로그·장애 알림, 2026-10-06 사용자 승인). 운영 EC2(~/bizaid, docker-compose.prod.yml, 5개 컨테이너)에서 10분마다 cron으로 도는 점검 스크립트 하나를 만든다.
- 확인: 컨테이너 5개 running, 디스크 80%·메모리 90% 이상, FastAPI 내부 상태 확인, 최근 10분 AI(Bedrock) 실패·시간 초과 3건 이상, 최근 10분 backend 오류 10건 이상. 오늘 AI 사용량은 비밀값 없이 셀 수 있을 때만 넣는다.
- 알림: 서버 설정 파일의 SNS 주제로 `aws sns publish` 메일. 같은 문제는 1시간에 1번, 풀리면 해결 메일 1통. --dry-run, --test 옵션.
- Docker 로그 크기 제한 확인, UptimeRobot용 backend 상태 확인 주소 조사, 서버 묶음·운영 설명서 반영.
앱 기능(frontend·backend·fastapi)은 바꾸지 않는다.

## 상태

구현·targeted 검증 완료, 최종 check-all·사용자 검토 대기. 오늘 AI 사용량 점검은 DB 비밀값 없이 셀 수 없어 제외했다. 이전 AI 개선 1단계 current-task 원문은 Final Report 부록에 보존했다.

## Read First

AGENTS → Registry → workflow/git-policy → [운영 설명서](../../docs/deployment.md) → docker-compose.prod.yml·Caddyfile·scripts/deploy.sh.
feature-development Skill, safety/file-boundaries, observability를 적용한다.

## Acceptance / Safety

- 로그·메일에 비밀값·개인정보·사용자 질문 원문을 넣지 않는다. SNS 주제 ARN은 코드에 넣지 않고 서버 설정 파일에서 읽는다.
- .env 파일 열람·출력 0. 운영 서버·AWS 접속 0(aws 명령은 스크립트에 쓰기만 한다). 새 패키지 설치 0.
- Caddyfile은 꼭 필요할 때만 바꾼다. commit/push 금지, 새 입력만 명시 staging.

## Validation

shellcheck(있으면) → 로컬 dev compose --dry-run 1회 → 계약 테스트 → check-all 1회.

## Expected Report

[Final Report](reports/development/2026-10-06-prod-monitoring.md)
