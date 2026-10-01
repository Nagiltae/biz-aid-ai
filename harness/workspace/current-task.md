# Current Task

## Goal / Context

2026-10-01 사용자 요청: V2-5 React V2 화면. 기존 V2 workflow API(V2-3·V2-4)를 React에서 질문 → Top 3 → 공고별 판정 → 부족 정보 → 답변 → 재판정 → 최종 결과까지 쓸 수 있게 연결한다.
새 AI 로직·LangGraph 재설계·순위 개인화·prompt·새 UI 라이브러리·LangSmith·AWS·Qdrant batch 변경은 범위가 아니다.

## Read First

[AGENTS](../../AGENTS.md) → [파일 경계](../rules/file-boundaries.md) → [AI 경계](../rules/ai-boundary-rules.md) →
[화면 API](../../contracts/frontend-backend/README.md) → [Spring ↔ FastAPI 경계](../../contracts/backend-ai/README.md).

## Scope / Acceptance

1. React는 Spring workflow API만 호출하고 nextAction에 따라 진행·답변만 요청한다(순서·분기 계산 금지).
2. 요청은 한 번에 하나. 복원은 GET만 하고 AI 단계를 자동 재실행하지 않는다. 409·연결 실패는 자동 재시도하지 않는다.
3. 추가 정보는 서버가 묻는 field만, 임시 정보로 표현한다. 최종 결과는 추천·지원 불가·판단 불가를 분리하고 추천 0건도 정상이다.
4. 진행률·예상 시간은 서버 값 외에 만들지 않는다. Spring AI 제한시간 90초는 바꾸지 않는다. V1 화면은 회귀하지 않는다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-v2-5-react-recommend.md).
모든 변경 후 `./scripts/check-all.sh`가 실제 exit 0이어야 한다.
