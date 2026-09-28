# Codex Dynamic Workspace Fix Report — 2026-09-27

범위: Harness Registry Drift Debugging. 제품 기능과 실제 Data Feasibility 측정은 수행하지 않았다.
상태: 정책 수정·회귀 테스트·Report 작성 전 검증 통과. 이 Report와 최종 Git index 구성 후 최종 검증을 재실행한다.
보완 Report의 독립 AGY Targeted Re-review는 PASS / review_complete다.
현재 수정 Task의 독립 Review·Human Review·Data Gate는 pending이다.

## 1. GitHub CI 실패 Evidence / 시작 상태

사용자 제공 원격 실패 Evidence:

```text
FAIL [harness]:
Registry drift:
missing=[],
unregistered=['harness/workspace/reports/agy-harness-fix-review\\.md']
```

실제 파일은 [agy-harness-fix-review.md](agy-harness-fix-review.md)이며 literal backslash가 없다.
Rollback 이후 직접 확인한 시작 상태는 dev, working tree clean, cached Diff 없음, Untracked 0개다.
이전 시도에서 남은 변경을 전제로 하지 않았다.

수정 전에 직접 실행한 check-harness와 check-all은 모두 exit 1이었다.
로컬 실패는 missing=[], unregistered=['harness/workspace/reports/agy-harness-fix-review.md']로 원격과 같은 누락이다.
기존 39개 Contract / Harness, 4개 CLI Integration은 통과했다.
재현 원문 로그: harness/workspace/artifacts/2026-09-27-dynamic-workspace-reproduce.log.
원격 CI를 다시 실행하거나 Push하지 않았다.

## 2. Root Cause

harness_check는 Git 파일 전체와 required_files의 집합을 동일하게 요구했다.
정적 규칙과 계속 생성되는 Report / Checkpoint를 구분하지 않아 안전한 새 External Memory도 Drift가 됐다.
Review 검증 뒤 생성된 정상 Report가 이 구조의 실패를 드러냈다.
파일명 변경·ignore·검사 삭제로 해결하지 않았다.

기존 테스트 fixture는 required_files만 복사해 새 Review 누락을 보이지 않게 했다.
이제 실제 Git 파일 목록을 복사하고 symlink도 보존해 Registry가 모르는 파일을 검사 입력에 포함한다.

## 3. Static Harness / Dynamic Workspace / Artifact

