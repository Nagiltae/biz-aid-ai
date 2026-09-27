# Observability 계획

AI Observability는 **LangSmith**로 확정했다. Langfuse는 사용하지 않는다.
현재 LLM / RAG가 없어 SDK·API key·연동 코드·trace는 없다.

향후 추적할 항목:

- Question
- Intent
- Retrieval Query
- Candidate Program IDs
- Retrieved Chunks
- Similarity Score
- Reranking Result
- Model
- Prompt Version
- Token Usage
- Latency
- Answer
- Citation
- Evaluation Result
- Fallback

Trace는 Spring 요청과 AI 실행·근거를 연결해야 한다.
기업 정보·질문에 포함된 개인정보와 credential의 저장·마스킹·보존 정책은
실제 연동 전에 결정한다. 현재 측정값을 작성하지 않는다.
일반 서비스 Prometheus / Grafana, HTTP·DB·다운로드·파싱·embedding 지표도 향후 계획이다.
