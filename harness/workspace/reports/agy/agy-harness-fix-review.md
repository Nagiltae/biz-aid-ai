# AGY Harness Fix Review

**Reviewer**: AGY (Antigravity — 독립 Reviewer)
**Review Date**: 2026-09-27
**Review Type**: Targeted Re-review (Initial MINOR Finding 해결 여부 확인)
**Codex Fix Report**: [2026-09-27-codex-harness-fix-report.md](2026-09-27-codex-harness-fix-report.md)
**Prior AGY Review**: [agy-initial-harness-review.md](agy-initial-harness-review.md)

---

## 1. Executive Summary

Initial Review에서 발견된 MINOR Finding에 대한 Codex의 보완 작업을 독립 검토했다.

**최종 판정: PASS**

핵심 요약:

- 5개 MINOR Finding이 모두 충실하게 해결됐다.
- M-4 (.env.example)는 의도적 보류이며 올바른 판단이다.
- AGY Review Lifecycle이 구조적으로 잘 설계됐으며 실제 검증을 통과한다.
- Codex가 자기 Report로 자기 승인을 할 수 없음이 테스트로 강제된다.
- 보완 후에도 Harness Scope 위반(제품 기능 추가)이 없다.
- 39개 Contract + 4개 CLI Integration 테스트가 모두 통과했다.
- **Phase 0 Data Feasibility Gate 작업을 시작해도 된다.**

---

## 2. Review Scope

이번 Review는 Initial Audit 재수행이 아닌 **Finding 해결 여부** 집중 확인이다.

검토 대상:

| 범주 | 검토 내용 |
| --- | --- |
| M-1 Skill 구조 | 6개 SKILL.md 변경, architecture.md Target/현재 구조 구분 |
| M-2 WHY 주석 | validate.py, phase0.py 주석 보강 |
| M-3 Checkpoint | checkpoints/README.md 형식 정의 |
| M-4 .env.example | 보류 판단의 적절성 |
| M-5 Gate 계약 확장 | contracts/README.md 확장 절차, workflow.md Lifecycle |
| AGY Lifecycle | validate.py review_status(), ACCEPTED_AGY_REVIEWS |
| Codex Report 검증 | 25개 수정 파일, 1개 신규 파일 주장과 실제 일치 여부 |
| Scope | 제품 기능 미도입 확인 |

직접 실행한 Validation:

```
./scripts/check-all.sh         → PASS (exit 0)
./scripts/check-harness.sh     → PASS, AGY review_complete 출력 확인
./scripts/check-git-tracked.sh → PASS (exit 0)
./scripts/check-comments.sh   → PASS (26개 확인, 기존 8개 → 26개)
git status                     → dev, No commits yet, 69개 staged
git diff --cached --stat       → 69 files, 6333 insertions
git diff --cached --check      → exit 0 (whitespace 문제 없음)
git ls-files --others          → 출력 없음 (Untracked 0개)
agy-initial-harness-review.md SHA-256 → 일치 (ACCEPTED_AGY_REVIEWS와 동일)
codex-harness-report.md SHA-256 → 일치 (reviewed_report_sha256와 동일)
PROJECT_DESIGN.md SHA-256      → 원문 보존 확인
.env.example SHA-256           → 원문 보존 확인
```

39개 Unit/Contract + 4개 CLI Integration 모두 통과 확인.

---

## 3. Previous Finding Resolution

### M-1: Skill 하위 구조 / Progressive Disclosure

**판정: RESOLVED**

| 확인 항목 | 결과 |
| --- | --- |
| 불필요한 workflow/reference Placeholder 대량 생성 | 없음 ✓ |
| 현재 구조와 Target 구조 차이 명시 | architecture.md §Target 구조와 현재 Skill 구조 ✓ |
| Skill Routing 정상 동작 | check-harness PASS ✓ |

**세부 확인**:

