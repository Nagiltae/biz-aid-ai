# 제품 Evaluation

현재 [Phase 0 보고서 양식](phase0-report-template.md)과 측정 계약만 준비한다.
실제 API / 문서 데이터가 없어 Gold 정답·RAG 성능 결과는 없다.

향후 Gold는 question, expected_program_ids, expected_document, expected_page,
expected_fact를 실제 원문 근거로 구축한다.
Retrieval Recall@K / MRR, groundedness / citation / answer, routing / structured output /
no-answer를 평가한다. Harness 개발 방식 평가는 harness/evals/에 분리한다.
