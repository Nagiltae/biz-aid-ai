# 기업마당 Profile / dev Live Probe Report

## 1. 범위 / Profile 구조

2026-09-28 사용자 승인: dev / prod Profile 격리·회귀·오프라인 검증 후 기존 최소 dev Live Probe.
Data Pipeline / API Contract Skill과 Static / Dynamic / Artifact 정책을 적용했다.
--profile은 필수이며 dev / prod만 지원한다. 미지정·local / staging / test / 기타 값은 exit 2다.
dev는 .env.dev, prod는 .env.prod만 읽고 반대 Profile / legacy .env fallback은 없다.
Git Branch와 Environment Profile은 별개다. Branch와 APP_PROFILE로 자동 선택하지 않는다.
.env.example의 APP_PROFILE=dev는 설정 예시이며 CLI 선택을 대신하지 않는다.
우선순위는 OS → 선택 파일 → 비밀이 아닌 Endpoint / json default다. 키의 default는 없다.
빈 OS key도 파일보다 우선한다. KEY=VALUE / export / 전체 quote만 읽고 셸 실행·source·보간·inline comment는 하지 않는다.
prod 파일 없는 OS 주입은 합성 Test로 검증했다. 운영 배포는 구현하지 않았다.
Compose의 network_mode=none / read_only와 CI 오프라인 경계는 유지한다.
100건 본 수집·전체 Collector·Download·Parser·DB·AI·제품 기능·GO / DROP은 수행하지 않았다.

## 2. 사용자 Secret 안전 정책

두 파일 존재와 dev key nonempty만 값 출력 없이 확인했다. 실제 .env.prod 내용은 읽지 않았다.
두 파일을 수정·삭제·덮어쓰기·stage·내용 출력·Fixture 복사하지 않았다.
dev byte digest와 양쪽 file stat를 내부 비교해 불변을 확인했고 내용 / digest는 출력하지 않았다.
실제 key로 추적 파일·Live Raw·Artifact·로그의 literal / URL-encoded / JSON-escaped 반사를 스캔해 노출 없음으로 확인했다.
기존 .env.* ignore / !.env.example을 유지하므로 .gitignore 변경은 없었다.
check-git-tracked는 파일이 없는 CI에서도 Profile ignore를 요구하고 추적 Secret / 숨긴 example을 거부한다.
원문에 key가 반사되면 저장을 거부하는 기존 정책, 예외 URL 비노출·redirect 금지·checksum / overwrite 정책을 유지했다.

## 3. 생성 / 수정 / 삭제 파일

이번 Task 생성: 이 Dynamic Workspace Report 하나. required_files에 개별 등록하지 않는다.
수정 18개와 이유:

| 파일 | 이유 |
| --- | --- |
| scripts/bizinfo_probe.py | 필수 Profile·선택 파일 격리·OS 우선·결과 Profile 기록 |
| scripts/lib/validate.py | Secret 파일 없는 CI에도 ignore 정책 검증 |
| scripts/check-all.sh | 별도 Live Probe와 미측정 100건 Gate를 구분하는 적용 제외 안내 |
| tests/contract/test_bizinfo_probe.py | Profile 격리·불변 / 비노출·no-data 음성 회귀 |
| tests/contract/test_harness_policy.py | Secret 추적 / ignore 누락 / example 숨김 거부 |
| tests/integration/test_bizinfo_probe_cli.py | CLI Profile 오류·NOT_RUN·설정 실패 비노출 |
| .env.example | APP_PROFILE 예시·빈 key·사용자 파일 보호 |
| contracts/external-api/README.md | Profile 실행·Sample / Mock / Live 분리·관찰 갱신 |
| contracts/external-api/bizinfo.contract.json | Profile Local 설정·Live Raw hash / no-data 관찰 |
| README.md | dev 명시 명령·Secret 파일 / 우선순위 안내 |
| harness/docs/data-pipeline.md | Profile / 실제 dev 경계와 active Report |
| harness/docs/architecture.md | 실제 dev 4요청 관찰과 100건 Gate 대기를 구현 상태에 동기화 |
| harness/docs/testing.md | Profile·Git Secret 검사 범위 |
| harness/rules/data-source-rules.md | 사용자 Secret 불변·prod 실제 읽기 / 호출 금지 |
| tests/README.md | 합성 Profile / 격리 Git·Live의 구분 |
| harness/registry.json | active Report 교체; Dynamic 파일 개별 등록 없음 |
| harness/workspace/current-task.md | 승인 Task·실제 관찰·Review pending |
| harness/changelog/harness-changes.md | 변경 승인 근거·관찰·Guardrail 유지 |

