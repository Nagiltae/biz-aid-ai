# 중소기업 지원사업 AI 프로젝트 설계안

> 프로젝트명(가칭): **BizAid AI**
>
> 현재 단계: **Phase 2 Full Document Acquisition** (2026-09-28 사용자 승인)
>
> 이 문서는 확정 설계가 아니라 데이터 검증 및 프로젝트 방향 논의를 위한
> 초안이다.

## 승인된 현재 실행 범위

2026-09-28 후속 사용자 승인: dev MySQL의 검증된 1,554개 `support_programs`에서
`printFlpthNm` / `flpthNm` 후보 전체를 수집해 Parser가 사용할 원본 byte·provenance·checksum·실패 상태를 만든다.
Phase 1B API FULL은 재실행하지 않는다. PDF/HWP/HWPX signature 판별까지만 수행하며 본문 Parsing·OCR·AI는 금지한다.
공개 문서 요청에는 API 인증정보를 전달하지 않고, V1/V2는 보존하며 신규 V3 metadata schema만 사용한다.

2026-09-28 후속 사용자 승인: Phase 1B dev FULL 전체 pagination / Raw 보존 / 완전성 검증 / 구조화 적재.
첫 실제 FULL은 soft-delete 후보 DRY_RUN만 수행하며 실제 적용·prod·증분 조회는 금지한다.
Phase 1A 모델·정규화·MySQL·Flyway V1/V2는 재사용하며 API 수집/검증은 DB transaction 밖에서 완료한다.
아래 Phase 1A 기록은 과거 승인 범위로 보존한다. 현재 실행 상세는 current-task와 FULL Contract를 따른다.

2026-09-28 사용자는 Phase 0 API Contract / Probe / 동일 100건 API 품질 / Document Download 검증 이후
Phase 1A 구조화 데이터 Pilot을 승인했다. 이번 실행은 기존 `api-quality-dev-20260928-01` 표본을
제품용 Python `data-pipeline/`에서 정규화해 dev MySQL에 적재하는 범위다.
DB 환경이 없었으므로 사용자 승인으로 Compose dev MySQL + 공통 `migrations/` Flyway를 도입한다.
Full sync의 완전성 / soft-delete 경계는 controlled test만 수행하며 live FULL은 실행하지 않는다.

사용자가 지정한 후속 순서: Phase 1B Full Structured Data Sync → Document Acquisition → Parsing →
Chunking → Vector Indexing → Retrieval → Answer Generation.
아래 기존 전체 로드맵은 Target 계획으로 보존한다. 이번 Task의 구체 범위는 이 승인과 current-task를 따른다.
본문 Parsing / OCR / RAG 가치 측정은 UNMEASURED이며, Phase 0 진행 종료를 GO/DROP 판정으로 간주하지 않는다.

------------------------------------------------------------------------

# 1. 프로젝트 개요

## 1.1 프로젝트 정의

기업 정보를 기반으로 현재 신청 가능한 중소기업 지원사업을 탐색하고, 실제
지원사업 공고문까지 분석하여 다음 정보를 근거와 함께 제공하는 AI 서비스.

-   신청 대상 여부 검토
-   지원 내용
-   지원 금액
-   신청 기간
-   세부 자격 조건
-   지원 제외 조건
-   필요 서류
-   신청 방법
-   주의사항
-   관련 근거

단순한 지원사업 검색 서비스가 아니라 다음 기능을 결합한다.

``` text
지원사업 검색
+
기업 개인화
+
공고문 분석
+
조건 검토
+
근거 기반 답변
```

------------------------------------------------------------------------

# 2. 해결하려는 문제

기업 지원사업 정보는 여러 기관에서 지속적으로 등록되며, 각 사업마다 신청
조건과 지원 내용이 다르다.

구조화된 API만으로는 다음과 같은 상세 조건을 확인하기 어려운 경우가
있다.

``` text
업력 제한
매출 조건
기업부설연구소 보유 여부
벤처기업 여부
중복지원 제한
지원 제외 업종
자부담 비율
필수 제출서류
선정 기준
예외 조건
```

따라서 다음 두 가지 데이터를 결합한다.

``` text
구조화 데이터
→ MySQL

공고문
→ RAG / Qdrant
```

------------------------------------------------------------------------

# 3. 핵심 설계 원칙

> **DB가 아는 것은 DB에게 묻고, 문서가 아는 것은 RAG에게 묻고, 판단과
> 설명이 필요한 부분만 LLM에게 맡긴다.**

## MySQL

정확한 조건 검색에 사용한다.

-   현재 접수 중인가?
-   서울 소재 사업인가?
-   지원대상이 중소기업인가?
-   지원분야가 기술인가?

## RAG

공고문의 상세 내용을 검색한다.

-   기업부설연구소가 필수인가?
-   지원 제외 조건은?
-   자부담은 얼마인가?
-   필수 제출서류는?
-   중복지원이 가능한가?

## LLM

자연어 이해와 여러 근거를 종합하는 데 사용한다.

-   사용자 질문 이해
-   기업 조건 구조화
-   여러 조건 비교
-   공고문 내용 설명
-   추천 이유 생성

------------------------------------------------------------------------

# 4. 데이터 출처

## 4.1 구조화 데이터

공공데이터포털의 **중소벤처기업부_중소기업 지원사업 공고 조회 서비스**를
사용한다.

주요 데이터:

-   `pblancId`
-   공고명
-   공고 URL
-   소관기관
-   수행기관
-   사업개요
-   지원분야
-   등록일
-   신청기간
-   수정일
-   지원대상
-   첨부파일
-   본문출력파일
-   해시태그
-   신청방법
-   문의처
-   사업신청 URL

## 4.2 비정형 데이터

API 응답에 포함된 공식 공고문 및 관련 첨부문서를 사용한다.

초기 RAG 우선 대상:

-   주 공고문
-   FAQ
-   안내문

초기 제외 후보:

-   개인정보 동의서
-   단순 신청서 양식
-   단순 제출 서식

------------------------------------------------------------------------

# 5. 전체 시스템 구조

``` text
                         React
                           │
                           │ REST / SSE
                           ▼
                     Spring Boot
                  ┌────────┼────────┐
                  │        │        │
                Auth     MySQL    Chat
                                    │
                                    ▼
                                FastAPI
                                    │
                               LangGraph
                                    │
                       ┌────────────┼────────────┐
                       │            │            │
                   LangChain      Qdrant        LLM
```

데이터 수집 시스템은 서비스 요청 처리와 분리한다.

``` text
기업마당 Open API
        │
        ▼
     Collector
        │
        ├──────────────→ MySQL
        │
        ▼
공고문 다운로드
        │
        ▼
 Document Parser
        │
        ▼
    Normalize
        │
        ▼
    Chunking
        │
        ▼
    Embedding
        │
        ▼
      Qdrant
```

------------------------------------------------------------------------

# 6. 기술 스택

## Frontend

-   React
-   Vite
-   TypeScript
-   TanStack Query
-   Zustand

역할:

