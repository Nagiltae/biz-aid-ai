# 기업마당 API Contract / 최소 Probe 작업 Report

## 1. 범위와 설계 해석

사용자의 2026-09-27 승인 Task는 Phase 0의 첫 API 근거 확인이다. 최상위 설계와 React / Spring Boot / FastAPI,
MySQL / Qdrant 책임 경계를 유지한다. 전체 Pipeline·100건 측정·제품 기능·GO / DROP을 구현하지 않는다.
Data Pipeline / API Contract Skill을 적용했고 Static 파일은 개별 Registry, Report는 Dynamic Workspace로 관리한다.
과거 AGY Targeted Re-review PASS는 보완 Report에 한정한다. 이 API Task의 독립 Review·Human Review·Gate는 pending이다.

## 2. 공식 Request / Sample Response Contract

사용자가 확인한 GET Endpoint와 9개 query 이름, serviceKey 필수를 CONFIRMED로 기록했다.
serviceKey 외 Optional 여부·default·날짜 형식·한도·key encoding·정렬 보장은 미확정이다.
공급자 명세 전체를 이번에 독립 확보한 것은 아니다. 공식 domain 검색은 결과가 없어 추가 공식 사실의 근거로 사용하지 않았다.
[상세 Contract](../../../contracts/external-api/README.md)와 [기계 계약](../../../contracts/external-api/bizinfo.contract.json)을 작성했다.

제공된 실제 sanitized Sample 10건을 [Fixture](../../../tests/fixtures/external-api/bizinfo-user-sample.json)에 저장했다.
전송 당시 wire byte는 없어 JSON indent만 정리했고 Raw field 값·Unicode·HTML·CRLF·null을 보존했다.
저장된 Fixture SHA-256: `e544fe5e7463687472ce28ea01ea81efbd471fdba49b7dc5f6f977884148aa5a`.
Sample은 Synthetic fixture나 이번 Live 호출로 만든 데이터가 아니다.
response.header와 body.items.item[]·정수 Pagination·20개 관찰 field를 검사한다.
공급자 field 필수성을 추정하지 않고 Probe의 식별용 pblancId만 nonblank string으로 요구한다.
null 허용 세 field, 비정형 기간, HTML, @ 연결 첨부, 모든 계층 Unknown field를 보존한다.
관찰하지 않은 오류 / 빈 결과 / 타입 차이는 실패 분류·원문 보존 대상으로 남긴다.

## 3. 환경변수와 Probe

.env.example에 BIZINFO_API_BASE_URL / BIZINFO_SERVICE_KEY / BIZINFO_DATA_TYPE을 추가했다.
실제 .env를 만들거나 변경하지 않았다. 실제 인증키는 코드·Fixture·Test·로그·Report에 기록하지 않았다.
[Probe](../../../scripts/bizinfo_probe.py)는 stdlib로 최대 4요청·timeout 15초·5 MiB 제한·재시도 없이 실행한다.
이 제한은 Local 안전 설정이며 공급자 공식 한도가 아니다. Compose network_mode=none / read_only와 CI를 유지한다.
CI는 Fixture·mock HTTP·credential 없는 CLI만 실행한다. Local key가 있으면 pages 1 / 2(각 rows 10),
Sample ID PBLN_000000000126771과 미존재를 가정한 Synthetic ID PBLN_999999999999999를 관찰한다.
후자의 실제 미존재를 사전에 보장하지 않는다. ID 반환·단건 / 빈 결과·중복·totalCount·순서를 그대로 분석한다.

key query는 출력하지 않는다. Redirect를 따르지 않으며 URL을 포함할 수 있는 예외는 고정 분류로 출력한다.
응답에 key가 반사되면 Raw를 수정해 저장하지 않고 저장 자체를 거부한다.
비밀 없는 성공 / 실패 응답 byte는 기존 snapshot / SHA-256 계약으로 data/raw에 보존한다.
run-id / 부분 Raw / 출력 충돌을 요청 전에 검사하고 덮어쓰지 않는다.

## 4. 실제 Probe 실행 여부 / 결과

