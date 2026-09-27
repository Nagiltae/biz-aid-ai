# Layer와 파일 경계

React → FastAPI 직접 호출 및 Frontend → DB 접근 금지.
Spring Boot가 회원·기업·사업·대화·즐겨찾기를 소유한다.
FastAPI는 서비스 DB를 임의 변경하지 않는다.
Data Pipeline은 사용자 인증·채팅 Domain을 수정하지 않는다.

현재 허용 실행 코드: Phase 0 로컬 도구·명시적인 최소 Local API Probe·dev 전용 5×20 API 품질 Batch·Harness validator·관련 테스트·Compose Batch.
Probe는 사용자 승인 Endpoint에 한정하며 CI Live 호출과 전체 Collector를 포함하지 않는다.
frontend/ backend/ ai/ data-pipeline/ migrations/ module 생성은 현재 범위 밖이다.
현재 Phase 0 도구를 전체 Pipeline 또는 FastAPI 모듈로 문서화하지 않는다.
