# Architecture와 현재 상태

근거: PROJECT_DESIGN.md §1–9, 19–25, 42–43, 48–58.
목적은 기업 프로필을 활용해 현재 신청 가능한 사업과 상세 조건을 근거와 함께 제공하는 것이다.

## 책임 경계

| 대상 | 설계상 책임 | 현재 상태 |
| --- | --- | --- |
| React | UI, 서버 상태 캐시, 선택 기업·채팅 UI 상태 | 미구현 |
| Spring Boot | 인증·기업·사업·대화·즐겨찾기 Source of Truth, 정확한 DB filtering, FastAPI 호출 | 미구현 |
| FastAPI | 질문 구조화·검색·비교·답변·Citation·Evidence 검증 | 미구현 |
| MySQL | 구조화 공고·서비스 데이터·Raw metadata / JSON | Phase 1A dev Pilot 구현 |
| Qdrant | 문서 Chunk vector와 근거 metadata | 미구현 |
| Python Data Pipeline | 요청 처리와 분리된 수집·정규화·다운로드·파싱·색인 | 구조화 API 정규화·적재 Pilot 구현, 나머지는 후속 |
| Phase 0 도구 | 로컬 원문 보존·무결성·미측정 보고서·관찰 계약 검증·명시적인 최소 Local API Probe | 구현, dev Probe·5×20 API 품질 Batch·동일 표본의 제한된 문서 Download Gate |
| Harness | Context / Rules / Skills / Validation / External Memory | 기반 구현, 과거 보완 Targeted Re-review PASS |

React는 Spring Boot를 통해 AI를 호출한다. Frontend는 DB에 접근하지 않는다.
FastAPI는 서비스 DB의 소유자가 아니다. 정확한 조건은 일반 코드와 MySQL이 결정한다.
MySQL 후보 pblanc_id로 Qdrant 검색 범위를 제한하는 구조는 향후 계획이다.

## 현재 실행 구성

`docker-compose.yml`은 `phase0`와 승인된 dev-db Profile의 MySQL / Flyway를 제공한다.
frontend / backend / ai / qdrant 컨테이너는 없다. 제품 Pipeline은 `data-pipeline/`이다.
Docker Compose는 개발환경 기준이며 운영 인프라는 미결정이다.
MongoDB·Langfuse는 도입하지 않는다. LangSmith 계획은 [observability.md](observability.md)에 있다.

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
3. §5 도식의 문서 Normalize와 §19 API Normalize는 대상이 다르다. 상세 Pipeline 설계 때 구분을 확정한다. 이번에 어느 쪽도 구현하지 않는다.
4. 사용자 확인 Endpoint / 인증 정보와 실제 Sample의 pagination / envelope / field 타입은 [External API Contract](../../contracts/external-api/README.md)에 있다. Pagination·ID·no-data와 5×20 품질 Run은 OBSERVED다. 공식 정렬·일반 오류 보장은 미확정이다.
5. §53의 이번 API 품질 Task는 12개 주요 필드·타입/nonblank 기준·실제 행 분모·기본 정렬 선두 100건을 사용한다. API 측정에서 의미·접속은 미측정이었다. 문서 성공률은 별도 Download Gate에서 측정하고 공식 최신순 보장은 미확정이다.
6. HWP / HWPX / HTML의 근거 page 대체 규칙과 표 추출 품질 기준이 미결정이다. Parser 선택 전에 검증한다.
7. §57의 과거 API 확인 서술과 이번 사용자 제공 Sample은 별개 Evidence다. Sample을 이번 Live 실행 결과로 재사용하지 않는다.

최상위 문서 자체는 수정하지 않는다. 미결정 사항은 기술 도입으로 해결하지 않는다.
100건 Gate 후의 50건 Vertical Slice는 별도 작업이며 현재 범위에 없다.

## 승인된 Phase 1A 구현

제품용 Python `data-pipeline/`이 구조화된 API source를 정규화해 dev MySQL에 저장한다.
공통 `migrations/` Flyway만 DDL owner다. Compose는 기존 phase0와 실제 MySQL / Flyway만 실행한다.
backend / ai / frontend / Qdrant는 미구현이다. 실제 Pilot은 기존 동일 100건 SAMPLE이며 FULL은 controlled test다.
제품 코드 경계와 lifecycle 안전조건은 [Pipeline](../../data-pipeline/README.md)에서 확인한다.

## 공식 환경 설정

dev → `.env.dev`, prod → `.env.prod`만 선택한다. Process Environment가 우선하고 generic `.env` / Profile fallback은 없다.
Dev MySQL은 Host 127.0.0.1:3306 → container 3306이며 사용자 계정·비밀번호와 volume을 보존한다.
설정 파일 선택과 실행 권한은 별개다. 현재 제품 API / DB 실행은 dev만 허용한다. [Infra](../../infra/README.md)를 따른다.
