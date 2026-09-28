---
name: data-pipeline-change
description: Phase 0 원문 보존과 데이터 검증 도구 또는 승인된 Pipeline 변경에 사용한다.
---

# data-pipeline-change

[Pipeline Context](../../docs/data-pipeline.md)와 [Source 규칙](../../rules/data-source-rules.md)을 읽는다.
원문·checksum·입력 계약을 확인하고 영향 범위를 제한한다. Phase 1A는 기존 동일 100 Item의 제품용 Normalize / dev MySQL 적재 Pilot이다.
FULL 완전성 / lifecycle은 controlled test만 수행한다. live FULL·증분 조회·문서 제품화·본문 Parser·index는 범위 밖이다.
실패 원문을 보존하고 덮어쓰기·재실행 정책을 검증한다.
실제 데이터 분석 시 [측정 절차](workflows/pipeline-validation.md)를 추가로 읽는다.
이 측정 절차는 별도 승인된 Gate Task에만 적용한다.
현재 Phase에서는 기존 측정 절차 외 추가 workflow/reference가 필요하지 않음.
