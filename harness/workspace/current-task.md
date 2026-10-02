# Current Task — 미지원 첨부 형식(IMP-009) 읽기 전용 조사

## Goal / Context

2026-10-02 사용자 요청: 미지원 첨부 형식(ZIP 144 / OTHER 107 / XLSX 50 / UNKNOWN 4, 고유 파일 기준)을 파싱·인덱싱에 넣기 위한 실체·분포·내용 가치·기술 조건을 읽기 전용으로 조사한다.
코드·DB·S3·Qdrant·`.env.dev`를 바꾸지 않는다. 파싱·인덱싱 실행, 라이브러리 설치, V1 collection·baseline 변경, commit/push는 범위가 아니다. 현재 V2 collection 전환 상태는 건드리지 않는다.

확정된 방향(사용자): DOCX·PPTX는 Docling XML 직접 읽기(VLM 없음). XLSX는 숨긴 시트 제외·저장된 계산값 사용·크기 상한 초과는 자르지 않고 문서 단위 실패. DOC·PPT·XLS는 LibreOffice로 DOCX·PPTX·XLSX 변환 후 같은 경로. 일반 ZIP은 내부 파일을 각각 문서로(깊이 1).

## Next Steps

1 공통 기반(형식 판별·Contract) → 2 XLSX → 3 DOCX·PPTX → 4 옛 오피스 → 5 일반 ZIP → 6 이미지(선택) → 화면 완주 + LangSmith → cases-v2 평가.

## Read First

[AGENTS](../../AGENTS.md) → [Backlog](../docs/improvement-backlog.md)(IMP-009·004·010) → [Source 규칙](../rules/data-source-rules.md) → `contracts/schemas/document-parsing.contract.json`(routes·hwpx_container_limits).

## Scope / Acceptance

1. 형식 실체·V2 범위 연결 수·압축 내부 구성·XLSX 분포·표본 내용 가치·기술 조건을 근거와 함께 표로 남긴다.
2. 원본은 읽기만 한다(로컬 보존본 SHA 확인, 압축은 메모리에서만 읽음). 결과는 IMP-009 Evidence로만 추가한다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-imp009-unsupported-formats.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
