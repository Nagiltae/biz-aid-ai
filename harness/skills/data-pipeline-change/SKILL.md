---
name: data-pipeline-change
description: Phase 0 원문 보존과 데이터 검증 도구 또는 승인된 Pipeline 변경에 사용한다.
---

# data-pipeline-change

[Pipeline Context](../../docs/data-pipeline.md)와 [Source 규칙](../../rules/data-source-rules.md)을 읽는다.
원문·checksum·입력 계약을 확인하고 영향 범위를 제한한다. Phase 1A 동일 100 Item Pilot은 보존한다.
Phase 1B FULL 증거와 구조화 DB를 보존한다. 현재 승인된 Phase 2는 검증된 dev DB에서 전체 문서 후보를 추출해
공개 원본 byte·checksum·source provenance·실패 metadata를 수집하는 범위다.
Document Contract의 순차 요청·자동 retry 0·redirect/size/timeout·HTML 거부·overwrite 금지·resume 경계를 따른다.
현재 승인된 Phase 3는 S3 원본을 DoclingDocument로 변환하는 Parser이며 [Parsing Contract](../../../contracts/schemas/document-parsing.contract.json)와
Source 규칙의 Phase 3 절을 따른다. route·container 한도·parse_key를 바꾸면 Contract와 Test를 함께 바꾼다.
prod·Phase 1B 재실행·원본 재다운로드/재업로드·OCR/Chunking/index/AI는 범위 밖이다.
실패 원문을 보존하고 덮어쓰기·재실행 정책을 검증한다.
실제 데이터 분석 시 [측정 절차](workflows/pipeline-validation.md)를 추가로 읽는다.
이 측정 절차는 별도 승인된 Gate Task에만 적용한다.
현재 Phase에서는 기존 측정 절차 외 추가 workflow/reference가 필요하지 않음.
