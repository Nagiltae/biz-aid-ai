# BizAid 운영 배포 설명서

사용자 확인 기준으로 **2026-10-05 `https://biz-aid.cloud` 운영 배포 완료**, 이미지 태그는 **20261005-03 / linux/amd64**다. 서버는 Ubuntu 24.04 x86_64, 메모리 8GB + swap 2GB, Docker 29 / Compose 5다. EC2·RDS·자료 전달 S3는 시드니(ap-southeast-2), Bedrock 호출은 서울(ap-northeast-2)이다.

묶음7-1b는 화면·서버 본체·AI 서버의 이미지 태그를 따로 관리한다. **현재 서버를 새 설정 방식으로 전환할 때는 기존 이미지를 그대로 사용하며 빌드·push가 필요 없다.** 이후 앱 업데이트 때만 맥북에서 선택한 서비스를 빌드·push하고 서버에서는 pull한다. 서버에는 GitHub 연결이나 소스 빌드가 필요 없다. 이 문서의 서버 접속·업로드·설정 적용·smoke는 사용자가 직접 실행한다. 현재 서버 전환은 §8, 이후 업데이트는 §9를 따른다. www 인증서는 적용·확인 전까지 미확인 상태다.

명령은 일반 따옴표가 필요한 곳에만 ASCII 따옴표를 쓴다. 서버에서는 Bash를 사용하고 폴더는 공백 없는 `~/bizaid`로 둔다. 문서에서 복사한 둥근 따옴표(`“ ”`, `‘ ’`)를 명령에 넣지 않는다. 실제 `.env.prod` 내용, 로그인 토큰, 전체 Compose 설정을 출력하거나 공유하지 않는다.

## 1. 개발·운영과 셸 변수를 구분

| 구분 | 개발 | 운영 |
| --- | --- | --- |
| 실행 | scripts/dev.sh | prod 단축함수 / docker-compose.prod.yml |
| 설정 | .env.dev / 작성 견본 .env.dev.example | 서버의 .env.prod / 작성 견본 .env.prod.example |
| DB | 로컬 MySQL | RDS MySQL 8.4, VERIFY_IDENTITY |
| 검색 DB | 기존 개발 Qdrant | 서버 내부 Qdrant / 복원한 V2 |
| 앱 | 로컬 개발 코드 | 기존 태그의 이미지 pull |
| AWS 인증 | 사용자 로컬 SDK 인증 | EC2 IAM Role / 키 파일 mount 없음 |
| AI 추적 | 선택적 개발 추적 | 운영에서는 비활성화 |

Compose는 셸에서 export한 값을 `--env-file`의 같은 이름 값보다 먼저 사용한다. **자료 전달 변수는 DEPLOY_TAG, DEPLOY_REGION, DEPLOY_BUCKET, DEPLOY_S3로 구분한다.** 운영의 BIZAID_FRONTEND_TAG·BIZAID_BACKEND_TAG·BIZAID_FASTAPI_TAG·AWS_REGION 등을 서버 셸에 export해서 전달 변수로 쓰지 않는다.

```bash
export DEPLOY_TAG=20261005-03
export DEPLOY_REGION=ap-southeast-2
export DEPLOY_BUCKET=YOUR_TRANSFER_BUCKET
export DEPLOY_S3=s3://${DEPLOY_BUCKET}/deploy/${DEPLOY_TAG}
```

`YOUR_TRANSFER_BUCKET`은 사용자가 관리하는 실제 자료 전달 버킷으로 바꾼다. 원본 문서 경로와 자료 전달 `deploy/<태그>/`는 서로 다르다. `.env.prod.example`의 AWS_S3_BUCKET·AWS_S3_PREFIX는 운영 서비스에서 전달·사용하지 않아 제거했으며, 개발 파이프라인 설정은 그대로다.

서버의 `~/.bashrc`를 편집해서 다음 함수를 한 번만 넣는다. `"$@"`는 전달한 명령 인자를 그대로 보존하기 위한 필수 ASCII 따옴표다.

```bash
prod() { docker compose --env-file ~/bizaid/.env.prod -f ~/bizaid/docker-compose.prod.yml "$@"; }
```

새 SSH 세션에서 사용할 수 있다. 지금 세션은 `source ~/.bashrc`로 불러온다. 과거 방식으로 남아 있는 export가 있으면 아래 공개 설정 이름을 해제하고 운영 파일의 값을 사용한다. 다른 MYSQL_*·JWT_*·INTERNAL_AI_* 이름도 운영 파일과 겹치는 export를 만들지 않는다.

```bash
unset BIZAID_IMAGE_REPO BIZAID_FRONTEND_TAG BIZAID_BACKEND_TAG BIZAID_FASTAPI_TAG BIZAID_IMAGE_PLATFORM AWS_REGION AWS_S3_BUCKET AWS_S3_PREFIX
```