-   로그인
-   기업 프로필 관리
-   지원사업 검색
-   지원사업 상세
-   AI Chat
-   근거 표시
-   지원사업 비교
-   즐겨찾기

TanStack Query는 서버 상태와 API 데이터 캐싱에 사용한다.

Zustand는 현재 선택 기업, 채팅 UI 상태, 선택된 지원사업 등 Client
State에 사용한다.

## Backend

-   Java 21
-   Spring Boot
-   Spring Security
-   MyBatis
-   MySQL
-   Flyway
-   WebClient
-   SSE

Spring Boot를 서비스의 Source of Truth로 사용한다.

담당:

-   회원
-   인증
-   기업 프로필
-   지원사업
-   즐겨찾기
-   대화
-   메시지
-   정확한 DB Filtering
-   FastAPI 연동

기본 호출 경로:

``` text
React → Spring Boot → FastAPI
```

React가 FastAPI를 직접 호출하지 않는다.

## AI

-   Python
-   FastAPI
-   Pydantic
-   LangChain
-   LangGraph
-   Qdrant Client
-   LLM Client
-   Embedding Client

역할:

-   질문 분석
-   Structured Output
-   Query Rewrite
-   Retrieval
-   Reranking
-   공고문 분석
-   지원조건 비교
-   답변 생성
-   Citation 생성
-   Evidence Validation

FastAPI가 서비스 데이터의 Source of Truth가 되지 않는다.

------------------------------------------------------------------------

# 7. MySQL 데이터 모델

초기 예상 테이블:

``` text
users

companies
company_profiles

support_programs
support_program_files
support_program_sync_history

conversations
messages

favorites

ai_request_logs
```

## support_programs

예상 필드:

``` text
id
pblanc_id
name

jurisdiction_name
executing_org_name

category
target
summary

application_start_date
application_end_date
application_period_raw

announcement_url

source_created_at
source_updated_at

application_method
application_url

hashtags

source
sync_status

created_at
updated_at
```

신청기간은 파싱된 값과 원본을 모두 보존한다.

``` text
application_start_date
application_end_date
application_period_raw
```

`2026-09-01 ~ 2026-10-01`뿐 아니라 `예산 소진시까지`와 같은 비정형 값이
존재할 수 있기 때문이다.

## support_program_files

``` text
id
program_id

file_type
file_name
source_url

mime_type
extension

download_status
parse_status

checksum

downloaded_at
parsed_at
```

파일 종류:

``` text
NOTICE
FAQ
GUIDE
APPLICATION_FORM
OTHER
```

------------------------------------------------------------------------

# 8. Qdrant

Collection:

``` text
support_program_documents
```

Payload 예시:

``` json
{
  "pblanc_id": "PBLN_000000000000001",
  "program_id": 123,
  "document_id": 456,
  "document_type": "NOTICE",
  "file_name": "공고문.pdf",
  "page": 5,
  "section": "지원대상",
  "source_url": "...",
  "source_updated_at": "...",
  "chunk_index": 12
}
```

핵심 Metadata:

-   `pblanc_id`
-   `document_id`
-   `document_type`
-   `page`
-   `section`
-   `source_url`

------------------------------------------------------------------------

# 9. 검색 구조

전체 문서를 무조건 Vector Search하지 않는다.

``` text
사용자 질문
      │
      ▼
조건 구조화
      │
      ▼
MySQL Hard Filter
      │
      ▼
후보 지원사업
      │
      ▼
pblanc_id 목록
      │
      ▼
Qdrant Metadata Filter
      │
      ▼
Semantic Retrieval
      │
      ▼
Reranking
      │
      ▼
LLM
      │
      ▼
근거 기반 답변
```

------------------------------------------------------------------------

# 10. 사용자 기업 프로필

예상 필드:

-   회사명
-   지역
-   기업형태
-   업력
-   업종
-   직원 수
-   주요사업
-   벤처기업 여부
-   기업부설연구소 여부
-   수출기업 여부
-   매출
-   관심 지원분야

예시:

``` text
회사명: ABC Tech
지역: 서울
기업형태: 중소기업
업력: 2년
업종: IT/SW
직원: 5명
주요사업: AI SaaS
벤처기업: O
기업부설연구소: X
수출기업: X
```

------------------------------------------------------------------------

# 11. 주요 사용자 질문

-   우리 회사가 지금 신청할 수 있는 지원사업 찾아줘.
-   AI 관련 기술개발 지원사업 있어?
-   마케팅 지원 받을 수 있는 사업 찾아줘.
-   이 사업 우리 회사 신청 가능해?
-   이 사업에서 최대 얼마까지 지원해줘?
-   자부담 있어?
-   기업부설연구소가 필수야?
-   지원 제외 조건은 뭐야?
-   제출서류 알려줘.
-   A 사업과 B 사업 비교해줘.

------------------------------------------------------------------------

# 12. Structured Output

사용자 질문을 구조화한다.

``` json
{
  "intent": "PROGRAM_SEARCH",
  "conditions": {
    "region": "서울",
    "business_age_years": 2,
    "company_type": "중소기업",
    "industry": "IT/SW",
    "interests": ["AI", "기술개발"]
  }
}
```

이 결과를 DB Filtering 등에 사용한다.

------------------------------------------------------------------------

# 13. RAG

기본 구조:

``` text
질문
 ↓
Query Understanding
 ↓
MySQL Candidate Filter
 ↓
Candidate IDs
 ↓
Qdrant Metadata Filter
 ↓
Vector Search
 ↓
Reranking
 ↓
Context
 ↓
LLM
 ↓
Grounded Answer
```

초기 Baseline:

``` text
Dense Retrieval
+
Metadata Filtering
```

평가 결과 필요성이 확인되면 다음을 검토한다.

``` text
Dense Retrieval
+
Sparse/BM25
+
RRF
+
Reranker
```

기술을 먼저 도입하고 이유를 나중에 찾지 않는다.

------------------------------------------------------------------------

# 14. Chunking

고정 길이 Chunk만 사용하는 것보다 문서 구조 기반 Chunking을 우선
검토한다.

공고문 예상 구조:

``` text
사업목적
지원대상
지원내용
지원규모
지원제외
신청방법
선정절차
제출서류
유의사항
문의처
```

구조:

``` text
Document
 ↓
Heading Detection
 ↓
Section
 ↓
Chunk
```

표는 가능한 경우 행/열 관계를 유지한다.

``` text
지원금액 | 정부지원 | 기업부담
5천만원 | 80%      | 20%
```

------------------------------------------------------------------------

# 15. Embedding

원칙:

``` text
Index Embedding Model
=
Query Embedding Model
```

초기에는 한국어를 지원하는 Multilingual Embedding 모델 하나로 Baseline을
구축한다.

Evaluation Dataset 구축 후 필요하면 다른 Embedding 모델과 비교한다.

------------------------------------------------------------------------

# 16. LLM 역할 분리

## 소형/저비용 모델

-   Intent Classification
-   Structured Output
-   Query Rewrite
-   Metadata Extraction

## 고성능 모델

-   복잡한 자격조건 분석
-   여러 공고 비교
-   최종 답변 생성

## 일반 코드

