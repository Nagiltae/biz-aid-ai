# Codex 작업 Report — 2026-09-27

## 1. 수행한 작업

Harness Context / Rules / Skills / Registry / deterministic validation / external memory /
human review 경로와 Phase 0 로컬 원문·보고서 도구를 구축했다.
실제 서비스나 전체 Data Pipeline은 구현하지 않았다.

## 2. 설계 해석

PROJECT_DESIGN.md 전체 58개 절을 읽었다. 기업 프로필과 공식 공고문 근거를 결합하는 서비스다.
현재 Phase 0이며 React → Spring Boot → FastAPI 경계를 유지한다.
MySQL은 서비스 사실과 구조화 검색, Qdrant는 문서 근거 검색을 담당할 계획이다.
Pipeline은 서비스 요청과 분리하며 Raw → Normalize → MySQL → Download → Parse →
Chunk / Embedding → Qdrant는 향후 작업이다.
Codex는 Developer / Generator, AGY는 독립 Reviewer다.
dev 개발 → 검증·사용자 확인 → main → op 흐름을 유지한다.

Harness를 먼저 준비하는 이번 요청을 §48·57의 순서보다 우선 적용한다.
현재 범위에서 Unit / Contract / 로컬 Integration을 실제 수행하고 제품 검증을 N/A로 공개한다.
DoD는 check-all 통과·문서 동기화·Git 추적·Report·사용자 검토 가능 상태다.
AGY 승인과 Data Gate 통과는 이번 검증으로 대체하지 않는다.

## 3. 생성 파일

아래 목록은 최초 Git 상태 대비 신규 프로젝트 파일이다.
기존 미추적 PROJECT_DESIGN.md는 내용 수정 없이 index에 추가한다.

