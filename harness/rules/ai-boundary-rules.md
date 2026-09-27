# AI 경계

DB로 판단 가능한 날짜·지역·기업형태·지원분야·상태를 LLM 판단으로 대체하지 않는다.
중요 Claim에는 Evidence / Source를 연결한다.
근거 없는 지원 가능 여부 확정 금지. Qdrant 결과만으로 정확한 날짜·상태 확정 금지.
근거가 부족하면 확인 불가를 반환한다.

현재 LLM·RAG·LangGraph·Qdrant Indexing은 금지 범위다.
LangSmith는 향후 Observability이며 지금 연동하지 않는다.
