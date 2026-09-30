# BizAid backend (Spring Boot)

회원·JWT 인증·기업정보·지원사업 조회·대화 저장을 맡는 서비스 서버다. React는 이 서버의 `/api`만 호출한다.
AI 검색·자격 판정은 `ai.AiGateway` 경계까지만 있고 FastAPI 연결은 다음 단계다(지금은 `ai_service_not_connected` 503).

| package | 역할 |
| --- | --- |
| `auth` | 회원가입·로그인·재발급·로그아웃, JWT 발급/검증 filter, Spring Security 설정 |
| `company` | 내 기업정보 등록·조회·수정(사용자 1명당 1개) |
| `program` | 기존 `support_programs` 조회 전용 매핑, QueryDSL 목록 검색, 상세 |
| `conversation` | 대화·메시지 저장과 조회 |
| `ai` | AI 검색·자격 판정 API와 `AiGateway`(FastAPI 연결 지점) |
| `common` | 오류 코드·공통 오류 응답·페이지 응답·Clock/QueryDSL Bean |

## 실행

환경변수: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `JWT_SECRET`(32byte 이상).
IntelliJ에서는 저장소 루트 `.env.dev`를 Run Configuration 환경변수로 불러오고 working directory를 `backend/`로 둔다.
Flyway는 기본값 `filesystem:../migrations`(공통 migration)를 읽는다. 다른 위치에서 실행하면 `FLYWAY_LOCATIONS`를 절대 경로로 준다.

테스트(H2 격리 DB, 로컬 Gradle 없이):

```bash
docker run --rm -v "$PWD":/app -v bizaid-gradle-cache:/home/gradle/.gradle -w /app gradle:8.14-jdk21 gradle test
```