-   신청기간
-   지역
-   기업형태
-   지원분야
-   현재 공고 상태

정확한 조건은 가능한 한 일반 코드와 DB에서 처리한다.

------------------------------------------------------------------------

# 17. LangGraph

처음부터 거대한 Agent 구조를 만들지 않는다.

실제 Workflow Branching 필요성이 확인되면 도입한다.

예상 구조:

``` text
START
  ↓
Question Analysis
  ↓
Intent Router
  │
  ├── PROGRAM_SEARCH
  │        ↓
  │    DB Candidate Search
  │        ↓
  │    Document Retrieval
  │
  ├── PROGRAM_QA
  │        ↓
  │    Specific Program Retrieval
  │
  └── PROGRAM_COMPARE
           ↓
      Multi-document Retrieval

             ↓
       Evidence Check
        │          │
      충분        부족
        │          │
        │      Query Rewrite
        │          │
        │      Retrieve Again
        │          │
        └────←─────┘
             ↓
      Answer Generation
             ↓
      Citation Validation
             ↓
            END
```

------------------------------------------------------------------------

# 18. Hallucination 방지

모든 중요한 Claim에는 Evidence가 존재해야 한다.

``` text
Claim
 ↓
Evidence
 ↓
Source
```

예:

``` text
Claim:
자부담 20%가 필요합니다.

Evidence:
공고문 8페이지

Source:
document_id
page
chunk_id
source_url
```

근거가 없으면 다음처럼 답한다.

``` text
제공된 공고문에서는 해당 내용을 확인할 수 없습니다.
```

------------------------------------------------------------------------

# 19. 데이터 파이프라인

별도 Python 모듈로 구성한다.

``` text
data-pipeline/

collector/
downloader/
parser/
normalizer/
chunker/
indexer/
validator/
```

Pipeline:

``` text
API
 ↓
Raw 저장
 ↓
Normalize
 ↓
MySQL Upsert
 ↓
신규/변경 판단
 ↓
File Download
 ↓
Checksum
 ↓
변경된 문서 Parsing
 ↓
Chunking
 ↓
Embedding
 ↓
Qdrant Upsert
```

------------------------------------------------------------------------

# 20. Raw Data 보존

원본 데이터는 삭제하지 않는다.

개발 환경:

``` text
data/

raw/
downloaded/
parsed/
failed/
```

목적:

-   Source 문제
-   Normalizer 문제
-   Parser 문제
-   Embedding 문제

를 구분하고 재현할 수 있도록 한다.

운영 환경에서는 S3/Object Storage 사용을 검토한다.

------------------------------------------------------------------------

# 21. Document Parser

초기 우선순위:

``` text
PDF
 ↓
HWPX
 ↓
HWP
 ↓
ZIP
```

Data Feasibility 결과에 따라 실제 지원 범위를 결정한다.

가능하면 API의 주 공고문 파일을 우선 처리한다.

------------------------------------------------------------------------

# 22. Data Quality

자동 Data Quality Report를 생성한다.

예:

``` text
Total API Records          1,518

Valid pblanc_id            100%

Notice File Available       96.8%

Download Success            98.1%

Parse Success               94.5%

Embedding Success           99.9%


File Format

PDF                         71%
HWPX                        18%
HWP                          9%
Other                        2%
```

위 수치는 예시이며 실제 검증 결과로 교체한다.

------------------------------------------------------------------------

# 23. Evaluation Dataset

서비스 완성 후 만드는 것이 아니라 초기부터 구축한다.

예:

-   서울 소재 중소기업 대상 사업 찾아줘.
-   업력 3년 이하 창업기업이 신청 가능한 사업 찾아줘.
-   이 사업 최대 지원금은?
-   기업부설연구소가 반드시 있어야 해?
-   이 사업에서 지원 제외되는 기업은?
-   자부담 얼마야?
-   제출서류는?
-   두 사업의 지원조건을 비교해줘.

Gold Dataset:

``` text
question

expected_program_ids

expected_document

expected_page

expected_fact
```

------------------------------------------------------------------------

# 24. AI Evaluation

측정 후보:

-   Retrieval Recall@K
-   MRR
-   Groundedness
-   Citation Accuracy
-   Answer Correctness
-   Routing Accuracy
-   Structured Output Accuracy
-   No-answer Accuracy

예:

``` text
Retrieval Recall@5 = 0.91

Citation Accuracy = 0.96

Groundedness = 0.94

Intent Routing Accuracy = 0.98
```

위 수치는 실제 평가 결과로 교체한다.

------------------------------------------------------------------------

# 25. Observability

## 일반 서비스

-   Prometheus
-   Grafana

측정:

-   HTTP Latency
-   Error Rate
-   Request Count
-   MySQL Latency
-   Qdrant Latency
-   Document Download Failure
-   Document Parse Failure
-   Embedding Failure

## AI Observability

LangSmith를 사용한다.

추적:

-   Question
-   Intent
-   Retrieval Query
-   Candidate Program IDs
-   Retrieved Chunks
-   Similarity Score
-   Reranking Result
-   Model
-   Prompt Version
-   Token Usage
-   Latency
-   Answer
-   Citation
-   Evaluation Result
-   Fallback

------------------------------------------------------------------------

# 26. Harness Engineering

이번 프로젝트에서 Harness Engineering은 단순한
`AGENTS.md + check-all.sh` 수준으로 두지 않는다.

핵심 목표는 다음과 같다.

``` text
AI가 코드를 생성한다.
        ↓
프로젝트 Context / Rule / Skill을 따라 작업한다.
        ↓
결정론적 Test / Lint / Contract / Integration 검증을 수행한다.
        ↓
검증 결과와 작업 상태를 파일로 남긴다.
        ↓
사람이 Git 변경 내역과 보고서를 확인한다.
        ↓
통과한 변경만 다음 단계로 이동한다.
```

핵심 원칙:

``` text
LLM 생성 / 수정
→ 확률적

Test / Lint / Contract / Script
→ 결정론적

AI 재수정
→ 확률적

재검증
→ 결정론적
```

Harness의 목적은 AI를 믿는 것이 아니라 **AI가 안전하게 작업할 수 있는
환경과 검증 루프를 만드는 것**이다.

------------------------------------------------------------------------

# 27. AI 도구 역할 분리

이번 프로젝트에서는 AI 도구의 역할을 명확히 분리한다.

## Codex

Codex는 **개발 Agent** 역할을 담당한다.

주요 역할:

``` text
기능 구현
버그 수정
테스트 작성
리팩터링
문서 동기화
Migration 작성
검증 스크립트 실행
작업 결과 보고
```

Codex는 반드시 다음 순서로 작업한다.

``` text
AGENTS.md
   ↓
현재 Task
   ↓
필요한 Harness Context / Rule / Skill
   ↓
관련 Product Code
   ↓
구현
   ↓
Test / Validation
   ↓
Workspace Report 작성
```

## AGY (Antigravity)

AGY는 **Harness / Project Reviewer** 역할을 담당한다.

주요 역할:

