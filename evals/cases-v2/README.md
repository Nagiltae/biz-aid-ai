# V2 provider 비교 시험 v1

작은 고정 시험 20건: 검색 8, 공고문 질문 7, 맞춤 추천 3, 공고 자격 판정 2.
기대값은 dev MySQL 공고 정보와 Qdrant V2 원문·기존 Gold를 대조해 **모델 실행 전에** 정했다.
`cases-v2.frozen.json`은 입력 checksum을 검증한다. 기준 변경은 별도 버전이며 V1 baseline은 변경하지 않는다.

## 채점

- 검색: 기대 공고 포함, 중복 없음, MySQL 후보 범위, 최대 5개. 정확한 순위 문자열은 비교하지 않는다.
- 질문: 대상 공고·원본 SHA+chunk 순번, 핵심 사실, 실제 검색된 chunk의 citation, 타 공고 혼입 없음.
  근거 없는 질문은 INSUFFICIENT_EVIDENCE와 citation 없음이 정답이다. 유사명 공고는 최신 공고 선택도 확인한다.
- 추천: 기대 공고 포함, Top 3 판정 완료, 공고별 근거 혼입 없음. 사용자 추가 정보 대기는 실패가 아니다.
  workflow는 저장용 축약 citation만 반환하므로 chunk readback 검증과 혼동하지 않는다.
- 자격: 최종 상태, 핵심 조건 결과 또는 UNKNOWN, citation 검증. 이유 문장의 전체 문자열을 비교하지 않는다.
- 시간은 관찰값이다. 채점 FAIL 조건으로 쓰지 않는다. 공개 표준단가 비용은 AWS 청구서가 아니다.

## 실행

명시적으로 승인된 dev 환경에서 순차로 실행한다. 기본 provider는 Ollama다. AWS 키 파일을 직접 읽지 않는다.

```bash
BIZAID_DOCLING_ARTIFACTS_PATH="$HOME/.cache/biz-aid/docling-artifacts" .venv/bin/python evals/cases-v2/evaluate.py --provider ollama --output harness/workspace/artifacts/development/bundle4-quality/ollama-results.json
BIZAID_DOCLING_ARTIFACTS_PATH="$HOME/.cache/biz-aid/docling-artifacts" .venv/bin/python evals/cases-v2/evaluate.py --provider bedrock --output harness/workspace/artifacts/development/bundle4-quality/bedrock-results.json
```

출력 파일이 있으면 재실행·덮어쓰기를 거부한다. 새 비교는 새 출력 경로와 사용자 승인으로 수행한다.
LLM은 순차 호출하며 재시도하지 않는다. Bedrock 환경 오류는 남은 시험을 중단한다.
결과는 Generated Artifact이며 Git에 넣지 않는다. 합성 기업정보와 공개 공고 식별값만 고정 입력으로 관리한다.
