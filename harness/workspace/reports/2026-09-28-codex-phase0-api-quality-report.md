# Phase 0 API 품질 작업 Report — 2026-09-28

## 1. Probe Exit Semantics 수정

SUCCESS / EXPECTED_NO_DATA / API_ERROR / TRANSPORT_ERROR / CONTRACT_ERROR를 구분했다.
03 NODATA_ERROR는 일반 성공이 아니다. 계약의 presumed_missing_id를 요청하는 명시적 Negative plan에서만
HTTP 200, 03 / NODATA_ERROR, items={}, numOfRows=0, totalCount=0, pageNo echo의 관찰 형태를 EXPECTED_NO_DATA로 분류한다.
page1 / page2 / known_id / 품질 Batch의 03은 API_ERROR다. malformed Negative는 CONTRACT_ERROR이며 HTTP 실패는 TRANSPORT_ERROR다.
Positive 전부 SUCCESS이고 Negative가 EXPECTED_NO_DATA일 때 Probe exit=0이다.
Negative가 00을 반환하면 실제 SUCCESS와 expected outcome이 달라 exit=1이다. Credential 없음은 NOT_RUN / exit=3을 유지한다.
기존 strict item Contract는 유지하고 품질 Batch는 Envelope 뒤에 field를 별도 계수해 이상 행이 분모에서 사라지지 않게 했다.

기존 dev Probe 4요청의 Raw / Report / 당시 exit 1은 수정하지 않았다.
이번 Task에서는 Probe Live 재실행 없이 합성 회귀로 새 exit 의미를 검증했고, 실제 HTTP는 품질 Batch의 5회뿐이다.

## 2. 100건 Sample 정의 / 설계 해석

**CONFIRMED — 사용자 승인 규칙**: 수집 시점 API 기본 정렬 기준 선두 100건.
pageNo=1–5 / numOfRows=20, 최대 5요청 / 100개 Item / 재시도 없음.
최근 100건·공식 newest-first 표본이라고 정의하지 않는다. 중복 Item을 제거하거나 부족분을 추가 요청으로 채우지 않는다.
별도 작은 Script를 선택했다. Probe는 4요청의 계약 관찰, 품질 Script는 고정 표본 수집·집계·재현을 담당하며 HTTP / Raw 경계만 재사용한다.
PROJECT_DESIGN.md의 전체 Pipeline을 구현하지 않는다. registry phase0-preparation은 기존 Harness 상태를 유지하며 이번 결과는 API 측정 부분이다.
full Gate / 문서 / Parsing / RAG / GO-DROP·서비스 DB 계약을 API 지표로 대체하지 않는다.

## 3. 실행 Run 정보

run_id: api-quality-dev-20260928-01 / profile: dev.
UTC started_at=2026-09-27T15:55:06.459420+00:00 / completed_at=2026-09-27T15:55:07.418004+00:00.
KST 2026-09-28 00:55:06–07이다.
requested_pages=[1,2,3,4,5] / requested_rows_per_page=20 / sample_target=100.
successful_pages=[1,2,3,4,5] / failed_pages=[] / total_items_received=100.
unique_pblanc_ids=100 / duplicate_pblanc_ids=[] / observed_total_counts=[1514,1514,1514,1514,1514].
collection_status=COMPLETED / http_requests_attempted=5 / 수집 CLI exit=0.
prod 요청 0회, 공고문 URL 요청·다운로드 0회, 자동 재시도 0회다. 요청은 승인 Endpoint의 GET뿐이다.

Local Run / metrics: harness/workspace/artifacts/bizinfo-quality-api-quality-dev-20260928-01.json (ignored).
실행 출력: harness/workspace/artifacts/phase0-api-quality-live-20260928.log (ignored).
Run / Raw SHA 검증 뒤 HTTP 없이 analyze를 두 번 실행해 JSON 재현과 아래 tracked Markdown을 생성했다.
원본 Run / metrics와 reproduced JSON이 정확히 일치했다.