``` text
Harness 구조 점검
프로젝트 구조 점검
문서 ↔ 코드 불일치 점검
규칙 누락 점검
테스트 사각지대 점검
Architecture Boundary 점검
Git 변경 누락 점검
Harness Drift 점검
완료 조건 점검
```

원칙적으로 AGY가 제품 기능을 주도적으로 구현하지 않는다.

``` text
Codex
→ Generator / Developer

AGY
→ Evaluator / Reviewer
```

Generator와 Evaluator 역할을 분리하여 동일 Agent의 자기검증에만 의존하지
않는다.

------------------------------------------------------------------------

# 28. Harness 포함 전체 프로젝트 구조

``` text
biz-aid-ai/
│
├── .git/
├── .gitignore
├── README.md
├── AGENTS.md                              # ★ Harness 진입점 / 프로젝트 지도
│
│   # Agent가 가장 먼저 확인하는 문서
│   #
│   # 포함:
│   # - 프로젝트 목적
│   # - 전체 Architecture 요약
│   # - 절대 지켜야 할 핵심 규칙
│   # - 현재 개발 방식
│   # - 작업별 읽어야 할 Rule / Skill / Docs Registry
│   # - 최종 DoD / Validation 진입점
│   #
│   # 모든 세부 지식을 넣지 않는다.
│   # Context / Registry / Progressive Disclosure 원칙 적용
│
├── harness/                               # ★ AI가 어떻게 일할지 정의
│   │
│   ├── docs/                              # [Detailed Context]
│   │   ├── architecture.md
│   │   ├── coding-conventions.md
│   │   ├── testing.md
│   │   ├── workflow.md
│   │   ├── data-pipeline.md
│   │   ├── rag.md
│   │   └── observability.md
│   │
│   │   # AGENTS.md에서 필요한 문서만 Routing
│   │   # 모든 작업에서 전부 읽지 않는다.
│   │   # → Progressive Disclosure / Context 절약
│   │
│   ├── agents/                            # [Agent = 누가 판단하는가]
│   │   ├── codex-developer.md
│   │   └── agy-reviewer.md
│   │
│   │   # codex-developer:
│   │   # - 구현 / 수정 / 테스트
│   │   #
│   │   # agy-reviewer:
│   │   # - Harness 점검
│   │   # - Architecture / Project 점검
│   │   # - Drift / 누락 검증
│   │   #
│   │   # Agent 남발 금지
│   │
│   ├── skills/                            # [Skill = 어떻게 작업하는가]
│   │   │
│   │   ├── feature-development/
│   │   │   ├── SKILL.md
│   │   │   ├── workflows/
│   │   │   │   └── feature-flow.md
│   │   │   └── references/
│   │   │       └── checklist.md
│   │   │
│   │   ├── debugging/
│   │   │   ├── SKILL.md
│   │   │   └── workflows/
│   │   │       └── rca.md
│   │   │
│   │   │   # Reproduce
│   │   │   # → Analyze
│   │   │   # → Hypothesis
│   │   │   # → Validate
│   │   │   # → Fix
│   │   │   # → Regression Test
│   │   │
│   │   ├── database-migration/
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   │       └── migration-rules.md
│   │   │
│   │   ├── api-contract-change/
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   │       └── contract-checklist.md
│   │   │
│   │   ├── data-pipeline-change/
│   │   │   ├── SKILL.md
│   │   │   └── workflows/
│   │   │       └── pipeline-validation.md
│   │   │
│   │   └── rag-change/
│   │       ├── SKILL.md
│   │       └── references/
│   │           └── rag-regression-checklist.md
│   │
│   │   # Skill description을 Routing 조건으로 사용
│   │   #
│   │   # description
│   │   #    ↓
│   │   # SKILL.md
│   │   #    ↓
│   │   # 필요한 workflow / reference만 추가 확인
│   │
│   ├── rules/                             # [Guardrail / Constraint]
│   │   ├── safety.md
│   │   ├── database-rules.md
│   │   ├── git-policy.md
│   │   ├── file-boundaries.md
│   │   ├── code-comment-policy.md
│   │   ├── ai-boundary-rules.md
│   │   └── data-source-rules.md
│   │
│   │   # 허용 / 금지 범위를 명확하게 정의
│   │   # "조심해서 작업" 같은 추상적 규칙 금지
│   │   # 핵심: Least Privilege
│   │
│   ├── workspace/                         # [State / External Memory]
│   │   ├── current-task.md
│   │   ├── reports/
│   │   ├── checkpoints/
│   │   └── artifacts/
│   │
│   │   # Agent 내부 기억에 의존하지 않는다.
│   │   # 현재 상태 / 결과 / 실패 원인을 파일로 외부화한다.
│   │   # Session 교체 후에도 Resume 가능해야 한다.
│   │
│   ├── evals/                             # ★ Harness 자체 평가
│   │   ├── agent-eval.md
│   │   ├── skill-eval.md
│   │   └── regression/
│   │
│   │   # 비교 예:
│   │   # Harness 적용 전/후
│   │   # Skill v1/v2
│   │   # Codex 단독 vs Codex + AGY Review
│   │   #
│   │   # 성공률 / 수정 횟수 / 시간 / Token / Cost / Regression 비교
│   │
│   └── changelog/
│       └── harness-changes.md             # Harness Evolution / Drift 수정 기록
│
├── contracts/                             # ★ 시스템 Boundary Contract
│   ├── frontend-backend/
│   ├── backend-ai/
│   ├── external-api/
│   └── schemas/
│
│   # Request / Response / Type / Error / Status Code
│   # 구현 전에 경계를 명시하고 Contract Test로 검증
│
├── frontend/
│   ├── src/
│   ├── tests/
│   └── ...
│
├── backend/
│   ├── src/
│   ├── src/test/
│   └── ...
│
├── ai/
│   ├── app/
│   ├── tests/
│   └── ...
│
├── data-pipeline/
│   ├── collector/
│   ├── downloader/
│   ├── parser/
│   ├── normalizer/
│   ├── chunker/
│   ├── indexer/
│   ├── validator/
│   └── tests/
│
├── migrations/                            # Flyway Migration
│   ├── V1__init.sql
│   └── ...
│
├── tests/                                 # ★ 시스템 수준 테스트
│   ├── contract/
│   ├── integration/
│   └── e2e/
│
├── evals/                                 # ★ 제품 AI Evaluation
│   ├── datasets/
│   ├── retrieval/
│   ├── generation/
│   ├── routing/
│   └── regression/
│
│   # harness/evals = AI 개발 방식 자체 평가
│   # root/evals    = 제품 AI 품질 평가
│
├── scripts/                               # ★ Deterministic Verification
│   ├── setup.sh
│   ├── check-format.sh
│   ├── check-lint.sh
│   ├── check-frontend.sh
│   ├── check-backend.sh
│   ├── check-ai.sh
│   ├── check-data-pipeline.sh
│   ├── check-contract.sh
│   ├── check-integration.sh
│   ├── check-e2e.sh
│   ├── check-eval.sh
│   ├── check-git-tracked.sh
│   ├── check-comments.sh
│   ├── check-harness.sh
│   └── check-all.sh                       # ★ 최종 Definition of Done
│
├── data/                                  # 개발용 Raw / Parsed 데이터
│   ├── raw/
│   ├── downloaded/
│   ├── parsed/
│   └── failed/
│
├── infra/
│   └── docker/
│
├── docker-compose.yml                     # 개발환경 실행
├── .env.example
│
└── .github/
    └── workflows/
        ├── ci.yml
        └── deploy-op.yml                  # op Merge 시 운영 배포용 (추후 구현)
```

