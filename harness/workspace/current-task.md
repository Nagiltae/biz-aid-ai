# Current Task

## Goal / Context

2026-09-28 사용자 승인: Negative Probe exit 의미와 기본 정렬 선두 100건 API 품질 측정.
이전 Task 전체는 이번 Final Report에 보존한다. 과거 AGY Evidence는 유지하며 현재 독립 Review / Human Review / Data Gate는 pending이다.

## Read First

[설계](../../PROJECT_DESIGN.md) → [AGENTS](../../AGENTS.md) →
[이전 Live Report](reports/2026-09-28-codex-bizinfo-profile-live-probe-report.md) →
[API Contract](../../contracts/external-api/README.md) → [Pipeline](../docs/data-pipeline.md) →
[Source](../rules/data-source-rules.md) → [Skill](../skills/data-pipeline-change/SKILL.md).

## Allowed Scope / Forbidden Scope

Expected Negative와 API 오류를 구분하고 dev 전용 고정 pages 1–5 / rows 20 품질 Batch를 실행한다.
전체 Offline Validation PASS와 dev credential 확인 이전에는 Live를 호출하지 않는다.
Raw byte / checksum / 시각 / Secret 보호 / overwrite 금지를 유지한다. 중복 Item을 제거하지 않는다.
.env.dev / .env.prod 수정·삭제·stage·값 출력 금지. 실제 prod 파일 읽기·prod 호출 금지.
공고문 다운로드·Parser·DB·AI·전체 Collector·GO / DROP 금지. Commit·Push·Merge·Branch 변경 금지.

## Acceptance / Validation / Expected Report

5종 field 상태·ID 중복/존재·기간·첨부 metadata / 확장자·totalCount·순서를 측정하고 재현 가능한 Report를 작성한다.
CONFIRMED 사용자 표본 규칙 / OBSERVED Live 결과 / UNCONFIRMED 공식 정렬 및 Primary 역할을 분리한다.
[Final Report](reports/2026-09-28-codex-phase0-api-quality-report.md).
Report와 Git index를 완성한 뒤 format / lint / contract / integration / comments / harness / git-tracked / all을 최종 실행한다.
최종 check-all 이후 tracked 파일을 변경하지 않는다. 동결 후 결과는 ignored 로그와 최종 응답으로 전달한다.
상태: 전체 Offline Validation PASS 후 dev에서 5요청 / 100개 Item / unique ID 100 / 중복 0을 관찰했다.
5 Page 모두 HTTP 200 / 00 / 20건 / totalCount 1514 / echo 일치다. 정렬은 관찰 내림차순이며 공식 보장은 미확정이다.
주요 12개 field는 타입/nonblank VALID 100%, 기간 DATE_RANGE 82 / FREE_TEXT 18, 추가 첨부 metadata는 14건 null이다.
Raw 5개 checksum과 오프라인 재현 일치를 확인했다. Report 작성·최종 index·최종 Validation 후 독립 Review / Human Review 대기다.
이전 Task의 25개 staged 파일은 보존했다. prod·다운로드·전체 Collector·GO/DROP은 수행하지 않았다.
