# 개발·운영 환경 쉬운 설명서

이 문서는 **2026-10-05 현재 코드와 실행 중인 로컬 환경**을 기준으로 썼습니다. 서버 설치·자료 복원 순서는 [운영 설명서](deployment.md)를 함께 보세요. 설정 점검의 전체 비교표는 [6-1 보고서](../harness/workspace/reports/development/2026-10-05-bundle6-1-prod-config-audit.md)에 있습니다.

## 1. 지금 어디에서 무엇이 실행되나요?

현재 맥북에서는 **개발 환경**이 실행 중입니다. AI 답변을 Bedrock으로 만든다고 운영 환경이 되는 것은 아닙니다.

| 프로그램 | 하는 일 | 맥북 개발 | AWS 운영 |
| --- | --- | --- | --- |
| 화면(React) | 로그인·검색·추천 결과 표시 | http://localhost:3000 | https://biz-aid.cloud |
| 서비스 서버(Spring) | 회원·기업정보·대화·사용 횟수 관리 | 개발 설정, 로컬 MySQL | 운영 설정, RDS |
| AI 서버(FastAPI) | 조건 분석·문서 검색·답변·자격 검토 | 개발 설정, 현재 Bedrock | 운영 설정, Bedrock 고정 |
| 일반 DB(MySQL) | 회원정보·공고·대화 등 저장 | 맥북 Docker 안 MySQL | AWS RDS MySQL |
| 검색 저장소(Qdrant) | 공고문에서 질문과 가까운 근거 찾기 | 맥북 Docker 안 V2 저장소 | 서버 Docker 안 V2 저장소 |
| 문서 보관함(S3) | 원본·파싱 결과 파일 보관 | 자료 처리 도구가 사용 | 기존 자료 보관; 질문 서버가 직접 읽지는 않음 |
| 외부 실행 기록(LangSmith) | AI 단계별 시간·상태 기록 | 켜는 설정 있음; 전송 성공은 별도 확인 | 설정과 관계없이 강제로 꺼짐 |
| 입구 서버(Caddy) | 도메인·HTTPS 연결 | 일반 개발 실행에는 없음 | 사용자 접속을 화면 서버로 전달 |

화면은 Spring만 부릅니다. Spring이 필요할 때 FastAPI를 부릅니다. 사용자의 브라우저가 FastAPI나 DB를 직접 부르지 않습니다.

## 2. 개발/운영을 고르는 스위치는 하나가 아닙니다

| 이름·파일 | 의미 | 개발에서 | 운영에서 |
| --- | --- | --- | --- |
| `docker-compose.yml` | 맥북 프로그램을 묶어 실행하는 목록 | `scripts/dev.sh`가 사용 | 사용하지 않음 |
| `docker-compose.prod.yml` | 서버 프로그램을 묶어 실행하는 목록 | 일반 개발에는 사용하지 않음 | 명시해서 사용 |
| Compose의 `--profile app` | 화면·Spring·AI·DB 서비스 묶음을 선택 | dev.sh가 지정 | 운영 목록은 이 선택이 필요 없음 |
| `SPRING_PROFILES_ACTIVE` | Spring 설정 선택 | 현재 `dev` | 운영 Compose가 `prod`로 고정 |
| `BIZAID_ENV` | FastAPI 설정 선택 | 없으면 `dev`; 현재 이 경우 | 운영 Compose가 `prod`로 고정 |
| `APP_PROFILE` | 예시에 있는 설정 이름 | 이것만 바꿔서는 서비스가 전환되지 않음 | 운영 Compose에서 사용하지 않음 |
| 도구의 `--profile dev` | 수집 등 일부 명령의 실행 환경 선택 | 도구 실행 때 직접 지정 | 운영 서비스 선택과 별개 |
| Git의 `dev` 브랜치 | 소스 작업 위치 | 개발 작업용 | 프로그램의 실행 모드와 별개 |

현재 Spring은 `dev`, FastAPI는 기본 `dev`, 검색 이름 구분은 `v2`, AI 답변 제공자는 `bedrock`입니다. 현재 컨테이너에서 비밀이 아닌 설정만 확인한 결과입니다.