------------------------------------------------------------------------

# 29. AGENTS.md 설계 원칙

`AGENTS.md`는 모든 세부 내용을 담는 거대한 설명서가 아니다.

역할은 다음과 같다.

``` text
Context
+
Project Map
+
Rule Registry
+
Skill Registry
+
Validation Entry Point
```

예상 구성:

``` text
1. Project Purpose
2. Current Architecture
3. Core Boundaries
4. Non-Negotiable Rules
5. Branch / Git Policy
6. Task Routing
7. Skill Routing
8. Required Validation
9. Definition of Done
10. Relevant Document Map
```

예:

``` text
DB Migration 작업
→ harness/rules/database-rules.md
→ harness/skills/database-migration/SKILL.md

RAG 변경
→ harness/docs/rag.md
→ harness/skills/rag-change/SKILL.md

외부 API Collector 변경
→ harness/docs/data-pipeline.md
→ harness/skills/data-pipeline-change/SKILL.md

API Contract 변경
→ contracts/
→ harness/skills/api-contract-change/SKILL.md
```

Agent가 모든 Harness 문서를 매번 읽는 구조를 만들지 않는다.

------------------------------------------------------------------------

# 30. Git / Branch 운영 정책

브랜치는 다음 세 개를 사용한다.

``` text
dev
→ 실제 개발 브랜치

main
→ 최신 검증 완료 코드

op
→ 운영 배포 대상 코드
```

사용자는 **dev 브랜치에서만 직접 개발**한다.

기본 흐름:

``` text
dev
 │
 │ 개발 / 테스트 / 검토
 ▼
Push
 │
 ▼
GitHub Actions CI
 │
 ▼
검증 완료
 │
 ▼
main Merge
 │
 │ 최신 안정 코드
 ▼
op Merge
 │
 ▼
GitHub Actions
 │
 ▼
자동 배포
```

운영 인프라 자체는 현재 단계에서 설계하지 않는다.

`op` 브랜치 Merge 시 자동 배포된다는 배포 Trigger만 프로젝트 규칙으로
고정한다.

------------------------------------------------------------------------

# 31. Git 변경 추적 정책

개발 중 생성되거나 수정되는 프로젝트 파일은 원칙적으로 모두 Git 변경
내역에서 확인할 수 있어야 한다.

2026-09-28 사용자 승인 Workspace lifecycle 정책: 위 추적 의무는 Control/Input 자산에 적용한다.
Generated Report / Checkpoint / Artifact는 non-gating 실행 산출물로 ignore 가능하며 Git 추적을 요구하지 않는다.
current-task와 정적 README는 strict 유지하고 committed 과거 기록은 보존한다. 구체적 경계는 harness/docs/workflow.md를 따른다.

금지:

``` text
Agent가 파일을 만들었지만 Git에서 보이지 않음

Untracked 파일을 남긴 채 작업 완료 선언

임시 수정 파일을 숨김

검증 결과에 영향을 주는 파일을 .gitignore로 임의 제외

사용자가 확인하지 못하는 위치에 결과물 저장
```

이를 위해 다음 검증을 둔다.

``` text
scripts/check-git-tracked.sh
```

검증 대상:

``` text
git status

Untracked Files

Modified Files

Deleted Files

Ignored File 중 프로젝트 결과물 존재 여부
```

Agent 작업 완료 보고에는 반드시 다음을 포함한다.

``` text
생성 파일

수정 파일

삭제 파일

변경 이유

실행한 검증

검증 결과

남아 있는 위험 / 미완료 항목
```

사용자가 실제 Git Diff와 변경 파일 목록을 보고 최종 판단한다.

------------------------------------------------------------------------

# 32. 한글 주석 정책

개발 중 작성하는 설명성 코드 주석은 **한글을 기본으로 한다.**

목적은 단순히 주석 수를 늘리는 것이 아니라 사용자가 코드를 학습하고 변경
이유를 이해할 수 있게 하는 것이다.

좋은 예:

``` java
// 기업마당 API의 신청기간은 "예산 소진시까지"처럼 날짜로 변환할 수 없는 값이 있으므로
// 파싱된 날짜와 원본 문자열을 함께 보존한다.
```

``` python
# MySQL에서 이미 후보 공고를 좁혔으므로 전체 Qdrant Collection을 검색하지 않고
# 후보 pblanc_id만 Metadata Filter로 제한한다.
```

피해야 하는 예:

``` java
// 변수 선언
String name;
```

``` python
# 반복문 실행
for item in items:
```

주석 원칙:

``` text
WHY
→ 왜 이렇게 설계했는가

BOUNDARY
→ 왜 이 계층에서 처리하는가

EXCEPTION
→ 어떤 데이터 예외 때문에 필요한가

RISK
→ 변경 시 무엇을 주의해야 하는가
```

단순히 코드가 하는 일을 그대로 번역하는 주석은 작성하지 않는다.

검증 보조:

``` text
scripts/check-comments.sh
```

이 스크립트는 모든 코드에 주석이 있는지를 기계적으로 강제하기 위한 것이
아니라, 새 핵심 로직에 설명성 주석이 누락됐는지 점검하는 보조 장치로
사용한다.

------------------------------------------------------------------------

# 33. Harness Rules

최소 Rule은 다음과 같이 구성한다.

## database-rules.md

``` text
Flyway Migration 사용

이미 적용된 V1~Vn Migration 수정 금지

DB 변경은 항상 신규 Migration 추가

Migration 파일 Git 추적 필수

Schema 변경 시 관련 Test / Docs 동기화
```

## git-policy.md

``` text
직접 개발은 dev에서만 수행

작업 완료 전 git status 확인

Untracked 파일 방치 금지

변경 파일 목록 보고 필수

Agent 임의 Push / Merge 금지

사용자 승인 없이 main / op 변경 금지
```

## file-boundaries.md

예:

``` text
React
→ FastAPI 직접 호출 금지

Frontend
→ DB 접근 금지

FastAPI
→ 서비스 DB 임의 변경 금지

Data Pipeline
→ 사용자 인증 / 채팅 Domain 수정 금지
```

## ai-boundary-rules.md

``` text
DB로 결정 가능한 조건을 LLM 판단으로 대체하지 않는다.

근거 없는 지원 가능 여부 확정 금지.

Qdrant 검색 결과만으로 정확한 날짜 / 상태를 확정하지 않는다.

중요 Claim에는 Evidence를 연결한다.

Evidence 부족 시 확인 불가 상태를 반환한다.
```

## data-source-rules.md

