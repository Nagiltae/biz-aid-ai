# BizAid AI

기업 정보와 지원사업 공고문 근거를 결합하는 AI 서비스 프로젝트다.
최상위 설계는 [PROJECT_DESIGN.md](PROJECT_DESIGN.md), 작업 진입점은 [AGENTS.md](AGENTS.md)다.

현재는 **Phase 0 준비**다. 승인된 API 100건 품질 검증을 수행하며 문서 Gate와 GO / DROP 판단은 대기 중이다.
제품 서비스, DB, 문서 Parser, RAG는 구현되지 않았다.

## 현재 실행 환경

Bash, Git, Python 3.11 이상, Docker Compose v2 이상이 필요하다.
Python 도구는 표준 라이브러리만 사용한다. 로컬 파일 도구·CI에는 필수 환경변수가 없다.

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

사용자 확인 Request·실제 Sample 기반 [기업마당 API Contract](contracts/external-api/README.md)와
최대 4요청의 Local Probe는 별도로 준비되어 있다. 사용자 관리 `.env.dev` / `.env.prod`는 Git에서 제외한다.
현재 실행은 `.env.dev`를 명시적으로 선택한다. OS Environment가 우선하며 Profile 간 fallback과 Branch 자동 선택은 없다.
`.env.example`의 APP_PROFILE은 예시이며 Probe의 `--profile`을 대신하지 않는다. Secret 파일은 덮어쓰지 않는다.
키를 명령 인수에 넣지 않는다. 키가 없으면 요청 없이 NOT_RUN(종료 3)을 기록한다.

```bash
python3 -B scripts/bizinfo_probe.py --profile dev --run-id bizinfo-probe-001
```

CI는 오프라인 검증만 수행한다. Compose Batch는 network_mode=none을 유지하며 Probe는 로컬에서 명시적으로 실행한다.
표본은 수집 시점 API 기본 정렬 기준 선두 100건(5×20)이다. 공식 정렬 보장·Gate 판단은 미확정이다. 세부 기준은 위 Contract를 따른다.

## 검토

`check-all.sh`는 현재 Harness 및 로컬 도구 범위만 검증한다.
제품 API·DB·AI 검증은 출력과 [검증 정책](harness/docs/testing.md)에 미구현으로 표시한다.
생성 파일은 Git index에 추가한 뒤 `git diff --cached`로 검토한다.
기반 구축 이력은 [최초 작업 보고서](harness/workspace/reports/2026-09-27-codex-harness-report.md),
독립 결과는 [AGY Initial Review](harness/workspace/reports/agy-initial-harness-review.md),
과거 보완은 [보완 보고서](harness/workspace/reports/2026-09-27-codex-harness-fix-report.md),
그 독립 PASS는 [AGY Targeted Re-review](harness/workspace/reports/agy-harness-fix-review.md)에 기록한다.
현재 API Task의 독립 검토·사용자 판단은 대기 중이다.
사용자가 Diff와 독립 Review를 확인한 뒤 다음 Task·Push·승격을 결정한다.

## Phase 0 API 품질 측정

전체 Offline Validation PASS 후 dev에서만 5요청을 실행한다. 기존 Raw / run-id / 출력은 덮어쓰지 않는다.

```bash
python3 -B scripts/phase0_api_quality.py collect --profile dev --run-id api-quality-dev-unique
python3 -B scripts/phase0_api_quality.py analyze --run-id api-quality-dev-unique --output harness/workspace/reports/api-quality-dev-unique.md --markdown
```

분석은 HTTP 없이 Raw checksum에서 재현된다. Raw와 실행 JSON은 ignored이며 해석 Report는 Git 추적한다.
100개 Item과 ID 유일성을 따로 계수한다. URL 접속·다운로드·Parser는 이 도구 범위에 없다.