삭제 없음. PROJECT_DESIGN·phase0.py·Raw / pending-only Gate 계약·기존 Sample Fixture·AGY 원문·과거 Report는 보존한다.
한글 WHY 주석은 Profile / 셸 경계·Secret 없는 CI의 ignore 검사·합성 no-data의 성공 오인 방지에 작성했다.

## 4. Regression Tests / Offline Validation

추가 Profile 회귀: Contract 14개(Probe 10개, Harness Git 4개)·CLI 3개.
추가 no-data 회귀 1개는 관찰 형태만 합성했으며 Live Raw를 Fixture로 복사하지 않았다.
기존 Secret·Raw checksum / overwrite·Static Drift·Dynamic 안전 / 추적·독립 Review·자기 승인 방지·Gate 검사 유지.

검증: 양쪽 선택 파일만 read·unsupported 실패·양방향 / legacy fallback 금지·OS 우선(빈 key 포함),
APP_PROFILE 자동 선택 금지·셸 표현 비실행·파일 불변·prod OS 주입·성공 / 실패 stdout / stderr / Report / log 비노출,
키 없는 NOT_RUN / exit 3·Secret ignore / 추적 거부·example 추적 / 숨김 거부·Secret 없는 CI 정책 검증.
모두 임시 합성 설정 / mock HTTP이며 사용자 Secret은 복사하지 않았다. CI는 실제 HTTP를 호출하지 않는다.

Live 전 실제 실행: 개별 Probe Contract 33개·CLI 6개 PASS.
전체 check-all exit 0, Contract / Harness 90개·Integration 10개·한글 주석 40개 검사 PASS 후에만 dev Live를 실행했다.
Local 기록: harness/workspace/artifacts/bizinfo-profile-offline-20260928.log (ignored).
이후 no-data 회귀를 추가했고 최종 검증에서 전체를 다시 확인한다.

## 5. dev Live 실행 / 요청 수

명령: python3 -B scripts/bizinfo_probe.py --profile dev --run-id bizinfo-dev-20260928-01.
새 고유 run-id를 확인했다. 실제 HTTP 4요청 / 재시도 0 / prod 0 / numOfRows=100 요청 0.
수집 UTC 2026-09-27 15:17:34–35 / KST 2026-09-28 00:17:34–35.
실제 dev 파일만 읽었으며 key를 명령 인수·출력에 넣지 않았다.
Local Artifact: harness/workspace/artifacts/bizinfo-probe-bizinfo-dev-20260928-01.json (ignored).
Probe 종료 **1**: 마지막 음성 요청의 non-00을 기존 api_error로 처리했다. 전체 Live PASS로 기록하지 않는다.

## 6. Pagination / Ordering / ID 결과

| 요청 | HTTP / header | Item / Pagination / ID |
| --- | --- | --- |
| page1 | 200 / 00 NORMAL_SERVICE | 10건, pageNo=1 / numOfRows=10 echo 일치, totalCount=1514 |
| page2 | 200 / 00 NORMAL_SERVICE | 10건, pageNo=2 / numOfRows=10 echo 일치, totalCount=1514 |
| known_id PBLN_000000000126771 | 200 / 00 NORMAL_SERVICE | 1건 / 반환 ID 일치 / pageNo=1 / numOfRows=10 / totalCount=1 |
| presumed_missing_id PBLN_999999999999999 | 200 / 03 NODATA_ERROR | items={} / item key 없음 / pageNo=1 / numOfRows=0 / totalCount=0 |

두 페이지 내부 / 페이지 간 ID 중복 없음, totalCount 일치.
각 페이지와 합친 20건 creatPnttm은 **Observed descending order**다.
page1 2026-09-23 13:50:28 → 11:25:45, page2 11:23:54 → 10:45:59.
공식 newest-first 보장과 timezone은 미확정이다. 제공 Sample totalCount=1518과 이번 1514의 변화 원인을 추정하지 않는다.
known_id 단건 필터는 이번에 동작했다. 다른 ID / 필터 조합 / 시점까지 보장하지 않는다.
Synthetic ID 미존재를 사전에 사실로 쓰지 않았으며 실제 NODATA_ERROR와 totalCount=0을 관찰했다.
빈 성공 item[]이 반환됐다고 쓰거나 {} / null을 강제로 []로 변환하지 않았다.
Probe는 non-00에서 item count / 성공 Pagination을 null로 남긴다. 위 missing body는 보존 Raw에서 직접 확인했다.
이는 한 요청의 no-data 관찰이며 모든 미존재 ID / 오류의 보장이 아니다.

## 7. Raw Evidence / checksum / Secret 비노출