| 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| `type prod` | 함수 정의의 경로가 ~/bizaid 기준 |
| `prod config --quiet` | §8에서 서비스별 태그 3줄을 추가한 뒤 오류 없이 종료하며 설정값을 출력하지 않음 |
| 전달 변수 | DEPLOY_* 이름만 사용하고 운영 앱 변수와 겹치지 않음 |

## 2. 맥북에서 새 실행 묶음만 준비

현재 서버·이미지·모델·공고 자료를 다시 만들지 않는다. `make_deploy_bundle.sh`는 서버 실행 파일만 담고 소스·실제 설정·모델·DB 자료는 포함하지 않는다. 새 출력 이름을 써서 기존 묶음을 보존한다.

```bash
export DEPLOY_KIT=/private/tmp/bizaid-deploy-kit-20261005-7-1b.tar.gz
scripts/make_deploy_bundle.sh $DEPLOY_KIT
shasum -a 256 $DEPLOY_KIT
aws login --profile bizaid-dev
aws s3 cp $DEPLOY_KIT ${DEPLOY_S3}/deploy-kit-7-1b.tar.gz --region $DEPLOY_REGION --profile bizaid-dev
```

이전 배포의 `programs.sql`, `v2.snapshot`, `models.tar.gz`, `data-manifest.json`은 기존 전달 경로에 둔다. 자료가 로컬 임시 폴더에만 있다면 별도 보관하되 기존 원문과 지문(SHA)을 덮어쓰지 않는다. 기존 Docker Hub 태그를 그대로 사용한다.

| 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| 실행 묶음 생성 | `서버 실행 묶음 생성 완료` |
| 묶음 내용 | Compose 2개, Caddyfile, 운영 견본, 스크립트 4개, 배포 설명서(총 9개) |
| SHA 기록 | 64자리 지문과 파일 이름, 비밀값 없음 |
| S3 업로드 | deploy/20261005-03/deploy-kit-7-1b.tar.gz에 새 파일 업로드 |
| 이미지 | 기존 20261005-03 태그 유지; 빌드·push 없음 |

## 3. 서버·DNS·보안 그룹과 자료 확인

