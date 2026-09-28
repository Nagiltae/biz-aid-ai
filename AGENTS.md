# Harness Entry Point

기업 프로필과 공고문 근거로 중소기업 지원사업을 탐색·검토하는 프로젝트다.
최상위 기준은 [PROJECT_DESIGN.md](PROJECT_DESIGN.md). 현재 **Phase 2 Full Document Acquisition**이다.

## 먼저 읽기

1. [현재 Task](harness/workspace/current-task.md)
2. [작업 절차](harness/docs/workflow.md), [Git 정책](harness/rules/git-policy.md)
3. 아래 Registry에서 작업에 필요한 Context / Rule / Skill만 선택한다.

## Project Map

예정 경계: React → Spring Boot → FastAPI.
Spring Boot / MySQL은 서비스 사실과 정확한 검색, FastAPI / Qdrant는 AI와 문서 근거를 담당한다.
제품 데이터 코드는 `data-pipeline/`, 공통 Flyway는 `migrations/`다. Phase 0 도구와 검증 증거는 보존한다.
[Architecture](harness/docs/architecture.md), [기계 Registry](harness/registry.json)가 실제 구현 상태를 기록한다.

## 반드시 지킬 것

- 개발은 dev에서만 한다. 임의 Push / Merge / force push / branch 삭제는 금지한다.
- 원문을 보존한다. Secret·Live payload는 Git에 넣지 않는다. 사용자 제공 sanitized Fixture 예외는 [Source 규칙](harness/rules/data-source-rules.md)을 따른다. Control/Input은 추적하고 Generated Workspace Output은 [Workflow](harness/docs/workflow.md)에 따라 non-gating으로 관리한다.
- 설명성 코드 주석은 한글 WHY / BOUNDARY / EXCEPTION / RISK로 작성한다.
- Codex는 Developer / Generator, AGY는 독립 Reviewer다. Codex가 AGY 승인 기록을 작성하지 않는다.
- Harness 규칙 완화·삭제 또는 큰 Architecture 변경은 먼저 보고하고 사용자 판단을 받는다.
- 현재 Task가 허용하지 않은 서비스·DB·RAG·LangGraph·Indexing을 구현하지 않는다.

## Routing Registry

| 작업 | Context / Rules | Skill |
| --- | --- | --- |
| Harness·환경 변경 | [Architecture](harness/docs/architecture.md), [Safety](harness/rules/safety.md), [파일 경계](harness/rules/file-boundaries.md) | [feature-development](harness/skills/feature-development/SKILL.md) |
| 오류 분석 | [Testing](harness/docs/testing.md), [주석](harness/rules/code-comment-policy.md) | [debugging](harness/skills/debugging/SKILL.md) |
| 데이터 실험 | [Pipeline](harness/docs/data-pipeline.md), [Source](harness/rules/data-source-rules.md) | [data-pipeline-change](harness/skills/data-pipeline-change/SKILL.md) |
| 계약 변경 | [Contracts](contracts/README.md), [Coding](harness/docs/coding-conventions.md) | [api-contract-change](harness/skills/api-contract-change/SKILL.md) |
| DB 변경 요청 | [DB 규칙](harness/rules/database-rules.md) | [database-migration](harness/skills/database-migration/SKILL.md) |
| RAG 변경 요청 | [RAG](harness/docs/rag.md), [AI 경계](harness/rules/ai-boundary-rules.md), [Observability](harness/docs/observability.md) | [rag-change](harness/skills/rag-change/SKILL.md) |

Skill은 현재 Task의 허용 범위를 늘리지 않는다. dev 구조화 FULL / 첫 soft-delete DRY_RUN이 승인됐으며 RAG는 미구현이다.
역할: [Codex](harness/agents/codex-developer.md), [AGY](harness/agents/agy-reviewer.md).

## Validation / DoD

`./scripts/setup.sh` → `./scripts/check-all.sh` → Report → AGY 검토 → Git Diff / 사용자 검토.
[Testing](harness/docs/testing.md)에 검사 범위·미구현 범위·종료 코드를 명시한다.
필수 조건은 입력 자산 검증 통과, 문서 동기화, 미추적 입력 파일 없음, 실행 결과 보고와 변경 목록 제공이다.
Generated Report / Checkpoint / Artifact 작성은 검증을 무효화하지 않는다. current-task·정적 README는 strict다.
Gate 통과나 AGY 검토를 실행하지 않고 통과했다고 기록하지 않는다.
Review 완료의 Evidence·검토 범위·Task 전환은 [Workflow](harness/docs/workflow.md)를 따른다.
변경 이유는 [Harness Changelog](harness/changelog/harness-changes.md)에 남긴다.
