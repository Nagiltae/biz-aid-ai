# 데이터 파이프라인

최종 Pipeline 계획은 API → Raw → Normalize → MySQL Upsert → 변경 판단 →
Download → Checksum → Parse → Chunk → Embedding → Qdrant다. 구현 범위는 아래 승인된 Phase 1A에 한정한다.

## 현재 도구

`scripts/phase0.py snapshot`은 이미 확보한 공식 JSON/XML 응답을 byte 그대로
data/raw/<run-id>/에 보존하고 SHA-256, 크기, 보존 시각, media type metadata를 만든다.
실제 수집 시각은 --collected-at으로 제공할 때만 기록하고 알 수 없으면 null로 둔다.
잘못된 JSON/XML·중복 key·DTD 응답도 원문을 보존하며 payload_syntax=invalid로 기록한다.
XML 형식 점검은 UTF-8만 지원한다. 다른 encoding 원문은 invalid로 표시하고 보존한다.
snapshot 자체는 HTTP 요청, API envelope 해석, pblancId mapping, key 제거를 수행하지 않는다.
입력에 credential이 포함되지 않은 응답인지 사용자가 확인한다. 원문은 Git에서 제외한다.
`verify-snapshot`은 계약·경로·크기·hash와 형식 상태의 일관성을 검증한다.
checksum PASS는 invalid 원문의 수집 품질 PASS를 뜻하지 않는다.
`init-report`는 모든 지표를 not_measured로 초기화한다. `validate-report`는 로컬 기록 계약만 검증한다.

## 별도 Local API Probe

사용자가 제공한 공식 Request 정보와 실제 Sample은 [External API Contract](../../contracts/external-api/README.md)에 기록한다.
`scripts/bizinfo_probe.py`는 명시적인 로컬 명령으로만 최대 4요청의 Pagination / ID 관찰을 수행한다.
CI는 실제 HTTP를 호출하지 않고 Fixture·mock transport·credential 없는 CLI만 검사한다.
Live 원문은 위 snapshot 도구를 재사용하며 인증키 반사 응답은 저장을 거부한다.
Probe는 필수 --profile dev / prod와 선택된 .env.{profile}만 사용한다. OS Environment가 우선하며 fallback은 없다.
사용자 Secret 파일을 수정하지 않는다. 현재 실제 실행은 dev이며 prod Secret은 읽거나 Live 호출에 사용하지 않는다.
첫 페이지 100건을 최근 100건으로 확정하지 않는다. 실제 관찰 상태는 current-task의 Final Report에서 확인한다.
이 도구는 전체 Collector / Normalize / Download / Parser / Data Gate 측정이 아니다.

## 실제 Gate 진행 전 준비

- 공식 명세와 credential 없는 실제 응답: endpoint·pagination·응답 경로·오류 형태 확인.
- API 품질 표본은 수집 시점 기본 정렬 선두 100건(5×20)으로 승인됐다. 문서 Gate 표본·판정 기준은 별도 Review한다.
- pblancId가 공고와 첨부의 동일성을 보장하는지 확인. 별도 entity matching은 요구하지 않는 설계다.
- 공고 상세 URL과 주 공고문 다운로드 URL을 분리해 확보율 측정.
- 원문과 다운로드 checksum, 실패 원문·이유·재시도 이력을 보존.
- PDF → HWPX → HWP → ZIP 순으로 실제 표·heading·scan·근거 위치를 비교.
- API에 없는 상세 조건·제외·중복지원·지원금·자부담·선정·서류·예외·주의사항을 근거와 대조.

[보고서 양식](../../evals/phase0-report-template.md)에 분자·분모·증거·예외를 기록한다.
[Report 계약](../../contracts/schemas/phase0-report.contract.json)은 upstream API 계약이 아니다.
Raw snapshot metadata 전용 MySQL 모델은 향후 계획이다. Phase 1A는 source_payload JSON을 저장한다.

## 승인된 API 품질 Batch

`scripts/phase0_api_quality.py collect --profile dev --run-id <unique-id>`는 pages 1–5 / rows 20의 5요청만 실행한다.
전체 Collector·자동 재시도·공고문 다운로드가 아니다. Probe HTTP 한도·Raw byte/checksum·overwrite 금지·Secret 보호를 재사용한다.
prod는 설정 로드 전 거부한다. CI는 합성 HTTP / 임시 Raw와 credential 없는 CLI만 검증한다.
12개 주요 field와 첨부 4개는 타입 / nonblank 기준 VALID·MISSING·NULL·BLANK·INVALID로 따로 계수한다.
URL 접속·field 의미는 UNMEASURED이며 INVALID가 아닌 값도 의미상 정확함을 보장하지 않는다.
기간은 분석용 DATE_RANGE / FREE_TEXT / MISSING / INVALID이며 Raw는 수정하지 않는다.
기간 MISSING 분류의 null / blank / key 없음은 별도 원인 count와 원래 field 상태로 보존한다.
확장자 분모는 @로 분리한 유효 파일명 token 수다. URL / 이름 pairing과 Primary Notice 역할은 가설로 유지한다.
Run Artifact는 pages / 실패 / next action과 품질 JSON을 저장한다. 실패 시 기존 Raw를 보존하고 재요청은 새 승인·run-id로 수행한다.
`analyze`는 Run / Raw checksum을 검증해 동일 지표와 Generated Markdown Report를 HTTP 없이 재현한다.
[품질 계약](../../contracts/schemas/phase0-api-quality.contract.json)은 full Gate 계약을 대체하지 않으며 gate_decision=pending을 유지한다.

