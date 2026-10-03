# Current Task — 맞춤 추천 기업 지역 조건(IMP-019 지역 부분)

## Goal / Context

2026-10-03 사용자 결정(규칙 변경 승인): A안 — 기업 지역과 다른 광역 지자체가 소관기관인 공고만 후보에서 제외하고 중앙부처·공공기관·소관기관 없음·전국 공고는 유지한다. 가안 — 기업 지역을 광역 지자체 선택(표준명)으로 바꾼다.
1단계 결정: 선택지는 데이터 기준 16개(광주·전남 대신 전남광주통합특별시), 질문 지역과 기업 지역이 다르면 충돌로 돌려준다(겹치는 지역만 남김, 중앙부처를 말한 질문은 충돌 아님), 변환할 수 없는 기존 값은 NULL.
판정 prompt·판정 규칙·Top 3 순위 계산·식별 key·근거 검색 변경, commit/push는 범위가 아니다. migration은 승인 전까지 `data-pipeline/pending-migrations/`에 둔다.

## Next Steps

질문 지역 충돌 처리 방식 결정 → V11 적용 승인 → 화면 확인 → IMP-029 → cases-v2.

## Read First

[AGENTS](../../AGENTS.md) → [AI 경계](../rules/ai-boundary-rules.md) → `contracts/schemas/company-region.contract.json` → `candidates/region.py`·`personalized.py` → [Backlog](../docs/improvement-backlog.md)(IMP-019·030).

## Scope / Acceptance

1. 매핑·표준명은 계약 파일 하나에만 있고 Spring·React·FastAPI가 그 파일을 쓴다.
2. 경기도 기업에서 서울·부산 소관 공고는 빠지고 중앙부처·매핑 없는 소관기관 공고는 남는다. 적용 조건이 결과에 기록된다.
3. 기업정보 지역은 표준명만 저장된다. 기존 값 변환 migration은 pending에 둔다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-03-company-region-filter.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
