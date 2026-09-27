# Phase 0 데이터 준비

최종 Pipeline 계획은 API → Raw → Normalize → MySQL Upsert → 변경 판단 →
Download → Checksum → Parse → Chunk → Embedding → Qdrant다. 이번에는 구현하지 않는다.

## 현재 도구

`scripts/phase0.py snapshot`은 이미 확보한 공식 JSON/XML 응답을 byte 그대로
data/raw/<run-id>/에 보존하고 SHA-256, 크기, 보존 시각, media type metadata를 만든다.
실제 수집 시각은 --collected-at으로 제공할 때만 기록하고 알 수 없으면 null로 둔다.
잘못된 JSON/XML·중복 key·DTD 응답도 원문을 보존하며 payload_syntax=invalid로 기록한다.
XML 형식 점검은 UTF-8만 지원한다. 다른 encoding 원문은 invalid로 표시하고 보존한다.
HTTP 요청, API envelope 해석, pblancId mapping, key 제거를 수행하지 않는다.
입력에 credential이 포함되지 않은 응답인지 사용자가 확인한다. 원문은 Git에서 제외한다.
`verify-snapshot`은 계약·경로·크기·hash와 형식 상태의 일관성을 검증한다.
checksum PASS는 invalid 원문의 수집 품질 PASS를 뜻하지 않는다.
`init-report`는 모든 지표를 not_measured로 초기화한다. `validate-report`는 로컬 기록 계약만 검증한다.

## 실제 Gate 진행 전 준비

- 공식 명세와 credential 없는 실제 응답: endpoint·pagination·응답 경로·오류 형태 확인.
- 최근 약 100건 선택 방법, 주요 필드와 null / blank / invalid 구분, 각 분모 확정.
- pblancId가 공고와 첨부의 동일성을 보장하는지 확인. 별도 entity matching은 요구하지 않는 설계다.
- 공고 상세 URL과 주 공고문 다운로드 URL을 분리해 확보율 측정.
- 원문과 다운로드 checksum, 실패 원문·이유·재시도 이력을 보존.
- PDF → HWPX → HWP → ZIP 순으로 실제 표·heading·scan·근거 위치를 비교.
- API에 없는 상세 조건·제외·중복지원·지원금·자부담·선정·서류·예외·주의사항을 근거와 대조.

[보고서 양식](../../evals/phase0-report-template.md)에 분자·분모·증거·예외를 기록한다.
[Report 계약](../../contracts/schemas/phase0-report.contract.json)은 upstream API 계약이 아니다.
MySQL Raw snapshot JSON column은 향후 계획이며 현재 Migration은 없다.
