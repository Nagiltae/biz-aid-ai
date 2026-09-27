# Codex Document Download Gate Task Report — 2026-09-28

## 1. 결론 / 실행 범위

기존 api-quality-dev-20260928-01의 동일 100 Item에서 printFlpthNm만 다운로드했다.
새 run-id=document-dev-20260928-01 / profile=dev / Evidence=LIVE_HTTP.
Target 100 / Attempted 100 / HTTP 요청 100 / SUCCESS 100 (100%) / 실패 0이다.
본문 의미·Parsing 성공률·Primary 실제 본공고 여부는 미확정이다.
전체 Data Feasibility GO / DROP은 pending이며 이번 Task AGY 독립 Review / Human Review도 pending이다.

[기계 생성 Gate Report](2026-09-28-phase0-document-download-report.md).
과거 [Rebase 검증](2026-09-28-post-rebase-merge-verification-report.md)과
[독립 AGY PASS](agy-post-rebase-verification-review.md)는 당시 Repository 검증 범위다.
이번 Task 독립 승인으로 재사용하지 않았다.

## 2. 구현 / 설계 선택

[제한된 Downloader](../../../scripts/phase0_document_download.py)와
[로컬 계약](../../../contracts/schemas/phase0-document-download.contract.json)을 추가했다.
Probe / API 품질 수집은 그대로 보존하고 다운로드·형식·파일 Evidence를 별도 Script로 분리했다.
Stdlib만 사용하며 전체 Production Pipeline / 새 Workflow Framework는 없다.
입력은 기존 5×20 Raw / Run artifact / checksum을 검증해 manifest에 고정한다.
100 Candidate가 pblancId·URL·filename·source page/item/hash까지 기존 표본과 순서대로 정확히 일치했다.
이전 Raw response 5개와 metadata 5개의 checksum도 변경하지 않았다.
표본은 수집 시점 API 기본 정렬 선두 100건이다. 공식 newest-first는 UNCONFIRMED다.

실제 실행 명령:

```bash
python3 -B scripts/phase0_document_download.py download --profile dev --run-id document-dev-20260928-01
python3 -B scripts/phase0_document_download.py analyze --run-id document-dev-20260928-01 --output harness/workspace/reports/2026-09-28-phase0-document-download-report.md
```

analyze는 HTTP 없이 Source / 파일 hash / metadata에서 지표와 Report를 재현한다.
출력 Report와 render 결과의 전체 문자 일치를 확인했다.

## 3. Local Safety Boundary / 주석

| 경계 | 구현 / 이유 |
| --- | --- |
| Profile | dev만 허용; prod는 Source / Secret 읽기 전 거부 |
| 인증 분리 | 공개 문서에 serviceKey·API key·Authorization·Cookie·Referer 전달 없음 |
| Secret | dev key는 입력·header·URL·body 반사 검출용; 고정 오류만 출력 |
| URL | HTTPS / www.bizinfo.go.kr / 공개 atchFileId·fileSn query. 외부 host·인증 query·userinfo 거부 |
| Redirect | 최대 3회; loop·Location 누락·경계 초과는 REDIRECT_ERROR |
| Stream | 최대 25 MiB; Content-Length와 독립적으로 실제 read를 최대값+1에서 중단 |
| Timeout / 간격 | socket timeout 15초 / Candidate 사이 0.25초 / 순차 처리 |
| Retry | 자동 재시도 0; Resume도 확정 실패를 반복 요청하지 않음 |
| 저장 | exclusive write; 기존 run / 파일 / metadata / summary overwrite 금지 |
| 형식 | signature / 제한된 container 구조 식별; 본문·표·업무 XML 추출 없음 |

위 제한은 공급자 공식 Rate Limit·최대 파일 크기·안전한 속도의 보장이 아니다.
SIZE_LIMIT_EXCEEDED에서는 최대 크기 이내 원본 prefix만 보존한다. complete_body=false이며
observed byte size는 하한이다. 전체 파일 크기나 완전한 파일 SHA를 주장하지 않는다.
Secret 반사 응답은 redaction 대신 저장을 거부한다. HTTP 예외·Location 원문은 출력하지 않는다.