``` text
지원사업 Source는 승인된 공식 데이터 출처만 사용한다.

외부 임의 데이터 Source 추가 금지.

pblanc_id를 Source Identity로 사용한다.

원문과 정규화 데이터를 구분한다.

원문 변경 여부를 추적할 수 있어야 한다.
```

------------------------------------------------------------------------

# 34. Skill 설계

Skill은 모든 작업 절차를 한 문서에 몰아넣지 않는다.

각 Skill의 `description`이 Routing 기준이 된다.

예:

## feature-development

``` text
요구사항 확인
→ 영향 범위 분석
→ Contract 확인
→ 구현
→ Unit Test
→ 관련 Integration Test
→ Docs 동기화
→ Validation
→ Report
```

## debugging

``` text
Reproduce
→ Evidence 수집
→ Analyze
→ Hypothesis
→ Validate
→ 최소 수정
→ Regression Test
→ Report
```

## database-migration

``` text
현재 Schema 확인
→ 신규 Migration 번호 확인
→ Migration 작성
→ 기존 Migration 불변 확인
→ Flyway 실행
→ Repository / Test 영향 확인
→ Validation
```

## data-pipeline-change

``` text
Raw Source 확인
→ 입력 Contract 확인
→ 변경 영향 분석
→ Collector / Parser 수정
→ 실패 데이터 보존
→ 재실행 가능성 확인
→ Data Quality Regression 확인
```

## rag-change

``` text
Baseline 확인
→ 변경 목적 정의
→ Retrieval / Chunk / Prompt 중 변경 범위 제한
→ Evaluation 실행
→ Baseline 비교
→ Regression 확인
→ 변경 근거 기록
```

------------------------------------------------------------------------

# 35. Workspace / External Memory

Agent 내부 대화 기억에 프로젝트 상태를 의존하지 않는다.

``` text
harness/workspace/current-task.md
```

에는 현재 작업을 기록한다.

예:

``` text
Task
현재 단계
목표
작업 범위
관련 파일
현재까지 완료된 내용
검증 결과
남은 문제
다음 작업
```

작업 완료 시:

``` text
harness/workspace/reports/
```

에 결과를 남긴다.

장시간 작업이나 데이터 파이프라인 작업은:

``` text
harness/workspace/checkpoints/
```

를 사용한다.

목표:

``` text
Resume
Recovery
Session 교체
Agent 교체
실패 원인 추적
```

------------------------------------------------------------------------

# 36. Contract First / Boundary Verification

서비스 간 경계는 코드만 보고 추론하게 두지 않는다.

``` text
contracts/
```

에 명시적으로 관리한다.

주요 Contract:

``` text
React ↔ Spring Boot

Spring Boot ↔ FastAPI

Data Pipeline ↔ 기업마당 API

FastAPI ↔ Qdrant Payload Schema
```

검증:

``` text
scripts/check-contract.sh
```

목표:

``` text
Request / Response 불일치

필수 Field 누락

Type 변경

Error Contract 변경

Payload Metadata 누락
```

등을 Integration 이전 단계에서 잡는다.

------------------------------------------------------------------------

# 37. Deterministic Verification

검증 스크립트는 Harness의 핵심 실행 장치다.

``` text
scripts/setup.sh
```

확인:

``` text
Java
Node
Python
Docker
MySQL
Qdrant
필수 환경변수
의존성
Health Check
```

영역별 검증:

``` text
check-format.sh
check-lint.sh

check-frontend.sh
check-backend.sh
check-ai.sh
check-data-pipeline.sh

check-contract.sh
check-integration.sh
check-e2e.sh
check-eval.sh

check-git-tracked.sh
check-comments.sh
check-harness.sh
```

최종 DoD:

``` bash
./scripts/check-all.sh
```

`check-all.sh`가 성공하지 않으면 Agent는 작업 완료를 선언할 수 없다.

------------------------------------------------------------------------

# 38. Harness Drift 검증

Harness도 시간이 지나면 코드와 불일치할 수 있으므로 Harness 자체를
검증한다.

``` text
scripts/check-harness.sh
```

점검 대상:

``` text
AGENTS.md에서 참조한 문서가 실제 존재하는가?

Skill Registry와 실제 Skill이 일치하는가?

Rule 링크가 깨지지 않았는가?

Validation Command가 실제 존재하는가?

Architecture 문서와 실제 Module이 크게 어긋나지 않는가?

현재 Branch Policy와 CI 설정이 일치하는가?

필수 Workspace / Report 구조가 유지되는가?
```

Harness 변경 이유는:

``` text
harness/changelog/harness-changes.md
```

에 기록한다.

------------------------------------------------------------------------

# 39. 테스트 구조

제품 테스트와 Harness 평가를 구분한다.

제품 테스트:

``` text
Level 1
Format / Lint

Level 2
Unit

Level 3
Component

Level 4
Contract

Level 5
Integration

Level 6
E2E

Level 7
AI Evaluation
```

주요 Boundary:

``` text
React → Spring

Spring → FastAPI

Spring → MySQL

FastAPI → Qdrant

Data Pipeline → 기업마당 API

Data Pipeline → Document Parser
```

Harness 자체 평가는:

``` text
harness/evals/
```

에서 관리한다.

비교 대상:

``` text
Harness 적용 전 / 후

Skill 적용 전 / 후

Codex 단독 / Codex + AGY Review

Rule 변경 전 / 후
```

평가 후보:

``` text
Task 성공률
Regression 발생률
수정 반복 횟수
검증 실패율
작업 시간
Token
Cost
사람의 재작업량
```

------------------------------------------------------------------------

# 40. CI / GitHub Actions

GitHub Actions는 Harness 규칙을 시스템적으로 강제하는 Enforcement
Layer로 사용한다.

## dev

사용자가 직접 개발하는 브랜치.

`dev` Push 시 CI를 실행한다.

``` text
dev Push
   ↓
Format
   ↓
Lint
   ↓
Unit
   ↓
Contract
   ↓
Integration
   ↓
Harness Check
   ↓
Build
```

실패하면 수정 후 다시 Push한다.

## main

최신 검증 완료 코드를 유지하는 브랜치.

``` text
dev
 ↓
CI 통과
 ↓
변경 내역 사용자 확인
 ↓
main Merge
```

`main`은 최신 안정 상태를 나타낸다.

## op

운영 배포 대상 브랜치.

``` text
main
 ↓
op Merge
 ↓
GitHub Actions
 ↓
자동 배포
```

현재 단계에서는 실제 운영 인프라를 설계하지 않는다.

다만 추후 운영 환경이 결정되더라도 **배포 Trigger는 op 브랜치
Merge**라는 규칙을 유지한다.

------------------------------------------------------------------------

# 41. CI와 AI Evaluation 분리

모든 AI Evaluation을 매 Push마다 실행하지 않는다.

예:

``` text
dev Push
→ Small / Deterministic Test
→ Small AI Regression Eval

main Merge
→ Medium Eval

Scheduled / Release Candidate
→ Full Eval
```

실행 시간과 API 비용 때문에 평가 수준을 분리한다.

------------------------------------------------------------------------

# 42. 개발환경

개발환경은 Docker Compose를 기준으로 한다.

예상 구성:

