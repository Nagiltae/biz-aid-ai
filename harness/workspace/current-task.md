# 현재 Task

## 목표 / 승인 범위

AI 개선 1단계(2026-10-06 사용자 승인). [0단계 측정](../../docs/ai-improvement-before.md)의 추천안 두 가지만 구현한다.
- IMP-019 A안: 기업정보(업종·업력·직원 수·매출 구간·사업자 형태·수출/벤처/연구소)로 코드가 만든 짧은 문장으로 같은 후보 안에서 hybrid 검색을 한 번 더 하고, 질문 검색과 가중 RRF로 합친다. 질문 비중을 더 크게 둔다. LLM 추가 없음.
- IMP-029 A안: 판정 prompt에 좋은 예/나쁜 예 1쌍과 짧은 묶기 예시를 추가한다. 최대 조건 수·출력 token 한도·evidence_ids 규칙은 그대로다.
기존 지역 필터·규모 필터·지역 가산점, original_rank 등 기존 기록 필드는 유지한다. 새 점수 필드는 계약에 추가한다.

## 상태

구현·측정 완료, 최종 check-all·사용자 검토 대기. 가중치는 0.3(일반 질문 0.6)으로 정했다. 이전 묶음6-0 current-task 원문은 Final Report 부록에 보존했다. 실제 수치는 [1단계 비교](../../docs/ai-improvement-after-1.md)와 Final Report를 따른다.

## Read First

AGENTS → Registry → workflow/git-policy → [0단계 측정](../../docs/ai-improvement-before.md) → Backlog IMP-019·IMP-029.
rag-change Skill, ai-boundary-rules, observability를 적용한다.

## Acceptance / Safety

- V1 baseline·V1 collection·Gold-v1·cases-v2 기대값, Parser/Chunker/BGE-M3/embedding_text, 식별 key·벡터는 바꾸지 않는다.
- 재정렬 모델·새 패키지는 추가하지 않는다. AI는 Bedrock만 쓰고 순차·재시도 없이 실행한다.
- 기업정보 검색 문장 원문은 로그·추적(LangSmith)·응답에 남기지 않는다. 사용한 항목 이름과 가중치만 남긴다.
- cases-v2 20/20 유지, 특히 V2-16~18 기대 공고가 Top3에 남아야 한다. 떨어지면 가중치만 조정한다.
- Secret 파일 열람·출력 0. commit/push 금지, 새 입력만 명시 staging. 운영 서버·Docker Hub·S3 접근 금지.

## Validation

targeted 계약 테스트 → 회사별 Top3·조건 분할 측정 재실행 → cases-v2 Bedrock 1회 → check-all 1회 → 전후 비교 문서.

## Expected Report

[Final Report](reports/development/2026-10-06-ai-improvement-1.md)