현재 서버에는 Docker 29 / Compose 5가 설치되어 있다. 기존 운영 서버의 패키지·서비스·volume을 지우지 않는다. 새 서버를 준비할 때만 [Docker Ubuntu 설치 안내](https://docs.docker.com/engine/install/ubuntu/)를 참고한다. 서버 IAM Role은 S3 자료 읽기와 승인된 Bedrock 모델 호출 권한을 사용한다. AWS 키 파일을 컨테이너에 넣지 않는다.

AWS 보안 그룹에서 서버의 **TCP 80과 443을 모두 외부에 허용**한다. 22는 관리자 IP만, RDS 3306은 서버 보안 그룹에서만 허용한다. 8080·8000·6333·6334는 공개하지 않는다. 서버 방화벽도 80/443을 막지 않아야 한다.

DNS의 대표 도메인과 www가 같은 서버를 가리켜야 한다. IPv6를 사용하지 않는 서버에 잘못된 AAAA 기록이 남아 있으면 인증서 발급이 실패할 수 있으므로 DNS 화면에서 함께 확인한다.

```bash
getent ahostsv4 biz-aid.cloud
getent ahostsv4 www.biz-aid.cloud
docker version --format '{{.Server.Version}}'
docker compose version
mkdir -p ~/bizaid/transfer ~/bizaid/certs
cd ~/bizaid
aws s3 cp ${DEPLOY_S3}/deploy-kit-7-1b.tar.gz deploy-kit-7-1b.tar.gz --region $DEPLOY_REGION
sha256sum deploy-kit-7-1b.tar.gz
```

맥북에서 기록한 묶음 SHA와 같을 때만 반영한다. **현재 운영 서버는 §8의 백업·전환 순서를 따른다.** 아래 직접 압축 풀기는 새 서버에 처음 설치할 때만 쓴다. 실제 `.env.prod`와 앱 이미지·자료는 압축에 없다. `prod` 함수는 별도 터미널에서도 ~/bizaid 경로를 사용한다.

```bash
tar -xzf deploy-kit-7-1b.tar.gz
```

**새 서버의 첫 복원에만** 기존 전달 자료를 받는다. 이미 공고·V2·모델을 복원한 운영 서버에서는 다음 다운로드·복원을 다시 실행할 필요가 없다.

```bash
for file in programs.sql v2.snapshot models.tar.gz data-manifest.json; do
  aws s3 cp ${DEPLOY_S3}/$file transfer/$file --region $DEPLOY_REGION
done
```

| 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| 대표 도메인·www DNS | 둘 다 의도한 서버 주소로 연결 |
| 서버 보안 그룹 | 80/443 외부 허용, 내부 앱 포트 비공개 |
| RDS 보안 그룹 | 서버에서 오는 3306만 허용 |
| 서버 묶음 SHA | 맥북의 지문과 일치 |
| 기존 운영 자료 | 삭제·재복원 없이 보존 |

## 4. RDS 신뢰저장소와 공개 인증서 권한

첫 설정이나 새 서버에서만 진행한다. 기존 `.env.prod`는 예시로 덮어쓰지 않는다. `.env.prod.example`의 YOUR_*와 example.com을 본인 설정으로 바꾸며 비밀값은 사용자만 입력한다.

```bash
cd ~/bizaid
if [ ! -e .env.prod ]; then cp .env.prod.example .env.prod; fi
chmod 600 .env.prod
nano .env.prod
```

아래는 시드니 RDS의 공개 인증기관 파일을 Java용 p12(신뢰저장소)로 만드는 실제 배포 방식이다. 비밀번호 추출 명령은 **사용자가 서버에서만 실행**하며 표준 출력으로 비밀번호를 내보내지 않는다. `set -x`를 켜지 않는다. 운영 파일의 비밀번호는 따옴표 없는 한 줄 값으로 입력한다.

```bash
mkdir -p certs
curl -fsSL https://truststore.pki.rds.amazonaws.com/ap-southeast-2/ap-southeast-2-bundle.pem -o certs/rds-ca.pem
if [ -e certs/rds-ca.p12 ]; then echo 기존_신뢰저장소가_있어_중단합니다; exit 1; fi
csplit -s -z -f certs/rds- -b %d.pem certs/rds-ca.pem /BEGIN/ {*}
export RDS_STORE_PASSWORD=$(grep ^MYSQL_TRUSTSTORE_PASSWORD= .env.prod | cut -d= -f2-)
if [ -z "$RDS_STORE_PASSWORD" ]; then echo 신뢰저장소_비밀번호를_먼저_입력하세요; exit 1; fi
for f in certs/rds-[0-9]*.pem; do
  n=$(basename $f .pem)
  docker run --rm --user $(id -u):$(id -g) -e RDS_STORE_PASSWORD -v $PWD/certs:/certs eclipse-temurin:21-jre keytool -importcert -noprompt -alias $n -file /certs/$n.pem -keystore /certs/rds-ca.p12 -storetype PKCS12 -storepass:env RDS_STORE_PASSWORD || { unset RDS_STORE_PASSWORD; exit 1; }
done
unset RDS_STORE_PASSWORD
chmod 755 certs
chmod 644 certs/*.pem certs/rds-ca.p12
```

`--user`를 지정해서 호스트 사용자 소유로 생성한다. 이미 root 소유 파일이 생겼다면 사용자 확인 후 소유권을 정리한다. 공개 CA와 p12에는 서버 비밀키가 없으며 일반 실행 사용자도 읽을 수 있게 한다. **같은 권한 명령을 실제 .env나 AWS 키 폴더에 쓰지 않는다.** [RDS 공식 TLS 안내](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)

이미지를 받은 뒤 인증서 폴더를 backend와 FastAPI 이미지의 **기본 실행 사용자**로 검사한다. 검사 컨테이너는 앱 서버를 실행하지 않고 파일을 모두 읽은 뒤 종료한다.

```bash
scripts/restore_deploy_data.sh certs certs
```

| 설정 | 의미 |
| --- | --- |
| BIZAID_IMAGE_REPO / BIZAID_IMAGE_PLATFORM | 기존 비공개 저장소 / linux/amd64 |
| BIZAID_FRONTEND_TAG | 화면 이미지 태그; 첫 전환은 20261005-03 |
| BIZAID_BACKEND_TAG | 서버 본체 이미지 태그; 첫 전환은 20261005-03 |
| BIZAID_FASTAPI_TAG | AI 서버 이미지 태그; 첫 전환은 20261005-03 |
| MYSQL_HOST / PORT / DATABASE / USER / PASSWORD | 본인 RDS 주소 / 3306 / 운영 DB 이름·계정·비밀번호 |
| MYSQL_SSL_MODE | VERIFY_IDENTITY |
| MYSQL_TLS_CERTS_PATH | 서버 절대 경로 /home/ubuntu/bizaid/certs |
| MYSQL_SSL_CA | /certs/rds-ca.pem |
| MYSQL_TRUSTSTORE_URL / TYPE / PASSWORD | file:/certs/rds-ca.p12 / PKCS12 / p12 생성 때 사용한 같은 비밀번호 |
| BIZAID_MODEL_PATH | /home/ubuntu/bizaid/models; 복원 목적지와 동일 |
| QDRANT_URL / COLLECTION | http://qdrant:6333 / 복원 manifest의 정확한 V2 collection 이름 |
| JWT_SECRET / INTERNAL_AI_API_KEY | 서로 다른 사용자 관리 비밀값 |
| BEDROCK_MODEL_ID / REGION | 승인된 global Haiku 4.5 모델 / ap-northeast-2 |
| AWS_REGION | FastAPI 기본 AWS 지역 ap-southeast-2 |
| FASTAPI_WORKERS | 1; 8GB 서버에서 무작정 늘리지 않음 |
| CADDY_SITE / HTTP_BIND / HTTPS_BIND | 대표 도메인 / 0.0.0.0:80 / 0.0.0.0:443 |
| BIZAID_TRIAL_ENABLED | true |
| BIZAID_AI_DAILY_LIMIT / PER_IP / GLOBAL_DAILY_LIMIT | 10 / 30 / 300 |
| BIZAID_SIGNUP_PER_IP_PER_DAY | 5 |

| 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| keytool | 각 인증서에 `Certificate was added to keystore` |
| `ls -ld certs` | drwxr-xr-x(755) |
| `ls -l certs/rds-ca.pem certs/rds-ca.p12` | -rw-r--r--(644), 호스트 사용자 소유 |
| 인증서 검사 | status=PASS, backend·fastapi 각각 uid=10001, readable_files가 양수 |

## 5. 첫 배포의 복원 순서와 모델 권한 확인

**이미 복원한 현재 운영 서버에서는 공고·Qdrant·모델 복원을 재실행하지 않는다.** 현재 모델은 다음 별도 검사만 실행할 수 있다. 이 명령은 모델 내용을 바꾸지 않고 폴더 755·파일 644를 맞춘 뒤 FastAPI 기본 사용자로 모든 파일을 읽는다.

```bash
cd ~/bizaid
scripts/restore_deploy_data.sh models-check models
scripts/restore_deploy_data.sh certs certs
```

새 빈 서버에 처음 배포할 때만 아래 순서를 사용한다. 빈 Qdrant에 FastAPI부터 올리면 시작 시 검사가 실패한다.

```bash
prod config --quiet
docker login --username YOUR_DOCKERHUB_USER
prod pull
scripts/restore_deploy_data.sh certs certs
prod up -d --no-deps qdrant backend
ready=false
for attempt in $(seq 1 36); do
  if docker compose --env-file ~/bizaid/.env.prod -f ~/bizaid/docker-compose.prod.yml -f ~/bizaid/docker-compose.restore.yml --profile tools run --rm --no-deps -T http-tools --fail --silent --max-time 5 http://backend:8080/api/health >/dev/null; then ready=true; break; fi
  sleep 5
done
if [ $ready != true ]; then echo backend_health_실패_복원하지_않음; exit 1; fi
scripts/restore_deploy_data.sh programs transfer
scripts/restore_deploy_data.sh qdrant transfer
scripts/restore_deploy_data.sh models transfer --model-path $PWD/models
prod up -d
```

복원은 SHA 확인 → 빈 목적지 확인 → 복원 → 개수·모델 파일 SHA 확인 순서다. 공고 6개 테이블은 모두 비어 있어야 하며 개수 오류는 COMMIT 전에 실패해 되돌린다. Qdrant는 동일 collection이 있으면 point 수가 0이어도 거절한다. 모델은 빈 목적지만 허용하고 링크·특수 파일을 거절한다.

모델 검사 실패 때는 모델을 자동 삭제하지 않는다. 출력의 service·파일 경로·이유를 확인하고 해결 후 `models-check`만 다시 실행한다. 서버에서 사용하는 실제 이미지 사용자는 Dockerfile의 bizaid(UID 10001)이며, 검사에서도 --user로 다른 사용자를 덮어쓰지 않는다.

| 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| 이미지 pull | 기존 frontend/backend/fastapi-20261005-03을 받음 |
| backend 준비 | /api/health가 정상 응답 후에만 공고 복원 |
| 공고 복원 | status=PASS, 6개 테이블 개수가 manifest와 일치 |
| V2 복원 | status=PASS, point_count가 manifest와 일치(이번 자료 60,362) |
| 모델 폴더 | drwxr-xr-x / 파일 -rw-r--r-- |
| 모델 읽기 검사 | status=PASS, fastapi uid=10001, readable_files 양수 |
| 인증서 읽기 검사 | backend·fastapi 각각 PASS |

## 6. Caddy 적용·www·smoke 확인

CADDY_SITE에는 `biz-aid.cloud`처럼 대표 도메인만 쓴다. Caddyfile이 대표 도메인과 `www.<대표 도메인>`을 함께 등록한다. www HTTPS 요청은 경로·조회 문자열을 보존해 대표 HTTPS 주소로 **301 영구 이동**한다. Caddy가 두 도메인의 인증서를 자동 발급·갱신하려면 DNS와 80/443 연결이 정상이어야 한다. [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https), [영구 이동 설정](https://caddyserver.com/docs/caddyfile/directives/redir)

Caddyfile은 파일 하나를 컨테이너에 연결한다. 압축 해제나 파일 통째 교체로 호스트 파일이 새로 생기면 기존 컨테이너가 예전 파일을 계속 볼 수 있다. **교체 후 Caddy만 다시 만든다. 단순 reload나 restart만으로 파일 연결이 갱신된다고 보장할 수 없다.** 인증서 저장 volume은 유지하며 앱 이미지 빌드나 앱 서비스 재시작은 필요 없다.

```bash
prod up -d --no-deps --force-recreate caddy
sha256sum Caddyfile
prod exec -T caddy sha256sum /etc/caddy/Caddyfile
prod exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
curl -sS -o /dev/null -w '%{http_code}\n' https://biz-aid.cloud/api/health
curl -sSI https://www.biz-aid.cloud/
curl -sSIL https://www.biz-aid.cloud/
scripts/smoke_prod.sh https://biz-aid.cloud
```

`curl -k`로 인증서 검사를 끄지 않는다. smoke는 체험 계정 1개와 **실제 AI 질문 1회**를 만든다. 자동 재시도하지 않으며 실패를 고친 뒤 담당자가 재실행 여부를 판단한다.

| 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| Caddy 재생성·파일 지문 | Caddy만 Recreated, 호스트·컨테이너 SHA의 첫 64자 일치 |
| Caddy validate | Valid configuration |
| 대표 /api/health | 200 |
| https://www.biz-aid.cloud/ | 인증서 오류 없이 HTTP 301, Location: https://biz-aid.cloud/ |
| www에서 이동 따라가기 | 최종 HTTP 200 |
| smoke | health·landing·trial·ai_query·usage 모두 PASS, 사용 횟수 1회 차감 |

## 7. 문제 해결·업데이트·백업·리허설 한계

| 문제 | 확인할 곳 | 대응 |
| --- | --- | --- |
| PermissionError /models/.../config.json, AI 500 | 모델 폴더 700 또는 파일 읽기 권한 | models-check models로 755/644와 실제 사용자 읽기 확인. 기존 모델 재복원·삭제는 하지 않음 |
| 인증서 PermissionError / p12 읽기 실패 | certs 755, pem·p12 644, 파일 소유자와 실제 mount 경로 | certs certs 검사. root 소유로 생성된 파일은 사용자 확인 후 소유권 정리 |
| smoke 실패 | stage, url, http_status, body_preview, reason | 실패한 단계부터 확인. body_preview는 비밀값을 가린 앞 300자이며 토큰·쿠키·요청 헤더는 출력하지 않음 |
| HTTP 상태가 null | 연결·DNS·시간 초과 등 응답 자체가 없는 경우 | 주소와 DNS, 보안 그룹, 서비스 상태를 확인 |
| www 인증서 발급 실패 | www DNS, 잘못된 AAAA, 80/443 보안 그룹·방화벽, Caddy 설정 적용 여부 | 두 도메인이 서버로 향하는지 확인. TLS 검사를 끄거나 앱 이미지를 재빌드하지 않음 |
| Caddy DNS/인증서 발급 지연 | DNS 전파와 인증기관 재시도·발급 제한 | 설정을 확인한 뒤 기다림; Caddy volume을 삭제하거나 발급을 반복하지 않음 |
| RDS 연결 실패 | 보안 그룹, DB 주소·이름, CA와 p12 비밀번호, VERIFY_IDENTITY | 공개 인증서 권한부터 확인하고 비밀값은 사용자만 점검 |
| Bedrock 호출 실패 | EC2 Role, 승인 모델 호출 권한, region, IMDSv2 | 키 파일을 새로 넣지 않고 기존 Role 권한 확인 |

smoke 실패 예시(진짜 응답이나 비밀값이 아닌 설명용 합성 예시):

```json
{"status":"FAIL","stage":"ai_query","url":"https://example.com/api/ai/query","http_status":500,"body_preview":"{\"code\":\"ai_service_unavailable\"}","reason":"HTTPError"}
```

서비스 상태는 `prod ps`로 확인한다. 오류 로그를 확인할 때 전체 설정·inspect 환경·인증 응답·개인정보 포함 로그를 공유하지 않는다. `down -v`, collection 삭제, DB reset은 사용하지 않는다. 이번 서버 정상 동작은 사용자 제공 사실이며 리허설·부하 검증 결과와 구분한다.

이미지 업데이트와 되돌리기는 §9의 서비스별 태그 절차를 따른다. 기존 데이터 복원은 반복하지 않는다. 되돌릴 때도 이미지와 이미 적용된 Flyway의 호환성을 먼저 확인한다.

RDS는 AWS 화면의 자동 백업·수동 snapshot을 사용한다. 회원 데이터 백업은 공고 덤프와 별도로 보관한다. V2는 새 이름으로 snapshot을 만들고 기존 백업을 덮어쓰지 않는다.

```bash
cd ~/bizaid
docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.restore.yml --profile tools run --rm --no-deps -T http-tools --fail --silent --max-time 180 -X POST http://qdrant:6333/collections/bizaid_v2_chunks_v1_228acdd12220/snapshots
export SNAPSHOT_NAME=RETURNED_SNAPSHOT_NAME.snapshot
mkdir -p backups
(set -o noclobber; docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.restore.yml --profile tools run --rm --no-deps -T http-tools --fail --silent --max-time 300 http://qdrant:6333/collections/bizaid_v2_chunks_v1_228acdd12220/snapshots/$SNAPSHOT_NAME > backups/$SNAPSHOT_NAME)
sha256sum backups/$SNAPSHOT_NAME
```

리허설 스크립트는 이미지 저장소·서비스별 태그·플랫폼을 인자로 받거나 BIZAID_IMAGE_REPO·BIZAID_FRONTEND_TAG·BIZAID_BACKEND_TAG·BIZAID_FASTAPI_TAG·BIZAID_IMAGE_PLATFORM 셸 설정에서 받는다. 맥북 프로젝트의 의존성이 설치된 .venv 환경을 사용한다. 선택한 이미지 3개를 미리 로컬에 준비해야 하며 기존 ARM 전용 이름이나 소스 build를 사용하지 않는다. 아래는 **실행 방식 설명이며 이번 작업에서는 리허설을 실행하지 않는다.** --execute는 실제 임시 DB·컨테이너·Bedrock 호출을 시작한다.

```bash
.venv/bin/python scripts/rehearse_prod.py --execute --image-repo YOUR_DOCKERHUB_USER/YOUR_PRIVATE_REPO --frontend-tag 20261005-03 --backend-tag 20261005-03 --fastapi-tag 20261005-03 --platform linux/amd64
```

**macOS Docker Desktop의 공유 폴더 권한은 Ubuntu 서버와 달라 서버의 PermissionError를 재현하지 못할 수 있다.** 맥북 리허설의 성공을 서버 권한 검사 통과로 대신하지 않는다. 복원 뒤 서버에서 이미지의 실제 실행 사용자로 읽기 검사와 HTTPS·www 확인을 별도로 수행한다. 이때도 worker는 1개로 유지하며 swap을 메모리 성능의 대체물로 보지 않는다.

| 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| 문제 대응 | 실패 단계와 파일 경로가 좁혀지고 비밀값 출력 없이 조치 |
| 백업 | 새로운 이름·지문으로 보존, 원본 덮어쓰기 없음 |
| 리허설 이미지 선택 | 지정한 저장소·태그·linux/amd64 사용 |
| 서버 최종 확인 | 모델·인증서 읽기 검사, 대표 HTTPS·www 이동·smoke를 따로 확인 |

## 8. 현재 운영 서버를 서비스별 태그 방식으로 전환

이번 전환에서는 이미지 3개를 모두 **20261005-03**으로 유지한다. §1의 DEPLOY_*와 prod 함수를 준비하고 §2에서 새 실행 묶음을 기존 S3 경로에 올린다. 기존 전달 자료·Docker 이미지·모델·DB·인증서 volume을 지우거나 다시 복원하지 않는다. `release.sh`는 맥북 전용이라 서버 묶음에 들어가지 않는다.

서버에서 §3처럼 새 묶음을 받아 SHA를 비교한다. 기존 파일은 별도 폴더에 보관하고, 압축은 임시 폴더에 먼저 푼다. 백업 폴더가 이미 있으면 멈춰 이전 백업을 보존한다.

```bash
cd ~/bizaid
mkdir -p backups
mkdir -m 700 backups/bundle7-1b || exit 1
cp -p .env.prod backups/bundle7-1b/.env.prod
chmod 600 backups/bundle7-1b/.env.prod
cp -p docker-compose.prod.yml Caddyfile backups/bundle7-1b/
cp -a scripts backups/bundle7-1b/
mkdir incoming-7-1b || exit 1
tar -xzf deploy-kit-7-1b.tar.gz -C incoming-7-1b
cp incoming-7-1b/docker-compose.prod.yml incoming-7-1b/docker-compose.restore.yml incoming-7-1b/Caddyfile incoming-7-1b/.env.prod.example .
cp -a incoming-7-1b/scripts/. scripts/
mkdir -p docs
cp incoming-7-1b/docs/deployment.md docs/
nano .env.prod
```

`.env.prod`에 다음 **공개 태그 3줄만 추가**한다. 다른 설정과 비밀값은 유지하며 견본 파일로 덮어쓰지 않는다. 과거 공통 태그 줄은 더 이상 읽지 않으므로 정리해도 된다. 백업은 서버 안에만 보관하고 업로드하거나 Git에 넣지 않는다.

```dotenv
BIZAID_FRONTEND_TAG=20261005-03
BIZAID_BACKEND_TAG=20261005-03
BIZAID_FASTAPI_TAG=20261005-03
```

서버 셸의 같은 이름 export를 §1의 unset으로 해제하고 검사한다. 전체 `prod config` 대신 아래 옵션을 사용하면 비밀값을 출력하지 않는다.

```bash
prod config --quiet
prod config --images
prod ps
prod up -d
prod ps
```

| 단계 | 정상이면 이렇게 보임 |
| --- | --- |
| 백업·파일 반영 | 기존 파일 백업 존재, .env.prod는 원래 파일 유지, 자료 재복원 없음 |
| 태그 추가 | 화면·서버 본체·AI 서버 모두 20261005-03 |
| config --quiet | 출력 없이 정상 종료; 태그 누락이면 해당 변수 이름과 이유로 실패 |
| config --images | 기존 저장소의 frontend/backend/fastapi-20261005-03; Qdrant·Caddy 이미지도 기존과 같음 |
| up -d 전후 | 앱 3개는 같은 이미지·설정이므로 기존 컨테이너 유지; 변경됐다면 다른 설정 변경 여부 확인 |

마지막으로 §6의 **Caddy 강제 재생성 → 호스트·컨테이너 파일 SHA 비교 → validate → 대표 HTTPS·www → smoke**를 실행한다. Caddy만 새 컨테이너가 되는 것은 의도한 결과이며, 인증서 volume은 그대로다. 태그 방식 전환에는 앱 이미지 재빌드·push가 없다. smoke는 AI 질문 1회를 실제 사용한다.

| 마지막 확인 | 정상이면 이렇게 보임 |
| --- | --- |
| Caddy 파일 연결 | 서버와 컨테이너 안 Caddyfile SHA 일치, validate 성공 |
| 대표 도메인·www | 대표 health 200, www 인증서 정상과 301 이동 |
| smoke | 5단계 모두 PASS |

## 9. 업데이트 배포: 필요한 서비스만 새 이미지로 교체

**서버를 §8 방식으로 전환한 뒤 사용한다.** 코드를 바꾸고 검토·검사·커밋까지 마친 상태에서 맥북의 릴리스 스크립트를 실행한다. 미커밋 변경이나 새 미추적 파일이 있으면 dry-run도 멈춘다. 이 스크립트는 Git commit/push나 서버 접속을 하지 않는다. Docker Desktop과 buildx, 비공개 저장소에 대한 Docker Hub 로그인·쓰기 권한이 필요하다.

```bash
docker login --username nagt1997
scripts/release.sh 20261006-01 backend --dry-run
scripts/release.sh 20261006-01 backend
```

예시 태그는 매번 새 이름으로 정한다. 기본 저장소는 `nagt1997/bizaid`다. 다른 저장소라면 **맥북에서만** BIZAID_IMAGE_REPO를 지정한다. 로그인 확인에는 기존 비공개 backend-20261005-03을 조회한다. 그 태그가 없어진 경우 맥북의 BIZAID_BACKEND_TAG를 조회 가능한 기존 backend 태그로 지정한다. 이 값은 로그인 검사 기준이며 새 릴리스 태그는 첫 번째 인자를 사용한다.

선택한 서비스만 linux/amd64로 만들고, 이미지에 현재 Git 커밋 번호를 `org.opencontainers.image.revision` 라벨로 기록한다. 모든 선택 태그가 비어 있는지 먼저 확인하고 push 직전에도 다시 확인한다. 이미 존재하는 태그는 중단하며 인증·통신 실패도 중단한다. **같은 서비스·태그를 동시에 릴리스하지 않는다.** dry-run은 계획만 표시하고 Docker·저장소에 접속하지 않으므로 로그인과 태그 존재 여부 검사는 실제 실행 때 한다. 실제 push가 실패하면 앞서 올라간 이미지는 보존하며 전체 성공 전에 서버를 적용하지 않는다. [Docker 이미지 조회](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/), [Docker 로그인](https://docs.docker.com/reference/cli/docker/login/)

| 맥북 단계 | 정상이면 이렇게 보임 |
| --- | --- |
| 로그인 | Login Succeeded; 토큰·비밀번호는 공유하지 않음 |
| dry-run | DRY-RUN, 선택한 서비스의 빌드·push 계획과 커밋 라벨; 실제 빌드·push 없음 |
| 실제 릴리스 | PASS와 선택한 서비스의 새 태그 줄·서버 명령 출력 |
| 다른 서비스 | 빌드·push 계획과 태그 변경 줄에 포함되지 않음 |

### 9-1. 서버 본체 하나만 배포

릴리스가 모두 성공한 뒤 서버에서 `.env.prod`의 해당 태그 줄만 바꾼다. 이전 태그를 별도로 기록해 두되 비밀값은 기록하지 않는다. 아래 예시에서 화면·AI 태그는 그대로다.

```bash
cd ~/bizaid
nano .env.prod
```

```dotenv
BIZAID_BACKEND_TAG=20261006-01
```

```bash
prod config --quiet
prod config --images
prod pull backend && prod up -d --no-deps backend
prod ps
scripts/smoke_prod.sh https://biz-aid.cloud
```

| 서버 단계 | 정상이면 이렇게 보임 |
| --- | --- |
| 태그·config | backend만 새 태그, frontend·fastapi는 기존 태그 |
| pull·up | backend만 교체, Qdrant·Caddy·나머지 앱은 유지 |
| smoke | health·landing·trial·ai_query·usage 모두 PASS |

### 9-2. 화면과 서버 본체를 함께 배포

화면과 서버 본체의 요청·응답 약속을 함께 바꿨다면 **두 태그를 함께 바꾸고 배포한다.** 서로 맞지 않는 버전을 따로 적용하지 않는다. 한 번의 릴리스에서는 선택한 서비스들이 같은 새 태그를 쓰며, 배포하지 않는 AI 서버 태그는 유지한다.

```bash
scripts/release.sh 20261006-02 frontend backend --dry-run
scripts/release.sh 20261006-02 frontend backend
```

성공 후 서버에서 다음 두 줄만 편집한다.

```dotenv
BIZAID_FRONTEND_TAG=20261006-02
BIZAID_BACKEND_TAG=20261006-02
```

```bash
prod config --quiet
prod config --images
prod pull frontend backend && prod up -d --no-deps frontend backend
prod ps
scripts/smoke_prod.sh https://biz-aid.cloud
```

| 단계 | 정상이면 이렇게 보임 |
| --- | --- |
| 맥북 | frontend·backend만 빌드·push 성공 |
| 서버 | 두 앱이 새 태그로 교체, fastapi 태그와 검색 자료 유지 |
| 확인 | smoke 모두 PASS, 화면에서 바꾼 기능도 직접 확인 |

fastapi만 또는 세 서비스를 모두 배포할 때도 같은 방식으로 서비스 이름과 해당 태그 줄을 지정한다. 서로 다른 시점에 만든 태그는 서비스별로 다른 값을 써도 된다.

### 9-3. 되돌리기와 적용 범위

문제가 생기면 **바꾼 서비스의 태그 줄만 기록해 둔 이전 값으로** 돌린다. 예를 들어 backend만 바꿨다면 다음 줄만 되돌린다.

```dotenv
BIZAID_BACKEND_TAG=20261005-03
```

```bash
prod config --quiet
prod pull backend && prod up -d --no-deps backend
prod ps
scripts/smoke_prod.sh https://biz-aid.cloud
```

화면·서버 본체를 함께 바꿨다면 두 태그를 함께 이전 값으로 돌리고 두 서비스를 지정한다. 이미지 태그를 돌려도 DB 구조와 검색 자료는 자동으로 되돌아가지 않는다.

| 주의·확인 | 해야 할 일 / 정상 결과 |
| --- | --- |
| DB 구조 변경(Flyway) 포함 | **배포 전에 RDS 수동 snapshot을 만들고 생성 완료를 확인**; 이전 이미지와 새 DB의 호환성도 먼저 확인 |
| 되돌리기 | 바꾼 서비스만 이전 이미지로 실행, smoke PASS; DB를 자동 삭제·복원하지 않음 |
| 검색 자료 재생성 필요 | 이 이미지 교체 절차만으로 처리할 수 없음; 별도 데이터 작업·검증·백업 절차를 먼저 준비 |
| 모델 변경 필요 | 새 모델 자료와 서버 읽기 권한 확인을 별도 준비; 기존 자료를 임의 덮어쓰지 않음 |
| 설정·Caddy만 변경 | 앱 이미지는 다시 만들지 않음; Caddy 파일 교체 시 §6대로 강제 재생성 |

[전체 프로젝트 설명](../PROJECT_MASTER_GUIDE.md) · [README](../README.md)
