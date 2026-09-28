# BizAid AI

기업 정보와 지원사업 공고문 근거를 결합하는 AI 서비스 프로젝트다.
최상위 설계는 [PROJECT_DESIGN.md](PROJECT_DESIGN.md), 작업 진입점은 [AGENTS.md](AGENTS.md)다.

현재는 **Phase 3 Document Parsing**이다. S3 원본 문서를 후속 Chunking이 소비할 DoclingDocument로 변환한다.
제품 데이터 Pipeline·dev MySQL·S3 원본 저장은 구현됐다. Parser는 HWPX와 Docling PDF route가 구현됐고 HWP 변환·서비스 API·OCR·RAG는 미구현이다.

## 현재 실행 환경

Bash, Git, Python 3.11 이상, Docker Compose v2 이상이 필요하다.
Phase 0 도구는 표준 라이브러리를 사용하며 Phase 1A/1B는 `.venv`의 제품 dependency가 필요하다. dev DB 설정은 [Infra](infra/README.md)를 따른다.

```bash
./scripts/setup.sh
./scripts/check-all.sh
docker compose --env-file .env.dev run --rm phase0 --help
docker compose --env-file .env.dev run --rm phase0 init-report --output /artifacts/phase0-report.json
```

Compose에는 파일 보존 도구 `phase0`와 dev-db Profile의 MySQL / Flyway가 있다.
Batch 실행에는 Docker daemon 및 최초 Python 이미지 다운로드가 필요하다.
dev MySQL은 사용자 관리 `.env.dev`로 127.0.0.1:3306에서 실행한다. 준비는 `.venv/bin/python -B infra/dev_mysql.py`를 사용한다.
setup은 CLI와 Compose 구성을 검사하며 daemon·네트워크 접근은 요구하지 않는다.

이미 확보한 공식 API 응답을 원문 그대로 보존하는 예:

```bash
python3 scripts/phase0.py snapshot /path/to/response.json --run-id sample-001 --media-type application/json
python3 scripts/phase0.py verify-snapshot data/raw/sample-001/metadata.json
python3 scripts/phase0.py init-report --output harness/workspace/artifacts/codex/phase0-report/phase0-report.json
python3 scripts/phase0.py validate-report harness/workspace/artifacts/codex/phase0-report/phase0-report.json
```

Compose에서 snapshot을 만들려면 입력을 `data/raw/inbox/`에 두고
`docker compose --env-file .env.dev run --rm phase0 snapshot /data/raw/inbox/response.json --run-id sample-001 --media-type application/json`
을 실행한다. 동일 run-id나 출력 파일은 덮어쓰지 않는다.
전체 Collector·Production Downloader·Parser는 없다. 승인된 문서 Gate 도구는 아래 범위로 제한한다. 도구가 보고서 생성만으로 Gate를 통과시키지 않는다.

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
실제 MySQL Integration을 포함하며 제품 API·AI는 [검증 정책](harness/docs/testing.md)에 미구현으로 표시한다.
생성 파일은 Git index에 추가한 뒤 `git diff --cached`로 검토한다.
기반 구축 이력은 [최초 작업 보고서](harness/workspace/reports/codex/2026-09-27-codex-harness-report.md),
독립 결과는 [AGY Initial Review](harness/workspace/reports/agy/agy-initial-harness-review.md),
과거 보완은 [보완 보고서](harness/workspace/reports/codex/2026-09-27-codex-harness-fix-report.md),
그 독립 PASS는 [AGY Targeted Re-review](harness/workspace/reports/agy/agy-harness-fix-review.md)에 기록한다.
현재 Task의 독립 검토·사용자 판단은 대기 중이다.
사용자가 Diff와 독립 Review를 확인한 뒤 다음 Task·Push·승격을 결정한다.

## Phase 0 API 품질 측정

전체 Offline Validation PASS 후 dev에서만 5요청을 실행한다. 기존 Raw / run-id / 출력은 덮어쓰지 않는다.

```bash
python3 -B scripts/phase0_api_quality.py collect --profile dev --run-id api-quality-dev-unique
python3 -B scripts/phase0_api_quality.py analyze --run-id api-quality-dev-unique --output harness/workspace/reports/codex/api-quality-dev-unique.md --markdown
```

분석은 HTTP 없이 Raw checksum에서 재현된다. Raw와 실행 JSON은 ignored이며 해석 Report는 Git 추적한다.
100개 Item과 ID 유일성을 따로 계수한다. URL 접속·다운로드·Parser는 이 도구 범위에 없다.

## 제한된 Document Download Gate

기존 API 100개 Item의 printFlpthNm만 dev에서 순차 다운로드한다. Offline PASS 후 명시적으로 실행한다.

```bash
python3 -B scripts/phase0_document_download.py download --profile dev --run-id <unique-id>
python3 -B scripts/phase0_document_download.py download --profile dev --run-id <same-id> --resume
python3 -B scripts/phase0_document_download.py analyze --run-id <id> --output harness/workspace/reports/codex/<report>.md
```

원본은 data/downloaded에서 checksum과 함께 보존하고 Git에서 제외한다.
[Pipeline 경계](harness/docs/data-pipeline.md)에 크기·Redirect·형식 식별·재개 제한을 명시한다. 문서 본문 Parser는 없다.

## Phase 1A Pilot / Phase 1B FULL / 현재 Phase 2

사용자 승인으로 기존 동일 100건의 제품용 Normalize / dev MySQL 적재를 구현한다.
[제품 Pipeline 실행 / 정책](data-pipeline/README.md), [dev DB 준비](infra/README.md),
[공통 migration](migrations/README.md)을 따른다. 기존 Phase 0 Gate / 증거는 보존한다.
Phase 1B는 실행 시점 totalCount 기반 dev 전체 pagination / Raw 검증 / 적재와 soft-delete 후보 DRY-RUN을 제공한다.
실제 soft-delete / prod는 범위 밖이다. Phase 2는 검증된 dev DB의 전체 문서 후보 원본과 provenance metadata를 수집한다.
문서 본문 Parsing/OCR/AI는 수행하지 않는다. FULL 및 Document Acquisition 명령과 실패 경계는 제품 Pipeline 문서를 따른다.
Phase 2.5는 기존 S3 object를 checksum으로 검증하고 MySQL relation에 위치 metadata를 연결한다. 로컬 corpus는 Review 전까지 보존한다.