운영에서는 API 설명 화면·상세 오류·자동 코드 재시작이 꺼집니다. 로그인 유지용 쿠키는 HTTPS에서만 보내도록 고정됩니다. 다른 웹사이트에 API를 모두 열어 주는 설정은 없고, 같은 사이트 주소의 `/api`로 통신합니다.

## 3. 설정 파일은 무엇이고 왜 형식이 다른가요?

| 파일 | 위치 | 용도 | 누가 읽나 | Git에 올리나 |
| --- | --- | --- | --- | --- |
| `.env.dev.example` | 프로젝트 맨 위 | 개발 설정 작성 예시 | 사용자가 참고; 서비스가 자동으로 읽지 않음 | 예 |
| `.env.dev` | 맥북 프로젝트 맨 위 | 실제 개발 설정·비밀값 | dev.sh를 통한 Compose, 일부 Python 도구 | 아니요 |
| `.env.prod.example` | 프로젝트 또는 서버 배포 묶음 | 운영 설정 작성 예시 | 사용자가 참고 | 예 |
| `.env.prod` | 서버 `/home/ubuntu/bizaid` | 실제 운영 설정·비밀값 | 명시적으로 선택한 운영 Compose | 아니요 |

현재 `.env.prod`는 아직 작성하지 않았다는 사용자 확인을 기준으로 합니다. 일반 `.env`나 과거 `.env.mysql.dev`는 사용하지 않습니다.

| 모양 | 읽는 프로그램 | 예 | 주의 |
| --- | --- | --- | --- |
| `.env` 파일의 `이름=값` | Compose·일부 Python 도구 | `MYSQL_PORT=3306` | 모든 항목이 모든 프로그램에 전달되는 것은 아님 |
| `.yml` 파일의 들여쓰기 | Compose 또는 Spring | `SPRING_PROFILES_ACTIVE: prod` | 파일 종류에 따라 읽는 프로그램이 다름 |
| `application-dev.yml` / `application-prod.yml` | Spring | DB 연결·로그·쿠키 정책 | 비밀값은 파일에 적지 않고 전달받음 |
| `${이름}` | Compose 또는 Spring | `${MYSQL_HOST}` | 실행할 때 해당 설정을 넣는 자리 |

