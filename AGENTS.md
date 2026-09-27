# Harness Entry Point

기업 프로필과 공고문 근거로 중소기업 지원사업을 탐색·검토하는 프로젝트다.
최상위 기준은 [PROJECT_DESIGN.md](PROJECT_DESIGN.md). 현재 **Phase 0 준비**다.

## 먼저 읽기

1. [현재 Task](harness/workspace/current-task.md)
2. [작업 절차](harness/docs/workflow.md), [Git 정책](harness/rules/git-policy.md)
3. 아래 Registry에서 작업에 필요한 Context / Rule / Skill만 선택한다.

## Project Map

예정 경계: React → Spring Boot → FastAPI.
Spring Boot / MySQL은 서비스 사실과 정확한 검색, FastAPI / Qdrant는 AI와 문서 근거를 담당한다.
현재 실행 코드는 `scripts/phase0.py`와 검증 도구뿐이다.
[Architecture](harness/docs/architecture.md), [기계 Registry](harness/registry.json)가 실제 구현 상태를 기록한다.

## 반드시 지킬 것

- 개발은 dev에서만 한다. 임의 Push / Merge / force push / branch 삭제는 금지한다.
- 원문을 보존한다. Secret·원본 payload는 Git에 넣지 않는다. 프로젝트 결과물을 ignore로 숨기지 않는다.
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

DB / RAG Skill은 향후 요청을 위한 절차이며 현재 Task의 허용 범위를 늘리지 않는다.
역할: [Codex](harness/agents/codex-developer.md), [AGY](harness/agents/agy-reviewer.md).

## Validation / DoD

`./scripts/setup.sh` → `./scripts/check-all.sh` → Report → AGY 검토 → Git Diff / 사용자 검토.
[Testing](harness/docs/testing.md)에 검사 범위·미구현 범위·종료 코드를 명시한다.
필수 조건은 검증 통과, 문서 동기화, 미추적 프로젝트 파일 없음, 보고서와 변경 목록 제공이다.
Gate 통과나 AGY 검토를 실행하지 않고 통과했다고 기록하지 않는다.
Review 완료의 Evidence·검토 범위·Task 전환은 [Workflow](harness/docs/workflow.md)를 따른다.
변경 이유는 [Harness Changelog](harness/changelog/harness-changes.md)에 남긴다.
