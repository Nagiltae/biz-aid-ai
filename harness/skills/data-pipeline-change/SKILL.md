---
name: data-pipeline-change
description: Phase 0 원문 보존과 데이터 검증 도구 또는 승인된 Pipeline 변경에 사용한다.
---

# data-pipeline-change

[Pipeline Context](../../docs/data-pipeline.md)와 [Source 규칙](../../rules/data-source-rules.md)을 읽는다.
원문·checksum·입력 계약을 확인하고 영향 범위를 제한한다. 현재 승인 범위는 dev 전용 5×20 API 품질 Batch까지다. 전체 Collector·문서 다운로드·Parser·DB·index는 구현하지 않는다.
실패 원문을 보존하고 덮어쓰기·재실행 정책을 검증한다.
실제 데이터 분석 시 [측정 절차](workflows/pipeline-validation.md)를 추가로 읽는다.
이 측정 절차는 별도 승인된 Gate Task에만 적용한다.
현재 Phase에서는 기존 측정 절차 외 추가 workflow/reference가 필요하지 않음.
