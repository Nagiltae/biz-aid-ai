# Current Task — 맞춤 추천 판정 90초 시간 초과·과열 진단·수정

## Goal / Context

2026-10-03 사용자 요청: /recommend에서 Top 3 중 2번째 공고 판정이 Spring AI_RESPONSE_TIMEOUT(90초)으로 실패하고, 실패 뒤에도 맥북 팬이 계속 돈다. 재현 질문 "우리 회사가 신청할 수 있는 금융 지원사업 찾아줘".
1단계로 실패 공고를 단독 재현해 원인(출력 폭주 / 입력 과다 / 모델 재적재 / 기타)을 숫자로 판정한다. 2단계로 최소 범위로 수정한다: LLM 출력 상한(num_predict·criteria maxItems·num_ctx), FastAPI LLM 기한 < Spring 응답 제한, 시간 초과 공고만 FAILED, 고아 생성 제거.
판정 규칙·prompt 문구·Top 3 순위·identity key 변경, chunk 길이 상한(근거 입력이 원인이면 Backlog 후보만), commit/push는 범위가 아니다.

## Next Steps

검토 → 5 화면 완주 + cases-v2 기준점(IMP-024·025·029 포함) → 6 XLSX → 7 옛 오피스.

## Read First

[AGENTS](../../AGENTS.md) → `data-pipeline/src/biz_aid_pipeline/rag/llm.py` → `eligibility/service.py` → `contracts/schemas/eligibility.contract.json`(criterion_output) → `contracts/schemas/internal-api.contract.json`(llm_call) → [Backlog](../docs/improvement-backlog.md)(IMP-020·029).

## Scope / Acceptance

1. 원인을 측정값(prompt·출력 token, 시간, criteria 수·중복, chunk 길이, ollama ps)으로 판정한다.
2. 한 판정 요청이 Spring 90초 안에 끝나고, 시간 초과·상한 도달은 그 공고만 고정 코드로 FAILED가 되며 workflow는 다음 공고로 간다.
3. 실패 뒤 Ollama 생성이 남지 않는다(slot 확인).
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-03-recommend-timeout-diagnosis.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