[기계 생성 Data Quality Report](2026-09-28-phase0-api-data-quality-report.md).

## 4. Page별 결과 / Pagination 품질

| Page | HTTP | resultCode / resultMsg | pageNo echo | numOfRows echo | Items | totalCount | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 200 | 00 / NORMAL_SERVICE | 1 | 20 | 20 | 1514 | SUCCESS |
| 2 | 200 | 00 / NORMAL_SERVICE | 2 | 20 | 20 | 1514 | SUCCESS |
| 3 | 200 | 00 / NORMAL_SERVICE | 3 | 20 | 20 | 1514 | SUCCESS |
| 4 | 200 | 00 / NORMAL_SERVICE | 4 | 20 | 20 | 1514 | SUCCESS |
| 5 | 200 | 00 / NORMAL_SERVICE | 5 | 20 | 20 | 1514 | SUCCESS |

Page Request Success=5/5 (100%). echo 일치=5/5. 페이지 누락·Item count 불일치·관찰 totalCount 변화는 각각 0이다.
totalCount의 일반 불변성이나 수집 중 데이터 변경 부재를 보장하지 않는다. 변화는 자동 실패가 아닌 Observation으로 처리한다.
실패 시 Run의 successful_pages / failed_pages / next_action을 확인하고 원문을 보존한다.
이번 next_action=review_quality_evidence다. 5 Page Run이므로 새 Checkpoint / Resume Framework를 만들지 않았다.

## 5. 실제 Item 수 / pblancId 품질

Actual Items=100 / target=100. ID key 존재 100/100 (100%) / usable nonblank string 100/100 (100%).
MISSING=0, NULL=0, BLANK=0, INVALID=0. unique count=100.
중복된 ID 종류=0 / 중복 추가 행=0. 페이지 내부 / 페이지 간 중복 없음.
중복을 제거하지 않은 원래 100개 Item을 모든 품질 비율의 분모로 사용한다.
이 결과는 이번 표본의 유일성이며 전체 Dataset의 ID 지속성·전역 유일성을 보장하지 않는다.

## 6. 주요 Field 품질

각 cell은 Count / Ratio이다. VALID는 제공 Sample에서 관찰한 타입에 맞는 nonblank string이다.
URL 문법·접속 가능성·기관 / 대상 의미·timestamp semantics는 이번 INVALID 정의에 포함하지 않으며 UNMEASURED다.
null / blank / key 없음과 wrong type을 분리한다. 서비스 필수성을 공급자 보장으로 확정하지 않는다.

| Field | VALID | MISSING | NULL | BLANK | INVALID |
| --- | --- | --- | --- | --- | --- |
| pblancId | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| pblancNm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| pblancUrl | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| jrsdInsttNm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| excInsttNm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| pldirSportRealmLclasCodeNm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| creatPnttm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| reqstBeginEndDe | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| updtPnttm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| trgetNm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| printFlpthNm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| printFileNm | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |

## 7. 신청기간 분포

Raw String은 그대로 보존한다. 분석용 날짜 범위는 YYYY-MM-DD ~ YYYY-MM-DD 형식과 달력 / 시작≤끝을 검사하며 서비스 날짜로 변환하지 않는다.

| 분석 분류 | Count | Ratio |
| --- | --- | --- |
| DATE_RANGE | 82 | 82% |
| FREE_TEXT | 18 | 18% |
| MISSING | 0 | 0% |
| INVALID | 0 | 0% |

FREE_TEXT 실제 관찰: 예산 소진시까지 13, 세부사업별 상이 1, 모집 완료시 1, 상시 접수 1, 세부신청별 상이 1, 선착순 접수 1.
기간 분류 MISSING은 분석에서 사용 불가한 상태지만 별도 period_unavailable_reasons와 원래 field 품질에서 MISSING / NULL / BLANK를 구분한다.
이번 세 원인 count는 실제 측정 결과 모두 0이다.

