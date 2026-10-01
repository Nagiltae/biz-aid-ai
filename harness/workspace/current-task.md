# Current Task — Codex 인수인계 문서 검토·보완

## Goal / Context

2026-10-01 사용자 요청: Codex의 인수인계 문서 작업(최초 최신화 + 추가 정정)을 실제 구현·기존 Report와 대조해 남은 불일치와 누락만 보완한다.
새 기능, AI 코드 리팩터링, prompt, migration, LangGraph·LangSmith 구현 변경, Parser/Chunk/Embedding, Qdrant 배치 조작, V1 기준선 수정, AWS 배포는 범위가 아니다.

## Current State Snapshot

- 완료: V1 E2E·고정 평가(10건 중 7 PASS), V2-0~V2-6 기능 구현(LangChain 호출 경계, 개인화 검색, Top 3 판정, LangGraph workflow + MySQL State, 최종 결과, React 맞춤 추천, 선택적 LangSmith 추적).
- 진행: V2 서비스 범위 2,541개 문서 파싱 RUNNING. 18:19 KST 조회 1,014/2,541(PARSED 1,011, 실패 3, 이전 run 결과 건너뜀 352).
- 실행 구조(프로세스 명령으로 확인): 실행 중인 batch는 `sh -c "파싱; 인덱싱 --collection-namespace v2 --parsed-only"`다. 파싱이 끝나면 같은 batch가 run `v2svc-20261001-index`를 이어서 실행한다(`;`라서 파싱 종료 상태와 무관). 그 run의 현재 기록 `STOPPED_ENVIRONMENT`(0 indexed)는 첫 파싱 중단 때의 시도다. 별도 인덱싱 재시작을 하지 않는다.
- 위험: 첫 중단 원인은 AWS 로그인 만료였다. batch 도중 만료되면 다시 `STOPPED_ENVIRONMENT`가 될 수 있다(재개 방법은 V2-0 Report §4).
- Qdrant: V1 `bizaid_chunks_v1_228acdd12220` green 3,849 point(동결), V2 `bizaid_v2_chunks_v1_228acdd12220` green 207 point(3문서 Smoke).
- 관측: LangSmith 진단 연결 확인(biz-aid, 928ce4c3…). `.env.dev` 설정 완료. 실제 사용자 workflow 추적은 미검증.

## Read First

[AGENTS](../../AGENTS.md) → [README](../../README.md) → [Master Guide](../../PROJECT_MASTER_GUIDE.md) → [Architecture](../docs/architecture.md) → [Backlog](../docs/improvement-backlog.md) → [Codex 인수인계 Report](reports/development/2026-10-01-project-handoff-docs.md).

## Scope / Acceptance

1. 코드와 맞지 않는 설명, 오래된 상태, 문서 간 충돌, 잘못된 다음 작업 지침만 고친다. Codex가 정확히 정리한 부분은 유지한다.
2. Backlog ID의 기존 의미를 보존한다. IMP-003 provider·생성 완결성(E01 판정 품질 Evidence 포함), IMP-019 개인화 순위, IMP-020 RESOLVED, IMP-021 workflow 보관·중단 점유, IMP-022 DB COMMENT, IMP-023 LangSmith 추적 범위.
3. 배치는 읽기 전용 조회만 한다. Secret 값은 읽거나 기록하지 않는다.
4. 다음 개발: 파싱 완료 → 같은 batch의 인덱싱 결과 확인 → V2 collection 완전성 검증 → 전환 → V2 기준선 평가·실제 workflow 추적 확인.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-01-handoff-review.md). 문서 경로·상태·비밀값·Git 경계를 확인하고 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
