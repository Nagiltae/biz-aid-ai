# Structured Data Pipeline — Phase 1A / 1B

제품 코드는 src/biz_aid_pipeline이다. scripts는 CLI 진입점이고 tests는 이 package를 import한다.
실행 환경: Python 3.11 / Pydantic v2 / SQLAlchemy 2 Core / PyMySQL / dev MySQL / 공통 Flyway.
기존 stack에 Python DB access와 migration이 없어 사용자 승인으로 이 최소 경계를 도입했다.

## 실행

[dev DB 준비](../infra/README.md) 후:

```sh
.venv/bin/python -B scripts/run_structured_ingestion.py --profile dev --run-id <new-unique-id> --report harness/workspace/reports/codex/<new-report>.md
```

고정 입력은 api-quality-dev-20260928-01의 API default-order head 100이다. 신규 API request를 하지 않는다.
manifest 및 5개 Raw byte의 SHA / 크기 / run 관계를 확인한다. 원본과 기존 Phase 0 증거를 변경하지 않는다.
Pilot CLI는 SAMPLE / dev만 제공하고 run-id / Report를 덮어쓰지 않는다. FULL은 아래 별도 진입점으로 실행한다.
공식 설정은 dev → `.env.dev`, prod → `.env.prod`다. Branch 이름으로 Profile을 선택하지 않는다.
DB와 API 모두 Process Environment → 선택한 Profile 파일 → Secret이 아닌 안전한 default 순서다.
서로 다른 Profile·generic `.env` fallback은 없다. `.env.dev` API key는 기존 Raw 반사 검사에만 사용한다.
Dev MySQL은 127.0.0.1:3306이며 MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD가 없으면 명확히 실패한다.
prod 설정 선택은 가능하지만 제품 API / DB / Pilot 실행은 dev만 허용한다. Secret 파일을 생성·수정하지 않는다.

## 책임

- config: 안전한 KEY=VALUE, Profile isolation, endpoint는 기존 API Contract 사용.
- bizinfo: Pydantic source model / 제한된 pagination client. API dict를 SQL로 직접 전달하지 않는다.
- ingestion: 검증된 표본 읽기 / normalization / run orchestration.
- persistence: SQLAlchemy Core로 실제 MySQL 트랜잭션 / 조회 / INSERT / UPDATE. Python DDL 없음.
- quality: machine-readable 계약 / completeness / Markdown 생성.

## Source / Normalizer

pblancId는 ASCII binary unique business key다. 최소 필수는 유효한 ID이고 나머지 실제 19개 field는
타입을 엄격하게 검증하며 nullable을 제품 보존 정책으로 허용한다. 이는 공급자의 필수 / nullable 보장을 뜻하지 않는다.
unknown source key도 JSON에 보존한다. 누락 / null / 빈 값의 차이는 source_payload에서 보존한다.
nullable scalar column은 누락과 null이 모두 SQL NULL일 수 있으므로 의미 판단에는 source_payload를 사용한다.
HTML / @ URL / filename / raw period를 trim·normalize·분해 저장하지 않는다.
날짜 범위가 실제 달력상 유효하고 start ≤ end일 때만 derived date를 생성한다.
FREE_TEXT는 정상이며 날짜 오인 / timezone 추측은 하지 않는다. 잘못된 날짜 / timestamp는 Raw와 observation을 남긴다.
URL syntax 오류는 observation이고 네트워크 / 의미 검증을 뜻하지 않는다.

## Fingerprint / Upsert

source_payload를 Unicode UTF-8 JSON으로 재귀 key 정렬 / compact / NaN 금지 직렬화 후 SHA-256 한다.
DB created_at / updated_at / last_seen / run / active / deleted는 이 입력에 포함되지 않는다.
Raw 공백 / null / 누락 / unknown source의 변경도 fingerprint를 바꾼다. 소스 타입 / 변환 정책 변경 시 버전을 별도 관리한다.
INSERT, 변경 UPDATE, 동일 CONTENT_NOOP을 구분한다. NOOP SQL은 source content / updated_at을 건드리지 않고 last_seen만 갱신한다.

## Presence lifecycle / atomicity

