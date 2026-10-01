# Observability — LangSmith 선택적 실행 추적

AI 실행 추적(Tracing)은 **LangSmith**로 확정했고 V2-6에서 V2 추천 workflow에 연동했다. Langfuse는 사용하지 않는다.

## 현재 범위

- 설정 `BIZAID_TRACING_ENABLED=true`와 `LANGSMITH_API_KEY`가 모두 있을 때만 켜진다.
- 프로젝트 기본 이름은 `biz-aid`다. 실제 key 값은 코드·문서·로그에 남기지 않는다.
- `workflow.start|continue|answer`와 personalized_search·natural_filter·mysql_candidates·qdrant_search·eligibility·apply_answers·final_result 단계를 직접 기록한다.
- LangChain/LangGraph 자동 추적은 사용하지 않으며 workflow 실행 중 강제로 끈다.
- 추적 실패는 AI 결과와 상태 전이를 멈추거나 바꾸지 않는다.

## 외부 전송 경계

전송 가능: 단계 이름, 시간, 상태, 개수, 고정 오류 코드, 공개 공고 ID, 기업정보 field ID, 사용자와 무관한 무작위 trace key.

전송 금지: 사용자 질문, 기업정보와 임시 답변 값, 문서 원문·검색 조각, prompt·모델 입력/출력, 비밀값, 예외 메시지 원문. 코드의 요약 함수와 형식 검사가 이 경계를 이중으로 확인한다.

## 확인된 것과 남은 것

- 실제 연결: V2-6에서 민감정보 없는 진단 실행(부모 1 + 자식 1)을 보내고 서버에서 다시 읽어 기존 `biz-aid` 프로젝트(ID 928ce4c3-0bc0-4801-bb22-3292eb3afb55)에 저장된 것을 확인했다.
- 개인정보 경계: 실제 workflow가 아니라 contract test(`tests/contract/test_tracing.py`)가 SDK의 실제 전송 HTTP 본문을 가로채 질문·기업정보·답변 값·근거 문장·예외 메시지·키가 없음을 확인한다.
- 설정: 사용자가 `.env.dev`에 API key와 `BIZAID_TRACING_ENABLED=true`를 넣었다. FastAPI를 이 설정으로 다시 띄운 뒤의 workflow 요청부터 기록된다.
- V1 query·단일 자격 판정과 V2 단독 검색/판정 endpoint는 추적하지 않는다(IMP-023).
- 미검증: 실제 사용자 workflow(start → continue → answers)가 LangSmith에 단계별로 기록되는지는 아직 실행하지 않았다. 장기 보존·비용·일반 서비스 지표도 정하지 않았다.
- V2-6 진단 중 이름 착오로 자동 생성된 `biz_aid` 프로젝트는 사용자가 삭제했다. 없는 프로젝트 이름으로 보내면 LangSmith가 새 프로젝트를 자동으로 만들므로 `LANGSMITH_PROJECT`는 실제 이름과 같아야 한다.

구현 경계는 `data-pipeline/src/biz_aid_pipeline/observability/tracing.py`, 계약은 `contracts/schemas/internal-api.contract.json`, 개인정보 규칙은 [AI 경계](../rules/ai-boundary-rules.md)를 따른다.
