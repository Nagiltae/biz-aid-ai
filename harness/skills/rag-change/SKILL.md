---
name: rag-change
description: 승인된 RAG baseline의 retrieval·chunk·prompt 변경을 평가할 때 사용한다.
---

# rag-change

현재 Phase에서는 추가 workflow/reference가 필요하지 않음. 아래 본문과 연결된 Context / Rule로 작업 범위를 확인한다.

[RAG Context](../../docs/rag.md)와 [AI 경계](../../rules/ai-boundary-rules.md)를 읽고 변경 목적과 범위를 제한한다.
V1 frozen baseline과 같은 Gold로 변경 전후를 비교하고 citation·groundedness·no-answer regression을 기록한다. 기준 변경은 기존 version을 덮어쓰지 않는다.
LangSmith 계획은 [Observability](../../docs/observability.md)에 있다. 필요성 없이 LangGraph를 추가하지 않는다.
