# 제품 Evaluation

현재 [Phase 0 보고서 양식](phase0-report-template.md)과 측정 계약만 준비한다.
실제 API / 문서 데이터가 없어 Gold 정답·RAG 성능 결과는 없다.

향후 Gold는 question, expected_program_ids, expected_document, expected_page,
expected_fact를 실제 원문 근거로 구축한다.
Retrieval Recall@K / MRR, groundedness / citation / answer, routing / structured output /
no-answer를 평가한다. Harness 개발 방식 평가는 harness/evals/에 분리한다.

## Phase 3-B.1 PDF Table Engine Evaluation

`table_engine/`은 Docling TableFormer·PP-TableMagic·Camelot의 표 추출을 같은 corpus에서 비교하는 benchmark 도구다.
`corpus.json`은 SHA·provenance만 고정하고, engine 출력·GT·crop evidence는 ignored `data/parsed/table-engine-eval/<run-id>/`에 둔다.
제품 parsing route를 대신하지 않으며 결과는 Source 규칙의 PDF Table Engine 절에 따라 사용자 결정에만 쓰인다.
