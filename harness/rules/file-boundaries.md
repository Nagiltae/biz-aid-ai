# Layer와 파일 경계

React → FastAPI 직접 호출 및 Frontend → DB 접근 금지.
Spring Boot가 회원·기업·사업·대화·즐겨찾기를 소유한다.
FastAPI는 서비스 DB를 임의 변경하지 않는다.
Data Pipeline은 사용자 인증·채팅 Domain을 수정하지 않는다.

현재 허용 실행 코드는 Phase 0 증거 도구, 승인된 구조화 `data-pipeline/`, 공통 Flyway, Phase 2 Document Acquisition, Phase 3 Parser, Harness validator와 관련 테스트다.
Phase 2 제품 코드는 DB Source를 읽고 공개 문서 원본과 metadata만 보존한다. 실행 entrypoint는 `scripts/`의 얇은 CLI다.
S3는 검증된 문서 binary의 영구 저장소다. ignored `data/downloaded/` legacy corpus는 migration source로 유지하며
AGY와 사용자 승인 전 삭제하지 않는다. 실패 응답은 ignored `data/failed/`, 실행 Report/Artifact는 non-gating workspace에 둔다.
Phase 3 Parser는 `data-pipeline/src/biz_aid_pipeline/parsing/`에 둔다. S3 원본 read와 DoclingDocument 생성까지가 경계다.
PDF 변환은 `parsing/pdf.py`의 `convert_pdf` 하나이며 HWP 경로도 이를 재사용한다. 모델 artifact·torch 임시 cache는 저장소 밖에 둔다.
3-B.1 표 engine benchmark 코드는 `evals/table_engine/`에 두며 제품 parsing route를 대신하지 않는다. 결과는 ignored `data/parsed/table-engine-eval/`에 둔다.
Chunking은 `data-pipeline/src/biz_aid_pipeline/chunking/`, Embedding·dev Qdrant 적재는 `indexing/`, 검색은 `retrieval/`, 근거 답변은 `rag/`, MySQL 정형 후보 선택은 `candidates/`(support_programs read-only)에 둔다.
`rag/`는 `retrieval.Retriever`를 그대로 호출하고 검색·embedding을 다시 구현하지 않는다. FastAPI 서비스(`ai/`)는 아직 없어 dev CLI가 진입점이다. frontend/ backend/ ai/ 생성은 현재 범위 밖이다.
의존은 parsing ← chunking ← indexing 한 방향이다. parser는 chunk하지 않고, chunker는 저장된 PARSED DoclingDocument만 읽고 다시 parsing하지 않으며,
indexer는 FinalChunk만 소비하고 parser·원본을 직접 읽지 않는다. `retrieval/`은 indexing의 embedder·collection 이름·schema 검사만 재사용하고 parsing·chunking·적재 경로(upsert·stale 정리·collection 생성)를 import·호출하지 않는다(test가 검사).
Phase 0 도구를 제품 Pipeline 또는 FastAPI 모듈로 문서화하지 않는다.
