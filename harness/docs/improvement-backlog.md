# Improvement Backlog

실제로 관찰했지만 blocker가 아니어서 기능 진행을 위해 **의도적으로 미룬** 개선만 기록한다.
정상적인 다음 기능, 근거 없는 아이디어, 일반 리팩터링 욕구, 이미 해결된 일은 넣지 않는다. 운영 규칙은 [Workflow](workflow.md#improvement-backlog)에 있다.

- 형식: ID, Area, Issue, Evidence, Why deferred, Revisit trigger, Side effect, Status(OPEN / RESOLVED / DROPPED)
  - 한글 설명: Area(영역), Issue(문제), Evidence(근거·관찰 사례), Why deferred(지금 미룬 이유), Revisit trigger(다시 볼 시점),
    Side effect(고칠 때 주의할 영향), Status(상태: OPEN 미해결 · RESOLVED 해결 · DROPPED 가치 없어 폐기)
- 같은 문제는 새 ID를 만들지 않고 Evidence·Revisit만 갱신한다. 해결·폐기 항목은 지우지 않고 Status와 근거 report를 남긴다.
- Evidence의 report는 `harness/workspace/reports/development/` 아래 파일이다.

## 단계 분류 (2026-10-01 V1 코드 마감)

| 단계 | 항목 | 기준 |
| --- | --- | --- |
| V1 마감 전 해결 | IMP-013(RESOLVED) | 다음 작업인 V1 AI 평가 기준선을 직접 막음 |
| V2에서 해결 | IMP-002, IMP-003, IMP-004, IMP-011, IMP-018 | 답변·검색 품질 개선. 기준선 고정 뒤 비교해야 효과를 잴 수 있음 |
| 운영/AWS 단계 | IMP-005, IMP-006, IMP-007, IMP-015, IMP-016, IMP-017 | 배포 이미지·실행 환경·대량 처리·DB 운영 정책 |
| 장기 개선 | IMP-009, IMP-010 | 미지원 형식·Parser 품질. 실제 실패 사례가 반복될 때 |

## IMP-001 chunk에 문서 제목·사업명 context 없음

- Area: Chunking / Retrieval
- Issue: FinalChunk의 embedding_text는 heading 경로와 본문뿐이다. "2. 지원 요건" 같은 일반 heading의 chunk는 사업명이 없어 질문의 사업명과 맞지 않는다.
- Evidence: Retrieval Evaluation G01. 정답 source는 세 mode 모두 1위였지만, 기대 chunk(#2 지원 요건)는 top5 밖이었고 개요 chunk가 1위였다(`2026-09-30-retrieval-evaluation.md`). RAG smoke G01은 같은 이유로 확인 불가였다(`2026-09-30-phase6-rag-answer.md`).
  DOCUMENT_QA smoke "비즈플러스카드 지원요건 알려줘"도 top5가 모두 같은 공고(#0·#1·#4·#5·#22)였지만 #2가 빠져 확인 불가였다(`2026-09-30-phase6d-discovery-list.md`). 같은 유형이 반복됐다.
- Why deferred: Hybrid Source Hit@1 12/12, Evidence Hit@5 11/12로 RAG blocker가 아니다. 1건만으로 Chunking을 바꾸지 않는다.
- Revisit trigger: 더 큰 Gold에서 같은 유형이 반복될 때, 또는 실제 RAG 실패가 title context 부족으로 반복될 때
- Side effect: embedding_text와 chunk identity가 바뀐다. re-chunk·re-embedding·re-indexing과 Retrieval Evaluation 재실행이 필요하다.
- Status: RESOLVED(`2026-09-30-imp001-title-context.md`). embedding_text 첫 줄에 공고명(support_programs.name)을 넣고, chunk text는 그대로 두었다. chunker_version 2로 chunk_set_key를 바꿔 100-source를 재적재했다(stale 3,849 삭제, 3,849 재적재).
  - G01 evidence 순위: dense·sparse·hybrid 모두 top5 밖 → 1위
  - "비즈플러스카드 지원요건" QA: #2 지원 요건이 E1, NCB·업력·매출 요건을 근거대로 답함
  - 정상 G05는 1위 유지

## IMP-002 표 직렬화 가독성과 표 구조 보존 범위

- Area: Parsing(표) / Chunking(serializer) / RAG
- Issue: 표 chunk가 "열, n = 값" triplet으로 직렬화되고 HWPX 병합 cell 값이 반복된다. 검색 순위도 낮고 LLM도 행·열 관계를 읽지 못한다. PP가 구조를 증명하지 못한 PDF 표는 구조 없는 text로 남는다.
- Evidence
  - Retrieval G09: HWPX 신청서 표, sparse miss, dense·hybrid 5위
  - RAG smoke G06: 기대 표 chunk가 top5에 있었는데 qwen3.5:9b가 "등급 → 지원금액"을 읽지 못해 INSUFFICIENT_EVIDENCE
  - 100-source corpus: 62문서 358 영역이 TABLE_QUALITY_FAILED text(`2026-09-30-phase3-3c-corpus-parsing.md`)
- Why deferred: hallucination 없이 보수적으로 실패한다. V1 진행 blocker가 아니고, 표 정확도 개선은 serializer·parser 양쪽 결정이다.
- Revisit trigger: V1 완료 후, 또는 IMP-003에서 Gemini로 같은 context를 줘도 실패할 때, 또는 실제 표 질문 실패가 반복될 때
- Side effect: serializer 변경은 chunk identity를 바꾼다(re-chunk·re-embedding·re-indexing·Retrieval Evaluation 재확인). 표 engine 변경은 parse_key와 Source 규칙의 evidence 요구를 따른다.
- Status: OPEN

## IMP-003 LLM provider 비교와 생성 완결성

- Area: RAG / LLM
- Issue: 현재는 로컬 qwen3.5:9b 하나로만 동작을 확인했다. 핵심 값은 맞지만 조건·기간을 빠뜨리거나 표현이 약간 부정확한 경우가 있다.
- Evidence: RAG smoke G05에서 금액은 정답이었지만 "최대 12개월"이 누락되고 "한 달에 최대 20만원"으로 표현했다. G06은 표를 해석하지 못했다(`2026-09-30-phase6-rag-answer.md`). provider 경계(`rag.llm.LlmProvider`)는 준비돼 있다.
  Eligibility smoke A의 criterion reason에 중국어 토큰("经营状态")이 섞였고, 8개 criterion 출력에 LLM 25~34s가 걸렸다(`2026-09-30-eligibility-v1.md`).
  natural-filter smoke B(서울 지역 소상공인 금융)는 "확인할 수 없다"면서 ANSWERED로 E2가 서울 지역 사업임을 "암시한다"고 해석을 덧붙였다. evidence 해석이 과장된 사례다(`2026-09-30-phase6c-natural-filter.md`).
  V1 기준선 10건에서 QA G05는 다시 금액은 맞았지만 최대 12개월을 빠뜨려 FAIL이었다. Eligibility 2건은 모델이
  `additional_facts.최근 2개월 매출(원)` 대신 허용되지 않은 `additional_facts.최근 2 개월 매출`을 내 application 검증에서 실패했다.
  G06 표 금액은 이번에는 32,760원을 근거와 함께 맞혔다(`2026-10-01-v1-ai-baseline.md`).
- Why deferred: V1 흐름과 grounding은 동작한다. 비교는 완성된 동일 서비스에서 해야 공정하다.
- Revisit trigger: AI 서비스 V1 완료와 프로젝트 정리 후
- Side effect: 비교 조건을 같게 한다(Retriever, top_k 5, context, prompt, output schema). 볼 항목은 정답성, groundedness, citation 정확도, 확인 불가 판단, 표 이해, latency, API 비용이다. 원격 API는 공고 첨부 내용을 외부로 보낸다.
- Evidence(V2-0, 2026-10-01): 기업정보 field ID + enum 제한 뒤 같은 E01~E03 입력 1회씩 확인에서 계약 오류는 0/3이 됐다. 다만 E01은 값이 있는 조건에 모델이 UNKNOWN을 내 NEEDS_MORE_INFO(기대 ELIGIBLE)가 됐다. 형식 문제가 아니라 판정 품질 문제다(`2026-10-01-v2-0-foundation.md`).
- Status: OPEN

## IMP-004 Retrieval 후처리(baseline 이후)

- Area: Retrieval
- Issue: 정답 문서를 찾은 뒤 같은 문서의 개요·머리 chunk가 근거 chunk보다 앞서는 경우가 많다.
- Evidence: Evidence 2위 사례 G04·G07·G08·G10, 5위 G09(`2026-09-30-retrieval-evaluation.md`)
- Why deferred: Hybrid Source Hit@1 12/12, Evidence Hit@5 11/12다. top5 context로 RAG가 동작하므로 Reranker·Query Rewrite·parent/neighbor expansion의 필요성이 아직 입증되지 않았다.
- Revisit trigger: 더 큰 Gold에서 evidence 순위·recall 문제가 확인될 때, 또는 실제 RAG 실패가 retrieval 순위 때문에 반복될 때
- Side effect: 후보마다 latency·모델 artifact가 늘어난다. 같은 Gold로 전후를 비교한다.
- Status: OPEN

## IMP-005 모델 artifact 검증이 전체 manifest 단위

- Area: Model artifact / 배포
- Issue: query embedding만 하는 process도 parsing·OCR 모델을 포함한 전체 artifact(약 3.7GB)가 있어야 하고, 시작할 때 전체를 hash한다.
- Evidence: manifest hash 2.6s, embedder init 4.8s 실측(`2026-09-30-pre-ai-service-cleanup.md` C)
- Why deferred: 지금은 한 dev 머신에서 모든 단계를 실행하고, 서비스 container가 없다.
- Revisit trigger: RAG를 FastAPI 등 별도 서비스·container로 배포할 때
- Side effect: scope별 검증 경로나 파일 digest cache를 도입하더라도 parse_key·chunk·embedding identity 계산은 바뀌면 안 된다.
- Status: OPEN

## IMP-006 현재 parse_key를 실행 환경에서 다시 계산

- Area: Chunking / Indexing
- Issue: chunking은 현재 parse_key를 실행 환경(paddle·docling 버전, HWP Docker 변환 이미지 identity)에서 다시 계산해 PARSED row를 찾는다. 그래서 indexing에도 parsing 환경이 필요하다. 같은 로직이 `parsing/corpus.py`와 `chunking/source.py`에 중복돼 있다.
- Evidence: `2026-09-30-pre-ai-service-cleanup.md` C·B-1(HWP 변환기 부재 시 실패 격리만 보강)
- Why deferred: 현재는 같은 머신에서 실행해 문제가 없다. B-1로 source 단위 실패 격리는 확보했다.
- Revisit trigger: indexing이나 서비스를 parsing 환경과 다른 곳에서 실행할 때, 또는 전체 corpus indexing 전
- Side effect: "최신 PARSED" 선택 규칙을 바꾸면 오래된 parser 결과를 쓰게 될 위험이 있어 identity 규칙과 함께 결정해야 한다.
- Status: OPEN

## IMP-007 전체 corpus 실행 전 처리량·메모리·운영 조건

- Area: Pipeline 운영
- Issue: 순차 처리라 전체 2,926건은 수십 시간 걸린다. 큰 PDF 한 건에 약 10분이 걸리고 parser worker peak RSS는 7GB다. indexing은 CPU float32다. AWS login 세션이 만료되면 실행이 멈춘다.
- Evidence
  - parsing 추정 30시간 이상(`2026-09-30-phase3-3c-corpus-parsing.md`)
  - dataset100 실측: parsing p95 66.9s·max 593s, peak RSS 7,168MB, indexing 9.1s/source
  - 1차 시도가 AWS 세션 만료로 STOPPED_ENVIRONMENT(`2026-09-30-dataset100-build.md`)
- Why deferred: 사용자 결정으로 전체 corpus는 실행하지 않았다. 100-source로 기능 개발에 충분하다.
- Revisit trigger: 전체 corpus parsing·indexing을 결정할 때
- Side effect: 병렬화·MPS/fp16은 embedding identity(dtype·device)와 메모리 경쟁에 영향을 준다.
- Status: OPEN

## IMP-008 공고 relation이 비활성·삭제 공고를 거르지 않음

- Area: Chunking / MySQL 결합
- Issue: `chunking/source.announcements()`는 ACQUIRED relation만 보고 공고의 source_active·soft-delete 상태를 보지 않는다. 마감·삭제 공고의 chunk도 적재·검색될 수 있다.
- Evidence: `2026-09-30-pre-ai-service-cleanup.md` C(현재 soft-delete는 DRY-RUN이라 영향 0)
- Why deferred: 지금은 삭제된 공고가 없다. 상태 판단은 MySQL hard filter 단계의 책임이다.
- Revisit trigger: MySQL 구조화 조건 + pblanc_id 후보 filter를 RAG에 결합할 때, 또는 soft-delete 적용을 승인할 때
- Side effect: 적재에서 거르면 index 재생성 정책이, 검색에서 거르면 MySQL 조회 경계가 필요하다.
- Status: RESOLVED. `candidates/`가 `source_active=1 AND source_deleted=0`인 공고만 후보로 내고, Retriever가 Qdrant MatchAny로 후보 밖 point를 검색하지 않는다.
  RAG CLI는 항상 이 경로를 거친다(`2026-09-30-phase6b-candidate-scoped-rag.md`). index에는 비활성 공고 point가 남을 수 있지만 RAG 경로에서는 도달할 수 없다(파생 index).
  scope 없는 `run_document_retrieval.py`는 dev 진단용이다.

## IMP-009 미지원 문서 형식(ZIP·XLSX·OTHER·UNKNOWN)

- Area: Parsing
- Issue: enabled route가 PDF·HWP·HWPX뿐이다. ZIP·XLSX·OTHER·UNKNOWN 첨부는 POLICY_PENDING으로 parsing·검색 대상이 아니다.
- Evidence: 100-source run에서 unsupported 305 relation(ZIP 144 / OTHER 107 / XLSX 50 / UNKNOWN 4)을 집계만 했다(`2026-09-30-phase3-3c-corpus-parsing.md`). ZIP은 member provenance Contract가 먼저 필요하다(Source 규칙).
- Why deferred: 주요 공고 본문은 PDF·HWP·HWPX에 있고, ZIP 전개는 provenance 계약 결정이 먼저다.
- Revisit trigger: 공고 핵심 정보가 이 형식에만 있는 사례가 RAG에서 확인될 때, 또는 전체 corpus 전 coverage를 판단할 때
- Side effect: 새 route는 parse_key route 범위와 Contract·Test를 함께 바꾼다.
- Status: OPEN

## IMP-010 Parser 품질 한계(OCR·읽기 순서·그림 해석)

- Area: Parsing
- Issue: OCR 품질은 표본으로만 확인했고 오인식 사례가 있다. Docling layout의 읽기 순서 역전을 그대로 둔다. 그림·차트 내용은 해석하지 않는다(visual VLM 보류).
- Evidence: `2026-09-30-phase3-3c-corpus-parsing.md` §9, `2026-09-29-phase3-3b5-pp-production.md` §4 Visual 보류
- Why deferred: 100건에서 반복되는 구조적 parser blocker가 없었다. VLM 출력은 native source text가 아니라 production에서 보류했다.
- Revisit trigger: RAG 실패가 OCR 오인식·순서·그림 정보 때문에 반복될 때
- Side effect: parser 변경은 해당 route의 parse_key를 바꿔 재parsing·재indexing이 필요하다.
- Status: OPEN

## IMP-011 신청기간 파생 날짜가 적어 마감 필터 효과가 작음

- Area: MySQL 정형 후보
- Issue: `application_start_date`·`application_end_date`는 원문이 유효한 날짜 범위일 때만 파생된다. "예산 소진시까지"·"세부사업별 상이" 같은 원문은 날짜가 없어 `--not-closed-on` 필터가 마감 여부를 판정하지 못하고 남긴다.
- Evidence: dev support_programs 1,554건 중 951건이 파생 날짜 NULL이다. smoke(금융+소상공인+2026-09-30)에서 후보 67건 중 64건이 period_unknown이었다(`2026-09-30-phase6b-candidate-scoped-rag.md`). 자연어 "지금 신청 가능" 경로도 같은 결과였다(67 중 64, `2026-09-30-phase6c-natural-filter.md`).
- Why deferred: 원문 해석 규칙을 새로 만들지 않는다(근거 없는 정규화 금지). 모르는 기간은 제외하지 않는 쪽이 안전하다.
- Revisit trigger: "지금 신청 가능" 필터가 제품 요구로 확정될 때, 또는 자격 판단 단계에서 기간 판정이 필요할 때
- Side effect: 기간 원문 분류 규칙은 Structured 정규화 규칙·fingerprint 버전과 함께 결정해야 한다.
- Status: OPEN

## IMP-012 필터 추출 LLM이 질문에 없는 조건을 만들어냄

- Area: 자연어 정형 조건 추출
- Issue: qwen3.5:9b 추출 결과에 질문에 없던 조건이 들어간다. 허용 값 검증은 통과하는 bool·자유 문구라 application이 막지 못한다.
- Evidence: smoke A("…지금 신청 가능한 거")에서 unapplied_constraints에 질문에 없는 "서울/부산/경기도 지역"이 나왔다(추출 prompt 예시가 새어 나온 것으로 보임). smoke B("서울 지역…찾아줘")는 "지금"이 없는데 currently_open_requested=true라 날짜 필터가 적용됐다(후보 69→67)(`2026-09-30-phase6c-natural-filter.md`).
- Why deferred: 이번 작업은 prompt tuning loop를 하지 않는다. hard filter 오적용 영향이 작고(마감 확정 공고 2건 제외), 자유 문구는 표시용이다.
- Revisit trigger: 자연어 필터를 사용자 경로(API·UI)에 노출하기 전, 또는 작은 추출 Gold로 정확도를 측정할 때
- Side effect: 예시 제거·표현 규칙 강화·질문 원문 근거 검사(추출 값이 질문 표현에 근거하는지)는 추출 결과를 바꾸므로 같은 질문 세트로 전후를 비교해야 한다.
- Status: RESOLVED. hard filter는 질문 원문 근거가 있을 때만 적용한다(`2026-09-30-phase6d-discovery-list.md`).
  - category·target: 허용 값이면서 질문에 그 표현이 있어야 한다.
  - currently_open: 질문에 모집·현재 계열 표현이 있어야 한다.
  - 근거 없는 제안과 질문에 없는 unapplied 문구는 discarded 진단으로만 남는다.
  - 남은 한계(위험 아님): 보수적 guard라 "대출"→금융 같은 바꿔 말한 조건은 적용되지 않는다(recall 손실). request_mode 판정은 LLM이지만 후보를 바꾸지 않는다.

## IMP-013 Gold evidence가 chunk_id(chunk identity 의존)로 고정됨

- Area: Evaluation
- Issue: gold-v1의 expected_evidence는 chunk_id로 판정한다(`evals/retrieval/evaluate.py`). chunk identity가 바뀌면 chunk 경계가 같아도 모든 evidence가 miss로 계산된다.
- Evidence: IMP-001로 chunker_version 2가 되면서 3,849 point의 chunk_id가 모두 바뀌었다. source별 chunk 수는 100/100 같다. G01·G05 확인은 (source_sha256, chunk_index)로 했다(`2026-09-30-imp001-title-context.md`).
- Why deferred: 이번 작업은 IMP-001 확인 3건만 한다. Gold 동결 규칙상 gold-v1은 수정하지 않는다.
- Revisit trigger: 다음 Retrieval Evaluation 실행 전
- Side effect: (source_sha256, chunk_index) 판정은 chunk 경계가 같을 때만 유효하다. 경계가 바뀌면 새 gold 버전(gold-v2)이 필요하다.
- Status: RESOLVED(`2026-10-01-v1-code-closing.md`). `evals/retrieval/evaluate.py`가 근거를 (정답 문서 SHA, chunk_index)로 판정하고 결과에 `evidence_match`를 기록한다. Gold-v1은 수정하지 않았다. IMP-001은 embedding 입력만 바꿔 조각 경계가 같으므로 유효하다. 평가 재실행은 다음 작업(기준선 고정)에서 한다.

## IMP-014 SEARCH_LIST가 공고 5개를 채우지 못함(IMP-001 이후)

- Area: Discovery(SEARCH_LIST)
- Issue: 목록은 후보 scope hybrid 20 chunk를 공고 단위로 중복 제거한다. IMP-001로 embedding_text에 공고명이 들어간 뒤 상위 chunk가 소수 공고에 몰려 목록이 짧아졌다.
- Evidence: "소상공인 금융 지원사업 찾아줘"(후보 69, index 보유 7)의 목록 공고 수가 5개(`2026-09-30-phase6d-discovery-list.md`, 재적재 전)에서 2개(`2026-09-30-internal-api-v1.md`, HTTP smoke)로 줄었다.
- Why deferred: 이번 작업은 기존 서비스를 HTTP로 노출하는 것이다. discovery 설정(fetch_chunks 20)과 순위 방식은 바꾸지 않았다.
- Revisit trigger: SEARCH_LIST를 사용자 화면(Spring Boot·React)에 연결하기 전
- Side effect: fetch_chunks를 늘리면 latency가 는다. Qdrant group 검색(공고별 최고 chunk)으로 바꾸면 순위 규칙이 바뀌므로 discovery 계약과 test를 함께 고친다.
- Status: RESOLVED(`2026-10-01-imp014-discovery-diversity.md`).
  - 진단: 같은 후보에서 hybrid 상위 20 조각의 고유 공고 2개(한 공고가 18개 차지), 상위 50은 3개(39개 차지). 조각 절단 수를 늘리는 것만으로는 해결되지 않았다.
  - 해결: 목록은 의미·단어 검색마다 공고별 최고 조각 하나(Qdrant `query_points_groups`, group_size 1)로 공고 순위를 만들고 기존 RRF로 합친다. Qdrant 호출은 2회 그대로다.
  - 결과: 같은 질문에서 공고 2개 → 5개, 중복 0, 범위 밖 0, LLM 호출 1회. 원인이 공고명 context라는 가설은 통제 실험으로 확인하지 않았다(해결에는 불필요).

## IMP-015 Spring Boot 기본 Flyway가 MySQL 8.4를 "검증되지 않은 버전"으로 경고

- Area: Service backend / DB migration
- Issue: Spring Boot 3.5.16이 관리하는 Flyway 버전은 시작할 때 "MySQL 8.4 is newer than this version of Flyway and support has not been tested"를 경고한다. 공통 flyway 컨테이너(redgate/flyway:11)와 Spring 내장 Flyway의 버전이 다르다.
- Evidence: 서비스 V1 Compose 실행 backend log. 같은 history에서 V6 적용·validate는 정상이었다(`2026-10-01-service-v1-react-spring.md`).
- Why deferred: 동작 실패는 없고, Flyway 버전을 따로 올리면 Spring Boot가 관리하는 호환 조합을 벗어난다. V1 기능을 막지 않는다.
- Revisit trigger: AWS RDS 이전, Spring Boot 업그레이드, 또는 새 migration에서 Flyway 오류가 났을 때
- Side effect: Flyway 버전을 올리면 공통 flyway 컨테이너와 같은 history를 읽는지(checksum·validate) 함께 확인해야 한다.
- Status: OPEN

## IMP-016 refresh_tokens의 폐기·만료 row 정리 정책 없음

- Area: Service backend / 인증
- Issue: Refresh Token은 재발급·로그아웃 때 삭제하지 않고 `revoked_at`만 기록한다. 만료되거나 폐기된 row를 지우는 작업이 없어 로그인할 때마다 row가 쌓인다.
- Evidence: E2E 1회(가입 → 로그인 → 재발급 → 로그아웃)에서 한 사용자의 row가 3개(유효 1, 폐기 2)가 됐다(`2026-10-01-service-v1-react-spring.md`).
- Why deferred: 폐기 기록은 재사용된 토큰(탈취 신호)을 알아보는 근거라 바로 지우면 안 된다. V1 사용 규모에서는 문제가 없다.
- Revisit trigger: 운영 배포 전, 또는 refresh_tokens 크기가 조회 성능에 영향을 줄 때
- Side effect: 정리 주기는 Refresh Token 수명(14일)보다 길게 잡아야 재사용 탐지가 유지된다.
- Status: OPEN

## IMP-017 FastAPI가 Compose app profile에 포함되지 않음

- Area: Service infra / Docker Compose
- Issue: `docker compose --profile app`은 MySQL·Spring·React만 올린다. FastAPI는 호스트에서 `scripts/run_api.py`(127.0.0.1:8000)로 먼저 띄우고 Spring 컨테이너가 `host.docker.internal:8000`으로 호출한다.
- Evidence: FastAPI 컨테이너화에는 torch·paddle·docling 의존성 설치(수 GB 이미지), BGE-M3 등 3.7GB artifact read-only mount, Qdrant URL loopback 전용 규칙(`qdrant_url_not_loopback`)과 Ollama 주소 정책 변경이 필요했다. 사용자 결정으로 이번에는 호스트 FastAPI 연결로 기능을 먼저 완성했다(`2026-10-01-ai-e2e-v1.md`).
- Why deferred: 핵심 목표(Spring ↔ FastAPI 기능 연결)를 인프라 변경이 막지 않게 하고, Qdrant·모델 정책 변경은 따로 검토가 필요하다.
- Revisit trigger: 배포 환경 설계(AWS) 또는 한 명령 실행이 필요할 때
- Side effect: 컨테이너 안 Qdrant 주소(qdrant:6333) 허용은 기존 loopback 경계 규칙 변경이라 사용자 승인이 필요하다. 모델 artifact identity(해시)는 mount만 하고 바꾸지 않아야 한다.
- Status: OPEN

## IMP-018 V2 서비스 collection의 기준일 이후 종료 공고 정리

- Area: Indexing / 서비스 검색 범위
- Issue: V2 collection은 기준일(2026-10-01)에 종료되지 않은 공고 문서로 만든다. 그 뒤 신청기간이 끝난 공고의 point는 자동으로 빠지지 않는다.
- Evidence: 서비스 범위 계산은 실행 시점 `--as-of`로 한 번 정한다(`indexing/service_scope.py`, `2026-10-01-v2-0-foundation.md`). 검색 시점의 마감 제외는 질문에 "지금 신청 가능"이 있을 때만 MySQL 후보 필터가 한다.
- Why deferred: V2 개발·데모 기간(수일)에는 영향이 작고, 첫 적재를 끝내는 것이 먼저다.
- Revisit trigger: V2 collection 전환 후 주기적 갱신이 필요할 때 또는 운영 배포 전
- Side effect: 정리는 V2 collection에서만 한다. V1 collection은 baseline 재현용이라 대상이 아니다. MySQL·S3 원본은 지우지 않는다.
- Status: OPEN
