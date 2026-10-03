# Current Task — 지역 작업 마무리 및 IMP-029 판정 실패 수정

## Goal / Context

2026-10-03 사용자 승인: Part 1 → Part 2를 완료한다. 기존 지역 측정의 60건 표본·근거는 [측정 Report](reports/development/2026-10-03-region-filter-measurement.md)에 보존한다.
지역 결정은 둘을 구분한다: 질문 지역은 추출하지 않고 unapplied 안내(결정 나), 후보 지역 필터는 현재 MySQL 소관기관 제외 유지. 가산점·신청 가능 지역 추출은 후속이며 이번에는 구현하지 않는다.
V11 적용 승인(TAB/개행 → NULL, 광주시 prefix 오분류 경계 수용). 기존 migration 수정 없이 pending V11을 공통 migrations/로 이동해 dev/test migrate/validate한다.

## Scope / Acceptance

1. V11 실제 변경 건수·재실행 확인. 이전 자유 입력 변환은 사용자 승인 범위다.
2. Backlog에 공고별 신청 가능 지역 추출 및 소관 메타데이터 불일치 기록, IMP-019/030 측정 Evidence 연결.
3. 사용자 범위 축소: 원인 표·해결안 비교 실험은 생략한다. IMP-029 prompt에 서류/절차/작성 항목 제외·반복 금지·관련 조건 묶기(보통2~8)를 명시하고 max_criteria15/max_output_tokens1280을 적용한다. 잘린 출력·15개 도달은 판정하지 않는다.
4. 기존 75초 LLM 기한·순차 호출 유지; 식별 key·embedding·Qdrant·지역 필터 로직 변경 없음. 실제 workflow Top3까지 공고별 단계90초 미만 확인.
5. 마지막 check-all. commit/push·prod 접근·범위 확장 없음. AGY 독립 Review 및 사용자 검토 pending.

## Read First

[AGENTS](../../AGENTS.md) → [Codex](../agents/codex-developer.md) → [AI 경계](../rules/ai-boundary-rules.md) → [DB 규칙](../rules/database-rules.md) → [진단](reports/development/2026-10-03-recommend-timeout-diagnosis.md) → eligibility 계약·service·llm provider.

## Next Steps

V11 dev2행 적용 및 prompt15개/1280token 변경 완료. 같은 입력 workflow1회는 Top3 모두 처리했고 판정2건 완료·123260 근거ID 오류1건, WAITING_FOR_USER다. 마지막 check-all1회 → Report → 사용자/AGY 검토 대기. 실패 재실행·추가 실험은 범위 밖이다. 다른 Task는 자동 시작하지 않는다.

## Validation / Reports

[Final Report](reports/development/2026-10-03-region-wrapup-and-imp029.md). targeted tests 및 마지막 `./scripts/check-all.sh` 실제 exit/count를 기록한다.