PDF magic / HWP CFB FileHeader signature / HWPX mimetype와 Contents 구조 /
XLSX package 구조를 확인하고 generic ZIP과 구분한다. HWP body / PDF text / 업무 XML은 읽지 않는다.
ZIP directory 4,096 entries / 총 uncompressed size 100 MiB / mimetype 128 bytes와
CFB sector 경계·chain cycle을 제한한다. 공식 형식 참고 자료는 계약의 format_sources에 있다.
식별은 파일 전체 무결성 검사·업무 Parser가 아니다.
SUCCESS는 complete non-empty HTTP 2xx body의 식별된 형식과 filename이 일치하는 경우다.
Content-Type 차이는 Observation이고 filename/actual 차이는 FORMAT_MISMATCH다.
URL_POLICY_ERROR / SECURITY_REJECTED도 별도 outcome으로 기록한다.

한글 WHY / BOUNDARY / EXCEPTION 주석은 공개 요청 인증 분리, URL / redirect 경계,
Content-Length 불신과 실제 stream limit, Secret 반사 저장 거부, OLE 오인 방지,
ZIP 폭탄 / 경로 탈출 방지, 중단 직전 고립 파일의 SUCCESS 방지에 작성했다.

## 4. Live Run / Download Gate 지표

UTC 시작=2026-09-27T17:16:57.458971+00:00 / 종료=2026-09-27T17:18:07.920478+00:00.
KST 2026-09-28 02:16:57–02:18:07 / 총 70.461507초.
HTTP 100회 / prod 0회 / 새로운 API 수집 0회 / Supplementary 파일 요청 0회 / CLI exit 0.
합성 Test는 SYNTHETIC_MOCK로 표시하며 실제 Run은 LIVE_HTTP다.

| 지표 | 실제 결과 / 분모 |
| --- | --- |
| Target / Attempted / Processed | 100 / 100 / 100 |
| SUCCESS / Rate | 100 / 100% (Target 100) |
| 모든 실패 outcome | 각각 0 / 0% (Target 100) |
| HTTP status | 200 × 100 |
| Redirect | 발생 0 / count 0 × 100 |
| URL missing / null / blank / invalid syntax / 정책 거부 | 각각 0 / URL 100 |
| URL unique / duplicate extra | 100 / 0 |
| Source / final host | www.bizinfo.go.kr × 100 |
| Declared filename extension | PDF 70 / HWP 15 / HWPX 15 |
| Actual format | PDF 70 / HWP 15 / HWPX 15 |
| Filename / Actual match | 100 / 100% (Target 100) |
| Content-Type | application/octet-stream × 100 |
| 구체적 형식 MIME과 다른 header | 100 (Observation) |
| File size min / max | 64,097 / 1,613,824 bytes |
| File size 평균 / 중앙값 | 384,271.74 / 253,215 bytes |
| Size 분모 | complete non-empty HTTP 2xx body 100 |
| Duplicate SHA-256 | 0 / complete non-empty HTTP 2xx body 100 |
| Supplementary token pairing | MATCH 86 / MISMATCH 0 / 양쪽 usable 86 |
| Supplementary URL / filename token 합계 | 138 / 138 |
| Primary Notice 가설 | SUPPORTED_BY_DOWNLOAD_EVIDENCE |

실제 빈 파일·HTTP / transport / redirect 실패·size 초과·UNKNOWN·format mismatch는 없었다.
중복을 제거하거나 실패를 분모에서 제외하지 않았다. 모든 count/ratio와 100개 file SHA 표는 Gate Report에 있다.
Content-Type은 전부 generic octet-stream으로 구체적 형식을 알려주지 않았다. 이것을 Download 실패로 세지 않았다.
Primary 가설은 다운로드·filename·형식·non-empty byte에 의해 지지됐지만 본문 의미는 미확정이다.
Supplementary token 수 일치가 의미상 positional pairing을 보장하지 않는다.
단일 Run의 URL 접속을 장기 안정성 / 전체 Dataset 성공률로 확대하지 않는다.

## 5. Evidence / Checkpoint / Resume

Local payload=data/downloaded/document-dev-20260928-01/ (Git ignored).
manifest.json은 source artifact SHA 및 page Raw / item index / filename / 공개 URL / 안전 설정을 고정한다.
각 pblancId의 document.bin / metadata.json에는 시각·HTTP·redirect count·final host·filename·Content-Type·size·SHA·actual format·outcome을 보존한다.
summary-0000.json에 Run / 지표가 있다. 원본 합계 38,427,174 bytes이며 삭제·변조하지 않았다.
각 원본의 SHA / 크기 / 형식을 다시 확인한 뒤 offline 분석을 재현했다.

