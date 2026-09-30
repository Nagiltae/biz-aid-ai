# Layer와 파일 경계

React는 AI 결과를 포함해 Spring Boot(`/api`)만 호출한다. React → FastAPI 직접 호출 및 Frontend → DB 접근 금지.
Spring Boot는 회원·인증·기업정보·대화 같은 서비스 데이터의 기준 시스템(Source of Truth)이다.
support_programs 등 공고·문서 데이터는 데이터 파이프라인이 적재하고 Spring은 조회만 한다(복제·schema 변경 금지).
FastAPI는 서비스 DB를 임의 변경하지 않는다.
Data Pipeline은 사용자 인증·채팅 Domain을 수정하지 않는다.

현재 허용 실행 코드는 Phase 0 증거 도구, 승인된 구조화 `data-pipeline/`, 공통 Flyway, Phase 2 Document Acquisition, Phase 3 Parser, Harness validator와 관련 테스트다.
Phase 2 제품 코드는 DB Source를 읽고 공개 문서 원본과 metadata만 보존한다. 실행 entrypoint는 `scripts/`의 얇은 CLI다.
S3는 검증된 문서 binary의 영구 저장소다. ignored `data/downloaded/` legacy corpus는 migration source로 유지하며
AGY와 사용자 승인 전 삭제하지 않는다. 실패 응답은 ignored `data/failed/`, 실행 Report/Artifact는 non-gating workspace에 둔다.
Phase 3 Parser는 `data-pipeline/src/biz_aid_pipeline/parsing/`에 둔다. S3 원본 read와 DoclingDocument 생성까지가 경계다.
PDF 변환은 `parsing/pdf.py`의 `convert_pdf` 하나이며 HWP 경로도 이를 재사용한다. 모델 artifact·torch 임시 cache는 저장소 밖에 둔다.
3-B.1 표 engine benchmark 코드는 `evals/table_engine/`에 두며 제품 parsing route를 대신하지 않는다. 결과는 ignored `data/parsed/table-engine-eval/`에 둔다.
Chunking은 `data-pipeline/src/biz_aid_pipeline/chunking/`, Embedding·dev Qdrant 적재는 `indexing/`, 검색은 `retrieval/`, 근거 답변은 `rag/`, MySQL 정형 후보 선택은 `candidates/`(support_programs read-only, 자연어 조건 추출은 `candidates/natural.py`, 공고 목록은 `candidates/discovery.py`)에 두고, request_mode 분기는 `rag/router.py`다. 단일 공고 자격 판단은 `eligibility/`(Profile snapshot 입력, DB·schema 없음)에 둔다.
`rag/`는 `retrieval.Retriever`를 그대로 호출하고 검색·embedding을 다시 구현하지 않는다. ai/ 생성은 현재 범위 밖이다.
서비스 V1은 `backend/`(Spring Boot)와 `frontend/`(React, features/·shared/)다.
Spring은 도메인 중심 package(auth·company·program·conversation·ai·activity) 안에 계층을 둔다: presentation(Controller·HTTP 요청/응답 DTO·입력 검증) → application(유스케이스·조회 결과) → domain(Entity·도메인 규칙·값) / infrastructure(JPA·QueryDSL Repository·JWT·외부 HTTP·설정 Properties).
의존은 presentation → application → domain 한 방향이며 application·domain은 presentation을 import하지 않는다. 신규 기능은 해당 도메인 아래에 두고, `common/`에는 여러 도메인이 실제로 공유하는 오류·페이지·설정만 둔다. Aggregate·Domain Event·Port/Adapter 같은 패턴은 실제 필요 전에는 들이지 않는다.
Spring의 AI 기능은 `ai.AiGateway` 경계 뒤에 두고 AI 검색·자격 판정 로직을 Java로 다시 구현하지 않는다.
Spring → FastAPI 호출은 `ai.HttpAiGateway`(동기 RestClient, 연결·응답 제한시간 환경설정) 한 곳에서만 한다. `/internal/v1/*`는 공유 키 헤더(`X-Internal-Api-Key`, 환경변수 `INTERNAL_AI_API_KEY`)로 서비스 간 인증을 한다.
FastAPI 내부 인증 실패(401/403)는 최종 사용자 로그인 실패가 아니라 서비스 설정 오류이므로 사용자 401로 전달하지 않는다(`ai_service_auth_failed`). FastAPI 내부 오류 상세는 React에 보내지 않는다.
내부 AI HTTP API는 `biz_aid_pipeline/api/`(FastAPI)이고, CLI와 API는 같은 `biz_aid_pipeline/runtime.py`의 ServiceRuntime을 호출한다.
FastAPI는 서비스 계층(Spring Boot)이 호출하는 내부 AI 인터페이스다. 브라우저 client가 직접 의존하지 않으며 CORS를 열지 않는다.
HTTP handler는 요청 검증·서비스 호출·직렬화만 하고 판단 로직은 기존 서비스에 위임한다.
BGE-M3·DB pool·Qdrant client·LLM 설정 같은 무거운 공통 자원은 HTTP 요청마다 다시 만들지 않는다.
NO_CANDIDATES·INSUFFICIENT_EVIDENCE·INELIGIBLE·NEEDS_MORE_INFO 같은 판단 결과는 전송 실패가 아니며 HTTP 200으로 돌려준다.
의존은 parsing ← chunking ← indexing 한 방향이다. parser는 chunk하지 않고, chunker는 저장된 PARSED DoclingDocument만 읽고 다시 parsing하지 않으며,
indexer는 FinalChunk만 소비하고 parser·원본을 직접 읽지 않는다. `retrieval/`은 indexing의 embedder·collection 이름·schema 검사만 재사용하고 parsing·chunking·적재 경로(upsert·stale 정리·collection 생성)를 import·호출하지 않는다(test가 검사).
Phase 0 도구를 제품 Pipeline 또는 FastAPI 모듈로 문서화하지 않는다.