## 8. Attachment Metadata 분포

분모는 100개 Item이다. Key 존재율과 usable/nonblank 확보율을 구분한다.

| Field | Key 존재 | VALID | NULL | BLANK | MISSING | INVALID |
| --- | --- | --- | --- | --- | --- | --- |
| printFlpthNm | 100 / 100% | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| printFileNm | 100 / 100% | 100 / 100% | 0 / 0% | 0 / 0% | 0 / 0% | 0 / 0% |
| flpthNm | 100 / 100% | 86 / 86% | 14 / 14% | 0 / 0% | 0 / 0% | 0 / 0% |
| fileNm | 100 / 100% | 86 / 86% | 14 / 14% | 0 / 0% | 0 / 0% | 0 / 0% |

URL / Filename positional pairing과 실제 접근 성공은 검증하지 않았다.

## 9. Filename 확장자 분포

분모는 각각 @로 분리한 nonblank filename의 token 수다. 프로그램 비율·실제 MIME·Parsing 성공률이 아니다.
NULL filename에서는 token을 만들어 UNKNOWN으로 계수하지 않는다. 모르는 suffix는 OTHER, suffix 없는 token은 UNKNOWN이다.

| 확장자 | printFileNm token 100개 | fileNm token 138개 |
| --- | --- | --- |
| PDF | 70 / 70% | 29 / 21.0145% |
| HWP | 15 / 15% | 50 / 36.2319% |
| HWPX | 15 / 15% | 45 / 32.6087% |
| ZIP | 0 / 0% | 12 / 8.6957% |
| OTHER | 0 / 0% | 2 / 1.4493% |
| UNKNOWN | 0 / 0% | 0 / 0% |

OTHER 2개는 실제 suffix XLSX이며 page 2 / item_index 0, page 5 / item_index 1에서 관찰했다. Index는 0부터 시작한다.
확장자만 집계했고 어떠한 파일도 다운로드하지 않았다.

## 10. Ordering Observation

creatPnttm을 관찰 형식 YYYY-MM-DD HH:MM:SS로 비교했다.
5 Page 내부, 1→2 / 2→3 / 3→4 / 4→5 경계와 전체 100건 모두 **Observed descending order**다.
동률은 내림차순 비교에 허용한다. timezone·등록일의 공식 의미·안정적 tie-break·newest-first 보장은 UNCONFIRMED다.
이번 한 시점 표본의 순서를 공식 Contract로 승격하지 않는다.

## 11. Primary Notice 가설

print URL + filename usable=100/100, print*와 flpth* / fileNm 동시 usable=86/100.
printFileNm에 공고 포함 91건, 공고문 포함 47건, 안내문 포함 5건이다. keyword count는 겹치므로 합산하지 않는다.
Primary Notice Candidate / Supplementary Attachment Candidate 역할을 지지하는 metadata 관찰이지만 역할 확정은 **UNCONFIRMED**다.
본문·첨부 구분·추가정보·URL pairing은 다음 별도 Document Gate에서 실제 검증해야 한다.

## 12. Exception Case / 미측정

기계 Report의 exceptions에 page / 0-based item_index / field / 상태를 보존했다.
이번 예외는 flpthNm NULL 14 + fileNm NULL 14 = field 상태 기록 28개다. 28개 공고 실패라는 뜻이 아니다.
NULL은 기존 Sample에서 허용되는 상태이며 자동 API 실패로 처리하지 않는다.
FREE_TEXT 18건·XLSX metadata 2 token을 별도로 관찰했으며 삭제·강제 정규화하지 않았다.
Positive API / Transport / Envelope 실패·ID 중복·INVALID period는 이번 실제 Run에서 0이었다.
다운로드·Parsing·URL reachability·field 의미·RAG 추가정보 가치·자동화 가능성은 **UNMEASURED**다.
GO / DROP은 판단하지 않고 gate_decision=pending을 유지한다.

## 13. Raw Evidence / 재현

