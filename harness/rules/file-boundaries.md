# Layer와 파일 경계

React → FastAPI 직접 호출 및 Frontend → DB 접근 금지.
Spring Boot가 회원·기업·사업·대화·즐겨찾기를 소유한다.
FastAPI는 서비스 DB를 임의 변경하지 않는다.
Data Pipeline은 사용자 인증·채팅 Domain을 수정하지 않는다.

현재 허용 실행 코드는 Phase 0 증거 도구, 승인된 구조화 `data-pipeline/`, 공통 Flyway, Phase 2 Document Acquisition, Harness validator와 관련 테스트다.
Phase 2 제품 코드는 DB Source를 읽고 공개 문서 원본과 metadata만 보존한다. 실행 entrypoint는 `scripts/`의 얇은 CLI다.
Binary는 ignored `data/downloaded/`, 실패 응답은 ignored `data/failed/`, 실행 Report/Artifact는 non-gating workspace에 둔다.
frontend/ backend/ ai/ Parser/OCR/Chunking/Embedding/Qdrant/RAG module 생성은 현재 범위 밖이다.
Phase 0 도구를 제품 Pipeline 또는 FastAPI 모듈로 문서화하지 않는다.
