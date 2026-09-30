# 개발 Infrastructure

Compose에는 기존 `phase0`, 승인된 dev DB profile `mysql` / `flyway`, dev-vector profile `qdrant`가 있다.
MySQL은 loopback 127.0.0.1:3306에서만 공개하며 컨테이너 내부도 3306이다. Flyway는 공통 migrations를 읽기 전용으로 mount한다.
MySQL 8.4 / Flyway 11을 사용한다. Flyway는 Apple Silicon에서도 linux/amd64로 실행한다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r data-pipeline/requirements.txt
.venv/bin/python -B infra/dev_mysql.py
```

마지막 명령은 `.env.dev`만 명시적으로 선택하며 사용자 설정을 생성·수정하지 않는다.
필수 값: MYSQL_DATABASE=biz_aid_dev, MYSQL_USER, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD.
MYSQL_HOST는 로컬 경계, MYSQL_PORT는 3306을 사용한다. Process Environment가 파일보다 우선한다.
파일이 없어도 Process Environment가 충분하면 실행되며 generic `.env`·다른 Profile fallback은 금지한다.
Compose는 `--env-file .env.dev` 또는 OS 주입 시 `--env-file /dev/null`을 사용하고 implicit env loading을 끈다.
prod의 설정 파일은 `.env.prod`지만 현재 DB 준비·제품 실행은 dev만 허용한다.
다른 주체가 Host 3306을 점유하면 기동 전에 실패하고 사용자 승인 전 자동 종료·삭제하지 않는다.
기존 프로젝트 MySQL의 포트 재구성은 `up -d`로 같은 volume을 연결하며 down -v / reset은 제공하지 않는다.
기존 volume의 계정·비밀번호는 환경파일 변경으로 자동 갱신되지 않는다. 사용자가 서버 계정도 일치시켜야 한다.
준비 도구는 기존 MYSQL_USER에 test DB 권한만 부여하며 계정 생성·비밀번호 변경은 하지 않는다.
root 준비 연결은 컨테이너 내부 127.0.0.1의 TCP로 명시한다. Unix socket 계정과 TCP 계정의 인증값이 다를 수 있다.
최초 DB 생성 SQL은 application schema를 소유하지 않는다. 실제 테이블은 공통 Flyway가 관리한다.
Docker 출력은 인증값 반사 시 전체를 제거하고 실패 출력은 보존하지 않는다. 새 로그는 `harness/workspace/artifacts/codex/infra-dev-mysql/logs/preparation.log`다. `docker compose config`의 Secret 값을 출력하지 않는다.
MySQL volume은 보존하며 Flyway clean / DB reset / prod / deployment는 제공하지 않는다.
`biz_aid_test`에는 명시적인 합성 fixture가 누적되고 실제 100건은 `biz_aid_dev`에만 저장한다.
컨테이너 DB 통신 TLS 해제와 public-key retrieval 허용은 로컬 dev network에만 적용한 설정이다.

공식 참고: [MySQL image](https://hub.docker.com/_/mysql),
[Flyway Docker](https://documentation.red-gate.com/fd/flyway-docker-321585710.html).

CI는 사용자 파일 없이 Process Environment에 공개 합성 test DB 설정을 주입한다. 실제 API / prod Secret은 사용하지 않는다.

HWP → PDF 변환 이미지(`infra/hwp-converter/Dockerfile`, LibreOffice headless + H2Orestart)는 host에 설치하지 않고 이 이미지로만 쓴다.
tag와 label은 Contract `routes.HWP.converter.dockerfile_sha256`와 같아야 하며 parser는 다른 이미지를 거부한다.

```sh
SHA=$(shasum -a 256 infra/hwp-converter/Dockerfile | cut -d' ' -f1)
docker build -t biz-aid/hwp-pdf-converter:${SHA:0:12} --label org.bizaid.dockerfile_sha256=$SHA infra/hwp-converter
```

dev Qdrant(`qdrant/qdrant:v1.19.1`)는 `docker compose --profile dev-vector up -d qdrant`로 띄운다. 127.0.0.1:6333에만 열고 volume `qdrant_dev`에 저장한다.
인증이 없으므로 loopback 밖에 열지 않는다(Harness Compose 검사가 강제). 내용은 다시 만들 수 있는 파생 index다.