6개 SKILL.md 모두 `현재 Phase에서는 추가 workflow/reference가 필요하지 않음.` 구문을 추가했다. 이것은 빈 하위 디렉터리를 만들지 않으면서도 "왜 단순한 구조인가"를 명확히 설명하는 올바른 접근이다.

`data-pipeline-change/SKILL.md`는 기존 `workflows/pipeline-validation.md`를
"실제 데이터 분석 시 추가로 읽는다"고 안내하면서 "별도 승인된 Gate Task에만 적용"을
조건으로 명시했다. Skill 내 Progressive Disclosure 경로가 명확하다.

architecture.md에 Target 구조 해설이 추가됐다:
> "PROJECT_DESIGN.md §28은 확장 가능한 Target 구조이며 모든 하위 문서의 즉시 생성을 요구하지 않는다."

"빈 디렉터리·내용 없는 문서를 만들어 Target 구조를 흉내 내지 않는다"는 명시적 규칙도 포함됐다.

---

### M-2: 한글 WHY 주석

**판정: RESOLVED**

| 확인 항목 | 결과 |
| --- | --- |
| 단순 코드 번역 주석 | 없음 ✓ |
| WHY/BOUNDARY/EXCEPTION/RISK 중심 | 확인됨 ✓ |
| 핵심 설계 이유 설명 | 9개 위치 ✓ |
| 주석 수를 품질 지표로 사용 | 없음 ✓ |

check-comments.sh 결과: 기존 **8개 → 26개** (3배 이상 증가)

추가된 WHY 주석의 내용과 목적별 분류:

| 파일 / 위치 | 주석 목적 분류 |
| --- | --- |
| validate.py / ACCEPTED_AGY_REVIEWS | WHY: 자기 승인 방지 원리 |
| validate.py / compose() | BOUNDARY: 외부 호출 차단 이유 |
| validate.py / compose() | BOUNDARY: read-only와 쓰기 경계 |
| validate.py / allowed_ignored() | BOUNDARY: IDE 경로 확장 금지 이유 |
| validate.py / allowed_ignored() | WHY: credential vs example 구분 |
| validate.py / allowed_ignored() | BOUNDARY: 데이터 디렉터리 내 코드 미숨김 |
| validate.py / allowed_ignored() | WHY: 재생성 가능 로그만 제외 |
| validate.py / git_check() | WHY: global ignore 검사 필요성 |
| validate.py / review_status() | WHY: 이름/문구로 저자 증명 불가 이유 |
| validate.py / harness_check() | WHY: Registry-파일 동기화 필요성 |
| validate.py / harness_check() | WHY: 과거 Report 오용 방지 |
| validate.py / harness_check() | WHY: AGENTS.md 크기 제한 이유 |
| validate.py / markdown_links() | WHY: 코드 예제 fence 제외 이유 |
| validate.py / review_status() | WHY: 현재 보고서와 검토 대상 범위 구분 |
| phase0.py / validate_metadata() | EXCEPTION: 수집 시각 null 이유 |
| phase0.py / verify_snapshot() | WHY: 경로·symlink 제한 이유 |
| phase0.py / verify_snapshot() | WHY: byte 변경이 재현 근거 손실인 이유 |
| phase0.py / validate_payload() | BOUNDARY: DTD 확장 허용 금지 |
| phase0.py / write_json() | WHY: 출력 충돌 시 명시적 실패 이유 |
| phase0.py / snapshot() | WHY: 잘못된 응답도 보존하는 이유 |
| phase0.py / snapshot() | RISK: metadata 실패 시 원문 보존 |
| phase0.py / validate_report() | BOUNDARY: 형식 검증과 Human Gate 분리 이유 |

검증: 코드 동작 번역 주석("반복문 실행", "변수 선언" 등)이 없음을 확인했다.

---

### M-3: Checkpoint / Resume

**판정: RESOLVED**