| 종류 | Registry / 검증 |
| --- | --- |
| Static Harness | required_files 개별 필수 목록. AGENTS·docs·agents·skills·rules·contracts·scripts·CI·current-task·기존 Workspace README 등은 새 미등록 파일 / 누락 시 Drift 실패 |
| Dynamic Workspace | reports/*.md, checkpoints/*.md 경로 규칙. 개별 파일명 등록 없이 Git 추적 Markdown 일반 파일 허용 |
| Ephemeral Artifact | 기존 artifacts/*.log / *.json, data 원문·재생성 결과 ignore 정책 유지. 코드·규칙·최종 해석 Markdown Report 숨김 금지 |

Dynamic Workspace의 두 경로 바로 아래만 허용한다.
symlink 파일 / 디렉터리·상위 경로 symlink·실행 권한·하위 디렉터리·비 Markdown·Untracked·ignore는 실패한다.
Git 목록과 실제 디렉터리를 함께 검사해 ignored 파일도 검사한다.
git check-ignore --no-index로 이미 추적된 파일과 global ignore도 대조한다.
체크포인트 내용의 의미·집계·안전한 재개 판단은 기존 Checkpoint 규칙과 Reviewer 검토를 따른다.
이번에 Collector나 실제 checkpoint를 생성하지 않았다.

## 4. Registry 변경 내용

- required_files 69개에서 과거 Report 3개를 제거해 정적 필수 66개를 유지한다. 실제 파일은 삭제하지 않았다.
- dynamic_paths에 reports/*.md와 checkpoints/*.md 두 경계를 명시한다.
- 새 작업 / Review Report·Checkpoint는 required_files에 개별 등록하지 않는다.
- checkpoints/README.md, artifacts/README.md, current-task.md는 고정 필수 문서로 유지한다.
- report는 현재 Task의 단일 [작업 Report](2026-09-27-codex-dynamic-workspace-fix-report.md) 연결이다.
  활성 Task 연결은 개별 필수 목록이나 Trusted Evidence 승인과 별개다.
- 최신 agy_review=review_complete는 유지하고 agy_review_evidence를 실제 AGY Fix Review 원문으로 동기화한다.
- phase·branches·execution_files·Skill / Rule / Agent·Compose / CI 목록과 정책은 유지한다.

## 5. 일반 Report와 Trusted Evidence / Review 상태

일반 Report의 존재와 안전성은 독립 Review 승인이 아니다.
새 AGY 이름의 Report를 추가해도 ACCEPTED_AGY_REVIEWS에 없는 Evidence로 review_complete를 주장하면 실패한다.
Codex 자신의 Report·위조 문구·미지원 상태로 자기 승인을 만들 수 없다.

사용자가 이번 요청에서 제공·확인한 실제 독립 Evidence만 기존 신뢰 기준에 추가했다:

| 관계 | SHA-256 |
| --- | --- |
| AGY 원문 agy-harness-fix-review.md | 7516021d9945f67d662a5e4fe6e68fe51f1e1ebdb4510ec84f73bcb70985c1d4 |
| 검토 대상 2026-09-27-codex-harness-fix-report.md | 1d5e68a85b599d59156d0e9038c73c4cbcf18d453ee282ebf46de96e2f852ada |

결과 pass는 독립 원문의 최종 PASS를 옮긴 것이며 새 판정을 작성하지 않았다.
Initial Review의 PASS WITH FIXES와 기존 checksum도 보존한다.
Evidence와 검토 대상은 안전한 Git 추적 Dynamic Workspace 파일이어야 하고 두 checksum이 일치해야 한다.
required_files 개별 등록은 Evidence 조건으로 사용하지 않는다.

check-harness 출력은 AGY review_complete / result=pass / 검토 대상=기존 보완 Report다.
현재 새 수정 Report는 검토 대상이 달라 CURRENT REPORT REVIEW: pending; human review PENDING이다.
hash는 무결성 확인이며 저자 신원 서명이 아니다. 사용자 확인·Diff / 독립 검토를 신뢰 경계로 유지한다.

## 6. 생성 / 수정 / 삭제 파일과 이유

생성 파일 1개: 이 작업 Report. Dynamic Workspace로 Git 추적하며 개별 Registry 등록 없음.

| 수정 파일 8개 | 이유 |
| --- | --- |
| [harness/registry.json](../../registry.json) | 정적 필수 목록과 동적 경계 분리, 최신 독립 Evidence / 활성 Task 연결 |
| [scripts/lib/validate.py](../../../scripts/lib/validate.py) | 공통 Workspace 안전 검사, 정적 집합 비교, Trusted Evidence 관계 유지 |
| [test_harness_policy.py](../../../tests/contract/test_harness_policy.py) | 실제 파일 fixture, 필수 Cases와 기존 Guardrail 회귀 |
| [workflow.md](../../docs/workflow.md) | 세 종류의 책임·Report / Evidence 분리·최종 검증 / 동결 순서 |
| [agy-reviewer.md](../../agents/agy-reviewer.md) | Review Report의 Git 추적과 Evidence 처리 구분, Report 생성 후 최종 검증 |
| [harness-changes.md](../../changelog/harness-changes.md) | 이번 원인·변경·독립 결과와 현재 Task 상태 기록 |
| [checkpoints/README.md](../checkpoints/README.md) | 기존 하위 디렉터리 / 개별 등록 안내를 바로 아래 <run_id>-<순번>.md 경계로 맞춤 |
| [current-task.md](../current-task.md) | 승인된 현재 Debugging 범위와 Report / Review 대기 상태 표현. 이전 전체 상태는 아래 보존 |

삭제 파일 없음. 테스트에서만 격리된 임시 Git 저장소의 합성 파일을 생성·정리했다.
README·PROJECT_DESIGN·Architecture·Testing·AGENTS·Git 정책·.gitignore는 수정하지 않았다.
기존 Report·AGY 원문·.env.example·Raw 도구·두 계약은 시작 시 SHA-256과 일치함을 직접 확인했다.
새 설명성 주석은 Workspace 경계·ignore 우회 방지·정적 비교·fixture 누락 재현의 이유를 한글로 설명한다.

## 7. Regression Tests

기존 39개에서 14개 Test를 추가해 총 53개 Contract / Harness 테스트를 실행한다.
기존 Lifecycle 테스트는 최신 검토 대상을 사용하고 Initial 결과 보존도 별도로 확인한다.

| 요청 Case | 실제 검증 |
| --- | --- |
| 1 추적 new-report.md | 개별 required_files 없이 check-harness / git-tracked 통과 |
| 2 추적 checkpoint-001.md | 개별 required_files 없이 두 검사 통과 |
| 3 malicious.py | reports / checkpoints 두 영역에서 두 검사 실패 |
| 4 script.sh | 두 영역에서 두 검사 실패. JSON도 비 Markdown으로 거부 |
| 5 symlink | 두 영역에서 두 검사 실패. 기존 독립 Evidence symlink 거부도 유지 |
| 6 Untracked Markdown | 두 영역에서 두 검사 실패 |
| 7 ignore Markdown | tracked / untracked 모두 두 영역에서 실패 |
| 8 Static 미등록 random-rule.md | 기존 Registry Drift 실패 |
| 9 일반 Report의 Evidence 주장 | user-acknowledged 기준 없음으로 실패. 새 Review 주기의 pending은 유지 |
| 10 독립 원문 / 검토 대상 checksum 일치 | Targeted PASS와 Initial PASS WITH FIXES 정상 인정, 현재 Task pending |

추가로 동적 경계의 정적 영역 확장·하위 디렉터리·실행 권한·고정 README 삭제·개별 Report 등록·Artifact 숨김을 거부한다.
기존 dev / CI·Skill / Rule·Routing·자기 승인·checksum 변조·Raw / overwrite·Contract·pending-only Gate 검증을 유지한다.

## 8. 실제 실행한 Validation / 최종 실행 순서

아래는 **이 Final Report 완성 전 실제 실행 결과**다. 완성된 Report까지 포함한 최종 실행 결과를 미리 PASS로 기록하지 않는다.

| 명령 | 실제 결과 |
| --- | --- |
| ./scripts/check-format.sh | exit 0, 개별 실행 및 check-all 내부 실행 |
| ./scripts/check-lint.sh | exit 0, 개별 실행 및 check-all 내부 실행 |
| ./scripts/check-contract.sh | exit 0, 53 tests |
| ./scripts/check-integration.sh | exit 0, 4 tests |
| ./scripts/check-comments.sh | exit 0, check-all에서 한글 주석 30개 검사 |
| ./scripts/check-harness.sh | check-all 내부 exit 0, Static / Dynamic / Evidence 검사 |
| ./scripts/check-git-tracked.sh | check-all 내부 exit 0, dev·Untracked 0·ignore / index 경계 |
| ./scripts/check-all.sh | Report 완성 전 exit 0, setup 포함 현재 적용 검사 전부 통과 |

초기 새 테스트 실행은 fixture의 staged 파일 정리에 git rm을 사용해 16개 subtest가 실패했다.
격리 fixture에서 index 제거 후 합성 파일을 정리하도록 수정했고 재실행은 53개 모두 통과했다.
Report 완성 전 전체 로그: harness/workspace/artifacts/2026-09-27-dynamic-workspace-pre-report.log.

이 Report와 current-task를 완성하고 명시적 git add를 마친 뒤 위 8개 명령을 각각 실행한다.
마지막 check-all 통과 후 추적 파일은 생성·수정하지 않는다.
최종 실행 원문·각 종료 코드·최종 Git 확인은 아래 ignored 로그와 최종 응답으로 전달한다:

harness/workspace/artifacts/2026-09-27-dynamic-workspace-final-validation.log.

검증 뒤 파일이 바뀌면 기존 결과를 Final로 취급하지 않고 index / 전체 검증 / Git 확인을 다시 수행한다.
실 API·다운로드·Parser·서비스·DB·E2E·AI Evaluation·Build는 N/A다.
제품 기능·가짜 API 수집·측정값·Gate GO/DROP은 만들지 않았다.

## 9. Git 상태

Report 완성 직전 실제 확인: dev, 수정 8개 + 신규 Report 1개가 staged, 추적 파일 71개.
git diff --cached --check는 exit 0이며 git ls-files --others --exclude-standard 출력은 없었다.
이 Report 내용까지 index에 다시 반영한 뒤 최종 상태를 확인한다.
최종 git status / cached stat / cached check / Untracked 확인은 위 최종 로그에 보존한다.
Commit·Push·Merge·프로젝트 Branch 변경 없음. Push는 사용자가 수행한다.

## 10. 남은 Risk / 미결정 사항 / 다음 검토

이번 수정의 독립 AGY Review와 Human Review는 대기한다. 과거 PASS는 이번 변경 승인이 아니다.
원격 CI 재실행 결과는 아직 없다. 로컬 최종 결과와 사용자 Push 이후 원격 결과를 구분한다.
동적 경계를 넓히거나 기록 형식 / Checkpoint 의미를 자동 검증할 필요가 생기면 별도 승인 Task에서 다룬다.
독립 Review 신뢰 기준의 장기 관리 / 저자 인증은 기존 정책의 한계이며 새 기술을 도입하지 않았다.
공식 API 계약·주요 필드·표본·분모·문서 근거 위치와 실제 Data Gate 측정은 기존대로 별도 미결정이다.
다음 작업은 Diff와 독립 검토다. 제품 기능이나 실제 수집 Task로 자동 진행하지 않는다.

## 부록: 이전 current-task 전체 보존

아래는 Rollback 이후 이번 Task 시작 시 실제 파일 내용이다.
과거 pending / 테스트 수는 당시 상태이며 최신 상태는 위 §5 / §8을 따른다.
상대 링크는 당시 current-task 위치 기준으로 보존했다.

```markdown
# Current Task

## Goal / Context

AGY Initial Harness Review의 MINOR Finding과 Harness 상태 전환을 정리한다.
현재 Phase는 phase0-preparation이며 이번 Task는 Harness Foundation 보완이다.
이 Task는 사용자의 2026-09-27 보완 요청으로 시작했다.
이전 Task 상태는 [보완 Report](reports/2026-09-27-codex-harness-fix-report.md)에 보존했다.
상태: 보완 구현·현재 적용 Validation 통과, 사용자 검토 대기.
Initial AGY Review: review_complete / PASS WITH FIXES.
이번 보완의 후속 AGY Review: pending. Human review: pending. Data Gate: pending.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[최초 Codex Report](reports/2026-09-27-codex-harness-report.md) →
[독립 Initial Review](reports/agy-initial-harness-review.md) →
[Workflow / Lifecycle](../docs/workflow.md).

## Allowed Scope / Requirements

M-1 Skill의 현재 하위 절차 필요성 명시, M-2 WHY / BOUNDARY / EXCEPTION / RISK 주석,
M-3 Checkpoint format·Resume·Recovery, M-5 Gate 계약 확장 절차,
current-task 전환·AGY Lifecycle·독립 Evidence 검증·관련 테스트·문서·Registry·Report.
Validation을 막는 IDE metadata는 좁은 ignore 정책으로 구분한다.

## Forbidden Scope / Non-goals

제품 기능·API Collector·Parser·DB·Migration·RAG·LangGraph·Indexing 구현 금지.
Gate go/drop 허용·API 환경변수 추정 금지.
Commit·Push·Merge·프로젝트 Branch 변경 금지.
최상위 설계·이전 Codex Report·독립 AGY Review 원문은 수정하지 않는다.

## Acceptance Criteria / Required Tests

현재 Review 결과를 독립 원문과 검토 대상 checksum으로 검증한다.
Codex Report·누락/변조/불일치 증거·미지원 상태는 Review 완료 근거로 거부한다.
이번 보완은 Initial Review의 승인 범위에 포함됐다고 기록하지 않는다.
제품 미구현 검증은 N/A, Human Review·Gate는 pending이다.

## Validation Command / Expected Report

check-format / lint / contract / integration / comments / harness / git-tracked / all.
[Final Report](reports/2026-09-27-codex-harness-fix-report.md).
다음 Task는 사용자 검토와 별도 승인 후에만 시작한다.

## 완료 / 남은 상태

M-1·M-2·M-3·M-5와 Task / Review Lifecycle을 보완했고 M-4의 명세 전 변수 추정은 보류했다.
39개 Unit / Contract / Harness와 4개 CLI Integration, check-all exit 0.
최상위 설계·이전 Codex / 독립 AGY 원문·.env.example·pending-only Gate 계약은 보존한다.
다음 작업은 보완 Report / Diff 검토이며 실제 API 명세·표본·분모·근거 기준은 미결정이다.
```
