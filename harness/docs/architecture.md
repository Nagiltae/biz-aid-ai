# Architecture와 현재 상태

근거: PROJECT_DESIGN.md §1–9, 19–25, 42–43, 48–58.
목적은 기업 프로필을 활용해 현재 신청 가능한 사업과 상세 조건을 근거와 함께 제공하는 것이다.

## 책임 경계

| 대상 | 설계상 책임 | 현재 상태 |
| --- | --- | --- |
| React | UI, 서버 상태 캐시, 선택 기업·채팅 UI 상태 | 미구현 |
| Spring Boot | 인증·기업·사업·대화·즐겨찾기 Source of Truth, 정확한 DB filtering, FastAPI 호출 | 미구현 |
| FastAPI | 질문 구조화·검색·비교·답변·Citation·Evidence 검증 | 미구현 |
| MySQL | 구조화 공고·서비스 데이터·Raw metadata / JSON | dev 공고 FULL(V1/V2), 문서 source·S3 위치(V3/V4), parse 상태·identity(V5) 구현 |
| Qdrant | 문서 Chunk vector와 근거 metadata | Phase 4-B dev Indexing(dense·sparse 적재) 구현, 검색은 미구현 |
| Python Data Pipeline | 요청 처리와 분리된 수집·정규화·다운로드·파싱·색인 | 구조화 FULL·문서 수집·S3 저장·PDF/HWP/HWPX Parser(OCR·PP 표)·Chunking·dense/sparse Indexing 구현 |
| Phase 0 도구 | 로컬 원문 보존·무결성·미측정 보고서·관찰 계약 검증·명시적인 최소 Local API Probe | 구현, dev Probe·5×20 API 품질 Batch·동일 표본의 제한된 문서 Download Gate |
| Harness | Context / Rules / Skills / Validation / External Memory | 기반 구현, 과거 보완 Targeted Re-review PASS |

React는 Spring Boot를 통해 AI를 호출한다. Frontend는 DB에 접근하지 않는다.
FastAPI는 서비스 DB의 소유자가 아니다. 정확한 조건은 일반 코드와 MySQL이 결정한다.
MySQL 후보 pblanc_id로 Qdrant 검색 범위를 제한하는 구조는 향후 계획이다.

## 현재 실행 구성

`docker-compose.yml`은 `phase0`, 승인된 dev-db Profile의 MySQL / Flyway, dev-vector Profile의 loopback Qdrant를 제공한다.
frontend / backend / ai 컨테이너는 없다. 제품 Pipeline은 `data-pipeline/`이다.
Docker Compose는 개발환경 기준이며 운영 인프라는 미결정이다.
MongoDB·Langfuse는 도입하지 않는다. LangSmith 계획은 [observability.md](observability.md)에 있다.
Phase 2.5에서 문서 binary의 영구 저장소는 고정 dev S3이고 MySQL은 provenance와 검증 metadata를 소유한다.
로컬 corpus는 migration 검토가 끝날 때까지 보존하며 장기 Source로 새로 생성하지 않는다.

## Target 구조와 현재 Skill 구조

PROJECT_DESIGN.md §28은 확장 가능한 Target 구조이며 모든 하위 문서의 즉시 생성을 요구하지 않는다.
현재 Phase 0 준비는 6개 SKILL.md와 data-pipeline-change의 기존 측정 workflow만 사용한다.
나머지 Skill은 짧은 본문과 상세 Context / Rule 링크로 충분하므로 추가 workflow/reference가 필요하지 않다.
복잡한 승인된 Task에서 독립 절차가 실제로 필요할 때만 하위 문서를 추가한다.
빈 디렉터리·내용 없는 문서를 만들어 Target 구조를 흉내 내지 않는다.

AGY Initial Review는 완료됐고 판정은 PASS WITH FIXES다.
과거 보완 Targeted Re-review는 PASS다. 현재 Task의 독립 검토·Human Review·Data Gate는 pending이다.
Review Lifecycle과 증거 범위는 [workflow.md](workflow.md)에서 관리한다.

## Phase 해석과 선결정 목록

