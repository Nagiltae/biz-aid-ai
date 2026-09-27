# Spring Boot ↔ FastAPI — 미구현

Spring Boot는 서비스 사실·후보 사업을, FastAPI는 질문 분석·근거 기반 답변을 담당한다.
구현 전에 기업 context·candidate IDs·응답 citation·fallback·오류·timeout·SSE 경계를 정의한다.
FastAPI ↔ Qdrant payload도 indexing 전에 별도 계약으로 검증한다.
현재 Request / Response·모델·prompt·payload schema는 확정하지 않는다.
