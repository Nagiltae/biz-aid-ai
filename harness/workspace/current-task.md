# 현재 Task

## 목표 / 승인 범위

묶음6-0 배포 준비물. [5-2 최종 기록](reports/development/2026-10-04-bundle5-2-predeploy.md)의 운영 기능을 유지하고 맥북→amd64 build·Docker Hub pull·서버 실행 묶음·공고/V2/모델 복원·설명서를 준비한다.
개발은 기존 docker-compose.yml/scripts/dev.sh/.env.dev/로컬 DB·검색 DB·dev profile 그대로다. 운영은 별도 prod Compose/RDS/서버 내부V2/image pull이다.

## 상태

추가 지시 구현·targeted검증 완료,최종검사·사용자검토대기. 이번 시작은dev/working tree clean. 이전Task의dirty시작 이력은Final Report 본문에보존한다.
이전 ARM 결과는Report에보존하고 이번amd64 앱3이미지build-only/베이스9개지원확인 완료. 서버는시드니 Ubuntu x86_64/8GB+swap2GB다, 운영 기본build는 별도override로 분리한다. 사용자가 EC2/RDS/S3/IAM을 생성했다는 사실을 반영하며 Agent의 서버 접속·실배포는 하지 않는다. DNS 연결은 pending. 기존 data02는재사용한다.
실제 exit/count와 준비 자료checksum·크기는 최종 Report를 따른다. 이후 단계 자동 시작 금지.

## Read First

AGENTS → Registry → workflow/git-policy → [운영 설명서](../../docs/deployment.md) →5-2 Report → [인수인계](handoff/bundle6-0-handoff.md).
feature-development Skill, safety/file-boundaries,architecture/testing을 적용한다.

## Acceptance / Safety

- 개발 Compose/dev.sh/dev profile/기존 migration·식별 key·vector는 변경하지 않는다. 공통·테스트application.yml은사용자가승인한동의버전2026-10-05.1만맞춘다.
- 운영EC2/RDS/S3는ap-southeast-2, Bedrock은ap-northeast-2. S3전달은deploy/<태그>/, RDS VERIFY_IDENTITY/시드니CA를유지한다. 공개예시는실제비밀이아닌값만채우며비밀칸은빈값이다.
- 국외이전문구는실제User/Company/추천State저장항목에맞추고법률검토필요를Report에명시한다.
- amd64 기본3이미지 태그는 한 비공개저장소의 frontend/backend/fastapi로 구분. 기본 운영은pull,명시 소스build만override다.
- 서버묶음은실행파일allowlist만 포함한다. 앱소스/test/Harness/Secret/데이터는 제외한다.
- 복원은checksum과빈대상확인→공고transaction 개수검증→V2정확개수→모델파일checksum. 기존데이터덮어쓰기/삭제는 금지한다.
- Agent의 docker login/push/AWS생성/S3업로드/Bedrock호출은 금지한다. 사용자 직접 명령만 준비한다.
- Secret파일 직접 열람·출력·수정0, SDK키를코드/이미지/서버묶음에넣지않는다.
- commit/push/branch 전환 금지. 새입력만명시staging,기존staged변경해제금지.
- sandbox차단은우회하지않고보고한다. Git index 차단은 기존 Git 정책의 명시 도구 승인을 따른다.

## Validation

targeted 배포계약/임시bundle config/amd64build/데이터SHA → dev.sh up 및로그인·목록확인 → 마지막check-all1회 → Generated Report/handoff.
실제AWS/RDS/서버성능검증은 별도로 남긴다.

## Expected Report

[Final Report](reports/development/2026-10-05-bundle6-0-deploy-kit.md)
