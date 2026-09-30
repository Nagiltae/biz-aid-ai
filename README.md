# BizAid AI

기업 프로필과 지원사업 공고문 근거를 결합해 중소기업이 신청 가능한 지원사업과 상세 조건을 찾도록 돕는 AI 서비스 프로젝트다.
최상위 설계는 [PROJECT_DESIGN.md](PROJECT_DESIGN.md), 작업 규칙 진입점은 [AGENTS.md](AGENTS.md)다.
이 README는 길잡이다. 세부 규칙은 아래 링크의 Harness 문서가 기준이다.

## 현재 상태

```text
기업마당 API → Raw 보존 → MySQL(공고)          [구현: dev FULL]
공고 첨부 → S3 원본(content SHA)                [구현]
S3 원본 → Parser(PDF·HWP·HWPX) → DoclingDocument → S3 + MySQL(parse row)   [구현: v1, 100문서 corpus 검증]
DoclingDocument → HybridChunker(BGE-M3 tokenizer) → FinalChunk              [구현]
FinalChunk → BGE-M3 dense 1024 + sparse → dev Qdrant                        [구현: 3문서 검증]
Retriever · Reranker · RAG · LangGraph · LLM · 서비스 API · Frontend        [미구현]
```

- canonical 문서 표현은 docling-core DoclingDocument 하나다. Markdown은 chunking 입력이 아니다.
- parser·tokenizer·embedding 모델은 저장소 밖 고정 artifact에서만 읽는다. 실행 중 모델 다운로드는 없다.
- parse_key → chunk_set_key → embedding_key가 단계별 결과 identity다. [Pipeline 문서](harness/docs/data-pipeline.md#identity-요약)를 본다.

## 디렉터리

| 경로 | 역할 |
| --- | --- |
| `data-pipeline/src/biz_aid_pipeline/` | 제품 Pipeline package: `bizinfo`·`ingestion`·`persistence`·`quality`(구조화), `documents`·`storage`(원본 수집·S3), `parsing`, `chunking`, `indexing` |
| `scripts/` | 얇은 CLI 진입점과 `check-*` 검증 스크립트 |
| `contracts/` | 단계별 Contract(JSON). [목록](contracts/README.md) |
| `migrations/` | 공통 Flyway migration(적용된 파일 수정 금지) |
| `infra/` | dev MySQL 준비, HWP→PDF 변환 Docker 이미지 |
| `tests/` | contract·integration test |
| `evals/` | 평가 양식과 Phase 3-B.1 표 engine benchmark(보존용, 제품 경로 아님) |
| `harness/` | 규칙·문서·Skill·Registry·현재 Task·보고서 |

## 로컬 실행

필요: Bash, Git, Python 3.11(stdlib `lzma` 포함), Docker Compose v2. 사용자 설정은 Git 밖 `.env.dev`([예시](.env.example)).

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r data-pipeline/requirements.txt
export BIZAID_DOCLING_ARTIFACTS_PATH=~/.cache/biz-aid/docling-artifacts
.venv/bin/python -B scripts/provision_docling_artifacts.py provision --allow-network   # 최초 1회, 약 3.7GB
./scripts/setup.sh && ./scripts/check-all.sh

.venv/bin/python -B infra/dev_mysql.py                    # dev MySQL + Flyway (infra/README.md)
docker compose --profile dev-vector up -d qdrant          # dev Qdrant 127.0.0.1:6333
```

S3는 boto3 credential chain으로 고정 dev bucket을 쓴다. HWP 변환 이미지는 [infra](infra/README.md)의 build 명령으로 만든다.

대표 CLI(모두 `--profile dev`만 허용):

| 단계 | 명령 |
| --- | --- |
| 구조화 FULL | `scripts/run_full_sync.py collect --profile dev --run-id <id>` |
| 문서 수집 | `scripts/run_document_acquisition.py collect --profile dev --run-id <id>` |
| Parsing(명시 SHA 1~3) | `scripts/run_document_parsing.py --profile dev --source-sha256 <sha>` |
| Corpus parsing | `scripts/run_corpus_parsing.py --profile dev --run-id <id> --max-completed <n>` |
| Chunking | `scripts/run_document_chunking.py --profile dev --source-sha256 <sha>` |
| Indexing | `scripts/run_document_indexing.py --profile dev --source-sha256 <sha>` |

library 진입점: `parsing.orchestration.run_source`, `chunking.cli.chunk_source`, `indexing.pipeline.index_source`, `indexing.embedder.BgeM3Embedder`.

## 문서 지도

- 구조·상태: [Architecture](harness/docs/architecture.md), [Pipeline 상세](harness/docs/data-pipeline.md), [Pipeline 실행 정책](data-pipeline/README.md)
- 규칙: [Source](harness/rules/data-source-rules.md), [파일 경계](harness/rules/file-boundaries.md), [AI 경계](harness/rules/ai-boundary-rules.md), [DB](harness/rules/database-rules.md), [Safety](harness/rules/safety.md)
- 검증: [Testing](harness/docs/testing.md), [Workflow](harness/docs/workflow.md)
- 현재 작업: [current-task](harness/workspace/current-task.md), [Registry](harness/registry.json), [Changelog](harness/changelog/harness-changes.md)
- 초기 Phase 0 도구(snapshot·Probe·API 품질·Download Gate): [Pipeline 문서의 현재 도구 절](harness/docs/data-pipeline.md)

CI는 dev push에서 `setup.sh`와 `check-all.sh`를 오프라인으로 실행한다. prod 실행·임의 push/merge는 하지 않는다.
