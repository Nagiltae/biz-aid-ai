# Harness 변경 이력

## 2026-09-28 — Phase 1B dev FULL Structured Sync

사용자 승인으로 첫 페이지의 실행 시점 totalCount 기반 전체 pagination과 페이지별 Raw snapshot / hash 재검증을 추가한다.
ID / count / 완전성 / normalization 검증이 끝나기 전에 DB mutation을 시작하지 않는다.
기존 모델·fingerprint·lifecycle·Flyway V1/V2를 재사용하고 DB-only atomic transaction / 협력적 시간 예산을 적용한다.
첫 Live FULL과 현재 dev 실행은 soft-delete 후보 DRY-RUN만 허용하며 실제 삭제 경로는 차단한다.
장기 FULL 안전 규칙을 Source / Pipeline / Skill / Contract에 기록하고 mock API + 실제 test DB 회귀로 연결한다.
과거 AGY 승인은 보존하며 이번 Task 독립 Review는 pending이다. Generated 산출물은 non-gating이다.
결과: [Phase 1B Report](../workspace/reports/codex/2026-09-28-phase1b-full-sync.md).

## 2026-09-27 — 최초 기반 구축

- 원인: 설계만 있고 Context·Registry·검증·External Memory가 없었다.
- 범위: Phase 0 준비에 필요한 Harness와 로컬 파일 도구·계약·테스트·CI.
- 전체 서비스·DB·Pipeline·RAG를 만들지 않도록 실제 구현 목록을 Registry로 고정한다.
- 미구현 제품 검증은 N/A로 공개한다. Gate 통과와 AGY 승인은 독립 상태로 둔다.
- Raw byte 보존과 hash 검증, 미측정 보고서 계약으로 다음 데이터 실험의 증거를 준비한다.
- 규칙 완화·삭제 없음. 최상위 설계 수정 없음.
- 실행 결과: [Codex Report](../workspace/reports/codex/2026-09-27-codex-harness-report.md).
- AGY 검토: pending.

## 2026-09-27 — AGY Initial Review 보완

- 근거: [독립 AGY Initial Review](../workspace/reports/agy/agy-initial-harness-review.md), PASS WITH FIXES.
- M-1: 불필요한 workflow/reference는 생성하지 않고 Target와 현재 Skill 구조를 명시.
- M-2: Compose·ignore·Registry·Context 크기·Review 증거·Raw 무결성·출력 충돌의 WHY 주석 보강.
- M-3 / I-4: Checkpoint Format·복원과 current-task 교체·이전 상태 보존 절차 정의.
- M-4: 공식 명세 전 환경변수 추정 없음. .env.example 보존.
- M-5: pending-only Gate 계약은 유지하고 측정·Human Review 후 확장 Task 절차만 정의.
- 사용자 요청에 따라 pending 고정 검사를 Evidence 검증이 필요한 review_complete 전환으로 교체.
  독립 원문·검토 대상 hash는 고정하며 자기 Report를 Evidence로 사용할 수 없도록 검증.
- Initial Review는 과거 Foundation 대상이다. 이번 보완의 후속 Review·Human Review·Data Gate는 pending.
- IDE가 생성한 로컬 .idea metadata만 제외하고 같은 경로의 코드·문서 숨김은 거부.
- 제품 기능·추정 upstream·기술 도입·Git 승격 없음.
- 결과: [보완 Report](../workspace/reports/codex/2026-09-27-codex-harness-fix-report.md).

## 2026-09-27 — Dynamic Workspace Registry Drift 수정

- 재현: clean dev에서 AGY Targeted Re-review 파일만 unregistered로 check-harness / check-all이 실패했다.
- 원인: 정적 Harness 구조와 계속 생성되는 External Memory에 같은 개별 등록 의무를 적용했다.
- required_files는 정적 필수 목록, dynamic_paths는 바로 아래 reports / checkpoints Markdown 경계로 분리한다.
  기존 Workspace README는 정적 필수 파일로 유지하고 새 기록은 Git 추적·ignore·일반 파일·symlink·실행 권한을 검사한다.
- 일반 Report 허용과 Trusted Evidence를 분리한다. 사용자 제공 Targeted Re-review PASS의 원문·검토 대상 hash만 별도 등록한다.
  현재 수정 Task의 Review·Human Review·Data Gate는 pending이다. AGY 원문·과거 Report는 수정하지 않는다.
- 실제 파일을 복사하는 fixture와 동적 기록·정적 drift·숨김·자기 승인 방지 회귀를 추가한다.
- Final Report → 최종 Git 상태 구성 → check-all → 동결 순서를 명시한다. 이후 변경 시 기존 Final 결과는 무효다.
- 결과: [수정 Report](../workspace/reports/codex/2026-09-27-codex-dynamic-workspace-fix-report.md).

## 2026-09-27 — 기업마당 Request / Sample Contract와 최소 Probe