Raw는 ignored data/raw/ 아래에 HTTP response byte 그대로 보존한다. request metadata에는 dataType / pageNo / numOfRows만 포함한다.
인증키·serviceKey·인증 query URL을 metadata / 로그 / Report에 저장하지 않는다.
각 Raw에 run_id·collected_at·SHA-256을 연결하며 5개 모두 기존 verify_snapshot을 통과했다.
기계 Data Quality Report에 각 Page Raw metadata 상대 경로·수집 시각·checksum이 모두 기록돼 있다.

재현 명령 (출력은 기존 파일과 다른 새 이름을 사용):

~~~bash
python3 -B scripts/phase0_api_quality.py analyze --run-id api-quality-dev-20260928-01 --output harness/workspace/artifacts/quality-recomputed-new.json
python3 -B scripts/phase0_api_quality.py analyze --run-id api-quality-dev-20260928-01 --output harness/workspace/reports/quality-recomputed-new.md --markdown
~~~

Run Artifact / Raw checksum으로 재현하며 HTTP를 호출하거나 환경 파일을 source하지 않는다.
Raw와 Artifact는 개발환경 Local Evidence라 fresh clone에는 없고, tracked 품질 Report가 측정 요약을 보존한다.
실제 sanitized Sample fixture와 synthetic 5×20 Test, 이번 Live 100건은 서로 다른 Evidence다.

## 14. 생성 / 수정 / 삭제 파일과 이유

Task 시작에는 이전 작업의 25개 staged 파일이 있었다. 이를 보존하고 이번 변경을 시작 byte와 비교했다.
생성 6개 / 기존 파일 수정 19개 / 삭제 0개다. 이전 Task의 .env.example·workflow·harness 정책 회귀·기존 Reports / Fixture는 추가 수정하지 않았다.

### 생성 파일

| File | 이유 |
| --- | --- |
| contracts/schemas/phase0-api-quality.contract.json | 사용자 승인 표본·field 상태·기간·확장자·pending 설정의 로컬 계약. |
| scripts/phase0_api_quality.py | dev 전용 5요청 수집·Raw checksum 재현 분석·기계 JSON / Markdown 생성. |
| tests/contract/test_phase0_api_quality.py | 합성 5×20의 품질·오류·Secret·Raw·prod 거부 회귀 16개. |
| tests/integration/test_phase0_api_quality_cli.py | credential 없는 CLI·dev 제한·재현·overwrite·출력 경계 회귀 5개. |
| harness/workspace/reports/2026-09-28-phase0-api-data-quality-report.md | 실제 Raw checksum에서 생성한 재현 가능한 품질 수치와 예외. |
| harness/workspace/reports/2026-09-28-codex-phase0-api-quality-report.md | Task의 변경·실행·한계·검토 대기·이전 current-task External Memory. |

### 수정 파일

