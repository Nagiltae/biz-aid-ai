# AGY Initial Harness Review

**Reviewer**: AGY (Antigravity — 독립 Reviewer)
**Review Date**: 2026-09-27
**Codex Report**: [2026-09-27-codex-harness-report.md](2026-09-27-codex-harness-report.md)
**Review Basis**: 독립 파일 확인 + 직접 Validation 실행

---

## 1. Executive Summary

Codex가 구축한 Phase 0 Harness Engineering 결과물을 독립적으로 검토했다.

전체 판정은 **PASS WITH FIXES**다.

핵심 요약:

- Validation Script는 실제 검증을 수행하며 가짜 `exit 0`이 없다.
- Harness 구조(Registry, Context Engineering, Progressive Disclosure, External Memory)가 대체로 잘 구성됐다.
- Scope 제한(Phase 0 범위 준수, MongoDB/Langfuse/LangGraph 미도입)이 올바르게 지켜졌다.
- Generator / Evaluator 분리가 문서와 검증 양쪽에서 명시되어 있다.
- 그러나 여러 **MINOR** 수준의 미비점이 발견됐다.
- **CRITICAL** 또는 **MAJOR** 수준의 Blocker는 없다.

---

## 2. Review Scope

검토한 파일 전체 목록:

| 범주 | 검토 대상 |
| --- | --- |
| 설계 | PROJECT_DESIGN.md (전체 §1–58) |
| 진입점 | AGENTS.md |
| Harness 문서 | harness/docs/ 전부 (7개) |
| Harness 규칙 | harness/rules/ 전부 (7개) |
| Harness Skill | harness/skills/ 전부 (6개 SKILL.md + 1개 workflow) |
| Agent 정의 | harness/agents/ (2개) |
| Registry | harness/registry.json |
| Workspace | current-task.md, reports/, artifacts/, checkpoints/ |
| Changelog | harness/changelog/harness-changes.md |
| 계약 | contracts/ 전체 (README 5개 + schemas 2개) |
| Scripts | scripts/ 전부 (9개 sh + lib/validate.py + phase0.py) |
| Tests | tests/ 전부 (3개 py) |
| CI | .github/workflows/ci.yml |
| Docker | docker-compose.yml |
| 기타 | .gitignore, .env.example, README.md, infra/README.md |
| Artifacts | 2026-09-27-check-all.log, docker-smoke-20260927.json |

직접 실행한 Validation:

```
./scripts/check-harness.sh   → PASS (exit 0)
./scripts/check-git-tracked.sh → PASS (exit 0)
./scripts/check-all.sh         → PASS (exit 0)
git status                     → dev, No commits yet, 67개 staged
git diff --cached --stat       → 67 files, 5059 insertions
git ls-files --others --exclude-standard → (출력 없음 — Untracked 0개)
```

Codex Report 주장과 AGY 직접 실행 결과가 일치한다.

---

## 3. Validation Executed

| Validation | Codex 주장 | AGY 독립 실행 결과 | 일치 여부 |
| --- | --- | --- | --- |
| check-all.sh PASS | PASS | PASS (exit 0) | ✓ |
| 27개 Unit/Contract 테스트 | PASS | PASS (27 tests, 2.47s) | ✓ |
| 4개 CLI Integration 테스트 | PASS | PASS (4 tests, 0.23s) | ✓ |
| check-harness.sh | PASS | PASS | ✓ |
| check-git-tracked.sh | PASS | PASS | ✓ |
| check-comments.sh (8개 확인) | PASS | PASS | ✓ |
| Untracked 프로젝트 파일 0개 | 0개 | 0개 | ✓ |
| Staged 파일 수 67개 | 67개 | 67개 | ✓ |
| Docker smoke (NOT_MEASURED) | PASS | 파일 확인 (ignore됨) | ✓ |

가짜 exit 0 검증 여부: **없음 — 실제 검증 수행 확인됨**.

미구현 N/A 투명성: check-all.sh, testing.md, Codex Report 모두 일관되게
"제품 Unit/E2E/AI Eval/Build는 N/A"임을 명시하고 있다.

---

## 4. Architecture Review

### 4.1 Layer Boundary

