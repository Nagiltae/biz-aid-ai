# Improvement Backlog

실제로 관찰했지만 blocker가 아니어서 기능 진행을 위해 **의도적으로 미룬** 개선만 기록한다.
정상적인 다음 기능, 근거 없는 아이디어, 일반 리팩터링 욕구, 이미 해결된 일은 넣지 않는다. 운영 규칙은 [Workflow](workflow.md#improvement-backlog)에 있다.

- 형식: ID, Area, Issue, Evidence, Why deferred, Revisit trigger, Side effect, Status(OPEN / RESOLVED / DROPPED)
  - 한글 설명: Area(영역), Issue(문제), Evidence(근거·관찰 사례), Why deferred(지금 미룬 이유), Revisit trigger(다시 볼 시점),
    Side effect(고칠 때 주의할 영향), Status(상태: OPEN 미해결 · RESOLVED 해결 · DROPPED 가치 없어 폐기)
- 같은 문제는 새 ID를 만들지 않고 Evidence·Revisit만 갱신한다. 기존 ID를 다른 문제에 재사용하지 않는다. 해결·폐기 항목은 지우지 않고 Status와 근거 report를 남긴다.
- Evidence의 report는 `harness/workspace/reports/development/` 아래 파일이다.

## 단계 분류 (2026-10-01 V1 코드 마감)

| 단계 | 항목 | 기준 |
| --- | --- | --- |
| V1 마감 전 해결 | IMP-013(RESOLVED) | 다음 작업인 V1 AI 평가 기준선을 직접 막음 |
| V2에서 해결 | IMP-002, IMP-003, IMP-004, IMP-011, IMP-018, IMP-019, IMP-020(RESOLVED), IMP-024, IMP-025, IMP-026, IMP-027, IMP-028, IMP-029, IMP-030, IMP-031, IMP-032 | 답변·검색 품질 개선. 기준선 고정 뒤 비교해야 효과를 잴 수 있음 |
| 운영/AWS 단계 | IMP-005(RESOLVED), IMP-006, IMP-007, IMP-015, IMP-016, IMP-017(RESOLVED), IMP-021, IMP-022, IMP-023 | 배포 이미지·실행 환경·대량 처리·DB 운영 정책 |
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
- Revisit trigger: V2 service collection 전환과 같은 평가 입력을 준비한 뒤. V1은 완료됐지만 V2 전체 데이터 기준이 아직 없다.
- Side effect: 비교 조건을 같게 한다(Retriever, top_k 5, context, prompt, output schema). 볼 항목은 정답성, groundedness, citation 정확도, 확인 불가 판단, 표 이해, latency, API 비용이다. 원격 API는 공고 첨부 내용을 외부로 보낸다.
- Evidence(V2-0, 2026-10-01): 기업정보 field ID + enum 제한 뒤 같은 E01~E03 입력 1회씩 확인에서 계약 오류는 0/3이 됐다. 다만 E01은 값이 있는 조건에 모델이 UNKNOWN을 내 NEEDS_MORE_INFO(기대 ELIGIBLE)가 됐다. 형식 문제가 아니라 판정 품질 문제다(`2026-10-01-v2-0-foundation.md`).
- Status: OPEN. 출력 계약 오류는 줄었지만 provider·생성 완결성 비교는 수행하지 않았다.

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
- Resolution(2026-10-03, IMP-017과 함께): 계약 `model_artifacts.expected_scope_manifest_sha256`(chunking·embedding)을 추가하고, 질문 서버(ServiceRuntime의 BGE-M3)는 그 두 범위 파일만 검증한다(`verified_scope_artifacts_sha256`, `BgeM3Embedder(scope_only=True)`). 파싱 모델이 없어도 동작하며 전체 3.7GB를 hash하지 않는다(범위 검증 1.4초). 파싱·청킹·인덱싱 배치는 전체 manifest 검증 그대로다. embedding_key는 같다(테스트·실측 `228acdd12220`). 기록 `2026-10-03-fastapi-compose-imp017.md`.
- Status: RESOLVED

- 운영 준비 메모(2026-10-03): Spring `RegionCatalog`가 개발 Compose의 `/contracts` read-only mount에서 읽는 `contracts/`는 운영 이미지에도 포함하거나 동등하게 제공해야 한다. 개발 host bind mount에 의존해 배포하면 지역 목록·검증이 실패한다. 운영 이미지 빌드 시 같은 계약 파일이 포함되는지 검증한다(개발 구현/RESOLVED 이력을 운영 배포 완료로 해석하지 않음).

## IMP-006 현재 parse_key를 실행 환경에서 다시 계산

- Area: Chunking / Indexing
- Issue: chunking은 현재 parse_key를 실행 환경(paddle·docling 버전, HWP Docker 변환 이미지 identity)에서 다시 계산해 PARSED row를 찾는다. 그래서 indexing에도 parsing 환경이 필요하다. 같은 로직이 `parsing/corpus.py`와 `chunking/source.py`에 중복돼 있다.
- Evidence: `2026-09-30-pre-ai-service-cleanup.md` C·B-1(HWP 변환기 부재 시 실패 격리만 보강)
- Why deferred: 현재는 같은 머신에서 실행해 문제가 없다. B-1로 source 단위 실패 격리는 확보했다.
- Revisit trigger: indexing이나 서비스를 parsing 환경과 다른 곳에서 실행할 때, 또는 전체 corpus indexing 전
- Side effect: "최신 PARSED" 선택 규칙을 바꾸면 오래된 parser 결과를 쓰게 될 위험이 있어 identity 규칙과 함께 결정해야 한다.
- Evidence(V2 적재, 2026-10-02): HWP 3문서(32b2382125143427…, 3a1c386039528334…, afc8778b27ef…)가 모든 시도에서 `parse_result_key_mismatch`(EXECUTION_FAILED)였다. parse 결과의 parse_key와 저장 직전 실행 환경으로 다시 계산한 값이 달라 저장을 거부한 것이며 원인은 아직 확인하지 않았다(`2026-10-02-v2-data-completeness.md`).
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
- Evidence(V2 적재, 2026-10-02): 서비스 범위 2,541문서 batch가 AWS 로그인 만료로 2회 STOPPED_ENVIRONMENT, 실행 중 git 브랜치 전환(dev→main)으로 1회 중단(실행 중 코드·indexing script가 바뀜)됐고 같은 run-id 재개로 끝났다. 인덱싱 실측 2,534문서 274분(6.5s/source), 61,335 point(`2026-10-02-v2-data-completeness.md`).
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
- Evidence(전체 corpus 조사, 2026-10-02, 읽기 전용): 고유 파일 ZIP 144 / OTHER 107 / XLSX 50 / UNKNOWN 4(V2 범위 125 / 105 / 39 / 2). ZIP = 일반 압축 134 + DOCX 8 + PPTX 1 + ODT 1, OTHER = PNG 59 + JPEG 48(HTML 오류 페이지 0), UNKNOWN = XLS 2 + DOC 1 + HWPML 1. 일반 압축 내부 728개(HWP 357·PDF 141·HWPX 90·XLSX 36·이미지 23·자리표시 txt 48·HWPML 8 등, 암호화·한도 위반·위험 파일 0, CP949 이름 237, 단독 첨부와 같은 SHA 8). XLSX 보이는 셀 중앙값 114·p95 42,059·최대 84,118, 양식형 35/50. V2 범위에서 point가 없는 27공고는 전부 미지원 형식 첨부만 가진 공고(이미지만 19). 형식별 정리·XLSX 상한 후보는 `2026-10-02-imp009-unsupported-formats.md`.
- Evidence(1단계 공통 기반, 2026-10-02): 형식 판별 세분화(DOCX·PPTX·ODT·DOC·XLS·PPT·PNG·JPEG·HWPML), 새 route 정의(전부 비활성), XLSX 상한(보이는 셀 5,000·10MB·시트 20, 초과 시 문서 단위 실패), 출처 종류(document_role) 기록 규칙. 기존 PDF·HWP·HWPX·XLSX 판별 3,029관계와 parse_key·chunk_set_key·embedding_key 불변 확인. 기존 행 재분류 123관계(121파일)는 미리보기만 하고 미적용(`2026-10-02-unsupported-formats-foundation.md`).
- Evidence(2단계 이미지 OCR, 2026-10-02): 재분류 123관계 적용(COMMIT). IMAGE_OCR route 활성화(표본만 실행). 표본 3개 PARSED(포스터 8.6초·6.9초, 긴 캡처 44.7초), 타일 경계 중복 제거 후 위치 기준 누락 0(`2026-10-02-image-ocr-stage2.md`). 전체 실행은 승인 대기.
- Evidence(3단계 DOCX·PPTX, 2026-10-02): docling-slim format-docx·format-pptx extra 추가(python-docx 1.2.0·python-pptx 1.0.2·xlsxwriter 3.2.9, 기존 버전 변경 0), DOCLING_DOCX·DOCLING_PPTX 활성화(단독 첨부만, 표본만 실행), ODT는 7단계로 연기. 표본 3개 PARSED, DOCX 글자 XML 대비 99.6~100%(`2026-10-02-office-stage3.md`).
- Evidence(3단계 전체 실행, 2026-10-02): PPTX 위치를 EMU → pt로 맞춘 뒤 V2 범위 단독 DOCX 6·PPTX 1을 적재(7 PARSED·7 INDEXED·신규 58 point, 기존 point 변경 0). V2 범위 1,372공고 전부 point 보유. 남은 미지원: 일반 ZIP·XLSX·옛 오피스(ODT·DOC·XLS·PPT)·HWPML(`2026-10-02-office-stage3.md` §8).
- Decision(2026-10-02, 사용자): XLSX·DOC·XLS·PPT는 의도적으로 제외한다(단독·압축 안 모두). 근거: 내용이 빈 신청 양식·명단·참고표 위주이고, 이 형식만 가진 공고가 없어 미적재 공고를 구제하는 효과가 0이며, 검색 근거를 밀어낼 위험이 있다. 다시 볼 조건: 서류·양식 질문이 반복 실패할 때, 양식 중심 기능(신청서 작성 도우미 등)을 만들 때. 일반 ZIP 안에서는 `EXCLUDED intentionally_excluded_format`으로 상태만 남긴다(V2 미리보기 XLSX 23개).
- Evidence(4단계 일반 ZIP, 2026-10-02): 펼치기 구현·미리보기(쓰기 없음). V2 범위 117압축 → 내부 639개 중 처리 대상 539(고유 510), 단독 첨부 중복 7, 제외 93, 압축 거부 0. ODT 1개 공고는 같은 제목 HWPX·HWP가 V2에 적재돼 있음(95 point). 기록 `2026-10-02-generic-zip-stage4.md`.
- Evidence(4단계 승인 실행, 2026-10-02): V10 적용(dev·test, backend Flyway 11.7.2 validate 통과). 117압축 펼치기 → DB 639행·S3 새 object 510(미리보기와 같음). 표본 7 파싱(PARSED 5·OCR_REQUIRED 2, Qdrant 없음). document_role 확인: 무작위 FORM 15/15가 실제 양식, "제출서류" 단서 오판 3. 전체 범위 A(510)/B(FORM 제외 191) 결정 대기(`2026-10-02-generic-zip-stage4.md` §9).
- Decision(2026-10-03, 사용자): 일반 ZIP 내부 파일은 범위 B로 적재한다. FORM(새 규칙 기준 323)은 S3 원본·DB 행으로 보관만 하고 파싱·적재하지 않는다. 다만 3단계 DOCX의 FORM 27 point는 이미 V2에 적재돼 있다. cases-v2에서 FORM 검색 제외 필터를 만들 때 그 27 point와 ZIP 내부 FORM 적재 여부를 함께 정한다. 같은 날 document_role 규칙도 개정했다("제출서류"는 안내·기준 → BODY, 목록·체크리스트 → LIST, 단독은 단서 아님 / FORM 단서 결과보고서·상세서·조사서·프로필 추가).
- Evidence(4단계 전체 실행 B, 2026-10-03): FORM이 아닌 187원본 파싱(170 PARSED·17 OCR_REQUIRED, 실패 0) → 신규 11,891 point(기존 point 변경 0). V2 2,816문서·73,430 point. 대형 참고자료 비중 문제는 IMP-028(`2026-10-02-generic-zip-stage4.md` §10).
- Status: OPEN

## IMP-010 Parser 품질 한계(OCR·읽기 순서·그림 해석)

- Area: Parsing
- Issue: OCR 품질은 표본으로만 확인했고 오인식 사례가 있다. Docling layout의 읽기 순서 역전을 그대로 둔다. 그림·차트 내용은 해석하지 않는다(visual VLM 보류).
- Evidence: `2026-09-30-phase3-3c-corpus-parsing.md` §9, `2026-09-29-phase3-3b5-pp-production.md` §4 Visual 보류
- Why deferred: 100건에서 반복되는 구조적 parser blocker가 없었다. VLM 출력은 native source text가 아니라 production에서 보류했다.
- Revisit trigger: RAG 실패가 OCR 오인식·순서·그림 정보 때문에 반복될 때
- Side effect: parser 변경은 해당 route의 parse_key를 바꿔 재parsing·재indexing이 필요하다.
- Evidence(V2 적재, 2026-10-02): 2,541문서 중 파싱 제외 4문서 — PDF 1(19ee2419ecd3…, docling_conversion_failed), HWPX 1(bcd40262462d…, malformed_xml), HWP 2(69d0e4d1c39c…, b86308ea8ac0…, OCR_REQUIRED). 각 공고는 다른 첨부 문서로 V2 collection에 남아 있다(`2026-10-02-v2-data-completeness.md`).
- Evidence(이미지 OCR 표본, 2026-10-02): 신뢰도 기준이 PDF와 같은 0.0이라 로고·장식에서 나온 한 글자 잡음 줄(예: "o" 0.34, ">" 0.31, "0" 0.14)이 본문에 남는다. 포스터 제목 글꼴에서 "청년일자리"→"첨년일자리", "장려금"→"장리금" 같은 오인식이 보였다(`2026-10-02-image-ocr-stage2.md`).
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
- Resolution(2026-10-03, 사용자 결정): FastAPI를 질문 처리 전용 이미지(`data-pipeline/Dockerfile`, `requirements-api.txt`, CPU torch 2.14.0, 파싱 의존성 없음, 1.91GB)로 만들어 Compose app profile의 `fastapi`로 넣었다. 코드·계약·모델 artifact는 읽기 전용 mount, `uvicorn --reload`로 코드 변경 시 자동 재시작, Qdrant는 `http://qdrant:6333`만 추가 허용(규칙 변경), Ollama는 host, Spring은 `http://fastapi:8000`. 조작은 `scripts/dev.sh`. host와 컨테이너의 검색 순위(3질문×3모드 상위 10)와 API 응답(3질문 전체 body)이 같다. 기록 `2026-10-03-fastapi-compose-imp017.md`.
- Status: RESOLVED

## IMP-018 V2 서비스 collection의 기준일 이후 종료 공고 정리

- Area: Indexing / 서비스 검색 범위
- Issue: V2 collection은 기준일(2026-10-01)에 종료되지 않은 공고 문서로 만든다. 그 뒤 신청기간이 끝난 공고의 point는 자동으로 빠지지 않는다.
- Evidence: 서비스 범위 계산은 실행 시점 `--as-of`로 한 번 정한다(`indexing/service_scope.py`, `2026-10-01-v2-0-foundation.md`). 검색 시점의 마감 제외는 질문에 "지금 신청 가능"이 있을 때만 MySQL 후보 필터가 한다.
- Why deferred: V2 개발·데모 기간(수일)에는 영향이 작고, 첫 적재를 끝내는 것이 먼저다.
- Revisit trigger: V2 collection 전환 후 주기적 갱신이 필요할 때 또는 운영 배포 전
- Side effect: 정리는 V2 collection에서만 한다. V1 collection은 baseline 재현용이라 대상이 아니다. MySQL·S3 원본은 지우지 않는다.
- Evidence(V2 적재 현황, 2026-10-02): V2 collection point의 공고 중 현재 CLOSED가 17공고·1,719 point다. 13공고(1,115 point)는 기준일 2026-10-01에 마감된 공고다. 4공고(604 point)는 기준일 전(09-30)에 마감돼 범위 밖인데, 범위 안 공고와 같은 첨부 문서를 공유해 indexing이 공고 relation마다 point를 만들면서 들어왔다. V2 개인화 검색은 MySQL 후보 단계에서 요청일 기준 마감 공고를 빼므로(`exclude_closed_on`) 이 point를 결과로 내지 않는다. V1 경로(`/api/ai/query`)는 "지금" 표현이 없으면 마감 공고를 빼지 않는 기존 동작 그대로다. 정리는 하지 않았다(`2026-10-02-v2-data-completeness.md`).
- Status: OPEN

## IMP-019 개인화 검색에서 기업정보는 후보 필터에만 쓰이고 순위에는 반영되지 않음

- Area: Discovery(V2 개인화 검색)
- Issue: 기업정보는 승인된 매핑(기업규모 → 지원대상)으로 후보만 줄이고, Top 3 순위는 질문 문장만으로 정한다. 기업규모 필터는 인증 대상 공고만 빼므로 후보가 크게 줄지 않는다.
- Evidence: V2-1 Smoke(소상공인·영업중·경기도·2024 개업, "우리 회사가 지금 신청할 수 있는 지원사업 찾아줘")에서 후보 1,237개, 지역·업력은 unapplied였다(`2026-10-01-v2-1-personalized-search.md`).
- Why deferred: 순위에 기업정보를 넣는 방법(검색 문장 보강, 가중치)은 품질 평가 기준(cases-v2)과 V2 collection 적재 완료 뒤에 비교해야 한다. 이번 범위는 흐름 구현이다.
- Revisit trigger: V2 collection 전환과 cases-v2 작성 뒤
- Side effect: 현재 승인된 기업 지역 기반 소관기관 제외 예외만 적용한다(AI 경계). 소관기관은 신청 가능 지역의 대리 지표라 여러 지역 대상 공고를 조용히 제외할 수 있다(IMP-030). 질문 지역 추출·검색 문장·순위 변경은 별도 비교/승인 대상이다.
- Partial resolution(2026-10-03, 사용자 결정·규칙 변경): 지역 부분을 반영했다. 기업 지역을 광역 지자체 16개 표준명 중에서 고르고(전남광주통합특별시는 하나), 맞춤 추천 후보에서 다른 광역 지자체 소관 공고만 뺀다(중앙부처·매핑 없는 소관기관 유지, `company-region` 계약). 경기도 중소기업·금융 질문의 후보는 145 → 43이다. 기록 `2026-10-03-company-region-filter.md`.
- Follow-up: 중앙부처 소관이면서 공고명에 지역 표기([전북]·[대전] 등)가 있는 공고는 이번에 유지한다. 2026-10-03 기준 마감이 확정되지 않은 중앙부처 공고 384건 중 63건(16%)이다(경북 8·경남 7·전북 6·충북·서울·부산·대구 각 5). 지역 한정 여부는 공고문을 봐야 해서 후속 후보로 둔다.
- Remaining(2026-10-03 사용자 결정 나): 질문 지역은 Natural Filter에서 정형 조건으로 추출하지 않고 서버의 unapplied 조건 그대로 화면에 눈에 띄게 알린다. 기업 지역과 중앙부처·매핑 없는 소관기관을 기준으로 찾았다는 안내와 기업정보 수정 링크를 제공한다. 별도 지역 키워드 추출은 하지 않는다. 근본 해결(질문 지역의 정형 추출)은 IMP-012·IMP-024와 함께 cases-v2로 변경 전후를 비교한 뒤 처리한다. 후속 후보 필터 결정(2026-10-03): MySQL 소관기관 필터 유지. 질문 지역 unapplied 결정 나와 별개다. 경기도 기준 종료 미확정1,314건 중 다른 광역812건(61.8%)을 다시 넣는 비용과 Top3 부적합 위험을 고려했다. [측정 Report](../workspace/reports/development/2026-10-03-region-filter-measurement.md)의 지자체 표본 관내30/40(75%)·명시적 누락4/40(10%)은 모집단 오류율 추정이 아니며 누락은 IMP-031 후속으로 복구한다. 순위 반영은 OPEN이다.
- Status: OPEN

## IMP-020 Top 3 자격 판정 전체 응답이 Spring 응답 제한시간을 넘음

- Area: V2 개인화 판정 / 서비스 응답 시간
- Issue: 개인화 검색과 공고 3개 판정을 한 요청에서 순차로 한다. 로컬 Qwen 판정이 공고당 30~60초라 전체가 Spring AI 응답 제한시간(90초)을 넘는다. 그대로 화면에서 부르면 504 ai_service_timeout이 된다.
- Evidence: V2-2 실제 Smoke 1회(V1 collection, 같은 기기에서 V2 batch 파싱 동시 실행): 총 161.0초, 판정 LLM 58.1·53.6·33.4초(`2026-10-01-v2-2-top3-eligibility.md`).
- Why deferred: 지시에 따라 제한시간을 몰래 늘리거나 비동기 작업 큐를 새로 만들지 않았다. 기능 구조(조합·격리)를 먼저 완성했다.
- Revisit trigger: LangGraph 단계와 진행 상태 UI 설계(공고별 단계 실행·진행 표시) 때
- Side effect: 제한시간만 늘리면 Spring 요청 스레드가 3분 가까이 묶인다. 단계별 상태 저장이나 공고별 요청 분리와 함께 결정해야 한다.
- Status: RESOLVED(`2026-10-01-v2-3-langgraph-workflow.md`). LangGraph 단계 실행으로 한 요청의 판정 LLM 호출을 최대 1건으로 나눴다. 실제 측정: 시작(검색·Top 3) 14.7초, 다음 단계(판정 1건) 39.4초로 모두 Spring 90초 안이다. 제한시간은 늘리지 않았다.

## IMP-021 ai_workflows 보관·정리와 중단된 단계 처리

- Area: Service backend / AI 흐름 상태
- Issue: 흐름 State(실측 약 12.7KB/건)는 완료 뒤에도 지우지 않는다. 단계 실행 중 서버가 죽으면 점유(step_started_at)가 남고, 5분이 지나야 다시 진행할 수 있다.
- Evidence: V2-3 Smoke workflow 1건 state_json 12,723 bytes. 점유는 5분 경과 시 재점유하고, 늦게 끝난 이전 요청은 version 불일치로 저장을 거부한다(`2026-10-01-v2-3-langgraph-workflow.md`).
- Why deferred: V2 데모 규모에서는 문제가 없고, 보관 기간은 운영 정책(개인정보·감사)과 함께 정해야 한다.
- Revisit trigger: 운영 배포 전 또는 ai_workflows 크기가 커질 때
- Side effect: 정리할 때 진행 중(IN_PROGRESS·WAITING_FOR_USER) 흐름은 지우면 안 된다.
- Status: OPEN

## IMP-022 activity_logs.target_type COMMENT에 WORKFLOW 누락

- Area: DB 문서(COMMENT)
- Issue: V8 `activity_logs.target_type` COMMENT는 USER·COMPANY·CONVERSATION·PROGRAM만 적혀 있는데, V2-3부터 workflow 활동 로그가 `WORKFLOW`를 쓴다.
- Evidence: `RecommendationWorkflowService`의 activityLog 호출. 이미 적용된 V8은 수정할 수 없어 새 migration(COMMENT 변경)이 필요하다(`2026-10-01-v2-4-final-result.md`).
- Why deferred: 동작에는 영향이 없고 이번 범위(최종 결과 계약)가 아니다.
- Revisit trigger: 다음 Spring migration을 추가할 때 함께 처리
- Side effect: 없음(COMMENT만)
- Status: OPEN

## IMP-023 실행 추적 범위가 V2 workflow 경로뿐

- Area: AI 관측(LangSmith)
- Issue: V2-6 추적은 `/internal/v2/workflows/{start,advance}`만 기록한다. V1 `/internal/v1/query`·단일 판정, V2-1·V2-2 단독 endpoint는 추적하지 않는다. LangSmith SDK 자체 경고 로그(전송 실패 시 trace id 목록)는 SDK logger로 따로 남는다(키·내용 없음 확인).
- Evidence: `2026-10-01-v2-6-langsmith-tracing.md`. 사용자는 `.env.dev`의 LangSmith API key와 `BIZAID_TRACING_ENABLED=true` 설정을 완료했고, 진단 중 잘못 생성됐던 `biz_aid` 프로젝트를 삭제했다. 이 정리는 추적 범위 자체를 넓히지는 않는다.
- Why deferred: 사용자 흐름은 V2 workflow로 옮겨 가고 있고, 같은 `traced` 감싸기로 필요할 때 추가할 수 있다.
- Revisit trigger: V1 화면 사용량이 많거나 V1 경로 성능 분석이 필요할 때
- Side effect: 추가할 때도 같은 형식 검사·자동 추적 off 범위를 지켜야 한다.
- Status: OPEN

## IMP-024 질문 유형(request_mode)이 LLM 판단만으로 정해짐

- Area: AI 질문 처리(V1 AI 검색)
- Issue: SEARCH_LIST·DOCUMENT_QA 분류를 `candidates/natural.py`의 LLM 출력이 정하고, 코드는 두 값 중 하나인지만 검사한다. 특정 공고의 내용을 묻는 질문이 목록 검색으로 분류될 수 있다.
- Evidence: 화면 확인(2026-10-02)에서 "청년일자리도약장려금 지원 대상 알려줘", "2026년 청년일자리 도약장려금 참여기업 모집 공고의 지원 대상 알려줘"가 둘 다 DOCUMENT_QA가 아니라 SEARCH_LIST로 분류됐다(후보 1,554건). 기록: `2026-10-02-office-stage3.md`.
- Why deferred: 분류 보정 방식(규칙 보조·예시·재질문)은 평가 질문과 기대값이 있어야 비교할 수 있다. 이번 단계(DOCX·PPTX)는 범위가 다르다.
- Revisit trigger: cases-v2 작성 시(분류 보정 + 공고 선택 방식 비교)
- Side effect: 분류를 바꾸면 SEARCH_LIST(목록) 질문의 동작도 함께 바뀐다. IMP-025(공고 선택)와 함께 본다.
- Status: OPEN

## IMP-025 이름이 비슷한 공고 중 특정 공고를 고르는 단계가 없음

- Area: AI 질문 처리(DOCUMENT_QA 근거 범위)
- Issue: DOCUMENT_QA는 MySQL 후보 전체 안에서 상위 조각을 검색해 답한다. 질문이 특정 공고를 가리켜도 그 공고 하나를 고르는 단계가 없어, 제목이 거의 같은 여러 공고(서울·충북·경기 등, 같은 제목의 [충북] 공고 2개)의 근거가 한 답변에 섞일 수 있다.
- Evidence: 화면 확인(2026-10-02)의 청년일자리도약장려금 질문. `rag/service.py`는 후보 범위(pblanc_ids) 안에서 top_k를 고르며 공고 단위 선택을 하지 않는다. 기록: `2026-10-02-office-stage3.md`.
- Why deferred: 공고 선택 방식(제목 일치 우선, 후보가 여럿이면 되묻기, 근거 공고 하나로 제한 등)은 cases-v2 기대값으로 비교해야 한다.
- Revisit trigger: cases-v2 작성 시(분류 보정 + 공고 선택 방식 비교)
- Side effect: 공고를 하나로 좁히면 여러 공고 비교 질문의 답이 달라진다. 근거 공고 격리 규칙(자격 판정)과 같은 원칙을 쓸지 함께 정한다.
- Status: OPEN

## IMP-026 Office 설정 hash가 계약 설명 문구까지 포함함

- Area: 문서 파싱 식별값(DOCLING_DOCX·DOCLING_PPTX parse_key)
- Issue: `office_config_sha256`이 계약 `office` 구역 전체를 hash한다. 이 구역에는 실행 설정뿐 아니라 설명 문구(converter·pages·location 등 영어 설명)가 들어 있어, 결과에 영향이 없는 문구 수정만으로 DOCX·PPTX parse_key가 바뀌고 재파싱 대상이 된다.
- Evidence: 3단계 PPTX 위치 단위 수정 때 `office.pages` 설명만 고쳤는데 DOCX·PPTX parse_key가 새 값이 됐다(그때는 저장된 결과가 없어 영향 없음, `2026-10-02-office-stage3.md` §8). 지금은 V2에 DOCX·PPTX 7원본·58 point가 있어 같은 수정이 재파싱을 부른다.
- Why deferred: 지금 고치면 그 자체가 hash 입력을 바꿔 적재된 7원본의 parse_key가 바뀐다. 사용자 결정으로 이번에는 기록만 한다.
- Revisit trigger: Office 설정을 바꿀 때(결과에 영향을 주는 값만 hash하는 구역으로 분리 — 예: `office.identity`)
- Side effect: 분리하는 순간 DOCX·PPTX parse_key가 한 번 바뀌므로 7원본 재파싱·재적재가 함께 필요하다. `image_ocr_config_sha256`도 `image_ocr` 구역 전체(설명 문구 engine·tiling·acceptance·value_basis 등 포함)를 hash하는 같은 구조라 IMAGE_OCR 105원본에도 같은 위험이 있다. 함께 정한다.
- Status: OPEN

## IMP-027 document_role BODY 단서 "지침"이 내부 운영 규정까지 본문으로 판정함

- Area: 조각 출처 종류(document_role) 판정
- Issue: BODY 단서 "지침"이 사업 지침(지원 대상·절차)뿐 아니라 신청자와 무관한 내부 운영 규정(예: 평가위원 수당지급 지침)도 BODY로 만든다.
- Evidence: 4단계 일반 ZIP 판정 확인(2026-10-02) 무작위 BODY 5개 중 "첨부 3. 대구테크노파크 전문가 수당지급 지침.hwp"(회의수당 지급 기준표)가 BODY로 판정됐다. 기록 `2026-10-02-generic-zip-stage4.md` §9.
- Why deferred: 한 건이고 내용이 짧아 검색 근거를 밀어낼 위험이 작다. 사용자 결정으로 기록만 한다.
- Revisit trigger: cases-v2에서 document_role을 검색 필터·가중치에 쓰기로 정할 때
- Side effect: "지침"을 빼면 실제 사업 지침 문서(관리지침·운영지침)가 UNKNOWN이 된다. 예외 단어(수당·위원·내부) 방식과 비교해야 한다.
- Status: OPEN

## IMP-028 ZIP 내부 대형 참고자료가 일부 공고의 검색 근거를 대부분 차지함

- Area: V2 검색 근거(Qdrant V2 collection, 일반 ZIP 내부 파일)
- Issue: 일반 ZIP 안의 참고 해설서·가이드북·매뉴얼은 공고 본문이 아니지만 쪽수가 많아 point가 매우 많다. 이 파일들은 FORM이 아니라 UNKNOWN으로 판정돼 범위 B에서도 적재됐다. 공고별 검색(DOCUMENT_QA·자격 판정 근거)은 후보 공고 안에서 상위 조각을 고르므로, 해당 공고에서는 본문 조각이 참고자료 조각에 밀릴 수 있다.
- Evidence(2026-10-03):
  - 새 point 11,891 중 9,449(79%)가 이름에 참고·해설서·가이드·매뉴얼·분류가 들어간 45원본에서 나왔다. point 500개를 넘는 원본 6개가 6,892 point다
  - 예: 「한국표준산업분류 제11차 개정 해설서」 1,011쪽 3,458 point → PBLN_000000000125978 공고의 3,963 point 중 3,936(99%)이 ZIP 내부 파일
  - 「국가과학기술표준분류체계 해설서」 407쪽 1,048 point(공고 2개)
  - 새 문서가 생긴 58공고 중 34곳에서 새 point가 공고 point의 절반을 넘는다
  - 기록 `2026-10-02-generic-zip-stage4.md` §10
- Why deferred: 사용자 지시로 기존 point와 이번 적재 point를 바꾸거나 지우지 않았다. 처리 방식은 사용자 결정이 필요하다.
- Revisit trigger: 지금(서비스가 V2를 읽음). 늦어도 cases-v2 작성 전
- 선택지
  - (a) 참고자료 원본의 point만 source_sha256으로 지우고 파싱 결과는 보관한다(언제든 다시 적재 가능)
  - (b) 원본당 point 상한(예: 200)을 넘는 원본은 적재하지 않는다
  - (c) document_role에 REFERENCE를 추가하거나 "참고·해설서·가이드·매뉴얼"을 단서로 써서 FORM과 같이 보관만 한다
  - (d) 그대로 두고 cases-v2에서 공고별 근거 순위를 비교한 뒤 정한다
- Side effect: (a)(b)는 이미 적재된 point 삭제라 사용자 승인이 필요하다. 참고자료에도 업종 코드 확인 같은 실제 답 근거가 있어 완전 제외는 일부 질문의 답을 잃는다.
- Decision(2026-10-03, 사용자): 선택지 a. 참고자료 45원본(9,449 point)의 V2 point만 source_sha256 필터로 삭제했다. 파싱 결과(MySQL)·S3 artifact는 보관한다. REFERENCE 판정(c)은 하지 않는다
  - 삭제 목록: `data/parsed/v2-zip-member-scope/2026-10-03/imp028-deleted-sources.txt`, 상세 `harness/workspace/artifacts/development/generic-zip-stage4/imp028-targets.json`
  - 되돌리기: `run_corpus_indexing.py --profile dev --run-id <새 run-id> --sources-file <해당 SHA 목록> --collection-namespace v2 --parsed-only`(재파싱 없이 보관된 artifact로 재적재)
  - 다시 적재할 때는 `index-sources-after-imp028.txt`를 쓴다(처음 125, 복원 뒤 130)
  - 결과: V2 63,981 point·2,771원본, 나머지 point·V1 변경 0, point 없는 공고 0. 기록 `2026-10-02-generic-zip-stage4.md` §11
- Follow-up(2026-10-03, 사용자): 삭제한 45원본 중 공고 본문 성격의 짧은 안내문 5원본(60 point)을 보관된 파싱 결과로 다시 적재했다
  - 복원: 기술료 납부 안내문, 연구개발과제 접수 전 필수 이행 사항, 직무발명보상 인센티브 활용안내, 제3자 부당개입 주의 안내문, 일터혁신 지원분야 세부내용
  - 삭제 전과 같은 point ID·hash 60/60
  - 지금도 제외: 40원본(`imp028-still-excluded-sources.txt`). 재적재 목록은 `index-sources-after-imp028.txt`(130)
  - V2 64,041 point·2,776원본. 고른 이유는 Report §11 후속에 있다
- Remaining: 재발 방지(REFERENCE 판정, 원본당 point 상한 등)는 미정이다. 다음 형식(XLSX 등)이나 ZIP 재적재 전에 정한다.
- Status: OPEN(45원본 point 삭제로 현재 영향은 해소, 재발 방지 미정)

## IMP-029 일부 공고에서 자격 판정 criteria를 지나치게 쪼개거나 반복 생성함

- Area: 자격 판정(eligibility) LLM 출력
- Issue: 지역산업위기대응 이차보전·인천 특별 경영안정자금 같은 공고에서 모델이 제출 서류·완화 규정까지 criterion으로 나열하거나 같은 조건을 반복한다. 2026-10-03 최초 안전장치에서는 출력 상한(criteria 12개·출력 1,024 token)에 닿으면 판정하지 않고 `eligibility_output_limit_reached`로 실패시키므로 시간 초과·과열은 막지만, 그 공고는 판정 결과가 없다.
- Evidence(2026-10-03, qwen3.5:9b):
  - PBLN_000000000123260: 5,000 token 동안 67개, 고유 13개(중복 54), 37개가 서류 관련
  - PBLN_000000000117611: 37개 1,735 token 97초
  - 정상 공고: 2·8·10개
  - 수정 뒤 두 공고는 52.5초·31.4초에 `eligibility_output_limit_reached`
  - 입력 근거 길이는 원인이 아니다(prompt 2,315~3,252 token, chunk 96~1,556자)
  - 기록 `2026-10-03-recommend-timeout-diagnosis.md`
- Follow-up(2026-10-03 사용자 승인): 비교 실험 없이 prompt에 서류/절차/작성 항목 제외·중복 금지·관련 조건 묶기(보통2~8)를 추가하고 상한15개/1280token으로 변경했다. 잘린 출력·15개 도달 실패 및75초 기한은 유지한다. [후속 Report](../workspace/reports/development/2026-10-03-region-wrapup-and-imp029.md)에 같은 입력 workflow1회 결과를 기록한다.
- Why deferred: corpus 전체에서 반복/과분할이 사라졌다고 단정하지 않는다. 사용자 요청대로 이번에는 비교 실험을 생략하고 좁은 기능 수정·workflow 확인만 한다.
- Evidence(후속 workflow1회): 동일 질문·저장된 기업 snapshot에서 126190 COMPLETED/NEEDS_MORE_INFO(6조건,37.42초), 117611 COMPLETED/NEEDS_MORE_INFO(7조건,49.95초). 123260은 상한 대신 eligibility_invalid_evidence_id로 FAILED(39.38초). Top3 처리 완료·WAITING_FOR_USER이며 모든 HTTP 단계90초 미만. IMP-029는 아직 부분 해결이다.
- Revisit trigger: 배포 시 이 실패를 화면에서 명시하고, 별도 승인된 123260 근거 ID 출력 원인 검토 또는 cases-v2 판정 기대값 비교 시
- Side effect: prompt를 바꾸면 기존 정상 공고의 criterion 수·결과도 달라질 수 있다. criteria 상한(12)도 함께 다시 정한다.
- Status: OPEN

## IMP-030 여러 지역 대상인데 소관이 한 광역인 공고가 다른 지역 기업 후보에서 빠짐

- Area: V2 맞춤 추천 후보(기업 지역 필터)
- Issue: 기업 지역 필터는 소관기관(jurisdiction_name)이 다른 광역 지자체인 공고를 뺀다. 여러 지역을 함께 대상으로 하는 공고도 소관이 한 광역이면 나머지 지역 기업의 후보에서 빠진다.
- Evidence: 2026-10-03 기준 1건. `[부산ㆍ울산ㆍ경남] 2026년 동남 정보보호클러스터 보안 테스팅 지원사업 공고`는 소관이 경상남도라서 부산·울산 기업에서는 후보가 아니다. 기록 `2026-10-03-company-region-filter.md`.
- Evidence(추가): [지역 측정 Report](../workspace/reports/development/2026-10-03-region-filter-measurement.md)에서 명시적 누락4/40(지역 허용3+소관 오류1), 원문 지역 조건 없음3·근거 부족3.
- Why deferred: 2026-10-03 사용자 결정으로 소관기관 필터는 유지한다. 신청 가능 지역 추출은 IMP-031에서 조건·근거를 보존해 후속 비교한다.
- Revisit trigger: 이런 공고가 늘거나 사용자 문의가 생길 때, 또는 IMP-019 후속(중앙부처 공고의 지역 표기)을 정할 때
- Side effect: 공고명 지역 표기를 대상 지역으로 쓰면 중앙부처 공고 63건의 처리와 같은 규칙으로 정해야 한다.
- Status: OPEN

## IMP-031 공고별 신청 가능 지역 추출

- Area: 맞춤 추천 / 자격 근거
- Issue: 소관기관은 기업의 신청 가능 지역을 보장하지 않는다. 현행 후보 hard filter 유지 결정과 누락 복구는 별개다.
- Evidence: [지역 측정 Report](../workspace/reports/development/2026-10-03-region-filter-measurement.md), 지자체 표본 명시적 누락4/40(10%).
- Follow-up: NATIONWIDE / REGION_LIST / UNKNOWN과 원문 evidence·source SHA·parse key·page/chunk를 보존해 공고 단위로 추출한다. 이전 예정·복수 사업장·수요/공급 기업 역할 등 조건을 단순 시·도 목록으로 잃지 않는다. 근거 부족은 UNKNOWN이다.
- Why deferred: 내일 배포 범위에서 제외. 현재 소관기관 필터를 유지하면서 cases-v2로 전후 비교 후 처리한다.
- Revisit trigger: 배포 후 지역 누락 복구 Task 승인 시. 입력·출력 비용 가정은 측정 Report에 있으며 실제 LLM 추출 비용은 미측정이다.
- Side effect: 신규 DB/계약·적재/근거검증 경계와 사용자 승인 필요. 기존 source_payload·fingerprint·검색 identity 보존.
- Status: OPEN

## IMP-032 공고 소관기관과 실제 신청 대상 지역 불일치

- Area: 원본 API metadata 데이터 품질
- Issue: PBLN_000000000124890은 대구 소관·대구 제목이지만 실제 공고 자격은 대전 유성구에 영업신고한 사업자이다. 소관기관 기반 필터가 적격 대전 기업에게 숨길 수 있다.
- Evidence: [지역 측정 Report](../workspace/reports/development/2026-10-03-region-filter-measurement.md) 표본13, 원문 “유성구에 영업신고한 상시근로자 5인 미만 사업자”.
- Why deferred: 원본을 임의 정정하지 않고 데이터 품질 관찰로 보존한다. 이번에 filter/DB source를 변경하지 않는다.
- Revisit trigger: IMP-031 근거 기반 지역 추출 또는 원본 공급자 확인 Task.
- Side effect: source 원문과 별도의 검증 결과를 구분해야 한다.
- Status: OPEN