기존 verify-snapshot으로 네 원문 byte·크기·수집 시각·hash·형식 상태를 검증했다.
원문 / metadata는 ignored data/raw에 보존하며 Git / Test Fixture로 복사하지 않는다.
아래 hash는 **API 응답 Raw**이며 Secret 파일 / 인증키 hash가 아니다.

| 요청 | Metadata 상대 경로 | Raw SHA-256 |
| --- | --- | --- |
| page1 | data/raw/bizinfo-dev-20260928-01-page1/metadata.json | 32109151c05e5ea3574e2ce7f50256e4b425f422e4a05bf583ce4c8274b24d57 |
| page2 | data/raw/bizinfo-dev-20260928-01-page2/metadata.json | 466653ca01921e122243d6ec1452d1db92cc48db19be829fd9cacec7b2f99da6 |
| known_id | data/raw/bizinfo-dev-20260928-01-known_id/metadata.json | 5f2404331b44d5d1d0f2e0af054e79ba9b6ed4182704407a5755ef7348bb0df6 |
| presumed_missing_id | data/raw/bizinfo-dev-20260928-01-presumed_missing_id/metadata.json | 26f7b5f14a715c16a2b3448d3f66c5620c1320bfdc554e08569bd0adfb9a8b85 |

Ignored Local Evidence는 원격 checkout의 필수 링크로 만들지 않기 위해 일반 상대 경로로 기록했다.
네 원문·Artifact·추적 파일·로그에서 실제 key 비노출을 별도 스캔했고 사용자 파일 불변을 확인했다.

## 8. CONFIRMED / OBSERVED / UNCONFIRMED

| 구분 | 결과 |
| --- | --- |
| CONFIRMED | 이전 사용자 확인 공식 Endpoint / Method / query / serviceKey 필수 유지 |
| OBSERVED | dev 페이지 1 / 2의 정상 응답·echo·10건씩·1514 일치·중복 없음 |
| OBSERVED | 실제 20건 내림차순·known_id 1건 일치·Synthetic ID 03 NODATA_ERROR / items={} |
| OBSERVED | 오프라인 합성 테스트 PASS와 Secret 불변 / 비노출; Live와 별개 |
| UNCONFIRMED | 공식 최신순 / timezone·ID 전역 유일성 / 지속성·전체 오류 / 빈 성공 형태 |
| UNCONFIRMED | 공급자 최대 rows / default / 날짜 / 기타 필터·최근 100건 Sampling Rule |
| UNCONFIRMED | 주요 Field 최종 분모 / invalid·공고문 후보 역할 / 첨부 pairing·100건 Download / Parsing / RAG 가치 |

기계 계약은 Local Profile와 Raw / no-data 관찰만 추가했다. 공급자 보장으로 승격하거나 03을 성공으로 허용하지 않았다.

## 9. 다음 100건 Gate 진입 / 남은 Risk

다음 승인 Task의 Pagination 준비를 뒷받침하는 작은 관찰을 확보했지만 최근 100건 Rule은 **UNCONFIRMED**다.
100건 본 수집은 시작하지 않았다. 사용자 Evidence Review 후 표본 표현 / 최신성 기준·중복 / 동률 / 시점·
주요 Field null / blank / invalid / 분모와 Checkpoint 정책을 확정하고 별도 Task를 승인해야 한다.
보장이 없으면 조회 당시 첫 페이지들에서 관찰한 100개 표본 등의 정책을 논의할 수 있다.
두 페이지만으로 전체 안정성·정렬·ID 지속성을 보장하지 못하며 데이터 변동의 중복 / 누락 / 총수 변화가 가능하다.
no-data는 한 ID의 결과다. prod는 합성 Test만 했으며 운영 배포 / Secret runtime 주입 자체는 구현하지 않았다.
현재 reader는 단순 설정 형식만 지원한다. 독립 AGY Review·Human Review·Gate는 pending이며 과거 PASS를 재사용하지 않는다.

## 10. 최종 Validation / Git 상태

추가 no-data 음성 회귀와 문서 동기화 후 전체 check-all을 두 번 재실행해 각각 exit 0을 확인했다.
Report 최종 작성 직전 실제 결과:

| 검사 | 실제 결과 |
| --- | --- |
| setup / format / lint | check-all 내부 실행 PASS / 0 |
| contract | 전체 91개 PASS / 0 (Profile와 no-data 회귀 포함) |
| integration | 전체 10개 PASS / 0 |
| comments | 한글 설명성 주석 41개 검사 PASS / 0 |
| harness | PASS / 0; 과거 독립 AGY PASS는 보완 Report 범위, 현재 Review / Human Review pending |
| git-tracked | PASS / 0; ignore / Secret 추적 / example 경계 유지 |
| all | 적용 오프라인 검사 PASS / 0; 별도 Live의 음성 응답 exit 1과 구분 |