1. §48·57의 Harness 배치와 이번 요청의 순서가 다르다. 이번 요청에 따라 Gate 준비용 Harness를 먼저 만든다. Phase 1 전체 착수로 간주하지 않는다.
2. §37·46·49의 전체 서비스 검증은 미구현 상태에 적용할 수 없다. 현재 적용 검증을 실행하고 제품 검증은 N/A로 공개한다. 제품 도입 때 해당 검증을 필수로 추가한다.
3. §5 도식의 문서 Normalize와 §19 API Normalize는 대상이 다르다. API Normalize는 `ingestion/normalizer.py`, 문서 Normalize는 Parsing Contract의 text 정규화(NFC·줄바꿈·제어문자)로 구현됐다.
4. 사용자 확인 Endpoint / 인증 정보와 실제 Sample의 pagination / envelope / field 타입은 [External API Contract](../../contracts/external-api/README.md)에 있다. Pagination·ID·no-data와 5×20 품질 Run은 OBSERVED다. 공식 정렬·일반 오류 보장은 미확정이다.
5. §53의 이번 API 품질 Task는 12개 주요 필드·타입/nonblank 기준·실제 행 분모·기본 정렬 선두 100건을 사용한다. API 측정에서 의미·접속은 미측정이었다. 문서 성공률은 별도 Download Gate에서 측정하고 공식 최신순 보장은 미확정이다.
6. 결정됨: HWP는 Docker LibreOffice+H2Orestart로 PDF 변환 후 PDF route, HWPX는 native XML adapter(page 없음, section·XML 경로 provenance), PDF 표는 PP-TableMagic + fail-closed TABLE_QUALITY_FAILED다. HTML·XLSX·ZIP은 POLICY_PENDING이다.
7. §57의 과거 API 확인 서술과 이번 사용자 제공 Sample은 별개 Evidence다. Sample을 이번 Live 실행 결과로 재사용하지 않는다.

최초 Phase 0 준비에서는 최상위 문서 자체를 수정하지 않았다. 후속 승인 범위는 해당 문서 첫머리에 기록한다.
미결정 사항은 기술 도입으로 해결하지 않는다.
100건 Gate 후의 50건 Vertical Slice는 별도 작업이며 현재 범위에 없다.

## 승인된 Phase 1A 구현

제품용 Python `data-pipeline/`이 구조화된 API source를 정규화해 dev MySQL에 저장한다.
공통 `migrations/` Flyway만 DDL owner다. Compose는 기존 phase0와 실제 MySQL / Flyway만 실행한다.
당시 backend / ai / frontend / Qdrant는 미구현이었다. Phase 1A 실제 Pilot은 기존 동일 100건 SAMPLE이며 당시 FULL은 controlled test였다.
제품 코드 경계와 lifecycle 안전조건은 [Pipeline](../../data-pipeline/README.md)에서 확인한다.

Phase 1B 승인으로 dev API 전체 pagination / Raw 완전성 검증 / 구조화 적재를 추가한다.
수집·검증·정규화와 DB mutation을 분리하며 첫 Live FULL은 후보 DRY-RUN만 수행한다. schema / 모델 / lifecycle 의미는 유지한다.

## 공식 환경 설정

dev → `.env.dev`, prod → `.env.prod`만 선택한다. Process Environment가 우선하고 generic `.env` / Profile fallback은 없다.
Dev MySQL은 Host 127.0.0.1:3306 → container 3306이며 사용자 계정·비밀번호와 volume을 보존한다.
설정 파일 선택과 실행 권한은 별개다. 현재 제품 API / DB 실행은 dev만 허용한다. [Infra](../../infra/README.md)를 따른다.

## Phase 3 Parsing 표현

문서 구조의 공통 표현은 docling-core의 DoclingDocument다. BizAid는 source SHA·route·parse_key·상태·경고만 결과 봉투에 둔다.
PDF와 HWP(→PDF)는 Docling 변환기, HWPX는 native XML Adapter가 같은 표현을 만든다. 자체 canonical document tree는 없다.
PARSED DoclingDocument의 결정론적 JSON은 S3, `(source_sha256, parse_key)` 상태·identity·pointer는 V5 MySQL이 소유한다.

## Phase 4 Chunking / Indexing

```text
parsing(S3 원본 → DoclingDocument, S3 + V5 row) ← chunking(현재 parse_key PARSED artifact → FinalChunk) ← indexing(FinalChunk → BGE-M3 → Qdrant)
```

| 저장소 | 소유 | 재생성 |
| --- | --- | --- |
| S3 | 문서 원본(content SHA), PARSED DoclingDocument JSON(parse_key 주소, immutable) | 원본은 불가, parsed는 parser로 가능 |
| MySQL | 공고(pblanc_id)·source relation·parse 상태·identity·artifact pointer | Flyway schema, 데이터는 Pipeline |
| Qdrant | FinalChunk point(id=chunk_id, dense+sparse, payload=FinalChunk.payload) | S3 parsed artifact + V5 row에서 다시 만들 수 있는 파생 index |

MySQL과 Qdrant는 `pblanc_id`·`source_sha256`으로만 연결한다. collection은 embedding_key별이고 dev loopback Compose Qdrant만 쓴다.
Retriever는 미구현이며 [AI 경계](../rules/ai-boundary-rules.md)와 [파일 경계](../rules/file-boundaries.md)를 따른다.
