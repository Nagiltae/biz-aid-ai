# Current Task — 묶음2 지역·데이터 정리

## Goal / Context

사용자 승인0~6. 묶음1 최종구현은1d6d726에 보존됐으며 고정10건/QA근거부족/서울후보0 관찰을 이어받는다. 제품 key·vector·V1은 불변,commit/push 없음.

## Scope / Acceptance

0 P3 조건별 MySQL조회,LLM반복없음.
1 company-region 별칭/권역계약으로 제목지역+소관 필터,중앙표본20 및공동지역 사례확인.
2 period normalizer 명시 날짜 보강,derived-only atomic refresh.
3 기준일2026-10-04 이전확정마감 V2point만snapshot 검증 후승인삭제;MySQL/S3/V1유지.
4 신규원본 admission,기존point재적재없음;수출바우처조회만.
5 Backlog·Architecture·계약동기화.
6 Spring기업지역 전달→FastAPI공통규칙→React안내. named QA타지역 유지+경고,회사없으면 전체지역.

## Read First

AGENTS→Codex→Backlog→AI경계/Source/DB→company-region/rag/indexing/internal-api 계약. [묶음1 Report](reports/development/2026-10-03-bundle1-quality.md),[지역 측정](reports/development/2026-10-03-region-filter-measurement.md).

## Validation / Reports

[Final Report](reports/development/2026-10-03-bundle2-region-data.md). Targeted Python/Spring/React와기존MySQL Integration,최종check-all1회,고정10질문script1회. 최종제품입력 확정후생성report/handoff만갱신. handoff는harness/workspace/handoff/bundle2-handoff.md.

## Next Steps

구현 및 승인정리 완료: 날짜603→604(1행),V2 64041→60362(62공고3679point),V1 3849유지. 고정10질문1회 완료(S4건 LISTED,Q2건 ANSWERED/1건 INSUFFICIENT_EVIDENCE,P2건Top3판정/서울P3 NO_CANDIDATES). 최종check-all을 실제 실행하고 결과를 Report로확인한다. AGY independent review pending이며다음묶음자동시작금지.