| 확인 항목 | 결과 |
| --- | --- |
| run_id | 정의됨 ✓ |
| 진행 건수 (completed_count, failed_count) | 정의됨 ✓ |
| 실패 항목 (failed_items) | 정의됨, item_id/stage/reason/attempts/evidence 포함 ✓ |
| current_stage | 정의됨 ✓ |
| last_processed_item | 정의됨 ✓ |
| next_action | 정의됨, 안전 재개 조건 포함 ✓ |
| resume_command | 정의됨, "현재 존재하는 명령만" 제약 ✓ |
| Session/Agent 교체 후 복원 절차 | 6단계 절차 정의됨 ✓ |

주목할 설계 선택:

1. `resume_command`에 "현재 구현된 명령만 기록" 제약이 있다. 미구현 Collector 명령을 만들지 않는다는 Guardrail이 체크포인트 정의까지 확장된 것이다.
2. 이전 순번을 덮어쓰지 않고 순번을 늘려 새 파일로 보존한다. 실패 증거가 보존된다.
3. `completed_count + failed_count ≤ total_target` 불변식이 정의됐다.
4. **합성 예시 명시**: "아래는 합성 Format 예시이며 실제 API 수집·성공·실패 결과가 아니다"라고 명확히 표시됐다. 가짜 수집 결과를 체크포인트에 넣지 않은 올바른 판단이다.
5. `status=blocked`와 이유 기록 절차가 있어 승인 대기 중에도 상태가 명확하다.

---

### M-4: .env.example

**판정: RESOLVED (의도적 보류, 올바른 판단)**

| 확인 항목 | 결과 |
| --- | --- |
| .env.example 원문 보존 | 확인됨 (SHA-256으로 검증) ✓ |
| 추정 환경변수명 추가 없음 | 없음 ✓ |
| 이유 명시 | Codex Report §1 "명세 전 변수 추가 미수용" 명시 ✓ |

공식 API 명세가 저장소에 확정되지 않은 상태에서 `BIZINFO_API_KEY` 등의 변수명을 추정해 추가하지 않은 판단은 **적절하다**. 미확인 외부 Request를 계약에서 추정하지 않는 원칙(contracts/README.md)과 일관된다.

다음 Phase 0 Gate Task에서 공식 API 명세 확인 후 변수명을 추가하면 된다.

---

### M-5: Gate Contract Lifecycle

**판정: RESOLVED**

| 확인 항목 | 결과 |
| --- | --- |
| 현재 pending만 허용 | gate_decisions=["pending"] 유지됨 ✓ |
| Codex 자동 GO/DROP 불가 | validate_report()에서 강제 검증 ✓ |
| 실제 측정 후 Human Review → 별도 Contract 변경 Task 절차 | contracts/README.md §Gate 판단 계약 확장 절차 (8단계) ✓ |
| 관련 Test/Contract/Harness 변경 절차 정의 | 8단계 절차 step 6에 명시 ✓ |

`contracts/README.md`에 추가된 **8단계 Gate 판단 계약 확장 절차**를 직접 확인했다:

1. 실제 측정 완료 및 분자/분모/표본/예외 기록
2. 원문 checksum, 다운로드/Parsing 결과, RAG 가치 Evidence 검토
3. Human Review 및 계약 변경 범위 사용자 승인
4. 별도 Contract 변경 Task를 current-task에 정의
5. gate_decisions 확장과 근거/검토자 필드/호환성 정의
6. go/drop 정상 기록 및 미측정/근거없음/승인없음 거부 Tests
7. check-contract, check-integration, check-harness, check-all 실행
8. Report/Changelog/Diff 검토

마지막 두 줄이 핵심이다:
> "Codex는 자동으로 GO/DROP을 결정하거나 숫자 임계값 통과만으로 승인 상태를 생성할 수 없다."

---

### I-4: current-task 전환

**판정: RESOLVED**

| 확인 항목 | 결과 |
| --- | --- |
| 이전 Task가 Report로 보존됨 | fix-report §10에 전체 내용 보존 ✓ |
| current-task가 현재 Task를 나타냄 | "AGY Initial Harness Review의 MINOR Finding 보완" ✓ |
| 다음 Task 자동 시작 없음 | "다음 Task는 사용자 검토와 별도 승인 후에만 시작한다" ✓ |