실행: `python3 -B scripts/bizinfo_probe.py --run-id bizinfo-contract-20260927-01`.
실제 .env 없음·비어 있지 않은 인증키 없음. 결과는 **NOT_RUN**, reason=credential_missing, 종료 코드 **3**, 요청 **0회**다.
Local 실행 Evidence: `harness/workspace/artifacts/bizinfo-probe-bizinfo-contract-20260927-01.json`.
이는 ignored Artifact이며 원격 저장소에 포함되지 않으므로 저장소 Markdown 링크의 필수 대상으로 만들지 않는다.
Pagination 결과와 pblancId 단건 / 미존재 동작은 **미측정**이다. 가상 응답 Test를 Live 결과로 기록하지 않는다.
불필요한 Checkpoint는 만들지 않았다.

## 5. CONFIRMED / OBSERVED / UNCONFIRMED

| 구분 | 결과 |
| --- | --- |
| CONFIRMED | 사용자 확인 Endpoint / GET / query 이름 / serviceKey 필수 |
| OBSERVED | 사용자 Sample envelope, 10건 / pageNo=1 / numOfRows=10 / totalCount=1518, 20개 field 타입·null·Raw 예외 |
| OBSERVED | Sample creatPnttm 내림차순과 PDF / HWP / HWPX / ZIP; Live 정렬·확장자 비율 주장이 아님 |
| UNCONFIRMED | 실제 페이지 동작·ID 필터·미존재 ID 오류 / 빈 형태·전체 ID 유일성 / 지속성 |
| UNCONFIRMED | 공급자 newest-first 보장·timezone·필터 default / 한도 / 형식·최근 100건 Rule |
| UNCONFIRMED | print* Primary Notice Candidate / flpth* Supplementary Candidate 역할·첨부 positional pairing |

## 6. 주요 Field 기준 초안 / 다음 Task의 결정

Contract 문서에 pblancId / pblancNm / pblancUrl / jrsdInsttNm / excInsttNm /
pldirSportRealmLclasCodeNm / creatPnttm / reqstBeginEndDe / updtPnttm / trgetNm /
printFlpthNm / printFileNm의 required 후보·null·blank·invalid 미결정 기준을 기록했다.
Sample 타입 검사와 100건 품질 측정 기준은 별개이며 null / blank / missing을 분리한다.
print* 미확보 허용은 측정 초안이지 Sample에서 null을 봤다는 의미가 아니다.
이번 Task에서 Null 비율·확장자 비율·다운로드 / Parsing 성공률·RAG 가치를 만들지 않았다.

다음: 로컬 ignored .env에 key를 설정하고 별도 unique run-id의 Probe Evidence를 Review한다.
공식 정렬 보장 / pagination 한도·ID / 빈 결과와 주요 Field 분모 / invalid를 검토한 뒤
최근 100건 표현·선정·중복 / 동률·시점·등록 / 수정 기준을 사용자와 확정한다.
100건 Gate와 Checkpoint 사용은 별도 승인 Task이며 자동 착수하지 않는다.

## 7. 생성 / 수정 / 삭제 파일과 이유

생성(6):

- contracts/external-api/bizinfo.contract.json: 근거·Request·관찰 Raw 타입·Probe 제한 설정.
- tests/fixtures/external-api/bizinfo-user-sample.json: 실제 sanitized 10건 Contract Evidence.
- scripts/bizinfo_probe.py: 제한된 명시적인 Local HTTP 관찰·Raw / secret 보호.
- tests/contract/test_bizinfo_probe.py: Sample·mock transport·실패 / 비노출 / 보존 회귀.
- tests/integration/test_bizinfo_probe_cli.py: 격리 CLI·NOT_RUN / 오류 / help 회귀.
- harness/workspace/reports/2026-09-27-codex-bizinfo-contract-probe-report.md: 이번 Task의 External Memory.

수정:

- .env.example: 사용자 확정 세 변수·키 보관 경계.
- contracts/external-api/README.md, contracts/README.md: 공식 Request와 Sample 관찰·미확정·주요 Field 초안 구분.
- harness/registry.json: 새 정적 계약·Fixture·실행 코드만 등록하고 active Report 교체. Report 개별 required 등록 없음.
- harness/workspace/current-task.md: 승인된 API Task로 교체·현재 Review pending.
- AGENTS.md, harness/docs/architecture.md, harness/docs/data-pipeline.md: 최소 Probe를 실제 구현 목록에 동기화.
- harness/rules/data-source-rules.md, harness/rules/file-boundaries.md: 승인된 sanitized Fixture 예외와 명시적 Probe 경계.
- harness/docs/testing.md, tests/README.md, scripts/lib/validate.py: 오프라인 API Contract·mock / CLI와 Live 미측정 구분.
- README.md: 실행 환경·명령 안내와 과거 독립 Review 범위 동기화.
- harness/docs/workflow.md: 과거 Task명 대신 현재 active Report의 Review 범위로 설명.
- harness/changelog/harness-changes.md: 승인 근거·변경 경계·현재 NOT_RUN / pending 기록.

삭제: 없음. PROJECT_DESIGN.md·과거 AGY 원문 / Codex Report·scripts/phase0.py·기존 Raw / Gate 계약은 변경하지 않았다.
주석은 한글 WHY / EXCEPTION 중심으로 redirect key 전달·.env 셸 비실행·예외 URL 비노출·Raw key 반사 거부·
Unknown field / 비정형 Raw 보존·부분 실행 충돌의 이유에만 작성했다.

## 8. Tests / Validation / 최종 Git 상태

작성한 테스트: 새 Contract 23개·CLI Integration 3개. 항상 오프라인이며 credential 있는 CI에서도 실제 HTTP를 호출하지 않는다.
Sample 구조·header·잘못된 envelope·정수 Pagination·ID 필수·null·비정형 / HTML / @ / 개행·unknown field·
Sample 순서·고정 4 mock 요청·HTTP / XML 실패 원문·key 반사 / URL 예외 / CLI 비노출·env 우선순위·redirect·
덮어쓰기 / 부분 Raw 충돌·ID 결과와 100건 Rule 미확정을 검증한다.

실제 실행: 새 Contract 23개 PASS, 새 CLI 3개 PASS, Local Probe NOT_RUN / exit 3.

최초 전체 check-contract 실행은 76개 중 9개가 실패했다. Report의 ignored Local JSON에 대한 Markdown 링크가
Git 파일만 복사하는 격리 Harness fixture에서 깨져 원래 검사까지 도달하지 못한 것이 원인이었다.
Artifact 경로를 일반 텍스트로 바꾸었으며 Harness / 링크 검사를 완화하거나 Fixture에 Artifact를 추가하지 않았다.
수정 후 Report 최종 작성 전에 check-all을 실제 재실행하여 종료 **0**을 확인했다.

| Report 최종 작성 전 실제 검사 | 결과 |
| --- | --- |
| check-format / check-lint | 각각 단독 실행 및 check-all 내부 실행 PASS / 0 |
| check-contract | 재실행에서 전체 76개 PASS / 0 (새 23개 포함) |
| check-integration | 전체 7개 PASS / 0 (새 3개 포함) |
| check-comments | 한글 설명성 주석 37개 검사 PASS / 0 |
| check-harness | PASS / 0; 과거 AGY pass, 현재 Report Review / Human Review pending |
| check-git-tracked | check-all 내부 실제 실행 PASS / 0 |
| check-all | 전체 적용 검사 PASS / 0; Live / 제품 검증은 미측정 / 미구현으로 출력 |

기록: `harness/workspace/artifacts/bizinfo-contract-probe-preliminary.log` (ignored Local 로그).
PROJECT_DESIGN·phase0.py·기존 Raw / Gate 계약·AGY 원문·과거 Codex Report 9개는 HEAD와 byte가 같음을 확인했다.

### Report 작성 후 최종 실행과 동결