| 경계 | PROJECT_DESIGN.md 원칙 | 현재 Harness 반영 |
| --- | --- | --- |
| React → FastAPI 직접 호출 금지 | §5, §6.2 | file-boundaries.md ✓ |
| FastAPI가 서비스 DB를 임의 수정하지 않음 | §6.3 | file-boundaries.md ✓ |
| Spring Boot = Source of Truth | §6.2 | architecture.md, file-boundaries.md ✓ |
| MySQL = 구조화 결정론적 필터 | §3 | architecture.md, database-rules.md ✓ |
| Qdrant = 문서 Chunk Semantic Retrieval | §8 | rag.md, ai-boundary-rules.md ✓ |
| LLM = 판단과 설명만 | §3, §16 | ai-boundary-rules.md ✓ |
| Data Pipeline ↔ 서비스 Domain 분리 | §19 | file-boundaries.md ✓ |

경계 위반 없음. MongoDB, Langfuse, LangGraph, Indexing 미도입 확인됨.

### 4.2 현재 구현 범위

`harness/registry.json`의 `unimplemented_modules`가 정확히 표시됨:
`["frontend", "backend", "ai", "data-pipeline", "migrations"]`

architecture.md의 현재 상태 표가 실제 파일 구조와 일치한다.

### 4.3 Phase 0 Scope 준수

Phase 0 금지 항목 미도입 확인:
- React/Spring Boot/FastAPI 코드 없음 ✓
- DB Migration 없음 ✓
- RAG/LangGraph/Indexing 없음 ✓
- 회원 시스템 없음 ✓
- 운영 배포 코드 없음 ✓

---

## 5. Harness Review

### 5.1 Context Engineering / Progressive Disclosure

AGENTS.md (49줄)는 간결하고 Router 역할에 집중한다.
전체 Harness 문서를 항상 읽게 강요하지 않으며,
작업 종류별로 필요한 Rule/Skill만 선택하도록 되어 있다.

check-harness.sh는 AGENTS.md 줄 수를 100줄 이하로 제한하며,
Skill이 AGENTS.md의 Routing Table에 연결됐는지 검사한다.

구현된 Progressive Disclosure 경로:

```
AGENTS.md (Routing Table)
  → harness/rules/ (작업별 Constraint)
  → harness/skills/*/SKILL.md (description → SKILL.md → workflow)
  → harness/docs/ (Architecture/Testing/Pipeline 등 상세)
```

흐름 연결 확인: **AGENTS.md Routing Table → SKILL.md 링크 연결이 실제로 동작함**.

### 5.2 Registry

registry.json이 실제 파일 목록과 일치하는지 harness_check()가 검증한다:
- required_files 67개 ↔ 실제 staged 파일 67개 ✓
- skills 6개 ↔ harness/skills/ 디렉터리 6개 ✓
- rules 7개 ↔ harness/rules/ 파일 7개 ✓
- agents 2개 ↔ harness/agents/ 파일 2개 ✓
- execution_files (py/sh) ↔ 실제 코드 파일 일치 ✓

Registry Drift 탐지가 실제로 동작함 (test_unimplemented_module_cannot_be_silently_added 등).

### 5.3 Agent Routing

Codex와 AGY의 역할 분리가 다음에서 명시됨:
- AGENTS.md "반드시 지킬 것" 섹션
- harness/agents/codex-developer.md
- harness/agents/agy-reviewer.md
- Codex Report §9 마지막 행: "AGY 독립 검토와 Human review도 pending이다."
- registry.json의 `"agy_review": "pending"`

중요: **Codex가 AGY 승인 기록을 작성하지 않았음을 확인했다**.
harness_check()가 `agy_review != "pending"`이면 실패하도록 강제한다.

### 5.4 Guardrail / Least Privilege

| Guardrail | 구현 위치 |
| --- | --- |
| dev branch 강제 | git_check()의 branch 검사 + CI |
| Untracked 파일 감지 | git_check()의 untracked 검사 |
| Ignore로 결과물 숨김 금지 | git_check()의 allowed_ignored() + check-ignore |
| 미구현 모듈 추가 감지 | harness_check()의 unimplemented_modules 검사 |
| AGY 자기 승인 금지 | harness_check()의 agy_review 검사 |
| Secret Git 미포함 | .gitignore + .env.example |
| 원문 덮어쓰기 금지 | phase0.py의 `open("xb")` 모드 |
| 가짜 Gate GO 금지 | phase0-report.contract.json의 gate_decisions 제한 |

### 5.5 External Memory / State / Resume