Checkpoint 12개는 시작·10개씩 확정·다운로드 종료를 순번으로 보존한다.
[최종 다운로드 Stage Checkpoint](../checkpoints/document-dev-20260928-01-0011.md):
completed_count=success_count=100 / processed_count=100 / failed_count=0 / remaining_count=0.
last_processed_pblancId=PBLN_000000000126669 / failed_items=[] / status=completed /
next_action=null / resume_command=null.
completed는 다운로드 Stage의 원본·checksum·집계 확정이며 Task 최종 Validation / AGY·Human 승인 / GO를 대신하지 않는다.
각 결과는 Candidate마다 먼저 확정하므로 Checkpoint 사이 결과도 checksum에서 복원한다.

부분 Run 재개 명령:

```bash
python3 -B scripts/phase0_document_download.py download --profile dev --run-id <existing-run-id> --resume
```

Resume는 동일 Source / manifest / 안전 설정과 모든 파일 hash / format을 검증하고 미처리 Candidate만 요청한다.
성공과 확정 실패를 모두 건너뛴다. 고립 파일·hash 불일치·검증되지 않은 SUCCESS는 멈춘다.
실패 재시도는 별도 사용자 판단 대상이다. 실제 Run에는 실패·중단이 없어 Live Resume는 실행하지 않았다.
Partial / Resume는 mock Test에서 성공 파일을 반복 요청하지 않는 방식으로 검증했다.

## 6. Offline Tests / 실제 Validation

[Unit/Contract](../../../tests/contract/test_phase0_document_download.py) 26개와
[CLI Integration](../../../tests/integration/test_phase0_document_download_cli.py) 5개를 추가했다.
기존 110 Unit/Contract / 15 Integration의 Test 본문은 변경하지 않았다.
회귀 범위: 기존 100개 표본과 SHA, 순차 요청, SUCCESS, 404/500, transport, Redirect / loop / limit /
외부 host / 인증 query 거부, empty, Content-Length와 독립적 size limit,
PDF/HWP/HWPX/XLSX/ZIP/UNKNOWN, container 경계, filename mismatch / MIME Observation,
duplicate URL / SHA, overwrite / 변조 / 고립 파일 거부, Partial / Resume / Checkpoint,
Supplementary token match / mismatch, Secret 반사 저장 거부·request/stdout/stderr/Report 비노출,
prod 설정 비읽기, Raw 보존, CLI 경계 / 실패 종료다. CI에서 실제 HTTP는 호출하지 않는다.

| 실제 실행 | 결과 |
| --- | --- |
| Document Unit/Contract 단독 | 26 PASS |
| Document CLI Integration 단독 | 5 PASS |
| Live 전 check-all.sh | PASS; Unit/Contract 136, Integration 20 |
| Live download CLI | exit 0; HTTP 100 / SUCCESS 100 |
| Offline analyze CLI | exit 0; HTTP 0 / Report 전체 재현 일치 |
| Live 후 check-all.sh | PASS; Unit/Contract 136, Integration 20 |
| 보존 Audit | PASS; 기존 26파일 hash / 핵심 Validator 10함수 AST 동일 |
| Raw / 다운로드 Audit | PASS; 이전 Raw 10파일 동일 / 다운로드 SHA 100개 확인 |
| Secret Audit | PASS; 309개 tracked/Evidence/log와 cached diff에서 dev key 반사 없음 |

보존 Audit 첫 범위에 tests/README.md를 포함해 예상된 문서 동기화를 불변 위반으로 탐지했다.
보호 대상은 기존 Test 본문·Fixture·API 도구·과거 Report로 바로잡아 재실행했다. 코드 회귀나 검증 완화는 아니다.
Offline / Live 후 check-all은 하위 format / lint / contract / integration / comments / harness / git-tracked를 실제 실행해 모두 PASS했다.
로그:
- harness/workspace/artifacts/document-download-offline-20260928.log
- harness/workspace/artifacts/document-download-live-20260928.log
- harness/workspace/artifacts/document-download-postlive-20260928.log

## 7. Report 이후 최종 검증

Report / index를 고정한 뒤 아래 8개를 다시 실행한다. 작성 시점에 후속 실행을 미리 PASS로 기록하지 않는다.
최종 도구 실행 결과는 harness/workspace/artifacts/document-download-final-validation-20260928.log /
document-download-final-validation-20260928.json에 기록하고 최종 응답에서 확인한다.
이는 재생성 가능한 검증 실행 artifact이며 최종 해석은 본 Report / Gate Report와 함께 읽는다.