- [.env.example](../../../.env.example)
- [.github/workflows/ci.yml](../../../.github/workflows/ci.yml)
- [.gitignore](../../../.gitignore)
- [AGENTS.md](../../../AGENTS.md)
- [README.md](../../../README.md)
- [contracts/README.md](../../../contracts/README.md)
- [contracts/backend-ai/README.md](../../../contracts/backend-ai/README.md)
- [contracts/external-api/README.md](../../../contracts/external-api/README.md)
- [contracts/frontend-backend/README.md](../../../contracts/frontend-backend/README.md)
- [contracts/schemas/phase0-report.contract.json](../../../contracts/schemas/phase0-report.contract.json)
- [contracts/schemas/raw-snapshot.contract.json](../../../contracts/schemas/raw-snapshot.contract.json)
- [data/downloaded/README.md](../../../data/downloaded/README.md)
- [data/failed/README.md](../../../data/failed/README.md)
- [data/parsed/README.md](../../../data/parsed/README.md)
- [data/raw/README.md](../../../data/raw/README.md)
- [docker-compose.yml](../../../docker-compose.yml)
- [evals/README.md](../../../evals/README.md)
- [evals/phase0-report-template.md](../../../evals/phase0-report-template.md)
- [harness/agents/agy-reviewer.md](../../../harness/agents/agy-reviewer.md)
- [harness/agents/codex-developer.md](../../../harness/agents/codex-developer.md)
- [harness/changelog/harness-changes.md](../../../harness/changelog/harness-changes.md)
- [harness/docs/architecture.md](../../../harness/docs/architecture.md)
- [harness/docs/coding-conventions.md](../../../harness/docs/coding-conventions.md)
- [harness/docs/data-pipeline.md](../../../harness/docs/data-pipeline.md)
- [harness/docs/observability.md](../../../harness/docs/observability.md)
- [harness/docs/rag.md](../../../harness/docs/rag.md)
- [harness/docs/testing.md](../../../harness/docs/testing.md)
- [harness/docs/workflow.md](../../../harness/docs/workflow.md)
- [harness/evals/agent-eval.md](../../../harness/evals/agent-eval.md)
- [harness/evals/regression/README.md](../../../harness/evals/regression/README.md)
- [harness/evals/skill-eval.md](../../../harness/evals/skill-eval.md)
- [harness/registry.json](../../../harness/registry.json)
- [harness/rules/ai-boundary-rules.md](../../../harness/rules/ai-boundary-rules.md)
- [harness/rules/code-comment-policy.md](../../../harness/rules/code-comment-policy.md)
- [harness/rules/data-source-rules.md](../../../harness/rules/data-source-rules.md)
- [harness/rules/database-rules.md](../../../harness/rules/database-rules.md)
- [harness/rules/file-boundaries.md](../../../harness/rules/file-boundaries.md)
- [harness/rules/git-policy.md](../../../harness/rules/git-policy.md)
- [harness/rules/safety.md](../../../harness/rules/safety.md)
- [harness/skills/api-contract-change/SKILL.md](../../../harness/skills/api-contract-change/SKILL.md)
- [harness/skills/data-pipeline-change/SKILL.md](../../../harness/skills/data-pipeline-change/SKILL.md)
- [harness/skills/data-pipeline-change/workflows/pipeline-validation.md](../../../harness/skills/data-pipeline-change/workflows/pipeline-validation.md)
- [harness/skills/database-migration/SKILL.md](../../../harness/skills/database-migration/SKILL.md)
- [harness/skills/debugging/SKILL.md](../../../harness/skills/debugging/SKILL.md)
- [harness/skills/feature-development/SKILL.md](../../../harness/skills/feature-development/SKILL.md)
- [harness/skills/rag-change/SKILL.md](../../../harness/skills/rag-change/SKILL.md)
- [harness/workspace/artifacts/README.md](../../../harness/workspace/artifacts/README.md)
- [harness/workspace/checkpoints/README.md](../../../harness/workspace/checkpoints/README.md)
- [harness/workspace/current-task.md](../../../harness/workspace/current-task.md)
- [harness/workspace/reports/2026-09-27-codex-harness-report.md](../../../harness/workspace/reports/2026-09-27-codex-harness-report.md)
- [infra/README.md](../../../infra/README.md)
- [scripts/check-all.sh](../../../scripts/check-all.sh)
- [scripts/check-comments.sh](../../../scripts/check-comments.sh)
- [scripts/check-contract.sh](../../../scripts/check-contract.sh)
- [scripts/check-format.sh](../../../scripts/check-format.sh)
- [scripts/check-git-tracked.sh](../../../scripts/check-git-tracked.sh)
- [scripts/check-harness.sh](../../../scripts/check-harness.sh)
- [scripts/check-integration.sh](../../../scripts/check-integration.sh)
- [scripts/check-lint.sh](../../../scripts/check-lint.sh)
- [scripts/lib/validate.py](../../../scripts/lib/validate.py)
- [scripts/phase0.py](../../../scripts/phase0.py)
- [scripts/setup.sh](../../../scripts/setup.sh)
- [tests/README.md](../../../tests/README.md)
- [tests/contract/test_harness_policy.py](../../../tests/contract/test_harness_policy.py)
- [tests/contract/test_phase0.py](../../../tests/contract/test_phase0.py)
- [tests/integration/test_phase0_cli.py](../../../tests/integration/test_phase0_cli.py)

## 4. 수정 파일

기존 파일의 내용 수정 없음. 새 파일의 보완은 위 생성 목록에 포함한다.
PROJECT_DESIGN.md는 보존한다.

## 5. 삭제 파일

없음. 기존 .DS_Store는 삭제하지 않고 ignore한다.

## 6. 각 변경의 이유