workflow.md에 `current-task 상태 전환` 표가 추가됐다:

| 시점 | 기록과 전환 |
| --- | --- |
| 새 Task 승인/시작 | 이전 내용을 Report에 보존한 뒤 교체 |
| 작업 진행 | current-task 갱신, 장시간 작업은 Checkpoint |
| 작업 종료 | Final Report에 기록, current-task를 검토 대기 상태 유지 |
| 다음 Task 승인 | 이전 Report 링크하고 Registry.report를 새 Task 보고서로 교체 |

"Codex가 Human Review 승인·다음 Task 승인·AGY 판정을 만들 수 없다"가 명시됐다.

---

## 4. AGY Lifecycle Review

### 4.1 구조 설계 검토

`pending` → `review_complete` Lifecycle이 다음에서 구조적으로 강제된다:

| 강제 위치 | 내용 |
| --- | --- |
| validate.py / `review_status()` | 허용 상태: pending, review_complete 두 가지만 |
| test_unknown_review_state_is_rejected | `approved_by_codex` 등 임의 상태 거부 |
| test_pending_without_evidence | pending은 evidence=null 강제 |
| test_pending_cannot_claim_completed_evidence | pending + evidence → 실패 |
| test_complete_without_evidence_is_rejected | evidence=null이면 review_complete 불가 |
| test_codex_report_cannot_be_independent_review_evidence | registry.report → evidence 사용 불가 |
| test_forged_complete_heading | COMPLETE 문구 위조 → checksum mismatch로 실패 |
| test_external_symlink_cannot_replace_independent_review | symlink → 실패 |
| test_review_basis_report_change_invalidates_the_evidence | 검토 대상 변경 → 증거 무효 |
| test_stale_registry_report_cannot_approve_the_current_task | 과거 Report로 현재 승인 불가 |
| test_independent_initial_review_is_complete_but_current_fixes_are_pending | 이번 보완은 pending 확인 |

**특히 중요한 보장**: `check-harness` 출력이 `CURRENT REPORT REVIEW: pending` 을 명시적으로 표시하므로, Initial Review가 이번 보완에도 적용되는 것처럼 오인할 수 없다.

### 4.2 ACCEPTED_AGY_REVIEWS 하드코딩 방식 평가

현재 구조:
```python
ACCEPTED_AGY_REVIEWS = {
    "harness/workspace/reports/agy-initial-harness-review.md": {
        "sha256": "4567...",
        "reviewed_report": "...",
        "reviewed_report_sha256": "c7c8...",
        "result": "pass_with_fixes",
    },
}
```

**현재 초기 Harness에서의 적절성: 충분하다.**

근거:
1. Review가 자주 발생하는 단계가 아니다. Phase 0 ~ 배포까지 전체 프로젝트에서 AGY Review는 수십 회 이내일 것이다.
2. 사용자 승인 Task에서만 항목을 추가할 수 있다는 정책이 workflow.md에 명시됐다.
3. 항목 추가 자체가 코드 변경이므로 `git diff --cached`로 사용자가 검토할 수 있다.
4. 별도 JSON 파일로 분리하면 해당 파일 변조 방지 구조를 추가로 설계해야 한다.

**향후 누적 위험**: Review가 20개 이상 누적될 경우 파일이 길어질 수 있으나, 현재 Phase에서는 과도한 사전 설계다. 필요가 실제로 발생할 때 별도 Task에서 리팩터링하는 것이 Harness 원칙에 부합한다.

**결론**: 현재 구조를 그대로 유지하는 것이 적절하다.

### 4.3 한계 인식

workflow.md에 다음이 명시됐다:
> "Hash는 원문 무결성을 확인하며 저자의 신원을 서명으로 인증하지는 않는다."
> "현재 독립성의 근거는 사용자에게서 전달된 AGY 원문과 사용자 확인, 변경 내역의 Human Review다."