source_active는 API universe 존재이고 신청 접수 상태가 아니다. 관측은 active=true / deleted=false / deleted_at=NULL이다.
복원은 동일 fingerprint에서도 가능하며 reactivated는 updated 또는 noop의 부분집합이다. count를 중복 합산하지 않는다.
SAMPLE/PARTIAL 미관측은 삭제 근거가 아니다. 이번 Pilot은 reconciliation을 실행하지 않는다.

FULL은 명시적인 scope, 모든 page 성공, transport/API/contract/normalization/persistence fatal 0,
duplicate 0, 정상 종료, 연속 page / echo, totalCount 일관성, unique=expected, run SUCCESS가 모두 필요하다.
빈 universe의 공식 동작은 미확정이므로 자동 삭제하지 않는다.
DB 실행 lock을 같은 연결에서 유지하고 전체 run을 한 transaction으로 처리한다.
완전성에 실패한 FULL / source validation 실패는 source 행을 변경하지 않고 FAILED 이력만 저장한다.
SQL 실패는 전체 source/lifecycle/run을 롤백하고 가능한 경우 별도 transaction으로 FAILED 이력을 기록한다.
DB 자체 불가 시 FAILED 이력 저장도 실패할 수 있으며 CLI Report의 고정 code로 보고한다.
재조정 직전 영속 run SUCCESS / 전체 검증 / 실제 last_seen_run_id 건수도 재확인한다.
검증된 FULL의 unseen active만 soft-delete 후보가 된다. 현재 dev FULL은 후보 DRY-RUN만 허용한다.
실제 적용은 controlled test DB에서만 검증하며 dev 적용은 별도 승인 Task 전까지 차단한다. 물리 DELETE 경로는 없다.

DB transaction commit 이후 파일 Report 쓰기가 실패할 수 있다. 이때 run_id를 재사용하지 말고
sync_history의 report_json을 사람 검토로 복원한다. DB와 파일 간 원자성을 주장하지 않는다.

## 후속 경계

## Phase 1B dev FULL

```sh
.venv/bin/python -B scripts/run_full_sync.py collect --profile dev --run-id <new-unique-id>
.venv/bin/python -B scripts/run_full_sync.py verify --run-id <existing-id>
```

첫 응답의 실행 시점 totalCount로 20건 단위 전체 pagination을 계획한다. 최신순·시점 고정 snapshot의 공급자 보장은 미확정이다.
오류·빈 page·count 변동·ID 중복/무효·건수 불일치는 FULL 실패다. 자동 재시도·incremental updtPnttm 요청은 없다.
모든 안전한 응답 byte와 metadata/hash는 data/raw/<run-id>/에 보존한다. Secret 반사 응답은 저장을 거부한다.
원문 재검증과 전체 normalization이 통과한 뒤 DB-only atomic transaction에 진입한다.
실행 lock·쿼리 timeout·협력적 60초 예산을 사용한다. 100건씩 읽기 검증하되 page별 commit은 하지 않는다.
협력적 예산은 진행 중인 blocking SQL을 즉시 중단하는 보장이 아니며 예산을 초과하면 전체 rollback한다.
acquisition.json / result.json은 artifacts/codex/phase1b-full-sync/<run-id>/에 남긴다.
Checkpoint는 page 단위 진행과 로컬 verify 명령만 보존하며 중단된 페이지를 다른 시점과 혼합해 이어 받지 않는다.
실제 soft-delete=0이며 verified SUCCESS FULL만 후보를 계산한다. 실행 실패 시 후보는 미측정(null)이다.
verify는 checksum/계약/ID/완전성/normalization을 오프라인 재검사하며 DB commit 성공을 대체하지 않는다.
DB commit 뒤 읽기 검증이 실패하면 최종 Gate FAIL이고 commit을 rollback했다고 주장하지 않는다.
별도 승인과 새로운 완전한 FULL 없이는 DRY-RUN 이력을 실제 삭제에 재사용할 수 없다.

updtPnttm incremental semantics / scheduler는 후속 검증 대상이다.
본문 Parsing / OCR / AI는 UNMEASURED다. 최신순 공식 보장도 UNCONFIRMED다. GO/DROP을 자동 판단하지 않는다.
기존 sample의 API totalCount=1514는 snapshot 당시 source universe 관찰이고 Pilot 목표 / 적재 대상은 100이다.

공식 참고: [SQLAlchemy transaction](https://docs.sqlalchemy.org/en/20/core/connections.html),
[MySQL dialect](https://docs.sqlalchemy.org/en/20/dialects/mysql.html).