```bash
./scripts/check-format.sh
./scripts/check-lint.sh
./scripts/check-contract.sh
./scripts/check-integration.sh
./scripts/check-comments.sh
./scripts/check-harness.sh
./scripts/check-git-tracked.sh
./scripts/check-all.sh
```

최종 check-all PASS 후 tracked 파일 / index를 변경하지 않고 git status / cached stat /
cached whitespace / untracked와 Report hash·index / HEAD 불변을 확인한다.
제품 / DB / AI / Parsing / OCR Validation은 N/A / UNMEASURED이며 성공 Test 수에 합치지 않는다.

## 8. 생성 / 수정 / 삭제 파일과 이유

Static 신규 4개는 Script·계약·Unit/Contract·CLI Integration Test다.
Dynamic 신규 14개는 Gate / Codex Report 2개와 Checkpoint 12개다.
Dynamic Markdown은 Git 추적하되 required_files에 개별 등록하지 않았다. 삭제 파일은 없다.

| 변경 | 파일 |
| --- | --- |
| 수정 | `AGENTS.md` |
| 수정 | `README.md` |
| 수정 | `contracts/README.md` |
| 생성 | `contracts/schemas/phase0-document-download.contract.json` |
| 수정 | `data/downloaded/README.md` |
| 수정 | `harness/changelog/harness-changes.md` |
| 수정 | `harness/docs/architecture.md` |
| 수정 | `harness/docs/data-pipeline.md` |
| 수정 | `harness/docs/testing.md` |
| 수정 | `harness/registry.json` |
| 수정 | `harness/rules/data-source-rules.md` |
| 수정 | `harness/rules/file-boundaries.md` |
| 수정 | `harness/skills/data-pipeline-change/SKILL.md` |
| 수정 | `harness/workspace/checkpoints/README.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0000.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0001.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0002.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0003.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0004.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0005.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0006.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0007.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0008.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0009.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0010.md` |
| 생성 | `harness/workspace/checkpoints/document-dev-20260928-01-0011.md` |
| 수정 | `harness/workspace/current-task.md` |
| 생성 | `harness/workspace/reports/2026-09-28-codex-document-download-gate-report.md` |
| 생성 | `harness/workspace/reports/2026-09-28-phase0-document-download-report.md` |
| 수정 | `scripts/check-all.sh` |
| 수정 | `scripts/lib/validate.py` |
| 생성 | `scripts/phase0_document_download.py` |
| 수정 | `tests/README.md` |
| 생성 | `tests/contract/test_phase0_document_download.py` |
| 생성 | `tests/integration/test_phase0_document_download_cli.py` |

AGENTS / README / Architecture / Pipeline / Skill / Source·File Boundary는 승인된 현재 실행 상태만 동기화했다.
Contracts / downloaded / testing / checkpoint / tests README는 실제 저장·측정·실행·복원 경계를 설명한다.
Registry는 새 Static 4개와 활성 Report 연결만 갱신했다. Dynamic / Trusted Evidence 정책은 유지했다.
current-task는 승인 범위와 Report를 연결하며 이전 내용을 아래 보존했다. Changelog는 변경 이유를 기록했다.
check-all / Validator는 적용 범위 출력만 수정했고 핵심 Guardrail AST는 유지했다.
PROJECT_DESIGN.md, .gitignore, .env.example, 사용자 Secret, Compose, 기존 API Contract / Probe /
품질 수집 도구, 기존 Test 본문 / Fixture / 과거 Report / AGY 원문은 변경하지 않았다.

## 9. Git / Secret 상태

시작 Branch=dev / HEAD=f2d4dab85979d06a82899ac2e9284e01f89c1279 / index 및 working tree clean.
현재 diff는 수정 17개 / 생성 18개, 총 35개 파일이며 자신의 변경만 stage해 Git Diff로 확인 가능하다.
프로젝트 Untracked 0 / unstaged diff 0 / cached whitespace 오류 0을 확인했다.
.env.dev / .env.prod / data/raw / data/downloaded / ignored Artifact는 index에서 제외했다.
사용자 Secret 파일의 inode·size·mtime는 처음과 같으며 prod 내용은 읽지 않았다.
dev key는 내부 반사 검사 외 request·fixture·metadata·Report·stdout/stderr·diff에 기록하지 않았다.
HEAD / Branch는 그대로다. Commit / Push / Merge / Rebase / Branch 변경은 하지 않았다.
최종 Git 상태는 후속 Final Validation과 최종 응답에서 다시 확인한다.

## 10. 남은 Risk / 다음 Gate