Compose가 선택한 파일에서 값을 꺼내 **Compose에 적힌 항목만** 각 프로그램에 전달합니다. Spring은 `.env.dev`를 자동으로 찾아 읽지 않습니다. IntelliJ에서 Spring만 실행한다면 실행 설정에 필요한 값을 전달해야 합니다. 현재 프로젝트에 별도 자동 가져오기 설정은 없습니다. [Spring 공식 설정 설명](https://docs.spring.io/spring-boot/reference/features/external-config.html)

이미 터미널에서 같은 이름을 `export`했다면 그 값이 파일보다 앞섭니다. 파일을 바꿨는데 예상과 다르면 해당 이름의 이전 설정을 확인하세요. `env`, `printenv`, 값이 나오는 `docker inspect`, `docker compose config` 전체 출력은 공유하지 마세요. 설정 확인에는 `config --quiet`를 씁니다. [Docker 공식 설정 설명](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)

## 4. 개발 설정을 전부 예시와 똑같이 맞춰야 하나요?

**아니요.** 예시는 선택 가능한 설정까지 포함합니다. 현재 개발 파일은 이름 24개, 개발 예시는 30개입니다. 아래 6개가 개발 파일에 없지만 현재 개발 실행에서 필요한 기본값이 있습니다. 비밀값이 맞는지는 이번 이름 비교로 판단하지 않았습니다.

| 개발 파일에 없는 이름 | 현재 처리 | 추가가 꼭 필요한가 |
| --- | --- | --- |
| `QDRANT_URL` | Compose 안은 `http://qdrant:6333`, 직접 실행 기본은 `http://127.0.0.1:6333` | 주소를 바꿀 때만 |
| `OLLAMA_BASE_URL` | Compose 안은 맥북 Ollama 주소로 고정, 직접 실행 기본은 `http://127.0.0.1:11434` | 직접 실행 주소를 바꿀 때만 |
| `OLLAMA_TIMEOUT_SECONDS` | Compose 기본 300이라도 제품 코드가 75초 이하로 제한 | 의도 표시용으로 75를 넣을 수 있음; 현재 수정하지 않음 |
| `REFRESH_COOKIE_SECURE` | 개발 기본 `false`; 개발 Compose는 이 항목을 전달하지 않음 | 직접 Spring 실행에서 변경할 때만 |
| `LANGSMITH_PROJECT` | 비어 있으면 `biz-aid` | 다른 기록 프로젝트를 선택할 때만 |
| `LANGSMITH_ENDPOINT` | SDK 기본 주소 | 다른 기록 서버를 사용할 때만 |

운영 예시에 `LLM_PROVIDER`, `REFRESH_COOKIE_SECURE`가 없는 것은 누락 오류가 아닙니다. 운영 Compose가 Bedrock을 고정하고, Spring 운영 설정이 HTTPS 쿠키를 `true`로 고정합니다. Bedrock이 실패해도 Ollama로 바뀌지 않습니다.

개발의 `QDRANT_COLLECTION_NAMESPACE=v2`는 저장소 이름을 만드는 구분값입니다. 운영의 `QDRANT_COLLECTION`은 **완성된 이름 전체**입니다. 운영에는 `bizaid_v2_chunks_v1_228acdd12220`을 씁니다. 둘을 같은 이름으로 바꾸지 마세요.

## 5. 맥북 개발 환경 사용하기

먼저 Docker Desktop을 켜고 터미널을 여세요. 아래 첫 명령으로 프로젝트 폴더에 들어갑니다.

```bash
cd ~/IdeaProjects/biz-aid-ai
scripts/dev.sh up
```

기존 `.env.dev`와 모델 폴더가 있어야 합니다. 기존 설정 파일을 예시로 덮어쓰지 마세요.

| 하고 싶은 일 | 복사할 명령 | 뜻 |
| --- | --- | --- |
| 켜기·중지 후 다시 켜기 | `scripts/dev.sh up` | 개발 프로그램 5개 실행; 기존 데이터 유지 |
| 실행 상태 | `scripts/dev.sh status` | 어떤 프로그램이 켜졌는지 확인 |
| 끄기 | `scripts/dev.sh down` | 개발 컨테이너를 내림; DB·검색 자료 보관 공간은 삭제하지 않음 |
| AI 서버만 다시 시작 | `scripts/dev.sh restart fastapi` | AI 서버를 다시 실행 |
| Spring 다시 시작 | `scripts/dev.sh restart backend` | 서비스 서버를 다시 실행 |
| 화면 서버 다시 시작 | `scripts/dev.sh restart frontend` | 화면 서버를 다시 실행 |
| Spring 로그 | `scripts/dev.sh logs backend` | 최근 기록부터 계속 보기; `Ctrl+C`는 로그 보기만 종료 |
| AI 로그 | `scripts/dev.sh logs fastapi` | AI 실행 기록 보기; 공유 전 개인정보·비밀 제거 |
| 화면을 새로 만들기 | `scripts/dev.sh build frontend` | 현재 화면 코드로 개발 이미지 생성 |
| Spring을 새로 만들기 | `scripts/dev.sh build backend` | 현재 Java 코드로 개발 이미지 생성 |

개발의 화면·Spring 코드는 이미지에 들어갑니다. 코드나 전달 설정을 바꾼 후에는 `restart`만으로 이미지·환경변수가 갱신되지 않습니다. 다음은 화면을 다시 만든 뒤 새 이미지로 교체하는 명령입니다.

```bash
scripts/dev.sh build frontend
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file .env.dev --profile app -f docker-compose.yml up -d --force-recreate frontend
```

Spring을 바꿨다면 위 두 명령의 `frontend`를 `backend`로 바꾸세요. FastAPI의 개발 소스는 연결된 폴더에서 읽고 자동 재시작합니다. Python 설치 목록을 바꿨다면 `build fastapi` 후 해당 컨테이너를 교체해야 합니다.

| 확인 | 주소·명령 | 기대 결과 |
| --- | --- | --- |
| 화면 | http://localhost:3000 | 소개·로그인 화면 |
| 서비스 서버 상태 | `curl -fsS http://127.0.0.1:8080/api/health` | 정상 상태 응답 |
| AI 서버 상태 | `curl -fsS http://127.0.0.1:8000/health` | 정상 상태 응답; AI 질문 성공까지 증명하는 것은 아님 |
| 개발 Spring API 설명 | http://127.0.0.1:8080/swagger-ui/index.html | 개발에서만 제공 |
| 개발 FastAPI 설명 | http://127.0.0.1:8000/docs | 개발에서만 제공 |

### 자주 나는 오류

| 증상 | 먼저 할 일 | 하지 말아야 할 일 |
| --- | --- | --- |
| Docker 연결 실패 | Docker Desktop 실행 후 `scripts/dev.sh status` | DB 보관 공간 삭제 |
| `.env.dev가 없습니다` | 기존 파일 위치 확인; 처음 준비할 때만 개발 예시 참고 | 운영 파일을 개발 파일 대신 사용 |
| `BGE-M3 모델 artifact가 없습니다` | 기존 `~/.cache/biz-aid/docling-artifacts` 모델 준비 상태 확인 | 임의 폴더를 만들어 오류만 숨기기 |
| 3306·3000·8080 등이 사용 중 | `docker ps`로 현재 컨테이너 확인; 사용 주체 확인 | 다른 DB·프로세스를 무조건 종료 |
| DB 인증 실패 | DB 계정과 파일의 비밀번호가 같은지 본인이 확인 | 파일 비밀번호만 바꿔 서버 계정도 바뀌었다고 생각하기 |
| 화면은 되는데 AI만 실패 | FastAPI 상태·로그 확인, Bedrock 로그인 또는 Ollama 상태 확인 | DB 초기화·자료 재적재 |
| Ollama 경고가 뜨지만 현재 Bedrock 사용 | dev.sh가 Ollama 연결을 항상 확인하는 경고임 | 경고만 보고 전체 프로그램 실패로 판단 |
| 화면/API에서 502 | backend 상태 확인 후 frontend 다시 시작 | 프론트엔드 API 주소를 FastAPI로 바꾸기 |
| 설정 변경이 반영 안 됨 | 프로그램 다시 생성 여부·터미널의 같은 이름 설정 확인 | 비밀이 포함된 설정 전체 출력·공유 |

## 6. AI 답변 없이도 사용할 수 있나요?

**화면·로그인·기업정보·공고 목록은 AI 답변을 호출하지 않고 사용할 수 있습니다.** `scripts/dev.sh up` 후 AI 검색·맞춤 추천 버튼을 누르지 않으면 됩니다. Ollama 실행이나 Bedrock 호출 없이 이 기능들을 확인할 수 있습니다.

AI 서버까지 띄우지 않으려면 다음처럼 개발 DB·Spring·화면만 지정해서 켤 수도 있습니다. 이미 실행 중인 FastAPI를 이 명령이 중지하지는 않습니다.

```bash
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file .env.dev --profile app -f docker-compose.yml up -d mysql backend frontend
```

이 경우 AI 기능은 사용할 수 없습니다. `LLM_PROVIDER=none` 같은 설정은 지원하지 않습니다. 서버 코드를 바꾸거나 운영 보안을 꺼서 실행할 필요는 없습니다.

## 7. 운영을 맥북에서 미리 시험할 수 있나요?

별도 DB·검색 저장소를 만드는 `scripts/rehearse_prod.py`가 있습니다. 이미지 저장소, 서비스별 태그 3개, 플랫폼을 지정할 수 있으며 ARM 이미지에 고정되어 있지 않습니다. 실행 전 해당 이미지를 준비해야 합니다. 이 도구는 실제 Bedrock 호출과 자료 복사를 하므로 일반 환경 확인 명령이 아닙니다. 맥북 Docker Desktop에서는 Ubuntu의 파일 권한 문제를 재현하지 못할 수 있습니다. 실행 인자는 [배포 설명서](deployment.md)를 참고하세요.

| 기존 리허설에서 확인한 것 | 아직 그 결과로 보장할 수 없는 것 |
| --- | --- |
| 당시 localhost에서 소개·체험·AI 질문·Top 3 처리 | 최신 amd64 이미지의 전체 동작 |
| 별도 MySQL·Qdrant 복원 | 실제 RDS 인증서·EC2 권한·도메인 HTTPS |
| 5명·10명 동시 요청 결과 | 실제 2 CPU 운영 서버의 속도 |
| localhost HTTP 요청 | 실제 HTTPS의 로그인 유지 쿠키 동작 |

설정 형식만 확인할 때는 서버에서 작성한 파일로 다음 명령을 씁니다. 프로그램을 시작하거나 AI를 부르지 않습니다. 인증서·모델·실제 자료가 준비됐는지까지 확인하는 명령은 아닙니다.

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml config --quiet
```

## 8. 서버 `.env.prod` 작성하기

서버에는 전체 소스가 아니라 배포 묶음을 풉니다. `/home/ubuntu/bizaid`에 배포 파일이 있다는 전제입니다. 아직 파일이 없을 때만 예시를 복사합니다.

```bash
cd /home/ubuntu/bizaid
test -e .env.prod || cp .env.prod.example .env.prod
chmod 600 .env.prod
nano .env.prod
```

`이름=값` 한 줄에 하나씩 적습니다. `nano`에서 저장은 `Ctrl+O` → Enter, 종료는 `Ctrl+X`입니다. 아래 비밀값 네 칸은 직접 채우세요. **AWS 접근 키는 넣지 않습니다.** 서버에 부여된 AWS 권한을 프로그램이 사용합니다.

### 비밀값 네 개

아래 생성 명령은 본인이 비공개 터미널에서 실행하는 안내입니다. 이번 점검에서 실행하거나 값을 생성하지 않았습니다. 결과를 채팅·보고서·Git에 넣지 마세요.

| 이름 | 무엇을 넣나 | 준비 방법 |
| --- | --- | --- |
| `MYSQL_PASSWORD` | RDS의 `bizaid_app` 계정에 이미 설정한 비밀번호 | **기존 서버 비밀번호 그대로**; 임의 새 값 입력 금지 |
| `JWT_SECRET` | 로그인 확인용 긴 비밀값 | 처음 만들 때 `openssl rand -hex 32`; 결과 64글자 입력 |
| `INTERNAL_AI_API_KEY` | Spring·FastAPI가 서로 확인하는 비밀값 | 별도로 `openssl rand -hex 32`; JWT 값과 다르게 생성 |
| `MYSQL_TRUSTSTORE_PASSWORD` | DB 인증서 묶음 파일을 만드는 비밀번호 | 처음 만들 때 `openssl rand -hex 24`; 인증서 준비 과정에도 **동일한 값** 입력 |

DB 비밀번호를 새로 정해야 하는 상황이면 RDS 계정 비밀번호와 파일을 본인이 함께 맞춰야 합니다. 파일만 바꿔도 DB 계정은 바뀌지 않습니다. 이미 사용 중인 로그인 비밀값을 바꾸면 기존 로그인에 영향을 줍니다.

### 비밀이 아닌 칸별 설정

| 이름 | 넣을 값·뜻 | 누가 사용하나 |
| --- | --- | --- |
| `MYSQL_HOST` | `bizaid-db.cb0ek4accq15.ap-southeast-2.rds.amazonaws.com` | Spring·FastAPI·DB 복원 도구 |
| `MYSQL_PORT` | `3306` | 위 프로그램 |
| `MYSQL_DATABASE` | `bizaid` | 위 프로그램 |
| `MYSQL_USER` | `bizaid_app` | 위 프로그램 |
| `MYSQL_SSL_MODE` | `VERIFY_IDENTITY`; 연결 암호화와 서버 이름 확인 | Spring·FastAPI·복원 도구 |
| `MYSQL_TLS_CERTS_PATH` | `/home/ubuntu/bizaid/certs`; 서버의 인증서 폴더 | Compose가 컨테이너에 연결 |
| `MYSQL_SSL_CA` | `/certs/rds-ca.pem`; FastAPI 안의 인증서 위치 | FastAPI |
| `MYSQL_TRUSTSTORE_URL` | `file:/certs/rds-ca.p12`; Spring용 인증서 묶음 위치 | Spring |
| `MYSQL_TRUSTSTORE_TYPE` | `PKCS12` | Spring |
| `QDRANT_URL` | `http://qdrant:6333`; 같은 서버 안 검색 저장소 | FastAPI |
| `QDRANT_COLLECTION` | `bizaid_v2_chunks_v1_228acdd12220`; 이름 전체 | FastAPI |
| `BIZAID_MODEL_PATH` | `/home/ubuntu/bizaid/models`; 모델 자료 폴더 | Compose가 FastAPI의 `/models`에 연결 |
| `BIZAID_IMAGE_REPO` | `nagt1997/bizaid`; 실제 Docker Hub 저장소 | Compose |
| `BIZAID_FRONTEND_TAG` | 화면 이미지 태그; 첫 전환은 `20261005-03` | Compose, 비어 있으면 실패 |
| `BIZAID_BACKEND_TAG` | 서버 본체 이미지 태그; 첫 전환은 `20261005-03` | Compose, 비어 있으면 실패 |
| `BIZAID_FASTAPI_TAG` | AI 서버 이미지 태그; 첫 전환은 `20261005-03` | Compose, 비어 있으면 실패 |
| `BIZAID_IMAGE_PLATFORM` | `linux/amd64`; 실제 서버 CPU 종류 | Compose |
| `CADDY_SITE` | `biz-aid.cloud`; DNS 연결도 필요 | Caddy |
| `CADDY_HTTP_BIND` | `0.0.0.0:80`; 외부 접속 입구 | Compose |
| `CADDY_HTTPS_BIND` | `0.0.0.0:443`; 암호화 접속 입구 | Compose |
| `BEDROCK_MODEL_ID` | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | FastAPI |
| `BEDROCK_REGION` | `ap-northeast-2`; AI 호출 주소 | FastAPI |
| `AWS_REGION` | `ap-southeast-2`; 일반 AWS 설정 | FastAPI에 전달 |
| `FASTAPI_WORKERS` | `1`; AI 서버 실행 개수 | Compose 시작 명령 |
| `BIZAID_TRIAL_ENABLED` | `true`; 체험 허용 | Spring |
| `BIZAID_AI_DAILY_LIMIT` | `10`; 계정별 하루 AI 횟수 | Spring |
| `BIZAID_AI_DAILY_LIMIT_PER_IP` | `30`; 같은 네트워크 하루 AI 횟수 | Spring |
| `BIZAID_AI_GLOBAL_DAILY_LIMIT` | `300`; 서비스 전체 하루 AI 횟수 | Spring |
| `BIZAID_SIGNUP_PER_IP_PER_DAY` | `5`; 같은 네트워크 하루 회원가입 수 | Spring |
| `AWS_S3_BUCKET` | 예시의 시드니 버킷 이름 | **현재 운영 Compose는 전달하지 않음**; 자료 이사 명령용 참고 |
| `AWS_S3_PREFIX` | `biz-aid/documents`; 기존 원본 문서 위치 | **현재 운영 Compose는 전달하지 않음**; 배포 자료의 `deploy/<태그>/`와 다름 |

마지막 두 항목을 파일에 적는 것만으로 S3 이사 명령에 자동 적용되지 않습니다. 실제 이사 명령은 [운영 설명서](deployment.md)의 공개 버킷·태그 지정 단계를 따릅니다. 현재 운영 서비스에는 자동 공고 갱신이 없어서 `BIZINFO_SERVICE_KEY`가 필요하지 않습니다.

### 비밀번호의 특수문자는 어떻게 하나요?

MySQL이 아래 문자를 무조건 금지하는 것은 아닙니다. **설정 파일을 읽는 방식에서 다른 뜻으로 해석될 수 있으므로**, 새 비밀값은 위처럼 숫자와 `a`~`f`만 나오는 생성 방식을 권합니다. 기존 비밀번호를 임의로 바꾸지는 마세요.

| 문자 | 생길 수 있는 문제 | 처리 |
| --- | --- | --- |
| `$` | 다른 설정 이름으로 바꿔 읽을 수 있음 | 운영 Compose 파일에서는 값 전체를 일반 작은따옴표로 감싸면 문자 그대로 읽음 |
| `#` | 앞에 띄어쓰기가 있으면 뒤가 설명으로 처리될 수 있음 | 값 전체를 작은따옴표로 감쌈 |
| 띄어쓰기 | 앞뒤 공백이 사라지거나 입력 실수 발생 | 필요하면 값 전체를 작은따옴표로 감쌈 |
| `"` | 큰따옴표 값의 시작·끝과 충돌 | 작은따옴표로 감싸면 큰따옴표를 보존 |
| `\` | 큰따옴표 안에서 다른 문자로 바뀔 수 있음 | 작은따옴표로 감싸면 일반 역슬래시를 보존 |
| `'` | 작은따옴표의 끝과 충돌 | Compose 문법의 이스케이프가 필요; 아래 주의 참조 |

Compose는 작은따옴표 안의 `\'`를 작은따옴표로 읽습니다. 다만 프로젝트의 직접 실행 Python 도구는 이 변환을 하지 않습니다. 따라서 복잡한 비밀번호를 개발 도구와 Compose 양쪽에 같은 표현으로 복사하지 마세요. `$$`로 일괄 바꾸는 방법도 모든 파일에 통하는 해결책이 아닙니다. 처리 규칙의 근거는 [Docker 공식 문법](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)입니다.

작은따옴표를 써야 할 때는 키보드의 일반 문자 `'`를 씁니다. 메모 앱에서 바뀐 둥근 따옴표 `‘ ’`는 쓰지 않습니다. 비밀번호를 명령 뒤에 직접 붙이거나 `.env.prod`를 `source`로 실행하지 마세요. 파일 안에 적고 Compose가 읽게 합니다.

## 9. 서버 시작 전에 확인할 순서

| 순서 | 확인 | 설명 |
| --- | --- | --- |
| 1 | 운영 이미지 3개가 Docker Hub에 있는가 | 맥북에서 만들어 올린 태그와 파일의 태그 일치 |
| 2 | `.env.prod` 비밀 네 칸이 준비됐는가 | DB 비밀번호·인증서 묶음 비밀번호의 실제 일치 확인 |
| 3 | 인증서 파일 2개가 준비됐는가 | 공개 CA PEM과 Spring용 p12; 만드는 명령은 운영 설명서 §4 |
| 4 | 자료 이사 묶음이 서버에 있는가 | 공고 DB·V2 검색 자료·모델 파일 |
| 5 | 설정 형식 검사 | `docker compose --env-file .env.prod -f docker-compose.prod.yml config --quiet` |
| 6 | DB 표 먼저 생성하고 공고 복원 | 운영 설명서 §5; 개발 DB 주소를 넣지 않음 |
| 7 | V2 검색 자료 복원·모델 확인 | 빈 검색 저장소에서는 AI 서버가 시작을 거부함; 기대 검색 조각 60,362개 |
| 8 | 전체 프로그램 시작 | 자료 복원 후 운영 Compose `up -d` |
| 9 | 실제 화면·로그인 유지·체험 확인 | DNS·HTTPS 확인; 질문 시험은 실제 AI 비용 발생 |

서버에서 같은 Docker 내부 주소 `http://qdrant:6333`, `http://fastapi:8000`을 쓰는 것은 맥북 DB를 쓰는 것이 아닙니다. **그 서버의 같은 실행 묶음 안 프로그램**을 가리킵니다. 외부 공개 주소는 Caddy의 HTTPS 주소입니다.

운영 설정을 바꾼 후에는 `restart` 대신 운영 Compose의 `up -d`로 필요한 컨테이너를 다시 생성해야 합니다. 사용자 데이터 삭제 명령인 `down -v`나 DB 초기화는 사용하지 않습니다.

## 10. 이 설명서의 확인 범위

이번에는 코드·설정·현재 컨테이너·로컬 운영 이미지의 내용을 읽기 전용으로 점검했습니다. AWS 접속·실제 AI 호출·운영 리허설·전체 검증 명령은 실행하지 않았습니다. 실제 서버의 RDS 연결·권한·HTTPS·응답 속도는 배포 단계에서 확인해야 합니다.
