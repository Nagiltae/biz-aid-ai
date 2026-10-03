# Current Task — 묶음 1 추천·답변 품질 및 고정 질문 회귀

## Goal / Context

2026-10-03 사용자 승인 범위 1→7. dev에서 기존 제품 경계를 최소 수정한다. 직전 근거 ID 오류는 당시 raw 응답이 없어 원인을 임의 확정하지 않는다. 현재 empty/outside 개수 진단을 추가한다.

## Scope / Acceptance

1. IMP-029 evidence_ids minItems1 및 근거 없는 criterion fail-closed.
2. Eligibility/DOCUMENT_QA Qdrant 근거에서 FORM 제외. UNKNOWN·role 없는 기존 point 유지. 목록 검색 영향 없음.
3. IMP-027 내부 지급 규정 document_role UNKNOWN. 승인된 V2 payload-only 정정, ID·vector·V1 불변.
4. 개인화 후보 Top10 중 최고 RRF90% 이상인 같은 표준 지역 소관 +0.001, Top3. 원점수·원순위·가산·최종점수 기록. MySQL 지역 제외·query·embedding·RRF 불변.
5. 명확한 목록/공고명+상세질문은 계약 규칙 우선, 애매한 의도만 기존 LLM.
6. 공고명 일치도→접수중→최신 선택, 동점 최대5 후보 사용자 선택. Spring은 검증·전달, React는 원래 질문+선택ID로 다시 요청.
7. 고정 검색4/문서QA3/맞춤추천3 순차 1회. 기존75초 LLM 기한 유지. 마지막 check-all 1회.

## Read First

AGENTS → Codex → [Backlog](../docs/improvement-backlog.md) → [AI 경계](../rules/ai-boundary-rules.md) → rag-answer/eligibility/indexing/internal-api 계약 → 해당 제품·테스트.

## Validation / Reports

[Final Report](reports/development/2026-10-03-bundle1-quality.md). 사용자 지정 `harness/workspace/handoff/bundle1-handoff.md`는 실행 상태 산출물이며 handoff에 제어 설정 변경이 필요 없다.
Generated JSON/log와 달리 regression-set/run.py는 사용자가 재사용할 실행 입력으로 strict 등록한다. 과거 V1 baseline 변경 없음.

## Next Steps

1~7 구현·고정질문10건1회 완료. 검색4 LISTED/QA2답변·1근거부족/추천2정보대기·1공고0개 완료. 123260 동일 snapshot1회는9조건·NEEDS_MORE_INFO·32.56초 정상. Python39/Spring10/React18 targeted PASS. 최종 check-all → Report. prod·secret 직접 읽기·재임베딩·V1변경·commit/push 금지. AGY 독립 검토 pending; 다음 묶음은 자동 시작하지 않는다.
