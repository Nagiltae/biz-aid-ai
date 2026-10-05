# 현재 Task

## 목표 / 승인 범위

묶음6-0 배포 준비물. [5-2 최종 기록](reports/development/2026-10-04-bundle5-2-predeploy.md)의 운영 기능을 유지하고 맥북 ARM build·Docker Hub pull·서버 실행 묶음·공고/V2/모델 복원·설명서를 준비한다.
개발은 기존 docker-compose.yml/scripts/dev.sh/.env.dev/로컬 DB·검색 DB·dev profile 그대로다. 운영은 별도 prod Compose/RDS/서버 내부V2/image pull이다.

## 상태

구현·검증 후 사용자 파일/Git 검토 대기. 실제 시작은5-2 신규20 staged와 추적수정58이 남은 상태였으며 이를 보존한다(사용자의5-2 커밋 완료 설명과 실제 Git 상태 차이는 Report에 기록).
ARM 앱3이미지 build-only 완료, 운영 기본build는 별도override로 분리한다. 실제 서버/AWS 배포는 아직 하지 않았다.
실제 exit/count와 준비 자료checksum·크기는 최종 Report를 따른다. 이후 단계 자동 시작 금지.

## Read First

AGENTS → Registry → workflow/git-policy → [운영 설명서](../../docs/deployment.md) →5-2 Report → [인수인계](handoff/bundle6-0-handoff.md).
feature-development Skill, safety/file-boundaries,architecture/testing을 적용한다.

## Acceptance / Safety

- 개발 Compose/dev.sh/profile/기존 migration·식별 key·vector는 변경하지 않는다.
- ARM3이미지 태그는 한 비공개저장소의 frontend/backend/fastapi로 구분. 기본 운영은pull,명시 소스build만override다.
- 서버묶음은실행파일allowlist만 포함한다. 앱소스/test/Harness/Secret/데이터는 제외한다.
- 복원은checksum과빈대상확인→공고transaction 개수검증→V2정확개수→모델파일checksum. 기존데이터덮어쓰기/삭제는 금지한다.
- Agent의 docker login/push/AWS생성/S3업로드/Bedrock호출은 금지한다. 사용자 직접 명령만 준비한다.
- Secret파일 직접 열람·출력·수정0, SDK키를코드/이미지/서버묶음에넣지않는다.
- commit/push/branch 전환 금지. 새입력만명시staging,기존staged변경해제금지.
- sandbox차단은우회하지않고보고한다. Git index 차단은 기존 Git 정책의 명시 도구 승인을 따른다.

## Validation

targeted 배포계약/임시bundle config/ARMbuild/데이터SHA → dev.sh up 및로그인·목록확인 → 마지막check-all1회 → Generated Report/handoff.
실제AWS/RDS/서버성능검증은 별도로 남긴다.

## Expected Report

[Final Report](reports/development/2026-10-05-bundle6-0-deploy-kit.md)
