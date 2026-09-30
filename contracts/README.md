# Boundary Contracts

활성 계약은 Phase 0 로컬 기록·외부 API Raw 응답부터 Phase 4 Chunking·Indexing까지 단계별 로컬 계약이다.

- [Raw snapshot](schemas/raw-snapshot.contract.json): byte 보존 metadata.
- [Phase 0 report](schemas/phase0-report.contract.json): 측정 상태·분모·증거·판단 기록.
- [기업마당 API](external-api/README.md): 사용자 확인 Request·실제 Sample·관찰 타입·명시적인 Local Probe.
- [Frontend / Backend 경계](frontend-backend/README.md), [Backend / AI 경계](backend-ai/README.md): 미구현.

*.contract.json은 이 프로젝트의 로컬 계약 설정이며 JSON Schema 표준을 구현한 파일이 아니다.
scripts/phase0.py가 로컬 기록의 엄격한 key / type / 상태 / 의미 검증을 수행한다.
scripts/bizinfo_probe.py는 Sample 기반 Raw 계약을 검사하고 unknown field를 보존한다.
Rate와 주요 필드 Null 비율은 0..1, 확장자 분포는 파일 건수로 기록한다.
분모·표본·제외 기준의 실제 적합성은 보고서 증거와 Human review로 확인한다.
새 field는 계약·도구·테스트·문서를 함께 변경한다.
미확인 외부 Request / Response를 이 계약에서 추정하지 않는다.
현재 도구 계약은 Gate pending만 허용한다. 실제 Gate 최종 GO / DROP은
측정 후 Markdown 보고서와 사용자 검토로 기록하며 기계 기록 확장은 별도 계약 변경이다.

## Gate 판단 계약 확장 절차

현재 gate_decisions=["pending"]을 유지한다. AGY Harness Review 완료는 Data Gate GO가 아니다.

1. 승인된 별도 Phase 0 Task에서 실제 측정을 완료하고 분자·분모·표본·예외·미측정 항목을 기록한다.
2. 원문 checksum, 다운로드 / Parsing 결과, API 대비 추가정보, RAG 가치의 Evidence를 검토한다.
3. 사용자가 측정 결과와 판단 근거를 Human Review하고 계약 변경 범위 및 기록할 판단을 승인한다.
4. 별도 Contract 변경 Task를 current-task에 정의한다. Codex는 승인된 범위만 구현한다.
5. gate_decisions 확장과 근거·검토자 필드·미측정 처리·기존 pending 기록 호환성을 함께 정의한다.
6. go/drop의 정상 기록 및 미측정·근거 없음·승인 없음의 거부 Tests, 관련 Docs를 수정한다.
7. check-contract, 관련 check-integration, check-harness, check-all을 실제 실행한다.
8. 변경 이유·독립 Evidence·사용자 판단·Validation 결과를 Report / Changelog에 기록하고 Diff로 검토한다.

이번 API 품질 측정은 일부 지표만 다룬다. 전체 Gate 측정과 최종 판단은 별도 승인 Task에서 수행한다.
Codex는 자동으로 GO/DROP을 결정하거나 숫자 임계값 통과만으로 승인 상태를 생성할 수 없다.
계약 확장은 사람의 판단을 기록할 방법을 만드는 것이며 그 자체가 Gate 통과를 뜻하지 않는다.

[API 품질 계약](schemas/phase0-api-quality.contract.json)은 승인된 dev 5×20 표본·상태·분모의 로컬 설정이다.
scripts/phase0_api_quality.py가 Run / Raw checksum에서 품질 요약을 재현한다. 의미·URL 접속·문서 Gate는 미측정이고 pending-only Gate 계약은 유지한다.

[Document Download 계약](schemas/phase0-document-download.contract.json)은 기존 표본 100개·dev·로컬 안전 경계·outcome을 정의한다.
형식 식별의 공식 참고 자료는 계약의 format_sources에 있으며 공급자 다운로드 제한을 뜻하지 않는다.
문서 checksum / metadata와 Gate Report는 scripts/phase0_document_download.py가 HTTP 없이 재현 검증한다.

[Phase 2 Document Acquisition 계약](schemas/document-acquisition.contract.json)은 dev Source 역할,
공개 URL/redirect/size/timeout/retry 안전 경계, 실제 format 후보, 실패 분류와 품질 Report 필드를 고정한다.
source role은 API field provenance이며 본공고/부속 의미 계약이 아니다. 본문 Parser 계약도 포함하지 않는다.

[Phase 3 Document Parsing 계약](schemas/document-parsing.contract.json)은 DoclingDocument 표현, detected-format route,
상태·경고 code, parse_key 버전 규칙, 정규화·문서 Gate, HWPX container 한도, 모델 artifact(scope별)와 미결정 항목을 고정한다.

[Phase 4-A Chunking 계약](schemas/document-chunking.contract.json)은 DoclingDocument 입력, HybridChunker 설정, BGE-M3 tokenizer, FinalChunk schema·identity·provenance를 고정한다.
[Phase 4-B Indexing 계약](schemas/document-indexing.contract.json)은 BGE-M3 dense·sparse 추론, embedding_key, Qdrant collection schema·point·payload·stale 규칙을 고정한다.
[Phase 5 Retrieval 계약](schemas/document-retrieval.contract.json)은 query embedding 재사용, collection 결정, read-only, dense·sparse·RRF hybrid, SearchResult field를 고정한다.
[내부 API 계약](schemas/internal-api.contract.json)은 FastAPI endpoint·요청·위임 서비스·HTTP 오류 매핑을 고정한다.
[Eligibility 계약](schemas/eligibility.contract.json)은 단일 공고 자격 판단의 입력·criterion·상태 규칙을 고정한다.
[Phase 6 RAG 답변 계약](schemas/rag-answer.contract.json)은 retrieval baseline, evidence context, grounding 규칙, 출력 schema, application citation, provider 경계를 고정한다.