| 파일 범위 | 이유 |
| --- | --- |
| AGENTS.md / harness/registry.json | 짧은 Project Map·routing과 실제 구현 목록·검증의 연결 |
| harness/docs/ | 목적·Architecture·단계·환경·테스트·미결정 사항의 progressive disclosure |
| harness/agents/ | Generator와 독립 Reviewer의 책임·증거 분리 |
| harness/rules/ | Git·Layer·Source·DB·AI·한글 주석·권한 제약 보존 |
| harness/skills/ | 작업 종류별 description routing과 필요한 절차만 제공 |
| harness/workspace/ | Task·checkpoint·보고서를 파일로 남겨 세션 교체와 검토 지원 |
| harness/evals/ / changelog/ | 개발 방식 평가와 Harness 변경 이유 기록 |
| contracts/ | 실제 upstream을 추정하지 않고 로컬 snapshot / report 계약만 검증 |
| scripts/ | 실행 가능한 deterministic validation과 원문 무결성·미측정 보고서 도구 |
| tests/ | 실패 입력·덮어쓰기·hash 변조·계약·CLI·Harness 정책 regression |
| evals/ | 실제 Gate 보고서 지표·분모·증거·판단 준비, 제품 AI 평가는 향후 구분 |
| data/ | Raw / downloaded / parsed / failed 보존 위치 및 Git 제외 정책 |
| infra/ / docker-compose.yml | 실제 Phase 0 Batch만 실행하고 DB·빈 제품 service는 추가하지 않음 |
| .github/workflows/ci.yml | dev Push에 현재 적용 검증, 배포 workflow는 미구현 |
| .gitignore / .env.example / README.md | Secret·원문·cache 제외, 실제 환경과 실행 방법 동기화 |

## 7. 작성한 Validation

setup / format / lint / contract / integration / git-tracked / comments / harness / check-all.
검증 범위와 종료 코드는 [testing.md](../../docs/testing.md)에 있다.
현재 코드의 Unit / Contract와 로컬 CLI Integration 및 Harness 정책 실패 regression을 작성했다.
제품 formatter·type checker·실 API·Parser·DB·E2E·AI Eval·Build는 미구현이다.

## 8. 실제 실행한 Validation

다음 명령을 로컬에서 실제 실행했다.

- ./scripts/setup.sh
- ./scripts/check-format.sh
- ./scripts/check-lint.sh
- ./scripts/check-contract.sh
- ./scripts/check-integration.sh
- ./scripts/check-git-tracked.sh (check-all 내부에서 실행)
- ./scripts/check-comments.sh
- ./scripts/check-harness.sh
- ./scripts/check-all.sh
- skill-creator의 quick_validate.py를 6개 SKILL 폴더 각각에 실행
- docker compose run --rm phase0 --help
- docker compose run --rm phase0 init-report --run-id docker-smoke-20260927 --output /artifacts/docker-smoke-20260927.json
- docker compose run --rm phase0 validate-report /artifacts/docker-smoke-20260927.json
- git diff --cached --stat, git diff --check, git diff --cached --check, git status
- git ls-files --others --exclude-standard

최종 검증 로그는 로컬 harness/workspace/artifacts/2026-09-27-check-all.log에 있다.
Docker smoke 보고서는 같은 artifacts/의 docker-smoke-20260927.json이다.
이 재생성 가능한 log / JSON은 ignore하고 해석·결과는 이 추적된 Report에 남긴다.
원격 GitHub Actions와 AGY는 실행하지 않았다.

## 9. Validation 결과

| Validation | 결과 / 실제 범위 |
| --- | --- |
| setup | PASS / Python 3.11.16, Bash, Git, Docker Compose 5.1.2와 Batch config |
| format | PASS / UTF-8·LF·newline·공백·JSON indent·Git whitespace |
| lint | PASS / Python AST·Bash syntax·실행 권한·JSON 중복 key |
| Unit / Contract / Harness policy | PASS / 27개, 형식 오류 원문 보존·수집/보존 시각 구분·계약·변조·덮어쓰기·정책 실패 검사 |
| CLI Integration | PASS / 4개, 실제 subprocess 흐름과 오류 종료 코드 |
| git-tracked | PASS / dev, 프로젝트 Untracked 0개, 금지 ignore 없음, 신규 index와 작업 파일 일치 |
| comments | PASS / 설명성 한글 주석 8개, WHY 적절성은 독립 검토 대상 |
| harness | PASS / 링크·Skill/Rule/Agent Registry·명령·구현 목록·Compose·dev CI·workspace |
| check-all | PASS / exit 0, 모든 현재 적용 검사 통과 |
| Skill quick_validate | PASS / 6개 모두 Skill is valid |
| Compose 실제 실행 | PASS / 이미지 확보·도구 help·미측정 보고서 생성·로컬 계약 검사 |
| 실제 API·Parser·제품 API·DB·E2E·AI Eval·Build | N/A / 미구현 또는 미측정, PASS로 계산하지 않음 |
| AGY / Human review | PENDING / 독립 검토·사용자 판단 대기 |