``` text
frontend
backend
ai
mysql
qdrant
```

필요한 경우 데이터 파이프라인을 별도 실행 Container 또는 Batch Command로
실행한다.

원칙:

``` text
README의 실행 방법
=
Docker Compose 실제 구성
=
setup.sh 검증 대상
```

문서에는 있는데 Compose에 없거나, Compose에는 있는데 실제 코드가
의존하지 않는 서비스를 방치하지 않는다.

------------------------------------------------------------------------

# 43. 원문 데이터 보존 전략

이번 프로젝트에서는 **MongoDB를 초기 도입하지 않는다.**

이유:

``` text
기업마당 API 원문은 JSON/XML 형태의 로그성 / 재처리용 데이터다.

현재 규모에서는 별도 Document DB가 반드시 필요한 요구사항이 없다.

MySQL JSON Column 또는 Raw File 저장만으로 Source 재현과 재처리가 가능하다.

MongoDB를 추가하면 개발 / Docker / 운영 / Monitoring / Backup 대상이 하나 더 늘어난다.
```

따라서 초기 구조는 다음과 같이 한다.

``` text
원본 API Response
→ 개발환경: data/raw/ 파일 보존

원본 수집 Metadata / 필요 Raw JSON
→ MySQL
```

예상 테이블:

``` text
support_program_raw_snapshots

id
pblanc_id
source
raw_payload_json
source_updated_at
collected_at
checksum
```

용도:

``` text
Normalizer 재실행

Source 변경 비교

Parser / Mapping 오류 재현

데이터 감사

회귀 테스트 Fixture 생성
```

향후 다음 조건이 실제로 발생하면 MongoDB 도입을 ADR로 다시 검토한다.

``` text
Raw Document 규모가 크게 증가

Schema 변형이 매우 심함

여러 버전의 원문 Snapshot 조회가 핵심 기능이 됨

MySQL JSON 저장이 병목 또는 관리 부담이 됨
```

즉, 현재는 **MongoDB를 넣지 않는 것이 더 적절하다.**

------------------------------------------------------------------------

# 44. Coding Agent Task 운영

Codex에게 큰 기능을 한 문장으로 던지지 않는다.

현재 작업은:

``` text
harness/workspace/current-task.md
```

에 정의한다.

Task 내용:

``` text
Goal

Context

Read First

Allowed Scope

Forbidden Scope

Requirements

Non-goals

Acceptance Criteria

Required Tests

Validation Command

Expected Report
```

예:

``` text
Goal
기업마당 API Collector 구현

Read First
- AGENTS.md
- harness/docs/data-pipeline.md
- harness/rules/data-source-rules.md
- harness/skills/data-pipeline-change/SKILL.md
- contracts/external-api/...

Forbidden Scope
- frontend 수정
- 인증 Domain 수정
- Qdrant Schema 변경

Validation
./scripts/check-data-pipeline.sh
./scripts/check-contract.sh
./scripts/check-git-tracked.sh
```

------------------------------------------------------------------------

# 45. 작업 완료 보고

Codex는 작업 완료 후 최소 다음 내용을 보고한다.

``` text
1. 무엇을 구현했는가

2. 왜 이렇게 구현했는가

3. 생성한 파일

4. 수정한 파일

5. 삭제한 파일

6. 주요 설계 결정

7. 작성 / 수정한 테스트

8. 실행한 Validation

9. Validation 결과

10. 실패하거나 미완료된 항목

11. 사용자가 직접 확인해야 할 부분
```

AGY 점검 시에는 별도 Reviewer Report를 생성한다.

예:

``` text
harness/workspace/reports/
  2026-xx-xx-codex-task-report.md
  2026-xx-xx-agy-review-report.md
```

------------------------------------------------------------------------

# 46. Harness Definition of Done

기능 구현이 끝났다는 기준은 "코드가 작성됨"이 아니다.

최소 DoD:

``` text
[ ] 요구사항 충족

[ ] 허용된 파일 범위 준수

[ ] 신규 / 수정 파일 Git 변경에 모두 표시

[ ] Untracked 프로젝트 파일 없음

[ ] 필요한 한글 설명 주석 작성

[ ] Unit Test 통과

[ ] Contract Test 통과

[ ] 관련 Integration Test 통과

[ ] 관련 AI Regression Eval 통과

[ ] 문서와 코드 동기화

[ ] Migration 규칙 준수

[ ] Harness Rule 위반 없음

[ ] check-all.sh 통과

[ ] 작업 Report 작성

[ ] 사용자가 Git Diff / Report를 검토할 수 있는 상태
```

------------------------------------------------------------------------

# 47. Harness Engineering 핵심 목표

이번 프로젝트에서 Harness Engineering으로 보여주려는 것은 단순히 AI 코딩
도구를 사용했다는 사실이 아니다.

``` text
Context Engineering

Progressive Disclosure

Agent / Skill Routing

Guardrail / Least Privilege

External Memory / State

Contract First

Deterministic Verification

Generator ↔ Evaluator 분리

Regression Evaluation

Harness Evolution

CI Enforcement

Human Review
```

를 실제 프로젝트 개발 프로세스에 적용하는 것이 목표다.

최종 개발 흐름:

``` text
사용자 요구사항
      ↓
Task / Context 정의
      ↓
Codex 구현
      ↓
Deterministic Verification
      ↓
Codex 수정
      ↓
AGY Harness / Project Review
      ↓
추가 수정
      ↓
check-all.sh
      ↓
Git Diff / Report
      ↓
사용자 판단
      ↓
dev Push
      ↓
GitHub Actions CI
      ↓
main
      ↓
op
      ↓
자동 배포
```

# 48. 개발 단계

## Phase 0 - Data Feasibility Gate

현재 단계.

``` text
API 100건 수집
 ↓
필드 분석
 ↓
공고문 URL 분석
 ↓
파일 다운로드
 ↓
파일 형식 통계
 ↓
Parser 테스트
 ↓
RAG 가치 검증
 ↓
GO / DROP
```

## Phase 1 - Foundation

``` text
Repository
Docker
MySQL
Qdrant
AGENTS.md
Docs
Scripts
CI
```

## Phase 2 - Data Pipeline

``` text
API Collector
Normalizer
MySQL
Document Downloader
Document Parser
Chunker
Embedding
Qdrant
```

## Phase 3 - Basic Service

``` text
회원
기업 Profile
지원사업 목록
지원사업 상세
검색
즐겨찾기
```

## Phase 4 - Basic RAG

``` text
Question
 ↓
Retrieval
 ↓
Answer
 ↓
Citation
```

## Phase 5 - Personalized AI

``` text
Company Profile
+
Natural Language Question

 ↓
Candidate Filter
 ↓
RAG
 ↓
Eligibility Analysis
 ↓
Grounded Answer
```

## Phase 6 - LangGraph

``` text
Intent Routing
Evidence Check
Retry
Query Rewrite
Program Comparison
Fallback
```

## Phase 7 - Evaluation

``` text
Gold Dataset
Retrieval Evaluation
Generation Evaluation
Routing Evaluation
Regression Test
```

## Phase 8 - Observability