- 근거: 사용자가 확인한 공식 GET Endpoint·query 정보와 제공한 실제 sanitized 10건 Sample.
- 관찰 Raw 계약·Fixture checksum·nullable / 비정형 / HTML / @ / unknown field 보존 Tests를 추가한다.
- 세 BIZINFO 환경변수를 명시하며 실제 key와 Live 응답은 Git에 넣지 않는다.
  사용자 제공 sanitized Fixture만 Source 규칙의 명시적인 추적 예외로 둔다.
- 최대 4요청의 명시적인 Local Probe만 허용한다. CI는 Fixture·mock HTTP·키 없는 CLI를 실행한다.
  Compose의 네트워크·read-only 경계, Raw hash / overwrite, pending-only Gate는 유지한다.
- 현재 key가 없어 Live NOT_RUN이며 최근 100건 Rule·정렬 / ID 보장은 미확정이다.
- 현재 Report로 Task를 전환하며 과거 독립 Evidence는 보존하고 현재 Review는 pending으로 구분한다.
- 결과: [API Contract / Probe Report](../workspace/reports/codex/2026-09-27-codex-bizinfo-contract-probe-report.md).

## 2026-09-28 — Profile 격리와 dev Live Probe

- 사용자 승인 dev / prod만 필수 CLI로 선택하며 Branch / APP_PROFILE 자동 선택·Profile / legacy .env fallback을 금지한다.
- 사용자 Secret 파일은 수정·삭제·stage하지 않는다. 기존 ignore는 유지하고 Secret 추적 / example 숨김 / ignore 누락 회귀를 추가한다.
- OS 우선·셸 비실행·선택 파일만 read·prod runtime 주입·NOT_RUN / key 비노출을 합성 오프라인 Test로 검증한다.
- 오프라인 전체 PASS 후 dev 4요청: 두 페이지 10건씩 / totalCount=1514 / 중복 없음 / 관찰 내림차순, 알려진 ID 1건 일치.
- Synthetic ID는 03 NODATA_ERROR / items={}를 관찰해 기존 Probe exit 1을 보존했다. 오류를 가짜 PASS로 바꾸지 않는다.
- Raw 네 개의 byte / checksum을 검증했다. prod 실제 읽기·Live 호출, 100건 본 수집·제품 기능·Gate 판단 없음.
- 최근 100건 Rule과 공식 정렬 보장은 미확정이며 현재 독립 Review / Human Review는 pending이다.
- 결과: [Profile / dev Live Report](../workspace/reports/codex/2026-09-28-codex-bizinfo-profile-live-probe-report.md).

## 2026-09-28 — Phase 0 API 품질 Task

사용자 승인에 따라 명시적 Negative Probe의 EXPECTED_NO_DATA를 실제 API 오류와 분리했다.
기본 정렬 선두 100건의 dev 전용 5×20 Batch / Raw 재현 분석 / 품질 계약 / 오프라인 회귀를 추가했다.
전체 Collector·다운로드·DB·AI는 추가하지 않고 pending-only Gate / Trusted AGY Evidence / Secret 정책을 유지한다.
실제 실행 결과와 변경 이유는 current-task의 Final Report에 기록한다.

## 2026-09-28 — 제한된 Document Download Gate

사용자가 동일 API 표본 100개의 Primary Candidate 다운로드를 승인했다. 별도 dev 도구·로컬 안전 계약·mock 회귀를 추가한다.
Static Registry에는 코드 / 계약 / Test만 등록하며 Report / Checkpoint는 기존 Dynamic 정책으로 추적한다.
API / prod Secret / Supplementary / Parser / GO-DROP·독립 Review Guardrail은 유지한다.
체크포인트는 결과별 원문 checksum에서 재개하며 과거 AGY PASS를 이번 Task 승인으로 재사용하지 않는다.

## 2026-09-28 Phase 1A 사용자 승인

구조화 데이터 제품 Pilot / dev MySQL / 공통 Flyway를 사용자 승인으로 추가했다.
Static Registry에 제품·migration·tests를 등록하고 Dynamic Report 규칙과 AGY 독립 Evidence 검증은 보존한다.
setup / CI는 Python 제품 dependency, integration은 실제 dev MySQL을 검증한다. 기존 phase0 네트워크·mount 경계는 그대로다.
기존 DB 없음 문구만 실제 구현 범위로 동기화한다. 이번 Task Review는 pending이며 이전 AGY PASS를 재사용하지 않는다.

## 2026-09-28 — Profile / Dev MySQL 포트 정책 정리

사용자 최종 정책에 따라 dev / prod 설정을 각 Profile 파일로 통일하고 Dev Host MySQL을 3306으로 전환했다.
Secret 생성과 별도 DB 설정 fallback을 제거했으며 기존 계정·volume·Pilot·Flyway 계보를 보존한다.
정적 Registry / Dynamic Report / AGY 독립 검토 규칙은 유지한다. 새 회귀와 최종 검증을 별도로 기록한다.
결과: [환경 정책 Report](../workspace/reports/codex/2026-09-28-codex-env-port-policy-report.md).

