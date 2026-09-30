# 제품 Evaluation

제품 Evaluation은 검색 Gold와 V1 AI 기준선을 보유한다. 실제 공고문에서 파생된 대용량 Gold·실행 결과는 ignored data 영역에,
사람이 검토한 작은 V1 서비스 사례와 동결 hash는 `v1_baseline/`에 둔다.

향후 Gold는 question, expected_program_ids, expected_document, expected_page,
expected_fact를 실제 원문 근거로 구축한다.
Retrieval Recall@K / MRR, groundedness / citation / answer, routing / structured output /
no-answer를 평가한다. Harness 개발 방식 평가는 harness/evals/에 분리한다.

Gold의 질문·기대 source·기대 evidence는 평가 대상(Retriever 등)을 실행하기 전에 확정하고 sha256으로 동결한다.
평가 결과를 본 뒤 Gold 정답을 유리하게 고치지 않는다. 고쳐야 하면 새 버전(gold-vN)으로 만들고 이전 결과와 섞지 않는다.

## V1 AI Baseline

`v1_baseline/cases-v1.json`은 V1 종료 시점의 고정 비교 세트다. SEARCH_LIST 4건, DOCUMENT_QA 3건,
Eligibility 3건으로 구성하며 기존 Gold-v1·실제 Smoke에서 확인한 기대값만 사용한다. 자연어 답변 전체는 비교하지 않고
공고 ID·순위, `(source_sha256, chunk_index)` 근거, citation, 핵심 사실, 자격 상태와 핵심 criterion을 판정한다.

`cases-v1.frozen.json`의 sha256이 다르면 실행을 거부한다. 기존 case나 기대값을 바꿔 과거 결과를 덮어쓰지 않으며,
평가 기준을 바꿔야 하면 새 baseline version을 만든다. 같은 V1/V2 비교는 가능한 한 동일 baseline을 사용한다.

실행 결과는 ignored `data/parsed/v1-ai-baseline/<run-id>/result.json`에 새 경로로 저장한다. 기존 결과는 덮어쓰지 않는다.

```bash
BIZAID_DOCLING_ARTIFACTS_PATH=~/.cache/biz-aid/docling-artifacts \
  .venv/bin/python -B evals/v1_baseline/evaluate.py \
  --profile dev \
  --cases evals/v1_baseline/cases-v1.json \
  --output data/parsed/v1-ai-baseline/<new-run-id>/result.json
```

2026-10-01 최초 실행은 10건을 1회 시도해 7 PASS / 3 FAIL이었다. 검색은 4/4 PASS, QA는 2/3 PASS였고,
Eligibility는 1/3 PASS(2건은 모델이 허용되지 않은 profile field 이름을 출력해 application 검증에서 실패)였다.
품질 실패나 실행 오류는 생산 코드를 조정하지 않고 [Improvement Backlog](../harness/docs/improvement-backlog.md)에 남긴다.

## Retrieval Evaluation

`retrieval/evaluate.py`가 동결된 Gold(ignored `data/parsed/retrieval-eval/<gold-version>/`)로 dense·sparse·hybrid를 같은 top_k로 실행하고
Source Hit@1·Source Hit@5·Evidence Hit@5를 계산한다. Gold hash가 동결 값과 다르면 실행하지 않는다. Gold·결과는 공고 첨부에서 파생되므로 Git에 넣지 않는다.

## Phase 3-B.1 PDF Table Engine Evaluation

`table_engine/`은 Docling TableFormer·PP-TableMagic·Camelot의 표 추출을 같은 corpus에서 비교하는 benchmark 도구다.
`corpus.json`은 SHA·provenance만 고정하고, engine 출력·GT·crop evidence는 ignored `data/parsed/table-engine-eval/<run-id>/`에 둔다.
제품 parsing route를 대신하지 않으며 결과는 Source 규칙의 PDF Table Engine 절에 따라 사용자 결정에만 쓰인다.