현재 세션 종료 후 다른 Agent가 파악할 수 있는 정보:
- `current-task.md` → 현재 무엇을 하는지, 허용/금지 범위, 다음 작업 ✓
- `reports/2026-09-27-codex-harness-report.md` → 무엇이 완료됐는지 ✓
- `registry.json`의 `"agy_review": "pending"` → 어디까지 했는지 ✓
- `checkpoints/README.md` → 체크포인트 구조 준비됨 (현재 체크포인트 없음)
- `artifacts/2026-09-27-check-all.log` → 어떤 검증을 했는지 ✓

**주목할 점**: checkpoints/ 디렉터리에 실제 체크포인트 파일이 없다.
현재 작업이 단일 세션으로 완료되었으므로 문제는 아니지만,
장기 작업 시 체크포인트 활용 절차가 명시적이지 않다 (MINOR 등록).

### 5.6 Deterministic Verification

각 Script 실제 검증 내용 분석:

| Script | 실제 검증 | 실패 조건 | 가짜 PASS 여부 |
| --- | --- | --- | --- |
| setup.sh | Python ≥3.11, bash/git 존재, Docker Compose ≥2, Compose 설정 | 버전 미달, 명령 누락 | 없음 ✓ |
| check-format.sh | UTF-8/LF/newline/trailing whitespace/JSON 정규화/git whitespace | 형식 위반 | 없음 ✓ |
| check-lint.sh | Python AST, Bash syntax, 실행권한, JSON 중복 key | 구문 오류 | 없음 ✓ |
| check-contract.sh | 27개 Unit/Contract 테스트 실행 | 테스트 실패 | 없음 ✓ |
| check-integration.sh | 4개 CLI 실제 subprocess 테스트 | 프로세스 오류 | 없음 ✓ |
| check-git-tracked.sh | branch, untracked, ignore, staged 동기화 | 정책 위반 | 없음 ✓ |
| check-comments.sh | Python 토큰/AST, Bash 주석 한글 여부 | 영어 주석 | 없음 ✓ |
| check-harness.sh | Registry drift, 링크, Skill, CI, Compose | Drift | 없음 ✓ |
| check-all.sh | 위 전부 실행, 하나라도 실패 시 exit 1 | 부분 실패 | 없음 ✓ |

특히 `test_failure_is_not_masked_by_later_success` 테스트가
check-all.sh의 실패 마스킹을 방지함을 검증하고 있다 (실제 테스트 통과 확인).

### 5.7 Harness Drift 검증 (check-harness.sh)

check-harness.sh가 실제로 검증하는 항목:
- AGENTS.md 줄 수 ≤ 100 ✓
- Skill이 AGENTS.md Routing에 있는지 ✓
- SKILL.md frontmatter (name, description) 형식 ✓
- `[TODO:` 미완성 표지 ✓
- Registry required_files ↔ 실제 파일 ✓
- execution_files (py/sh) ↔ Registry ✓
- unimplemented_modules 디렉터리 미존재 ✓
- `.github/workflows/`에 ci.yml만 있는지 ✓
- ci.yml의 branches: [dev], permissions: contents: read ✓
- ci.yml에 setup.sh, check-all.sh run이 있는지 ✓
- Compose 서비스와 Registry 일치 ✓
- Compose mount, entrypoint, network_mode, read_only ✓
- Harness Report 파일 존재 ✓
- 모든 md 링크의 대상 파일 존재 ✓

매우 포괄적으로 자기 검증이 구현되어 있다.

---

## 6. Git / Branch Review