이 Report와 current-task를 최종 작성하고 수정 경로만 다시 Git index에 반영한다.
그 뒤 요청한 format / lint / contract / integration / comments / harness / git-tracked / all을 순서대로 실제 실행한다.
최종 check-all 뒤에는 추적 파일을 수정하지 않으며 결과는
`harness/workspace/artifacts/bizinfo-contract-probe-final-validation.log`와 최종 응답에 기록한다.
이 Report의 위 PASS는 이미 실행한 사전 결과다. 아직 실행하지 않은 최종 결과를 미리 PASS로 선언하지 않는다.
마지막으로 git status / git diff --cached --stat / git diff --cached --check /
git ls-files --others --exclude-standard를 실행하고 동결 전후 추적 파일 byte / index 동일성을 확인한다.

### Git 상태

시작 당시 clean dev / origin/dev였다. Report 최종 작성 직전 새 6개·수정 16개, 총 22개를 stage했고
Untracked 프로젝트 파일은 **0개**, git diff --cached --check는 종료 **0**이었다. 삭제는 없다.
이번 마지막 Report / current-task 갱신도 재stage한 뒤 최종 검증한다.
Commit·Push·Merge·Branch 변경은 수행하지 않았다. 최종 Git 명령의 실제 출력은 위 동결 후 로그와 최종 응답으로 전달한다.

## 9. 남은 Risk / 미구현

Live credential 부재로 실제 Pagination / ID / 오류 동작·정렬·100건 Rule은 미결정이다.
관찰 타입과 다른 적법 응답은 계약 차이로 실패할 수 있으며 Raw Evidence와 사용자 Review로 별도 확장한다.
서로 다른 요청 시점의 dataset 변동은 totalCount / 순서 / 중복 관찰에 영향을 줄 수 있다.
회사·첨부의 동일성, 공고문 후보 역할과 ZIP / Parser 처리, 주요 Field 기준은 이번에 확정하지 않는다.
제품 기능·전체 Collector·100건 본 수집·Download·Parser·DB / Migration·AI / LangSmith·Gate 판단은 미구현이다.

## 10. 교체 전 current-task 전체 보존

```markdown
# Current Task

## Goal / Context

Static Harness와 Dynamic Workspace의 Registry Drift 책임을 분리한다.
현재 Phase는 phase0-preparation이며 사용자의 2026-09-27 Debugging 요청으로 시작했다.
Rollback 이후 clean dev에서 check-harness / check-all의 동일 실패를 재현했다.
이전 Task 전체는 [이번 Report](reports/2026-09-27-codex-dynamic-workspace-fix-report.md)에 보존한다.
보완 Report의 독립 AGY Targeted Re-review: review_complete / PASS.
현재 수정 Task의 독립 Review·Human Review·Data Gate: pending.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[Registry](../registry.json) → [Workflow](../docs/workflow.md) →
[Debugging](../skills/debugging/SKILL.md) → [AGY Fix Review](reports/agy-harness-fix-review.md).

## Allowed Scope / Forbidden Scope

Registry·validate.py·Harness 회귀 테스트, 필요한 최소 Workflow / Reviewer / Checkpoint 안내·Changelog·External Memory.
제품 기능·API 수집·Parser·DB·RAG·LangGraph·Indexing·추정 API 환경변수·Gate go/drop 구현 금지.
Commit·Push·Merge·프로젝트 Branch 변경 금지. 설계·AGY 원문·과거 Codex Report·Raw / Contract 정책은 보존한다.

## Acceptance / Validation / Expected Report

새 추적 Report·Checkpoint는 개별 등록 없이 통과하고 코드·symlink·Untracked·ignore는 실패한다.
정적 Registry·Skill / Rule·AGENTS Routing·독립 Evidence / checksum·자기 승인 방지는 유지한다.
format / lint / contract / integration / comments / harness / git-tracked / all을 실제 실행한다.
[Final Report](reports/2026-09-27-codex-dynamic-workspace-fix-report.md).
Final Report와 Git index 구성 후 최종 check-all을 실행한다. 이후 추적 파일 변경 시 재검증한다.
상태: 정책 수정·53개 Contract / Harness와 4개 Integration·Report 작성 전 check-all 통과.
Final Report를 완성했으며 최종 Git index 구성 후 검증과 Git 확인을 수행한다. 최종 종료 코드는 Report의 로그와 최종 응답을 따른다.
다음 Task는 별도 사용자 승인 후에만 시작한다.
```