실제 API·공고문 성능 수치는 미측정, Gate는 PENDING이다.
원문을 보존한 시각을 실제 수집 시각으로 오인하지 않도록 분리했다.
수집 시각은 제공하지 않으면 null이다. 형식 오류 원문도 payload_syntax=invalid로 보존한다.
verify-snapshot의 PASS는 byte 무결성 결과이며 upstream 정상 수집 판정이 아니다.

저장소는 최초 commit이 없는 dev였다. 신규 66개 파일과 기존 미추적 PROJECT_DESIGN.md를
index에 추가하여 총 67개 경로가 Git Diff로 검토 가능하다.
원본 설계 내용 수정·삭제 없음. Commit·Push·Merge·force push·branch 삭제 없음.
초기 git add는 파일시스템의 .git 읽기 전용 제한으로 실패했으나
해당 index 기록 권한을 승인받아 성공했다. 최종 Validation에 남은 실패는 없다.

## 10. 아직 구현하지 않은 부분

API Collector·100건 수집·Downloader·PDF/HWP/HWPX Parser·Normalizer·MySQL·Migration·
Chunking·Embedding·Qdrant Indexing·React·Spring Boot·FastAPI·회원·RAG·LangGraph·
LLM·LangSmith 연동·Prometheus/Grafana·운영 배포.
AGY 독립 검토와 Human review도 pending이다.

## 11. 발견한 설계상 문제

- §48·57은 Harness를 Gate 이후에 배치하나 이번 요청은 먼저 준비하도록 한다.
- §37·46·49의 전체 환경·테스트는 현재 구현 상태에 적용할 수 없다.
- §5와 §19의 Normalize 대상은 문서와 API로 다르며 상세 Pipeline 단계에서 구분이 필요하다.
- 저장소에 upstream endpoint·인증·응답 envelope·pagination·field mapping·실제 응답 근거가 없다.
- §53의 주요 field, 유효성·Null 정의, 수집/성공률 분모, 최근 100건 선정 기준이 미결정이다.
- HWP/HWPX/HTML의 page 대체 근거 및 표 품질 기준이 미결정이다.
- §57의 API 확인 서술은 이번 저장소에 재현 가능한 증거가 없다.

사용자가 이번 범위를 명확히 지정한 순서·환경 문제는 그 지시에 따라 준비했다.
나머지는 보류하고 Source·Parser·DB·모델을 추정 도입하지 않았다.
로컬 보고서 계약은 준비 단계 pending만 허용하며 최종 Gate 판단을 자동 생성하지 않는다.

## 12. 다음 단계 제안

AGY가 Git Diff·Report·check-all과 적용 제외 범위를 독립 검토한다.
사용자는 공식 API 명세와 credential 없는 실제 응답을 제공하고
주요 field·분모·100건 선정·근거 위치 기준을 확정한다.
그 다음 별도 Phase 0 Task로 약 100건 수집·URL·다운로드·형식별 Parsing·API 대비 추가정보·
RAG 가치·자동화를 측정해 실제 Data Feasibility Report와 GO / DROP 판단을 만든다.
Gate 통과 전 Phase 1 전체나 50건 Vertical Slice로 진행하지 않는다.