Local 기록: harness/workspace/artifacts/bizinfo-profile-post-live-preliminary-20260928.log,
harness/workspace/artifacts/bizinfo-profile-final-report-preparation-20260928.log (ignored).
보호 파일 11개(설계·기존 도구 / Raw / Gate 계약·Sample·과거 Report / AGY)는 Task 시작 byte와 일치했다.
Git Diff / 추적 파일에서 실제 key를 별도 스캔해 노출 없음을 확인했다.

이 Report와 current-task를 최종 작성·stage한 다음 format / lint / contract / integration / comments /
harness / git-tracked / all을 각각 순서대로 다시 실행한다.
위 PASS는 이미 실행한 작성 전 결과이며 아직 실행하지 않은 최종 결과를 미리 PASS로 선언하지 않는다.
최종 check-all 이후 추적 파일을 수정하지 않고 실제 종료 코드는
harness/workspace/artifacts/bizinfo-profile-final-validation-20260928.log와 최종 응답에 기록한다.
이후 git status / git diff --cached --stat / git diff --cached --check /
git ls-files --others --exclude-standard를 확인한다. 추적 byte / index·HEAD·Secret 파일 불변과 최종 비노출도 확인한다.

시작 시 이전 22개 staged 결과와 사용자 example unstaged 수정이 있었다.
이번 Task는 생성 Report 1개 / 수정 18개 / 삭제 0개이며, 누적 Git Diff는 이전 Task를 포함해 총 25개(신규 7 / 수정 18)다.
Report 최종 작성 직전 Untracked 프로젝트 파일 0개, cached whitespace check exit 0을 확인했다.
최종 Report / current-task 변경만 재stage하며 사용자 Secret은 추가하지 않는다.
Commit·Push·Merge·Branch 변경·사용자 Secret stage 없음. 최종 Git 출력은 동결 후 Local 로그와 최종 응답으로 전달한다.

## 11. 교체 전 current-task 전체 보존

```markdown
# Current Task

## Goal / Context

사용자의 2026-09-27 요청으로 Phase 0 첫 실제 Task인 기업마당 API Raw Contract와 최소 Local Probe를 준비한다.
Phase 표기는 phase0-preparation을 유지하며 최근 100건 본 측정·GO / DROP은 이번 범위가 아니다.
이전 Task 전체는 이번 Final Report에 보존한다. 과거 보완의 독립 AGY Targeted Re-review PASS Evidence는 유지한다.
현재 API Task의 독립 Review·Human Review·Data Gate는 pending이다.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[Pipeline](../docs/data-pipeline.md) → [Source](../rules/data-source-rules.md) →
[data-pipeline-change](../skills/data-pipeline-change/SKILL.md) →
[External API Contract](../../contracts/external-api/README.md) → [Workflow](../docs/workflow.md).

## Allowed Scope / Forbidden Scope

사용자 확인 Request·실제 sanitized Sample Fixture·Raw Response Contract·환경변수·최대 4요청 Local Probe·관련 Tests와 문서.
100건 본 수집·전체 Collector·Download·Parser·DB·Migration·Qdrant·RAG·LangGraph·제품 API·LangSmith·GO / DROP 금지.
dev에서만 작업하며 Commit·Push·Merge·Branch 변경은 하지 않는다. 인증키·Live 원문은 Git에 넣지 않는다.

## Acceptance / Validation / Expected Report

Sample의 HTML·비정형 기간·null·@ 연결 첨부·Unknown field를 보존한다.
Unit / Contract는 항상 실행하고 Live Probe는 명시적인 Local Command로 분리한다.
현재 .env와 key가 없어 실제 Probe 명령은 NOT_RUN / 종료 3 / 요청 0회다.
Pagination·ID 동작·정렬 보장·최근 100건 Rule은 UNCONFIRMED로 유지한다.
[Final Report](reports/2026-09-27-codex-bizinfo-contract-probe-report.md).
format / lint / contract / integration / comments / harness / git-tracked / all을 실제 실행한다.
Report·Git index 구성 후 최종 검증과 Git 확인을 수행하며 이후 추적 파일을 변경하지 않는다.
상태: Contract·Probe·Report 작성, 사전 check-all에서 Contract 76개 / Integration 7개 PASS, Local NOT_RUN 확인.
Git index를 최종 구성한 뒤 마지막 검증을 실행한다. 이후 실제 종료 결과는 Report의 로그와 최종 응답을 따른다.
다음 100건 Gate Task는 Probe Evidence와 Sample / 주요 Field 정책의 사용자 Review 후 별도 승인한다.
```