## 2026-09-28 — 사용자 credential 재검증과 Database COMMENT 정책

사용자 변경 credential을 유지하고 root 준비 연결을 실제 인증에 성공한 로컬 TCP로 명시했다. 계정·비밀번호는 변경하지 않는다.
적용된 V1을 보존하는 신규 V2로 application Table / Column COMMENT만 추가한다.
DB 규칙·Migration Skill·Testing 문서를 연결하고 실제 dev/test schema 전체의 COMMENT 누락·placeholder를 Integration / check-all에서 실패시킨다.
새 업무 테이블도 자동 탐색하며 Flyway 내부 테이블만 제외한다. COMMENT 외 정의와 기존 Pilot 100건 보존을 검증한다.
사용자 승인으로 example credential placeholder만 비웠으며 Secret 파일과 과거 Report는 보존한다.
현재 독립 Review는 pending이다. 결과: [Database COMMENT Report](../workspace/reports/codex/2026-09-28-codex-database-comments-report.md).

## 2026-09-28 — Workspace output lifecycle / Validation boundary

사용자 승인으로 workspace 전체를 Inventory하고 current-task 1개·정적 README 2개와 실행 산출물을 분리한다.
Report/Checkpoint Markdown과 Artifact JSON/log는 non-gating이며 미추적·ignore·공백·존재·index 상태로 build를 실패시키지 않는다.
format/lint/comments·Git diff·Registry/links의 공유 파일 목록을 바꾸고 Control/Input strict 검증과 command 실패 전파를 유지한다.
AGY 참조와 자기 승인 방지는 strict metadata로 보존하며 원문 checksum / 누락은 별도 non-gating 신뢰 상태로 표시한다.
committed 원문은 보존하고 HEAD에 없는 staged 생성 Report 7개는 로컬 파일을 유지한 채 index만 제거한다.
최종 검증 뒤 새 Generated Report를 작성하며 생성물만 추가됐을 때 재검증하지 않는다. Phase 1A 제품·Migration·Secret은 변경하지 않는다.
결과: [Workspace lifecycle Report](../workspace/reports/codex/2026-09-28-codex-workspace-lifecycle-report.md).

## 2026-09-28 — Generated Output Producer / Task별 보관

사용자 승인으로 Report / Artifact 전체 Inventory와 정적·실행·accepted·과거 Evidence 참조 그래프를 만든다.
원문을 보존해 Codex/AGY 전용 디렉터리와 Task별 Artifact로 옮기며 참조 없는 superseded 중간 로그만 명시적으로 정리한다.
accepted review는 경로만 갱신하며 hash·verdict·상태를 바꾸지 않는다. historical Report 내부는 relocation mapping으로 보완한다.
Registry / Agent 지침에 Producer 출력 경로를 고정하고 current-task·static anchor strict / generated non-gating 경계는 유지한다.
기존 도구와 제품 CLI의 입출력 참조만 이동 위치로 갱신한다. 제품 데이터 처리·DB·Migration·checkpoint·Secret 변경은 없다.
결과: [Output cleanup Report](../workspace/reports/codex/2026-09-28-workspace-output-cleanup.md).

## 2026-09-28 — Phase 2 Full Document Acquisition

사용자 승인으로 검증된 Phase 1B dev DB를 Source로 전체 문서 후보의 원본 byte와 provenance metadata를 수집한다.
V1/V2를 보존한 신규 V3, 제품 documents package, 얇은 CLI, 품질 계약과 offline/MySQL 회귀를 정적 Registry에 추가한다.
공개 요청에는 인증정보를 전달하지 않으며 순차 요청·자동 retry 0·redirect/size/timeout·HTML 거부·exclusive 저장을 적용한다.
URL/SHA dedupe 뒤에도 모든 pblancId/source field/token relation을 보존한다. Parser/OCR/AI와 prod는 범위 밖이며 현재 Review는 pending이다.

## 2026-09-29 — Phase 2.5 S3 Document Storage

사용자 승인으로 Phase 2의 3,231개 고유 binary를 고정 dev S3의 content-addressed object와 연결한다.
수동 구현의 metadata-link PUT 가능성, MySQL rowcount 재실행 의존, cached HEAD-only 검증, write smoke를 제거했다.
V4는 검증된 S3 위치 metadata만 추가하고 legacy `storage_path`와 로컬 1.6GB corpus를 보존한다.
로컬 SHA/S3 HEAD checksum 전수 검증 뒤 3,288 relation을 원자적으로 연결하고 실제 S3 byte로 Phase 2 run을 재검증한다.
prod/upstream HTTP/Parser/S3 삭제는 수행하지 않으며 AGY 독립 Review와 로컬 삭제 사용자 승인은 pending이다.