| 검토 항목 | 상태 |
| --- | --- |
| 현재 브랜치 | dev ✓ |
| Commit 존재 | No commits yet (최초 상태) ✓ |
| Staged 파일 수 | 67개 (신규, 삭제·수정 없음) ✓ |
| Untracked 프로젝트 파일 | 0개 ✓ |
| main/op 변경 | 없음 ✓ |
| 임의 Push/Merge | 없음 ✓ |
| Force push | 없음 ✓ |
| Branch 삭제 | 없음 ✓ |
| .gitignore 범위 | Secret/credential/cache/payload만 제외, 결과물 문서 포함됨 ✓ |
| 정상 Ignore 대상 | .DS_Store, .env, .venv, __pycache__, data/raw/* 등 ✓ |
| 잘못된 Ignore | 발견되지 않음 ✓ |

`allowed_ignored()` 함수 분석:
- `data/raw/**`, `data/downloaded/**` 등의 payload 파일 → 허용 ✓
- `harness/workspace/artifacts/*.json`, `*.log` → 허용 ✓
  (단: 이 파일들은 재생성 가능한 실행 결과임. Codex Report가 해석·증거는 추적 Report에 남긴다고 명시함 ✓)
- `.md`, `.py`, `.sh`, `.yml` 확장자는 data 디렉터리에서도 추적 대상 ✓

---

## 7. Contract Review

| 계약 영역 | 상태 | 문제 |
| --- | --- | --- |
| Raw snapshot (로컬) | 구현됨, 실제 검증 통과 | 없음 ✓ |
| Phase 0 report (로컬) | 구현됨, 실제 검증 통과 | 없음 ✓ |
| 기업마당 API (upstream) | 미확정 상태 명시 | 없음 ✓ |
| React ↔ Spring Boot | 미구현 명시 | 없음 ✓ |
| Spring Boot ↔ FastAPI | 미구현 명시 | 없음 ✓ |
| FastAPI ↔ Qdrant payload | 미구현 명시 | 없음 ✓ |

**중요 검증**: 가짜 Contract 통과 여부 확인.

`contracts/schemas/phase0-report.contract.json`의 `gate_decisions`가
`["pending"]`만 허용하므로 "go"나 "drop"을 기계적으로 생성할 수 없다.
이것은 validate_report()에서 강제 검증된다.

upstream API 계약을 추정해서 만들지 않았음을 확인했다.
`contracts/external-api/README.md`는 계약이 아니라 "확인할 증거 목록"으로 명시되어 있다.

---

## 8. Test / Validation Review

### 8.1 구현된 테스트 목록

**tests/contract/test_phase0.py** (18개):
- 초기 Report가 not_measured + pending인지 ✓
- 누락/미지 field 거부 ✓
- 미측정 metric에 수치/성공 주장 불가 ✓
- rate 분자/분모/일치 검증 ✓
- count/distribution/qualitative 타입 검증 ✓
- 불가능한 null rate (>1) 거부 ✓
- gate=go 사전 주장 불가 ✓
- timezone 없는 timestamp 거부 ✓
- target_count 임의 변경 불가 ✓
- 원본 보존·경로 traversal 방지·XSS·DTD 차단 등 ✓

**tests/contract/test_harness_policy.py** (9개):
- 유효한 Registry가 통과하는지 ✓
- 깨진 링크 탐지 ✓
- Untracked 파일 탐지 ✓
- Ignore로 결과물 숨김 탐지 ✓
- 잘못된 브랜치 거부 ✓
- 미구현 모듈 추가 탐지 ✓
- CI branch drift 탐지 ✓
- 영어 설명 주석 거부 ✓
- 부분 실패 마스킹 방지 ✓

**tests/integration/test_phase0_cli.py** (4개):
- snapshot→verify→init-report→validate-report 전체 흐름 ✓
- 기존 파일 덮어쓰기 금지 ✓
- 잘못된 계약/누락 입력 실패 ✓
- CLI 사용 오류(exit 2) 구분 ✓

### 8.2 커버리지 사각지대 (N/A로 명시됨)

- 실제 기업마당 API 수집 테스트 없음 (명시됨)
- PDF/HWP/HWPX Parser 테스트 없음 (명시됨)
- Spring Boot/FastAPI/React 테스트 없음 (명시됨)
- E2E/AI Eval 없음 (명시됨)

사각지대는 testing.md와 check-all.sh 출력에서 명확히 N/A로 표시됨.

---

## 9. CI Review

```yaml
on:
  push:
    branches: [dev]
permissions:
  contents: read
```

| 항목 | 상태 |
| --- | --- |
| dev Push 트리거 | ✓ |
| read-only 권한 | ✓ |
| setup.sh 실행 | ✓ |
| check-all.sh 실행 | ✓ |
| 자동 merge/push | 없음 ✓ |
| 가짜 Deploy Workflow | 없음 ✓ |

**중요 확인사항**: `deploy-op.yml`이 없음.

PROJECT_DESIGN.md §28 구조도에는 `.github/workflows/deploy-op.yml`이
"(추후 구현)"으로 명시되어 있다.
현재 harness_check()는 `ci.yml`만 있어야 통과하도록 설계되어 있다
(`if workflows != {".github/workflows/ci.yml"}: raise`).

이것은 의도된 설계다: 운영 배포 환경이 미결정이므로 가짜 deploy-op.yml을
만들지 않은 것은 **올바른 판단**이다.

workflow.md에서 "현재 운영 배포 workflow는 없다"고 명시됨 ✓.

CI가 GitHub Actions에서 실제 실행됐는지는 이 Review에서 확인 불가
(로컬 환경, 원격 실행은 별도 확인 필요).

---

## 10. Data Feasibility Readiness

### 10.1 Gate 준비 구조

| 항목 | 상태 |
| --- | --- |
| Phase 0 Report 계약 | 구현됨 ✓ |
| 22개 측정 지표 정의 | 계약에 명시 ✓ |
| 초기 합격 기준 (threshold) | 계약에 명시됨, "Human review 필요" 조건부 ✓ |
| 자동 GO 불가 구조 | gate_decisions=["pending"] 강제 ✓ |
| Raw 보존 도구 | phase0.py snapshot 구현됨 ✓ |
| Checksum 검증 | verify-snapshot 구현됨 ✓ |
| 잘못된 응답 보존 | payload_syntax=invalid 처리 ✓ |
| 재실행 방지 | 동일 run-id 덮어쓰기 금지 ✓ |
| 실제 API 수집 도구 | 미구현 (올바른 판단) |
| 실제 100건 데이터 | 미수집 (Phase 0 Gate 실행 전) |

### 10.2 미결정 사항 문서화 (Codex Report §11 + architecture.md)

모두 올바르게 보류됨:
- API endpoint/인증/envelope/pagination 미확인 ✓
- 주요 필드 목록, null/blank/invalid 정의 미결정 ✓
- 수집 분모 미결정 ✓
- 100건 선정 기준 미결정 ✓
- HWP/HWPX page 대체 규칙 미결정 ✓
- §57의 "API 응답 확인" 주장 재현 증거 없음 → 사용하지 않음 ✓

---

## 11. Overengineering Review

| 항목 | 판정 |
| --- | --- |
| 사용하지 않는 Agent | 없음. 2개만 정의됨 ✓ |
| 불필요한 Docker 서비스 | 없음. phase0만 있음 ✓ |
| MongoDB/Langfuse 추가 | 없음 ✓ |
| 전체 Pipeline 조기 구현 | 없음 ✓ |
| 제품 DB/Migration | 없음 ✓ |
| 가짜 완성 Contract | 없음. 미구현 영역은 README만 있음 ✓ |
| 불필요한 Placeholder 구조 | data/downloaded, data/parsed, data/failed README만 존재 — Phase 0에서 필요한 범위 ✓ |

Skill 6개가 적절한지:

현재 Phase 0에서 바로 필요한 Skill은 `data-pipeline-change`, `feature-development` 정도다.
`database-migration`, `rag-change`는 "향후 작업" 절차이나 SKILL.md 자체에
"현재 구현하지 않는다"고 명시되어 있어 오남용 방지가 되어 있다.

전체적으로 Overengineering이 없다는 판단이다.

---

## 12. Findings

### CRITICAL

없음.

---

### MAJOR

없음.

---

### MINOR

#### M-1: Skill 하위 구조 불완전 (PROJECT_DESIGN.md §28 vs 실제)

- **관련 파일**: `harness/skills/`, PROJECT_DESIGN.md §28, §34
- **문제 내용**: PROJECT_DESIGN.md §28 구조도는 각 Skill 디렉터리에
  `workflows/`와 `references/` 하위 폴더를 명시한다.
  예: `feature-development/workflows/feature-flow.md`,
  `feature-development/references/checklist.md`,
  `debugging/workflows/rca.md` 등.
  현재 구현에서 `data-pipeline-change/workflows/pipeline-validation.md`만 존재하며
  나머지 5개 Skill에는 하위 폴더가 없다.
- **Evidence**:
  ```
  find harness/skills -type f
  → SKILL.md 6개 + workflows/pipeline-validation.md 1개
  ```
  §28에 `feature-development/workflows/feature-flow.md` 등 명시됨.
- **왜 문제인가**: SKILL.md가 "필요한 workflow/reference만 추가 확인"을
  안내하는 구조인데, 해당 문서가 없으면 SKILL.md가 최종 도착점이 된다.
  복잡한 작업에서 Progressive Disclosure의 다음 단계가 없다.
- **Harness 원칙**: Progressive Disclosure, Skill Routing (§34, §1200)
- **권장 수정 방향**: 각 Skill의 하위 workflow/reference가 현재 Phase 0에서
  필요한지 판단하고, 필요하다면 추가하거나 SKILL.md에 "현재 하위 절차 없음"을
  명시한다. PROJECT_DESIGN.md §28의 디렉터리 구조가 최종 목표 구조라면
  architecture.md에 "현재 단순화된 Skill 구조" 상태를 기록한다.

#### M-2: 한글 주석 8개로 커버리지가 매우 작음

- **관련 파일**: `scripts/phase0.py`, `scripts/lib/validate.py`
- **문제 내용**: check-comments.sh가 "8개 checked"라고 출력한다.
  phase0.py는 325줄, validate.py는 296줄로 총 621줄의 실질적 코드인데
  설명성 주석이 8개에 불과하다.
- **Evidence**:
  ```
  check-comments.sh → PASS: Korean explanatory comments (8 checked)
  ```
  phase0.py의 주석: `# Metadata로 저장소 밖의 파일을 읽지 못하도록...`,
  `# 잘못된 응답도 Source 문제 재현에 필요하므로...`,
  `# 외부 원문을 검사하는 준비 도구이므로...`,
  `# 원문 재처리 증거를 잃지 않도록...`,
  `# 미측정을 0이나 성공으로 해석하면...`
  validate.py의 주석: `# CI checkout의 detached HEAD는...`,
  `# global ignore까지 검사해...`,
  `# 코드 예제 안의 문자열은...`
- **왜 문제인가**: code-comment-policy.md가 WHY/BOUNDARY/EXCEPTION/RISK 주석을
  요구하는데 621줄 코드에 8개는 부족하다. validate.py의 `compose()` 함수 내
  Compose 제약 검사 이유, `allowed_ignored()` 함수의 허용 조건 이유,
  `harness_check()` 내 여러 정책 강제 이유에 주석이 없다.
- **Harness 원칙**: code-comment-policy.md, §32
- **권장 수정 방향**: WHY 관점의 핵심 설계 결정에 한글 주석 추가.
  특히 validate.py의 compose() 검증 조건, allowed_ignored() 분류 기준,
  harness_check()의 agy_review 강제 이유에 주석을 추가한다.
  단, 코드 번역 주석은 추가하지 않는다.

#### M-3: checkpoints/ 활용 절차 미정의

- **관련 파일**: `harness/workspace/checkpoints/README.md`
- **문제 내용**: checkpoints/ 디렉터리는 존재하지만 README에 구체적인
  체크포인트 저장 형식, 복원 절차, 어떤 상황에서 사용하는지가 명시되지 않는다.
- **Evidence**: `checkpoints/README.md` 내용 확인 — 빈 placeholder 수준
- **왜 문제인가**: External Memory / Resume 원칙(§35)에 따라 세션 교체 후
  다른 Agent가 작업을 이어받을 수 있어야 하는데, 체크포인트 형식이 없으면
  실제 장기 작업(API 100건 수집 등)에서 활용이 어렵다.
- **Harness 원칙**: Workspace/External Memory, Resume/Recovery (§35)
- **권장 수정 방향**: 실제 100건 수집 작업 시작 전에 체크포인트 형식(run-id,
  완료 건수, 실패 항목, 다음 단계)을 checkpoints/README.md에 정의한다.

#### M-4: .env.example이 실질적으로 비어 있음

- **관련 파일**: `.env.example`
- **문제 내용**: .env.example이 주석 2줄뿐이다. "실제 API 계약 확인 후
  필요한 변수 이름을 추가하라"고 안내하나, 현재 API 관련 사전 준비가
  전혀 없다. `BIZINFO_API_KEY`나 `BIZINFO_API_URL` 등의 변수 이름 예시조차 없다.
- **Evidence**: `.env.example` 파일 내용 3줄
- **왜 문제인가**: 다음 Phase 0 Gate 작업(실제 API 100건 수집)을 위해
  어떤 환경변수가 필요한지 미리 식별해두지 않으면, 수집 작업 시
  인증 방법이 불명확한 상태로 시작할 수 있다.
- **Harness 원칙**: 미결정 사항을 기술 도입으로 해결하지 않는 원칙과 연관
- **권장 수정 방향**: 공식 API 명세 확인 후 최소 변수 이름(값 없이)을
  .env.example에 추가한다. 단, 공식 명세 확인 전에는 추정 변수명을
  임의로 추가하지 않는다.

#### M-5: `phase0-report.contract.json`의 `gate_decisions`에 "go"/"drop"이 없음

- **관련 파일**: `contracts/schemas/phase0-report.contract.json`
- **문제 내용**: `gate_decisions`가 `["pending"]`만 허용한다.
  이는 현재 단계에서는 올바른 제약이지만, 실제 Gate 판단 단계에서
  "go"/"drop"을 기록하려면 계약을 변경해야 한다.
  이 변경 절차가 어디에도 명시되어 있지 않다.
- **Evidence**: `phase0-report.contract.json` line 45-47
- **왜 문제인가**: 다음 단계(실제 100건 측정 후 GO/DROP 판단)에서
  계약을 변경해야 할 때 절차가 불분명하다.
- **Harness 원칙**: Contract First, Harness Evolution
- **권장 수정 방향**: contracts/README.md 또는 contracts/schemas/에
  "Gate 판단 계약 확장 절차"를 간단히 기록한다.
  확장 시 contracts/README.md와 tests/를 함께 업데이트한다.

---

### INFO

#### I-1: Harness Evaluation (harness/evals/) 기준 데이터 없음

- **관련 파일**: `harness/evals/agent-eval.md`, `harness/evals/skill-eval.md`
- **내용**: Codex 단독 vs Codex+AGY 비교 평가 구조가 준비됐으나
  현재 기준(baseline) 데이터가 없다. "현재 비교 결과 없음"이 파일에
  명시되어 있으므로 문제는 아니다. 이번 AGY Review가 첫 데이터 포인트가 될 수 있다.

#### I-2: 도커 smoke 결과물이 ignore됨

- **관련 파일**: `harness/workspace/artifacts/docker-smoke-20260927.json`
- **내용**: `harness/workspace/artifacts/*.json`이 .gitignore에 포함되어
  있어 docker-smoke 결과가 staged되지 않는다. Codex Report §8에서
  "재생성 가능한 log/JSON은 ignore하고 해석·결과는 추적된 Report에 남긴다"고
  명시했으므로 의도된 설계다. 단, 이 파일이 CI에서는 생성되지 않으므로
  CI에서 docker smoke가 실행될 경우 결과 추적 방법이 필요하다.

#### I-3: §57의 "실제 API 응답 확인" 주장의 재현 증거 부재

- **관련 파일**: PROJECT_DESIGN.md §57, architecture.md §7
- **내용**: PROJECT_DESIGN.md §57이 "기업마당 API 발견 → 실제 API 응답 확인"을
  완료된 것처럼 서술하지만 저장소에 증거가 없다. Codex가 이를 올바르게
  식별하고 "이번 실행 결과로 재사용하지 않는다"고 명시했다.
  설계 문서의 이 부분은 과거 수작업 확인의 기록일 수 있으며,
  Harness 관점에서는 재현 가능한 증거가 없다.

#### I-4: 현재 Phase와 다음 Phase 경계가 current-task.md에서 불명확

- **관련 파일**: `harness/workspace/current-task.md`
- **내용**: "다음 단계"가 "AGY 검토 후 실제 명세·응답 제공"이라고 되어 있으나,
  구체적인 다음 Task 파일 생성 절차가 없다. 다음 Task가 시작될 때
  current-task.md를 어떻게 전환할지(새 파일 생성 vs 내용 교체)가
  workflow.md에 명시되어 있지 않다.

---

## 13. Codex Report vs Actual State

| Codex 주장 | AGY 확인 결과 | 일치 |
| --- | --- | --- |
| 67개 파일 신규 생성 (PROJECT_DESIGN.md 포함) | git diff --cached --stat: 67 files ✓ | ✓ |
| check-all PASS | 직접 실행: PASS ✓ | ✓ |
| 27개 Unit/Contract 테스트 PASS | 직접 실행: 27 tests OK ✓ | ✓ |
| 4개 CLI Integration PASS | 직접 실행: 4 tests OK ✓ | ✓ |
| AGY 검토 PENDING | registry.json agy_review="pending", 본 Review 이전 ✓ | ✓ |
| 원문 수정·삭제 없음 | PROJECT_DESIGN.md 내용 변경 없음 ✓ | ✓ |
| Commit·Push·Merge 없음 | "No commits yet on dev" ✓ | ✓ |
| MongoDB/Langfuse 미도입 | 파일 없음, docker-compose.yml에 없음 ✓ | ✓ |
| React/Spring Boot/FastAPI 미구현 | 해당 디렉터리 없음 ✓ | ✓ |
| 한글 주석 8개 | check-comments 출력: 8 checked ✓ | ✓ |
| Gate=PENDING (자동 GO 불가) | gate_decisions=["pending"], docker-smoke 확인 ✓ | ✓ |
| 미구현 보고서 계약 검증 (not_measured) | validate_report() 강제 검증 ✓ | ✓ |
| Skill 6개 valid | check-harness Registry drift 없음 ✓ | ✓ |

Codex Report의 허위 주장은 발견되지 않았다.

---

## 14. Recommended Fixes

우선순위순 수정 권장사항:

### 권장-1 (MINOR M-2): 핵심 로직 한글 주석 보강

`validate.py`와 `phase0.py`에서 WHY가 빠진 핵심 결정에 한글 주석을 추가한다.

예시 대상:
- `validate.py`: `compose()` 함수의 network_mode/read_only 강제 이유
- `validate.py`: `allowed_ignored()` 분류 기준 (왜 artifacts/*.json은 허용하는가)
- `validate.py`: `harness_check()` 내 AGENTS.md 100줄 제한 이유

코드 번역 주석은 추가하지 않는다.

### 권장-2 (MINOR M-1): Skill 하위 구조 현황 명시

각 Skill의 SKILL.md에 "현재 추가 workflow/reference 없음 — Phase 0에서 불필요"를
명시하거나, 실제로 필요한 Skill(feature-development, debugging)에
간단한 workflow 문서를 추가한다.

### 권장-3 (MINOR M-3): checkpoints/ 형식 정의

실제 100건 Gate 수집 작업 시작 전에 체크포인트 형식을 정의한다.
최소: run-id, 완료 건수, 실패 목록, 다음 실행 명령.

### 권장-4 (MINOR M-5): 계약 확장 절차 기록

`contracts/README.md`에 Gate 판단 후 gate_decisions 확장 절차를 추가한다.

### 권장-5 (INFO I-4): current-task 전환 절차 명시

`harness/docs/workflow.md`에 Phase 전환 시 current-task.md
업데이트 절차(또는 새 파일 생성 규칙)를 추가한다.

---

## 15. Final Verdict

## PASS WITH FIXES

### 근거

**진행 가능 이유**:

1. Validation이 실제 검증을 수행하며 가짜 PASS가 없다.
2. Phase 0 Scope 제한이 올바르게 지켜졌다.
3. Generator/Evaluator 분리가 구조적으로 강제된다 (agy_review 검증).
4. Architecture Boundary가 rules에서 명확히 정의됐고 미구현이 투명하다.
5. Codex Report의 주장이 실제 파일/실행 결과와 일치한다.
6. 원문 보존/checksum/덮어쓰기 금지/경로 traversal 방지가 실제로 구현됐다.
7. MongoDB, Langfuse, LangGraph, 운영 인프라가 추가되지 않았다.

**수정 권장 이유** (CRITICAL/MAJOR 아님):

1. (M-1) Skill 하위 구조가 설계 문서(§28)와 불일치한다.
2. (M-2) 핵심 로직 WHY 주석이 부족하다 (8개/621줄).
3. (M-3) checkpoints/ 활용 절차가 없어 장기 작업 Resume에 불완전하다.
4. (M-5) Gate 판단 계약 확장 절차가 없다.

이 수정사항들은 다음 Phase 0 Gate 작업 시작 전이나 도중에 처리 가능하다.
현재 단계(Harness 구축 완료, AGY 검토 완료) 판정을 블로킹하지 않는다.

**다음 단계 조건**:

사용자가 이 Report와 `git diff --cached`를 검토한 후 Push 여부를 결정한다.
Push 후 실제 Phase 0 Gate 작업(100건 수집, URL 확인, 다운로드, Parsing)으로
별도 Task를 시작한다. 공식 API 명세와 credential 없는 실제 응답을 먼저 확보한다.

---

*AGY Review Status: **COMPLETE***
*Codex 승인 기록: AGY 독립 작성 — Codex가 대신 작성하지 않음*