| File | 이유 |
| --- | --- |
| AGENTS.md | 현재 실제 실행 도구에 dev API 품질 Batch를 추가해 routing과 구현 상태를 맞춘다. |
| README.md | 로컬 collect / offline analyze 명령과 승인 표본·범위를 설명한다. |
| contracts/README.md | 부분 API 품질 계약을 full Gate 계약과 구분하고 pending 확장 절차를 유지한다. |
| contracts/external-api/README.md | Negative 결과 경계·5×20 표본·실제 관찰·field VALID 한계를 명시한다. |
| contracts/external-api/bizinfo.contract.json | Probe outcome / Negative 조건, 승인 표본 연결, 별도 Live 관찰을 기록한다. 과거 관찰은 보존한다. |
| harness/changelog/harness-changes.md | 사용자 승인 범위와 이번 도구·회귀 변경 이유를 남긴다. |
| harness/docs/architecture.md | 부분 API 측정과 미래 Pipeline·문서 Gate의 실제 구현 상태를 구분한다. |
| harness/docs/data-pipeline.md | 고정 Batch·분모·상태·Raw 재현·실패 후 next action을 문서화한다. |
| harness/docs/testing.md | 합성 오프라인 검증과 dev Live·Expected Negative의 경계를 설명한다. |
| harness/registry.json | 새 정적 계약·실행 코드·Test를 등록하고 활성 Report를 바꾼다. Dynamic Report 개별 등록은 하지 않는다. |
| harness/rules/data-source-rules.md | 이번 승인 dev 5×20 범위·비중복 제거·Raw/Secret 정책을 동기화한다. |
| harness/rules/file-boundaries.md | 현재 허용된 제한 Batch를 실행 경계에 반영한다. 전체 Collector 범위는 늘리지 않는다. |
| harness/skills/data-pipeline-change/SKILL.md | 이번 사용자 승인 범위를 현재 절차에 맞춘다. 새 Framework / workflow는 추가하지 않는다. |
| harness/workspace/current-task.md | 이전 Task를 Report에 보존하고 현재 범위·실제 진행·Review 대기를 기록한다. |
| scripts/bizinfo_probe.py | HTTP / Raw helper와 Envelope 검증을 공유하고 명시적 Negative만 EXPECTED_NO_DATA로 분류한다. Positive / strict item 검증은 유지한다. |
| scripts/check-all.sh | Live API 품질은 별도 실행이고 문서 Gate는 미측정이라는 적용 제외 메시지를 정확히 한다. |
| scripts/lib/validate.py | 적용 Test 설명에 API 품질 mock / CLI를 반영한다. 검증 조건·Guardrail은 바꾸지 않는다. |
| tests/README.md | 새 Contract / CLI 회귀와 합성 Evidence 범위를 안내한다. |
| tests/contract/test_bizinfo_probe.py | Negative / Positive / HTTP 실패 / malformed no-data / 예상 불일치를 회귀로 구분한다. |

## 15. Tests / Validation

신규 품질 Unit / Contract 16개: 고정 5×20 합산, 중복 보존, 5종 field 분리, totalCount 변화 Observation,
기간 / calendar 예외·Raw 불변, @ 확장자·OTHER / UNKNOWN, Partial HTTP 실패, NOT_RUN / UNMEASURED,
echo / 초과 Item Contract 오류, short Page, Raw / output collision, transport 예외 / 인증키 반사 비노출,
stdout / Report 비노출, Raw checksum 변조 / 재현, prod 사전 거부, Positive 03 API_ERROR.
CLI Integration 5개: credential 없음 exit 3, prod / 임의 Profile / Secret 인수 거부, JSON 재현 / overwrite 거부,
Markdown 출력 / 경로 경계, help. 실제 HTTP 없이 임시 환경에서 실행했다.
Probe 회귀는 34→37개: fake missing result를 실제 관찰 형태로 갱신하고 명시 Negative만 예상 결과,
malformed / HTTP 실패, Negative의 예상 밖 성공을 검사했다. 기존 Secret / Profile / Raw Test는 유지했다.

최초 전체 Offline check-all exit=1: Draft Report에 보존한 이전 current-task의 상대 링크가 현재 Report 위치에서 잘못 해석됐다.
Harness와 관련 회귀 9개가 같은 broken link로 실패했다. 원문을 코드 블록으로 보존해 navigation 해석을 막았다.
검사를 완화하지 않았다. 실패 로그: harness/workspace/artifacts/phase0-api-quality-offline-20260928.log.
수정 후 전체 Offline check-all **exit=0**: Unit / Contract **110개**, Integration **15개**, setup / format / lint / comments / harness / git-tracked 모두 PASS.
로그: harness/workspace/artifacts/phase0-api-quality-offline-verified-20260928.log.
이 PASS와 dev credential 확인 후에만 실제 Batch 5요청을 실행했다.

