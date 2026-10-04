# Current Task — 묶음5-1 공개 서비스용 기능

## Goal / Scope

dev clean working tree에서 사용자 승인 묶음5-1을 수행한다. 판정 출력 상한 1280→2560(15개·75초·fail-closed 유지)과 Bedrock 120174 단일 판정 1회 확인.
비로그인 소개 화면, 체험 계정(설정 on/off·합성 기업정보·수정 불가·24시간 뒤 정리·체험 합산 하루 200회), 사용자별 하루 AI 30회(한국 자정·원자적 증가), /privacy·/terms 초안과 가입 필수 동의 기록, 모든 화면 하단 데이터 출처.
새 Flyway V13만 추가·dev 적용(기존 migration 불변). key/vector/V1·V2 collection 불변. Secret 열람, prod, commit/push 없음.

## Read First

AGENTS→Registry→DB 규칙/database-migration→api-contract-change. [이전 묶음4](reports/development/2026-10-04-bundle4-quality.md), Backlog IMP-003·029·033·034.

## Validation / Reports

Spring·React·Python 테스트 → nginx 경유 스모크 → 고정 10질문 회귀 1회(현재 provider) → 최종 check-all 1회.
[Final Report](reports/development/2026-10-04-bundle5-1-features.md), Artifact artifacts/development/bundle5-1-features/.
사용자 지정 handoff/bundle5-1-handoff.md는 항목 종료마다 갱신한다.

## Next Steps

구현·검증 결과는 Report 참조. 약관·개인정보처리방침 문구와 문의처, 공공데이터 이용허락 조건(IMP-034)은 사용자 확인 대기. 독립 AGY 검토 대기. 사용자가 한 번에 commit한다. 자동 다음 Task 시작 금지.