``` text
Prometheus
Grafana
AI Trace
```

## Phase 9 - Deployment

``` text
Docker
AWS
CI/CD
```

------------------------------------------------------------------------

# 49. 배포 / 실행 정책

## 개발환경

현재 개발환경은 Docker Compose를 기준으로 한다.

``` text
docker-compose.yml

├── frontend
├── backend
├── ai
├── mysql
└── qdrant
```

Data Pipeline은 필요에 따라 별도 Batch Command 또는 Container로
실행한다.

개발환경에서 다음을 목표로 한다.

``` text
git clone
 ↓
.env 구성
 ↓
./scripts/setup.sh
 ↓
docker compose up
 ↓
개발 가능
```

## 운영환경

현재 단계에서는 운영 인프라 구조를 결정하지 않는다.

확정된 규칙은 하나다.

``` text
main
 ↓
op Merge
 ↓
GitHub Actions
 ↓
자동 배포
```

실제 AWS 구성, 배포 대상, Container Registry, Network, Secret 관리 등은
서비스 구현과 개발환경 검증이 진행된 이후 별도 ADR에서 결정한다.

# 50. 초기 제외 기술

초기 버전에서는 다음 기술을 의도적으로 제외한다.

-   Kafka
-   Kubernetes
-   Airflow
-   과도한 Microservices
-   Multi-Agent
-   GraphRAG
-   Knowledge Graph
-   Fine-tuning

필요성이 확인되면 추가한다.

기술 개수를 늘리는 것이 목적이 아니다.

------------------------------------------------------------------------

# 51. 프로젝트에서 보여줄 역량

## Backend Engineering

-   Spring Boot
-   MySQL
-   REST API
-   Authentication
-   SSE
-   Docker
-   AWS

## Data Engineering

-   Open API
-   ETL
-   Document Collection
-   Parsing
-   Data Quality
-   Incremental Update

## AI Application

-   RAG
-   Embedding
-   Vector DB
-   Structured Output
-   Reranking
-   LangChain
-   LangGraph

## AI Reliability

-   Evaluation
-   Grounded Answer
-   Citation
-   Fallback
-   Observability

## AI-assisted Engineering

-   Harness Engineering
-   Codex
-   AGENTS.md
-   Automated Validation
-   CI
-   ADR

------------------------------------------------------------------------

# 52. Data Feasibility Gate

프로젝트 구현 전에 실제 데이터 약 100건을 대상으로 검증한다.

## API 품질

-   `pblancId` 존재율
-   `pblancId` Unique 여부
-   주요 필드 유효율
-   신청기간 Parsing 가능성
-   수정 공고 추적 가능 여부

## 공고문 품질

-   공고문 URL 존재율
-   다운로드 성공률
-   URL 안정성
-   PDF 비율
-   HWP 비율
-   HWPX 비율
-   ZIP 비율

## Parsing 품질

-   PDF Text Extraction 성공률
-   HWPX Parsing 성공률
-   HWP Parsing 성공률
-   Scan PDF 비율
-   Table Extraction 품질
-   Heading Detection 가능성

## RAG 가치

API에 없는 다음 내용이 공고문에 실제 존재하는지 확인한다.

-   세부 지원조건
-   제외조건
-   중복지원 제한
-   지원금
-   자부담
-   선정기준
-   제출서류
-   예외조건
-   주의사항

------------------------------------------------------------------------

# 53. Data Feasibility 합격 기준

초기 기준:

``` text
Sample
100개 공고

API 정상 수집률
>= 99%

pblancId 존재율
= 100%

주요 필드 유효율
>= 95%

공고문 URL 확보율
>= 90%

공고문 다운로드 성공률
>= 95%

문서 Text Extraction 성공률
>= 90%

API ↔ 공고문 별도 Entity Matching
불필요
```

RAG:

``` text
공고문에 API보다 상세한 조건 존재

자격조건 추출 가능

제외조건 추출 가능

지원조건 추출 가능

근거 페이지 추적 가능
```

기준을 크게 충족하지 못하면 기술적으로 억지로 해결하기보다 데이터 소스
또는 프로젝트 자체를 재검토한다.

------------------------------------------------------------------------

# 54. 첫 번째 Vertical Slice

전체 기능을 만들기 전에 아주 작은 End-to-End 기능을 먼저 완성한다.

``` text
기업마당 API
 ↓
공고 50건
 ↓
MySQL
 ↓
공고문 다운로드
 ↓
Parsing
 ↓
Chunking
 ↓
Embedding
 ↓
Qdrant
 ↓
질문
 ↓
후보 검색
 ↓
RAG
 ↓
근거 포함 답변
```

예제 질문:

``` text
서울에 있는 IT 중소기업이 신청할 수 있는 기술개발 지원사업을 찾아줘.
```

이 Vertical Slice가 성공한 뒤 범위를 확장한다.

------------------------------------------------------------------------

# 55. 최종 사용자 Flow

``` text
회원가입
 ↓
기업 Profile 등록
 ↓
지원사업 탐색
 ↓
AI에게 자연어 질문
 ↓
질문 Structured Output
 ↓
기업 Profile 결합
 ↓
MySQL Candidate Search
 ↓
Qdrant Document Retrieval
 ↓
Eligibility Analysis
 ↓
Evidence Validation
 ↓
LLM Answer
 ↓
지원사업 + 추천 이유 + 조건 + 근거 표시
```

------------------------------------------------------------------------

# 56. 프로젝트 핵심 차별점

이 프로젝트의 목적은 단순한 RAG 챗봇을 만드는 것이 아니다.

``` text
Structured Data
+
Deterministic Filtering
+
Document RAG
+
Personalization
+
Evidence Validation
+
AI Evaluation
+
Observability
+
Harness Engineering
```

을 하나의 실제 서비스로 구성하는 것을 목표로 한다.

------------------------------------------------------------------------

# 57. 현재 프로젝트 상태

``` text
기업마당 API 발견
 ↓
실제 API 응답 확인
 ↓
공고문 URL 연결 확인
 ↓

[현재]
Data Feasibility Gate

 ↓
서비스 요구사항 확정
 ↓
Architecture 확정
 ↓
Harness 구축
 ↓
Vertical Slice
 ↓
전체 개발
 ↓
Evaluation
 ↓
Observability
 ↓
Deployment
```

------------------------------------------------------------------------

# 58. 현재 가장 먼저 해야 할 작업

아직 서비스 구현을 시작하지 않는다.

첫 번째 작업:

> **기업마당 API 최근 공고 약 100건을 대상으로 Data Feasibility Report
> 작성**

결과물:

-   총 공고 수
-   API 필드별 Null 비율
-   `pblancId` 중복 여부
-   공고문 존재율
-   파일 확장자 분포
-   다운로드 성공률
-   Parsing 성공률
-   공고문 평균 페이지
-   API 대비 공고문 추가정보 분석
-   RAG 적용 가치
-   자동화 가능 여부
-   발견된 예외 Case
-   최종 GO / DROP 판단

이 검증을 통과한 뒤 프로젝트의 상세 구현 설계를 확정한다.