Live / 재현 / Report 동기화 뒤 최종 전 전체 check-all을 다시 실행해 **exit=0**을 확인했다.
Unit / Contract 110개 / Integration 15개, 한글 주석 46개와 Harness / Git 추적 검증이 모두 PASS였다.
로그: harness/workspace/artifacts/phase0-api-quality-post-live-20260928.log.
이 결과는 Report 최종 작성 전 실제 실행한 검증이며 아래 최종 동결 검증과 구분한다.
이 Report의 Final 실행 절차와 아래 로그는 실행 시점·결과를 구분하며 아직 실행하지 않은 검증을 미리 PASS로 기록하지 않는다.
Report / index를 최종 완성한 뒤 format / lint / contract / integration / comments / harness / git-tracked / all을 각각 실행한다.
동결 후 실제 결과는 harness/workspace/artifacts/phase0-api-quality-final-validation-20260928.log와 최종 응답으로 기록한다.
최종 check-all PASS 이후 tracked 파일을 수정하지 않는다.

## 16. Secret 비노출 / Git 정책

실제 dev 키를 값 출력 없이 로드하고 모든 tracked 파일·cached diff·Raw / Artifact / Log를 canonical / URL / JSON 변형으로 점검해 노출 없음을 확인했다.
.env.dev는 byte digest·file stat이 시작 상태와 일치하며 .env.prod는 내용 없이 stat만 비교해 불변을 확인했다.
prod Secret 내용은 읽지 않았다. 두 파일은 ignore / untracked Secret 정책을 유지하고 .env.example은 tracked다.
원문 반사 / 인증 URL / Exception에 키가 포함되면 고정 안전 오류를 기록하고 해당 Raw 저장을 거부한다.
설계·기존 Raw / Gate 계약·원본 Sample·과거 작업 Report·독립 AGY 원문은 byte가 시작과 일치한다.
Branch=dev / HEAD 불변, Commit·Push·Merge·Branch 변경 없음. 과거 Trusted AGY Evidence를 현재 Task 승인으로 사용하지 않는다.

새 기계 Report는 Dynamic Workspace Markdown이며 개별 required_files 등록을 하지 않는다.
최종 index에 이번 변경과 신규 Report만 명시적으로 반영하고 Secret / Raw / ignored Artifact는 포함하지 않는다.
이 Report 작성 후 git status / git diff --cached --stat / git diff --cached --check /
git ls-files --others --exclude-standard로 최종 상태를 확인한다.
Report 동결 직전 Untracked 프로젝트 파일=0, cached whitespace exit=0을 실제 확인했다.
누적 cached Diff는 이전 Task를 포함한 총 32개 파일이며 이번 시작 대비 변경은 신규 6 / 수정 19 / 삭제 0이다.
Report의 마지막 결과 보완분을 stage한 뒤 index와 working tree 일치 상태에서 최종 8개 검증과 Git 확인을 실행한다.
현재 Report / Human Review / Data Gate는 pending이다.

## 17. 남은 Risk / 미확정 항목 / 다음 Document Download Gate

CONFIRMED: 사용자 제공 공식 Request 정보와 이번 5×20 표본 / field 상태 / 분모 / dev-only 범위.
OBSERVED: 5 Page 정상, 100개 / unique 100 / 중복 0, totalCount 1514, 타입/nonblank 품질, 기간·파일 metadata 분포·내림차순.
UNCONFIRMED: 공식 newest-first / 안정적 ordering·Dataset 변동 / pagination 일관성의 일반 보장,
Primary / Supplementary 역할·URL / filename positional pairing·ID 장기 지속성·의미상 필수성·timestamp timezone.
UNMEASURED: 실제 파일 확보·다운로드 성공·PDF/HWP/HWPX/ZIP/XLSX 처리·API 대비 상세정보·RAG 가치·자동화.

