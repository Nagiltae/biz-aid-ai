# Current Task — 묶음4 Bedrock 연결·품질 시험

## Goal / Scope

dev clean working tree에서 사용자 승인 묶음4를 수행한다. 기존 LlmProvider 경계에 Bedrock ConverseStream/tool use,75초 전체기한·출력상한·fail-closed·SDK credential chain을 연결한다. Ollama 기본 동작은 유지한다.
실제MySQL/Qdrant V2 근거의 작은cases-v2 세트를 먼저동결하고 Ollama1회→Bedrock1회,기존고정10질문Bedrock1회만 순차실행한다. 목록중복후처리·context표가독성만 보강하고key/vector/V1/기준선은불변이다.
Secret직접열람/수정,prod,commit/push,반복튜닝없음. AWS sandbox 제한은우회하지않고상태보고한다.

## Read First

AGENTS→Codex→Registry→AI경계/Source/RAG/Observability→rag-change/api-contract-change.
[이전 묶음3](reports/development/2026-10-04-bundle3-service.md),Backlog IMP-002·003·004.

## Validation / Reports

fake Bedrock 계약검사→동결cases 각provider1회→고정10회귀Bedrock1회→최종check-all1회.
[Final Report](reports/development/2026-10-04-bundle4-quality.md),Artifact artifacts/development/bundle4-quality/.
사용자 지정handoff/bundle4-handoff.md는항목종료마다갱신한다.

## Next Steps

구현·provider당1회실측·기존10질문회귀완료. Bedrock19/20, Ollama15PASS/3품질FAIL/2채점오류. Bedrock120174는기존1280token 상한에닿아fail-closed. 사용자설정/출력예산·배포선택및독립AGY검토대기. 최종검증결과는Report/Artifact참조. 자동다음Task시작금지.