CONFIRMED: 사용자 승인 표본·dev 범위·로컬 안전 계약·공식 Request 정보.
OBSERVED: 같은 100개 URL의 HTTP 200·non-empty 원본·SHA·형식·filename 일치·중복 없음·Supplementary token 수 일치.
UNCONFIRMED: 공식 newest-first, 장기 URL 안정성, Primary 본문 의미, Supplementary 의미상 pairing, 전체 Dataset 자동 확보율.
UNMEASURED: text parsing·표/근거 위치·scan/OCR·full container integrity·API 대비 상세 정보·RAG 가치.

다운로드 Evidence는 다음 Parsing Gate에서 검토할 수 있다. 진입은 사용자 / 독립 Review와 별도 승인 Task에서 결정한다.
확보한 70 PDF / 15 HWP / 15 HWPX 원본, metadata/checksum, Source Raw 연결을 넘긴다.
본문이 실제 공고인지·파싱 도구 지원 범위·부분 손상·성공 기준·표/근거 추출은 다음 Task에서 측정한다.
Local Safety 경계 밖의 host / 인증 query / 대형 파일은 명시적 실패 대상이다.
단일 Run 결과를 지속적인 운영 안정성으로 확대하지 않는다.

AGY Review에서는 인증 분리, bounded stream / Redirect, CFB/ZIP 식별 경계,
고립 파일 / 변조 / 확정 실패의 Resume, 분모 / UNMEASURED, Checkpoint Stage / 전체 Task 종료 구분,
현재 Task pending과 과거 독립 Evidence 범위, Report 이후 Final Validation / index 불변을 확인한다.

## 11. 이전 current-task 전체 보존

아래 내용은 Task 전환 이전 상태다. 당시 Git / 검증을 이번 실행 결과로 해석하지 않는다.

```text
# Current Task

## Goal / Context

2026-09-28 사용자 승인: 수동 Rebase 충돌 해결 후 Repository 보존 / 회귀 검증.
245e045의 Harness CI 의도와 fe9df22의 API / Profile / 100건 품질 의도를 현재 HEAD에서 확인한다.
이전 API 품질 Task 전체는 이번 Report에 보존한다. 과거 AGY Evidence와 현재 독립 Review / Human Review pending을 유지한다.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[Git 정책](../rules/git-policy.md) → [Workflow](../docs/workflow.md) →
[Testing](../docs/testing.md) → [Debugging Skill](../skills/debugging/SKILL.md) →
[이전 API 품질 Report](reports/2026-09-28-codex-phase0-api-quality-report.md).

## Allowed Scope / Forbidden Scope

Git 상태 / graph / 기준 Commit / marker / 테스트 본문 / 문서 연결을 읽고 실제 오프라인 Validation을 실행한다.
Rebase 진행 중이면 continue / abort 없이 중단한다. 명백한 Rebase 회귀만 근거를 기록한 뒤 최소 수정한다.
제품 기능·Document Download Gate·Parser·DB·AI·Architecture / Harness 재설계·Live API 호출은 범위 밖이다.
사용자 Secret 파일은 수정·stage·값 출력하지 않는다. Commit·Push·Merge·Branch 변경·force push 금지.

## Acceptance / Validation / Expected Report

정적 Registry·Dynamic Workspace 안전·Trusted AGY·Profile·Expected Negative·고정 5×20 품질 계약을 보존한다.
[Final Report](reports/2026-09-28-post-rebase-merge-verification-report.md).
Report / index를 완성한 뒤 format / lint / contract / integration / comments / harness / git-tracked / all을 최종 실행한다.
이후 git status / diff checks / untracked / log와 파일 불변을 확인한다. 최종 check-all 이후 tracked 파일을 변경하지 않는다.
상태: dev / clean으로 시작했고 reflog에 rebase finish가 있다. 진행 중 디렉터리 / unmerged index는 없다.
REBASE_HEAD 잔여 참조는 원래 fe9df22를 가리키며 변경하지 않았다. HEAD=76bd206은 245e045를 부모로 갖는다.
HEAD tree와 fe9df22 tree는 완전히 같고 원격 핵심 Guardrail / 테스트 본문은 유지됐다.
원래 상태의 8개 Validation PASS / Contract 110 / Integration 15. 기존 Raw 5개를 읽기만 해 품질 Report와 재현 일치를 확인했다.
회귀 수정 / 코드 / Test 변경은 없다. 검증 Report와 Task 연결 metadata만 기록하고 최종 검증 후 독립 Review / Human Review 대기다.
```
