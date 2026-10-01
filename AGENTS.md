# Harness Entry Point

기업 프로필과 공고문 근거로 중소기업 지원사업을 탐색·검토하는 프로젝트다.
현재 상태의 기준은 production code·Harness·[PROJECT_MASTER_GUIDE](PROJECT_MASTER_GUIDE.md)다. [PROJECT_DESIGN.md](PROJECT_DESIGN.md)는 최초 목표와 배경을 보존한다. AI 계층(RAG·자격 판단·FastAPI 내부 API)과 **React + Spring Boot 서비스 V1**이 Spring ↔ FastAPI로 연결됐다(AI E2E V1). V2는 LangChain 호출 경계·개인화 검색·Top 3 판정·LangGraph 추천 흐름·React 화면·선택적 LangSmith 추적(V2-0~V2-6)까지 구현됐다. V2 전체 데이터 파싱·별도 Qdrant 적재와 전환 검증은 진행 중이다.

## 먼저 읽기

1. [현재 Task](harness/workspace/current-task.md)
2. [작업 절차](harness/docs/workflow.md), [Git 정책](harness/rules/git-policy.md)
3. 아래 Registry에서 작업에 필요한 Context / Rule / Skill만 선택한다.

## Project Map

경계: React(`frontend/`) → Spring Boot(`backend/`) → FastAPI(`data-pipeline/`)로 연결됐다. React는 Spring만 호출한다.
Spring Boot / MySQL은 서비스 사실과 정확한 검색, FastAPI / Qdrant는 AI와 문서 근거를 담당한다.
제품 데이터 코드는 `data-pipeline/`, 공통 Flyway는 `migrations/`(Spring도 같은 계보)다. Phase 0 도구와 검증 증거는 보존한다.
[Architecture](harness/docs/architecture.md), [기계 Registry](harness/registry.json)가 실제 구현 상태를 기록한다.

## 반드시 지킬 것

- 개발은 dev에서만 한다. 임의 Push / Merge / force push / branch 삭제는 금지한다.
- 원문을 보존한다. Secret·Live payload는 Git에 넣지 않는다. 사용자 제공 sanitized Fixture 예외는 [Source 규칙](harness/rules/data-source-rules.md)을 따른다. Control/Input은 추적하고 Generated Workspace Output은 [Workflow](harness/docs/workflow.md)에 따라 non-gating으로 관리한다.
- 설명성 코드 주석은 한글 WHY / BOUNDARY / EXCEPTION / RISK로 작성한다.
- Codex와 Claude는 같은 Task를 이어서 수행하는 Developer / Generator, AGY는 독립 Reviewer다. Agent handoff로 Harness 제어 파일을 바꾸지 않으며 개발 Producer가 AGY 승인 기록을 작성하지 않는다.
- Harness 규칙 완화·삭제 또는 큰 Architecture 변경은 먼저 보고하고 사용자 판단을 받는다.
- 현재 Task가 허용하지 않은 서비스·DB·LangGraph 확장·Reranker·자격 판단을 구현하지 않는다.

## Routing Registry

| 작업 | Context / Rules | Skill |
| --- | --- | --- |
| Harness·환경 변경 | [Architecture](harness/docs/architecture.md), [Safety](harness/rules/safety.md), [파일 경계](harness/rules/file-boundaries.md) | [feature-development](harness/skills/feature-development/SKILL.md) |
| 오류 분석 | [Testing](harness/docs/testing.md), [주석](harness/rules/code-comment-policy.md) | [debugging](harness/skills/debugging/SKILL.md) |
| 데이터 실험 | [Pipeline](harness/docs/data-pipeline.md), [Source](harness/rules/data-source-rules.md) | [data-pipeline-change](harness/skills/data-pipeline-change/SKILL.md) |
| 계약 변경 | [Contracts](contracts/README.md), [Coding](harness/docs/coding-conventions.md) | [api-contract-change](harness/skills/api-contract-change/SKILL.md) |
| DB 변경 요청 | [DB 규칙](harness/rules/database-rules.md) | [database-migration](harness/skills/database-migration/SKILL.md) |
| RAG 변경 요청 | [RAG](harness/docs/rag.md), [AI 경계](harness/rules/ai-boundary-rules.md), [Observability](harness/docs/observability.md) | [rag-change](harness/skills/rag-change/SKILL.md) |

Skill은 현재 Task의 허용 범위를 늘리지 않는다. 구현: dev 구조화 FULL / 문서 수집 / S3 저장 / PDF·HWP·HWPX Parser(OCR 포함) / Chunking / BGE-M3 dense·sparse dev Indexing / read-only Retriever / RAG Answer v1 / MySQL 후보 결합 / 자격 판단 v1 / FastAPI 내부 API / React + Spring Boot 서비스 V1(JWT·JPA·QueryDSL) / V2 맞춤 추천 workflow·화면·선택적 추적.
미구현·미완료: FastAPI Compose 통합(IMP-017)·Reranker·운영 배포·V2 전체 collection 검증/전환·V2 전체 품질 평가. 단계 경계는 [파일 경계](harness/rules/file-boundaries.md)를 따른다.
역할: [Codex](harness/agents/codex-developer.md), Claude CLI는 [bootstrap](CLAUDE.md), Claude 클라우드 세션은 [GitHub 읽기·대화](harness/agents/claude-cloud-advisor.md), [AGY](harness/agents/agy-reviewer.md).

## Validation / DoD

`./scripts/setup.sh` → `./scripts/check-all.sh` → Report → AGY 검토 → Git Diff / 사용자 검토.
[Testing](harness/docs/testing.md)에 검사 범위·미구현 범위·종료 코드를 명시한다.
필수 조건은 입력 자산 검증 통과, 문서 동기화, 미추적 입력 파일 없음, 실행 결과 보고와 변경 목록 제공이다.
Generated Report / Checkpoint / Artifact 작성은 검증을 무효화하지 않는다. current-task·정적 README는 strict다.
Gate 통과나 AGY 검토를 실행하지 않고 통과했다고 기록하지 않는다.
Review 완료의 Evidence·검토 범위·Task 전환은 [Workflow](harness/docs/workflow.md)를 따른다.
변경 이유는 [Harness Changelog](harness/changelog/harness-changes.md)에 남긴다.
프로젝트 전체 설명은 [PROJECT_MASTER_GUIDE](PROJECT_MASTER_GUIDE.md), 한국어 용어 표준은 [용어집](harness/docs/glossary-ko.md)을 따른다.
blocker가 아니어서 의도적으로 미룬 관찰 문제는 [Improvement Backlog](harness/docs/improvement-backlog.md)에 기록한다([Workflow](harness/docs/workflow.md#improvement-backlog)).
