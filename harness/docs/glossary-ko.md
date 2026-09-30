# 프로젝트 한국어 용어집

사람이 읽는 설계·보고 문서에서 쓰는 표준 한국어 표현이다. 처음 쓸 때는 "한글 뜻(영문 용어)" 형태로 쓴다.
코드 식별자·API field·Contract enum·제품명(FastAPI, Qdrant, BGE-M3 등)은 바꾸지 않는다.
전체 설명과 사례는 [PROJECT_MASTER_GUIDE](../../PROJECT_MASTER_GUIDE.md)의 용어 사전을 따른다.

| 영문 용어 | 표준 한국어 표현 | 이 프로젝트에서의 뜻 |
| --- | --- | --- |
| Parsing | 문서 읽기·구조화 | PDF·HWP·HWPX를 DoclingDocument로 바꾸기 |
| DoclingDocument | 공통 문서 구조 | 모든 형식이 수렴하는 유일한 문서 표현 |
| OCR | 이미지 글자 인식 | 글자 층이 없는 page만 PP-OCRv5로 인식 |
| Chunking | 문서 조각 나누기 | HybridChunker로 FinalChunk 생성 |
| FinalChunk | 최종 문서 조각 | 적재·검색 단위(chunk_id, 공고 ID, 근거 위치 포함) |
| embedding_text | 검색용 입력 문장 | 공고명 + heading 경로 + 본문 |
| Embedding | 문장을 검색용 숫자로 바꾸기 | BGE-M3 dense 1024 + sparse |
| Indexing | 검색용 벡터 적재 | Qdrant collection에 point upsert |
| Retrieval / Retriever | 근거 검색 / 근거 검색기 | dense·sparse·RRF hybrid 검색 |
| Dense / Sparse / Hybrid Search | 의미 검색 / 단어 검색 / 혼합 검색 | 두 검색 순위를 RRF로 합침 |
| RRF | 순위 합산 | 점수가 아니라 순위로 두 결과를 합침(k=60) |
| Vector DB | 벡터 검색 저장소 | Qdrant |
| RAG | 근거 기반 답변 생성 | 검색 근거만 보고 LLM이 답함 |
| Structured Output | 정해진 형식의 AI 응답 | JSON schema로 강제한 LLM 출력 |
| Grounding | 근거 기반 판단 | 근거 밖 사실·조건을 만들지 않음 |
| Citation | 근거 연결 | 답변이 어느 공고 몇 쪽 근거인지 앱이 연결 |
| Candidate / Candidate Filter | 후보 공고 / 후보 필터 | MySQL 정형 조건으로 고른 pblanc_id |
| Scope | 검색 범위 제한 | 후보 밖 공고를 Qdrant에서 검색하지 않음 |
| SEARCH_LIST / DOCUMENT_QA | 공고 목록 찾기 / 특정 공고 질문 | request_mode 두 가지 |
| Company Profile Snapshot | 기업 정보 스냅샷 | 자격 판정에 넣는 그 시점 기업 값(저장 안 함) |
| Eligibility | 지원 자격 판정 | 공고 1개 + 기업 정보로 조건별 판정 |
| MET / NOT_MET / UNKNOWN | 충족 / 미충족 / 판단 불가 | 조건별 판정 결과 |
| ELIGIBLE / INELIGIBLE / NEEDS_MORE_INFO / INSUFFICIENT_EVIDENCE | 지원 가능 / 지원 불가 / 정보 추가 필요 / 공고 근거 부족 | 앱이 계산하는 최종 상태 |
| Router | 요청 분기기 | request_mode에 따라 목록 또는 문서 QA로 보냄 |
| ServiceRuntime | 공통 실행 환경 | 모델·DB pool·Qdrant·LLM 설정을 한 번 만들어 재사용 |
| LlmProvider | LLM 연결 경계 | Ollama 등 모델 교체 지점 |
| Contract | 구성요소 간 규칙 | contracts/schemas의 JSON 규칙 |
| Harness Engineering | 에이전트 작업 통제 체계 | 범위·경계·계약·검사를 저장소에 기록하고 자동 검사 |
| Endpoint | API 호출 주소 | /internal/v1/query 등 |
| Lifespan | 앱 시작·종료 생명주기 | 서버 시작 때 runtime 생성, 종료 때 정리 |
| Connection Pool | 연결 재사용 묶음 | SQLAlchemy engine |
| Fallback | 실패 시 대체 처리 | 원칙적으로 조용한 대체를 하지 않음 |
| parse_key / chunk_set_key / embedding_key | 파싱 / 조각 / 임베딩 결과 식별값 | 설정이 바뀌면 새 값 → 재처리 범위 결정 |
| stale point | 오래된 검색 point | 같은 source의 이전 chunk point, 재적재 뒤 삭제 |
