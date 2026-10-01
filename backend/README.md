# BizAid backend (Spring Boot)

회원·JWT 인증·기업정보·지원사업 조회·대화 저장을 맡는 서비스 서버다. React는 이 서버의 `/api`만 호출한다.
AI 검색·자격 판정은 `ai.HttpAiGateway`가 호스트 FastAPI 내부 API를 호출한다(공유 키 `INTERNAL_AI_API_KEY`, 연결 3s·응답 90s 제한시간, 자동 재시도 없음).

도메인 중심 package 안에 계층을 둔다. 의존 방향은 presentation → application → domain이고, infrastructure는 저장소·외부 연결 구현이다.

| package | 역할 |
| --- | --- |
| `auth` | 회원가입·로그인·재발급·로그아웃. infrastructure에 JWT 발급/검증 filter, Spring Security 설정 |
| `company` | 내 기업정보 등록·조회·수정(사용자 1명당 1개). domain `CompanyDetails`로 HTTP DTO와 분리 |
| `program` | 기존 `support_programs` 조회 전용 매핑, infrastructure에 QueryDSL 목록 검색 |
| `conversation` | 대화·메시지(AI 결과 JSON 포함) 저장과 조회 |
| `ai` | AI 검색·자격 판정·V2 추천 workflow 유스케이스, `AiGateway` ← `HttpAiGateway`, `ai_workflows` State 저장·단계 점유·낙관적 잠금 |
| `activity` | 사용자 활동 기록(activity_logs). 각 Application Service가 명시적으로 호출 |
| `common` | 여러 도메인이 함께 쓰는 오류 코드·공통 오류 응답(error), 페이지 응답(web), Clock·QueryDSL Bean(config) |

| 계층 | 두는 것 |
| --- | --- |
| presentation | Controller, HTTP 요청/응답 DTO, 입력 검증 |
| application | 유스케이스(Service), 조회 결과 모델, 트랜잭션 경계 |
| domain | Entity, 값, 도메인 규칙(예: 모집 상태 계산) |
| infrastructure | Spring Data JPA·QueryDSL Repository, JWT, 외부 HTTP, 설정 Properties |

설정: `application.yml`(공통) + `application-dev.yml`(로컬, 기본 profile) + `application-prod.yml`(운영: 주소·경로 기본값 없음, Secure Cookie 고정, DB TLS). 비밀값은 어떤 profile에도 쓰지 않는다.

V2 추천은 Spring이 MySQL의 `ai_workflows` JSON과 version을 소유한다. FastAPI는 받은 State로 검색 또는 판정을 한 단계만 실행하고, React는 응답의 `nextAction`만 따라간다. 한 요청에서 판정하는 공고는 최대 1건이며, 동시 진행은 단계 점유와 version으로 막는다.

## 실행

환경변수: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `JWT_SECRET`(32byte 이상), `INTERNAL_AI_API_KEY`(FastAPI와 같은 값). 선택: `AI_BASE_URL`(기본 http://127.0.0.1:8000), `AI_CONNECT_TIMEOUT`, `AI_RESPONSE_TIMEOUT`.
IntelliJ에서는 저장소 루트 `.env.dev`를 Run Configuration 환경변수로 불러오고 working directory를 `backend/`로 둔다.
Flyway는 기본값 `filesystem:../migrations`(공통 migration)를 읽는다. 다른 위치에서 실행하면 `FLYWAY_LOCATIONS`를 절대 경로로 준다.

테스트(H2 격리 DB, 로컬 Gradle 없이):

```bash
docker run --rm -v "$PWD":/app -v bizaid-gradle-cache:/home/gradle/.gradle -w /app gradle:8.14-jdk21 gradle test
```