100건 API metadata와 notice 후보 / 확장자 / Raw Evidence는 확보됐으므로 다음 Document Download Gate의 검토 입력으로 사용할 수 있다.
진입과 다운로드 표본 / 위험 / 성공 분모·확장자 처리·공식 Source / pairing 기준은 사용자와 독립 Review의 별도 승인 Task에서 결정한다.
이번 Task는 API 부분 결과만 제공하며 다음 Gate를 자동 시작하거나 GO / DROP을 판단하지 않는다.
수집은 offset pagination이라 수집 중 데이터 변경 시 중복·누락이 생길 수 있고 한 Run으로 전체 안정성을 보장하지 않는다.
Local Raw는 Git에 없으므로 새 환경에서 실제 측정 재현에는 안전하게 이전한 Local Evidence가 필요하다.

## 18. 이전 current-task 보존

이전 Task 원문을 아래 코드 블록에 보존한다. 링크는 당시 workspace/current-task 위치 기준이며 현재 navigation이 아니다.

```markdown
# Current Task

## Goal / Context

2026-09-28 사용자 승인: 최소 기업마당 Probe의 dev / prod Profile 격리와 dev Live 관찰.
Environment Profile은 Git Branch와 별개이며 Branch 자동 선택은 금지한다.
이전 Task 전체는 이번 Report에 보존한다. 과거 AGY Evidence를 유지하고 현재 Review·Human Review·Data Gate는 pending이다.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[이전 Report](reports/2026-09-27-codex-bizinfo-contract-probe-report.md) →
[API Contract](../../contracts/external-api/README.md) → [Pipeline](../docs/data-pipeline.md) →
[Source](../rules/data-source-rules.md) → [Skill](../skills/data-pipeline-change/SKILL.md).

## Allowed Scope / Forbidden Scope

필수 --profile dev / prod, 선택 .env.{profile}만 읽기·OS 우선·fallback 금지·비밀 보호·회귀·오프라인 검증.
오프라인 전체 PASS와 dev key 존재 시 기존 고정 계획의 최대 4요청 dev Live·Raw Evidence·관찰 Report.
.env.dev / .env.prod 수정·삭제·stage·값 출력 금지. 실제 prod 파일 읽기·prod Live 호출 금지.
100건 본 수집·전체 Collector·Download·Parser·DB·AI·제품 기능·GO / DROP 금지.
dev Branch에서만 작업하며 Commit·Push·Merge·Branch 변경을 수행하지 않는다.

## Acceptance / Validation / Expected Report

Profile 격리·필수 선택·OS 우선·비실행·비노출·Git ignore / 추적 금지 / example 추적을 회귀로 확인한다.
Unit / Contract / CLI Integration / Harness PASS 이전에는 Live를 호출하지 않는다.
Mock과 Live Evidence를 구분하고 실제 HTTP·페이지·ID·빈 형태·정렬을 OBSERVED로 기록한다.
공식 정렬 보장과 최근 100건 Rule은 Evidence가 부족하면 UNCONFIRMED로 유지한다.
[Final Report](reports/2026-09-28-codex-bizinfo-profile-live-probe-report.md).
Report·Git index를 구성한 뒤 format / lint / contract / integration / comments / harness / git-tracked / all을 최종 실행한다.
최종 check-all 이후 추적 파일을 변경하지 않으며 실제 결과는 Report의 로그와 최종 응답에 기록한다.
상태: 오프라인 check-all PASS 후 dev Live 4요청을 실행했다. 페이지 10건씩 / totalCount=1514 / 중복 없음 / 관찰 내림차순.
Sample ID는 일치하는 1건, Synthetic ID는 03 NODATA_ERROR / items={}로 관찰했고 기존 api_error / exit 1을 보존했다.
Raw 네 개의 checksum·Secret 비노출·파일 불변을 확인했다. 추가 음성 회귀 후 Contract 91개 / Integration 10개와 check-all PASS.
Final Report를 완성했으며 index 구성 후 마지막 8개 검증 / Git 확인을 수행한다. 이후 결과는 Local 로그와 최종 응답을 따른다.
이전 Task의 22개 staged 변경은 보존하며 이번 변경과 구분해 Report에 기록한다.
```