## 승인된 Document Download Gate

`scripts/phase0_document_download.py`는 source run `api-quality-dev-20260928-01`의 checksum을 검증한 동일 100개 Item만 사용한다.
새 API 수집은 하지 않는다. `download --profile dev --run-id <unique-id>`는 printFlpthNm만 순차 요청한다.
공개 파일 요청에는 API key·Cookie·Authorization·Referer가 없다. dev key는 반사 검출에만 사용하고 prod 파일은 읽지 않는다.
HTTPS / www.bizinfo.go.kr / 공개 atchFileId·fileSn query만 허용하며 Redirect도 같은 경계를 따른다.
최대 Redirect 3회, 파일 25 MiB, socket timeout 15초, Candidate 사이 0.25초는 Local Safety Boundary다.
공급자 공식 Rate Limit이나 안전한 속도 보장이 아니다. Content-Length와 별개로 실제 stream read를 제한한다. 자동 재시도는 없다.

`data/downloaded/<run-id>/manifest.json`은 표본·Raw reference·안전 설정을 고정한다.
각 `<pblancId>/document.bin` / metadata.json은 원본 byte·HTTP·Redirect·host·시각·size·SHA·형식·outcome을 보존한다.
SIZE_LIMIT_EXCEEDED의 저장 byte는 한도 내 prefix이며 observed size는 하한이다. 전체 파일 크기는 미측정이다.
Secret 반사 응답·header·인증 URL은 저장/요청을 거부하며 예외 상세를 출력하지 않는다.
PDF signature, HWP FileHeader signature, HWPX / XLSX ZIP 구조만 식별하며 본문·표·XML 내용을 추출하지 않는다.
형식 식별은 완전한 파일 유효성 검사가 아니다. Content-Type 차이는 Observation이며 filename/actual 차이는 FORMAT_MISMATCH다.
SUCCESS는 완전한 non-empty HTTP 2xx body의 식별 가능한 형식이 filename 확장자와 일치하는 경우다.

원본·metadata·summary-<순번>.json은 exclusive write로 보존한다. 기존 run-id는 --resume에서만 사용한다.
재개는 manifest / 이전 Source / 저장된 모든 checksum과 형식을 검증한 후 미처리 Candidate만 요청한다.
확정 실패는 재시도하지 않는다. 중단된 고립 파일이나 불일치는 중단 후 사람의 검토 대상이며 SUCCESS로 세지 않는다.
Checkpoint는 시작·10개 결과 확정마다·실패·중단·최종 Report용 집계 확정에 순번을 늘려 기록한다.
completed_count=SUCCESS, processed_count=SUCCESS+실패, remaining_count=100-processed_count다.
다운로드 종료 Checkpoint의 completed는 원본·결과가 확정됐다는 뜻이며 전체 Task Validation / Gate 승인이 아니다.
Task 종료는 Control/Input index·check-all의 exit 확인 후 Generated 해석 Report·AGY/Human Review로 기록한다.

`analyze --run-id <id> --output harness/workspace/reports/codex/<report>.md`는 HTTP 없이 source·파일 checksum을 검증해 동일 지표를 재현한다.
기본 분모는 Target 100이며 size / format / hash처럼 실제 body가 필요한 지표는 별도 측정 분모를 명시한다.
Supplementary는 @ token count만 비교한다. 의미상 pairing·Primary 본공고 의미·장기 URL 안정성은 미확정이다.
[Download 계약](../../contracts/schemas/phase0-document-download.contract.json)의 제한은 로컬 설정이며 pending-only Gate를 유지한다.

## Phase 1A Structured Data Pipeline Pilot

사용자 승인으로 [제품 코드](../../data-pipeline/README.md)의 Source Model → Normalizer → Repository 경계를 구현한다.
기존 api-quality-dev-20260928-01의 manifest / 5개 Raw checksum을 고정해 동일 100건만 읽는다.
새 API 조회 없이 dev MySQL에 적재하고 동일 표본 재실행을 검증한다.
공통 [Flyway](../../migrations/README.md)가 schema owner이며 Python은 DDL을 만들지 않는다.
원본 JSON / HTML / URL / @ 파일명 / 기간은 그대로 보존하고 안전한 날짜만 파생한다.
canonical source fingerprint는 DB lifecycle을 포함하지 않는다. 동일 원본은 content NOOP / last_seen 갱신이다.
SAMPLE/PARTIAL의 미관측은 삭제 근거가 아니다. FULL 완전성 검사·run 성공·DB lock을 모두 통과해야 soft-delete한다.
복원은 관측 근거로 SAMPLE에서도 가능하며 source_active는 접수 상태를 뜻하지 않는다.
FULL은 controlled test만 실행한다. 운영 접근·증분 parameter·본문 Parser·Document 제품화·AI는 미구현이다.
[품질 계약](../../contracts/schemas/structured-data-quality.contract.json)은 적재 품질과 completeness를 기록하며 GO/DROP을 판단하지 않는다.