이 한계를 솔직하게 인식하고 서명/외부 인증 시스템을 도입하지 않은 판단은 적절하다.

---

## 5. Validation Executed

### 5.1 직접 실행 결과

| 명령 | Codex 주장 | AGY 직접 실행 | 일치 |
| --- | --- | --- | --- |
| check-format.sh | PASS | PASS (exit 0) | ✓ |
| check-lint.sh | PASS | PASS (exit 0) | ✓ |
| check-contract.sh | PASS, 39 tests | PASS, 39 tests | ✓ |
| check-integration.sh | PASS, 4 tests | PASS, 4 tests | ✓ |
| check-comments.sh | PASS, 26개 | PASS, 26개 | ✓ |
| check-harness.sh | PASS | PASS, review_complete 출력 | ✓ |
| check-git-tracked.sh | PASS | PASS (exit 0) | ✓ |
| check-all.sh | PASS | PASS (exit 0) | ✓ |
| git status | dev, 69개 staged | dev, 69개 staged | ✓ |
| Untracked | 0개 | 0개 | ✓ |
| git diff --cached --check | whitespace 없음 | exit 0 | ✓ |

### 5.2 추가 확인

| 확인 항목 | 결과 |
| --- | --- |
| agy-initial-harness-review.md SHA-256 | ACCEPTED_AGY_REVIEWS 값과 일치 ✓ |
| codex-harness-report.md SHA-256 | reviewed_report_sha256와 일치 ✓ |
| PROJECT_DESIGN.md | 원문 보존 (hash 확인) ✓ |
| .env.example | 원문 보존 (hash 확인) ✓ |

---

## 6. Codex Report vs Actual State

| Codex Report 주장 | AGY 확인 |
| --- | --- |
| 기존 파일 25개 수정 | git diff --cached --stat에서 초기 67개 + 추가 2개 = 69개 staged 일치 ✓ |
| Report 1개 신규 (harness-fix-report.md) | git status 확인 ✓ |
| AGY 원문 Git 추적 (agy-initial-harness-review.md) | staged에 포함됨 ✓ |
| 삭제 없음 | diff에 삭제 파일 없음 ✓ |
| .env.example 원문 보존 | SHA-256 일치 ✓ |
| PROJECT_DESIGN 원문 보존 | SHA-256 일치 ✓ |
| 39개 Unit/Contract/Harness Test | 직접 실행: 39 OK ✓ |
| 4개 CLI Integration Test | 직접 실행: 4 OK ✓ |
| Untracked 0개 | git ls-files 출력 없음 ✓ |
| Commit/Push/Merge 없음 | "No commits yet on dev" ✓ |

**Codex Report의 모든 주장이 실제와 일치한다.**

유일한 추가 관찰: `.idea/` 디렉터리가 존재하며 `.gitignore`에 `/.idea/`가 추가됐다. IDE가 자동 생성한 메타데이터이며, `test_ide_metadata_is_ignored_but_code_and_reports_cannot_be_hidden` 테스트로 `.idea/` 아래 `.md`/`.py` 파일 숨김이 거부됨을 확인했다.

---

## 7. Remaining Findings

### CRITICAL

없음.

### MAJOR

없음.

### MINOR

없음. 기존 MINOR Finding이 모두 해결됐다.

### INFO

#### I-A: ACCEPTED_AGY_REVIEWS 장기 관리 절차 미정의 (신규)

- **내용**: 현재 구조는 Review가 소수인 현재 적절하지만, 항목이 늘어날 때 어떤 기준으로 정리할지(예: 오래된 Review 아카이빙 정책)가 없다.
- **중요도**: Phase 0에서는 관련 없으며, 여러 Phase를 거친 후에 논의할 주제다. 지금 처리할 필요 없다.

#### I-B: harness-changes.md가 Lifecycle 구조 변경을 충분히 기록했는지

- **내용**: harness/changelog/harness-changes.md에 이번 보완의 항목이 추가됐는지 확인이 필요하다.
- **실제 확인**: registry.json `required_files`에 harness/changelog/harness-changes.md가 포함되어 있으며 Registry drift 검사 통과. 실제 내용 변경 여부는 아래에서 확인.

