# BizAid AI

기업 정보와 지원사업 공고문 근거를 결합하는 AI 서비스 프로젝트다.
최상위 설계는 [PROJECT_DESIGN.md](PROJECT_DESIGN.md), 작업 진입점은 [AGENTS.md](AGENTS.md)다.

현재는 **Phase 0 준비**다. 실제 API 100건 검증과 GO / DROP 판단은 아직 수행하지 않았다.
제품 서비스, DB, 문서 Parser, RAG는 구현되지 않았다.

## 현재 실행 환경

Bash, Git, Python 3.11 이상, Docker Compose v2 이상이 필요하다.
Python 도구는 표준 라이브러리만 사용한다. 현재 필수 환경변수는 없다.

```bash
./scripts/setup.sh
./scripts/check-all.sh
docker compose run --rm phase0 --help
docker compose run --rm phase0 init-report --output /artifacts/phase0-report.json
```

Compose에는 실제 파일 보존·보고서 도구인 `phase0` Batch만 있다.
Batch 실행에는 Docker daemon 및 최초 Python 이미지 다운로드가 필요하다.
`docker compose up`으로 실행할 상시 서비스는 아직 없다.
setup은 CLI와 Compose 구성을 검사하며 daemon·네트워크 접근은 요구하지 않는다.

이미 확보한 공식 API 응답을 원문 그대로 보존하는 예:

```bash
python3 scripts/phase0.py snapshot /path/to/response.json --run-id sample-001 --media-type application/json
python3 scripts/phase0.py verify-snapshot data/raw/sample-001/metadata.json
python3 scripts/phase0.py init-report --output harness/workspace/artifacts/phase0-report.json
python3 scripts/phase0.py validate-report harness/workspace/artifacts/phase0-report.json
```

Compose에서 snapshot을 만들려면 입력을 `data/raw/inbox/`에 두고
`docker compose run --rm phase0 snapshot /data/raw/inbox/response.json --run-id sample-001 --media-type application/json`
을 실행한다. 동일 run-id나 출력 파일은 덮어쓰지 않는다.
실제 Collector·Downloader·Parser는 없다. 도구가 보고서 생성만으로 Gate를 통과시키지 않는다.

## 검토

`check-all.sh`는 현재 Harness 및 로컬 도구 범위만 검증한다.
제품 API·DB·AI 검증은 출력과 [검증 정책](harness/docs/testing.md)에 미구현으로 표시한다.
생성 파일은 Git index에 추가한 뒤 `git diff --cached`로 검토한다.
기반 구축 이력은 [최초 작업 보고서](harness/workspace/reports/2026-09-27-codex-harness-report.md),
독립 결과는 [AGY Initial Review](harness/workspace/reports/agy-initial-harness-review.md),
현재 보완은 [보완 보고서](harness/workspace/reports/2026-09-27-codex-harness-fix-report.md)에 기록한다.
Initial Review는 PASS WITH FIXES이며 이번 보완의 후속 검토와 사용자 판단은 대기 중이다.
사용자가 Diff와 독립 Review를 확인한 뒤 다음 Task·Push·승격을 결정한다.
