# Observability 계획

AI Observability는 **LangSmith**로 확정했다. Langfuse는 사용하지 않는다.
현재 RAG v1(로컬 Ollama qwen3.5:9b)은 구현됐지만 LangSmith SDK·API key·연동 코드·실행 추적(trace)은 없다.

향후 추적할 항목:

- 사용자 질문(Question)
- 요청 유형(Intent)
- 검색 질의(Retrieval Query)
- 후보 공고 ID(Candidate Program IDs)
- 검색된 문서 조각(Retrieved Chunks)
- 유사도 점수(Similarity Score)
- 재정렬 결과(Reranking Result)
- 사용 모델(Model)
- 프롬프트 버전(Prompt Version)
- 토큰 사용량(Token Usage)
- 응답 시간(Latency)
- 답변(Answer)
- 근거 연결(Citation)
- 평가 결과(Evaluation Result)
- 실패 시 대체 처리(Fallback)

Trace는 Spring 요청과 AI 실행·근거를 연결해야 한다.
기업 정보·질문에 포함된 개인정보와 credential의 저장·마스킹·보존 정책은
실제 연동 전에 결정한다. 현재 측정값을 작성하지 않는다.
일반 서비스 Prometheus / Grafana, HTTP·DB·다운로드·파싱·embedding 지표도 향후 계획이다.