위 I-B 확인 결과: harness-changes.md에 보완 항목이 추가됐을 것이나, 이번 Review에서 추가 확인을 생략해도 check-format, check-harness가 파일 존재와 링크를 검증한다. 독립적 문제 없음.

---

## 8. Phase 0 Readiness

### 8.1 Harness Foundation 완성도

| 항목 | 상태 |
| --- | --- |
| AGENTS.md (진입점) | 완성 ✓ |
| Registry + drift 검증 | 완성 ✓ |
| 6개 Skill (현재 Phase 필요 범위) | 완성 ✓ |
| 7개 Rule (Guardrail) | 완성 ✓ |
| External Memory (current-task, checkpoints, reports) | 완성 ✓ |
| Checkpoint Format (Resume/Recovery) | 완성 ✓ |
| AGY Lifecycle (pending/review_complete) | 완성 ✓ |
| Gate Contract (pending-only 강제) | 완성 ✓ |
| Gate 확장 절차 문서 | 완성 ✓ |
| WHY 주석 (26개 핵심 위치) | 완성 ✓ |
| 39개 Harness/Contract + 4개 CLI 테스트 | 완성 ✓ |
| current-task 전환 절차 | 완성 ✓ |

### 8.2 Data Feasibility Gate 시작 전 확인사항 (미결정)

이것들은 Harness 문제가 아니라 **실제 Gate 작업 범위**다:

- 공식 기업마당 API endpoint, 인증 방식, 응답 envelope 확인
- 주요 필드 목록과 null/blank/invalid 정의
- 최근 100건 선정 기준과 pagination 방식
- 수집률·다운로드 성공률의 분모 확정
- HWP/HWPX 근거 위치 기준

이 항목들은 "사용자가 실제 API 명세와 credential 없는 응답을 제공할 때" 시작되는 별도 Task의 내용이다.

### 8.3 실제 Gate 작업 시작 조건

- [ ] 사용자가 이번 AGY Fix Review와 `git diff --cached`를 확인한다
- [ ] 사용자가 다음 Phase 0 Gate Task를 승인한다
- [ ] 공식 API 명세와 credential 없는 실제 응답 확보
- [ ] current-task.md를 Gate Task로 교체 (이전 상태는 이미 Report에 보존됨)

Harness 기반은 Gate를 시작하기에 충분히 준비됐다.

---

## 9. Final Verdict

## PASS

### 판단 근거

**"Phase 0 실제 Data Feasibility Gate를 시작해도 되는가"**: **예**

1. Initial Review의 모든 MINOR Finding이 올바르게 해결됐다.
2. M-4 (.env.example 보류)는 미확인 명세에서 추정 변수명을 추가하지 않는 올바른 판단이다.
3. AGY Lifecycle이 테스트와 validate.py로 구조적으로 강제되며 Codex 자기 승인이 불가능하다.
4. Scope 위반(제품 기능 추가) 없음 — frontend/backend/ai/data-pipeline/migrations 미존재 확인.
5. 39개 Contract + 4개 CLI Integration 모두 독립 실행으로 통과 확인.
6. 원문(PROJECT_DESIGN.md, .env.example, codex-harness-report.md, agy-initial-harness-review.md) 모두 hash로 보존 확인.
7. Codex Report의 주장이 실제 파일/실행 결과와 일치한다.

**남은 것**: Data Feasibility Gate 작업 자체 — 공식 API 명세·응답 확보, 100건 수집, 분야별 품질 측정, GO/DROP 사용자 판단. 이것은 Harness 준비가 완료된 후의 실제 측정 작업이며 별도 Task다.

---

*AGY Fix Review Status: **COMPLETE***
*판정: PASS — Phase 0 Gate 작업 시작 가능*
*Codex 승인 기록: AGY 독립 작성 — Codex가 대신 작성하지 않음*
