---
name: data-pipeline-change
description: Phase 0 원문 보존과 데이터 검증 도구 또는 승인된 Pipeline 변경에 사용한다.
---

# data-pipeline-change

[Pipeline Context](../../docs/data-pipeline.md)와 [Source 규칙](../../rules/data-source-rules.md)을 읽는다.
원문·checksum·입력 계약을 확인하고 영향 범위를 제한한다. Phase 1A 동일 100 Item Pilot은 보존한다.
현재 승인된 Phase 1B는 dev FULL 전체 pagination·Raw·완전성·정규화·MySQL 적재와 첫 soft-delete DRY_RUN이다.
FULL의 영속 안전 규칙은 Source 규칙과 FULL Contract를 따른다. prod·실제 soft-delete·증분 조회·문서 제품화·Parser·index는 범위 밖이다.
실패 원문을 보존하고 덮어쓰기·재실행 정책을 검증한다.
실제 데이터 분석 시 [측정 절차](workflows/pipeline-validation.md)를 추가로 읽는다.
이 측정 절차는 별도 승인된 Gate Task에만 적용한다.
현재 Phase에서는 기존 측정 절차 외 추가 workflow/reference가 필요하지 않음.
