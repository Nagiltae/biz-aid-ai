# BizAid 운영 배포 설명서

서버는 **Ubuntu24.04 ARM(t4g.large, linux/arm64)**, DB는 **RDS MySQL8.4**다. 저장소 전체를 서버에 복사하지 않는다.
Docker Hub 비공개 저장소1개에서 `frontend-태그`, `backend-태그`, `fastapi-태그` 이미지를 받는다.
이 문서의 login/push/S3 업로드/서버 변경은 **사용자가 직접 실행**한다. 비밀값은 명령·로그·Git에 넣지 않는다.

## 1. 개발과 운영은 분리

| 구분 | 개발(그대로 유지) | 운영 |
| --- | --- | --- |
| 실행 | scripts/dev.sh up | docker compose --env-file .env.prod -f docker-compose.prod.yml |
| Compose | docker-compose.yml | docker-compose.prod.yml; 일회성 복원은 docker-compose.restore.yml 추가 |
| 설정 파일 | .env.dev | .env.prod(서버에서 직접 작성) |
| profile | Spring dev / FastAPI dev | Spring prod / FastAPI BIZAID_ENV=prod |
| DB | 로컬 MySQL / 기존 volume | RDS MySQL8.4 / TLS로 서버 인증 |
| 검색 DB | 로컬 Qdrant / V1·V2 보존 | 서버 내부 Qdrant / V2만 복원 |
| 코드 | 로컬 build·개발 mount | 이미지 pull / 소스·reload 없음 |
| AWS 인증 | 기존 로컬 SDK 체계·사용자 AWS 로그인 | EC2 IAM Role / 키 파일 mount 없음 |
| 추적 | 기존 선택적 LangSmith | 설정과 무관하게 강제 off |

### 맥북에서 준비

새 태그와 새 출력 경로를 쓴다. 이미지 태그를 재사용하면 이전 버전으로 되돌리기 어렵다.

```bash
export BIZAID_IMAGE_REPO='DockerHub사용자명/비공개저장소명'
export BIZAID_IMAGE_TAG='20261005-01'
export DEPLOY_DATA_DIR='/private/tmp/bizaid-transfer-20261005-01'
export DEPLOY_KIT='/private/tmp/bizaid-deploy-20261005-01.tar.gz'

# 공고6테이블 덤프 + V2 snapshot + 모델 묶음 + 원본 개수/모델 파일 SHA/자료 SHA manifest
.venv/bin/python scripts/prepare_deploy_data.py "$DEPLOY_DATA_DIR" \
  --model-path "$HOME/.cache/biz-aid/docling-artifacts"
scripts/make_deploy_bundle.sh "$DEPLOY_KIT"
shasum -a 256 "$DEPLOY_KIT" "$DEPLOY_DATA_DIR/programs.sql" \
  "$DEPLOY_DATA_DIR/v2.snapshot" "$DEPLOY_DATA_DIR/models.tar.gz" "$DEPLOY_DATA_DIR/data-manifest.json"

# 기존5-2 도구를 개별로 실행할 수도 있다(위 wrapper와 중복 실행하지 않음).
# scripts/export_program_data.sh biz-aid-ai-mysql-1 <새.sql>
# scripts/snapshot_v2_qdrant.sh http://127.0.0.1:6333 bizaid_v2_chunks_v1_228acdd12220 <새.snapshot>
# scripts/prepare_model_bundle.sh <모델cache> <새.tar.gz>

# 사용자 AWS 로그인 후 기존 버킷의 이번 배포 전용 prefix를 지정한다.
aws login --profile bizaid-dev
export TRANSFER_S3_URI='s3://기존버킷/biz-aid/deploy/20261005-01'
for file in programs.sql v2.snapshot models.tar.gz data-manifest.json; do
  aws s3 cp "$DEPLOY_DATA_DIR/$file" "$TRANSFER_S3_URI/$file" --profile bizaid-dev
done
aws s3 cp "$DEPLOY_KIT" "$TRANSFER_S3_URI/deploy-kit.tar.gz" --profile bizaid-dev

# Docker Hub 개인 비공개 저장소는 사용자가 웹에서 미리 만든다. 토큰은 login 입력창에만 입력한다.
docker login --username 'DockerHub사용자명'
scripts/push_images.sh "$BIZAID_IMAGE_REPO" "$BIZAID_IMAGE_TAG"
```

`--build-only`를 마지막 인자로 붙이면 push 없이 ARM build만 한다. 자료의 SHA(내용 확인용 지문)는 비밀값이 아니다.
회원·기업·대화·체험·동의·활동·workflow·Flyway 이력·V1 collection은 이사하지 않는다.
덤프는 INSERT만 포함하고 복원 schema는 backend 이미지 안의 기존 Flyway로 만든다.

## 2. AWS 화면에서 먼저 준비

- EC2: Ubuntu24.04 ARM / t4g.large / 데이터·모델을 담을 충분한 EBS(예:40GB 이상). 실제 CPU credit·메모리는 배포 후 관측한다.
- RDS: MySQL8.4, 빈 DB와 앱 사용자, EC2 보안그룹에서만3306 허용. 외부 공개 DB로 열지 않는다.
- EC2 role: 필요한 Bedrock InvokeModel/InvokeModelWithResponseStream와 이번 전달 prefix S3 GetObject만. global inference profile의 대상 지역 권한도 확인한다.
- EC2 metadata([AWS 안내](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html)): IMDSv2 사용, 컨테이너가 role을 쓸 수 있도록 hop limit2를 확인한다. 서버에 AWS Access Key를 저장하지 않는다.
- 서버 보안그룹:80/443 공개,22는 사용자 IP만.8080/8000/6333/6334는 공개하지 않는다.
- DNS: biz-aid.cloud를 EC2 고정 주소로 연결. HTTPS는 Caddy가 자동 처리한다.
- S3/비공개 Hub는 기존 자원을 사용하며 자료 삭제·동기화 삭제 옵션은 사용하지 않는다.

## 3. Ubuntu 처음 설정

새 서버 기준이다. 기존 서비스가 있는 서버의 패키지/volume을 임의 제거하지 않는다.
[Docker 공식 Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)의 apt 저장소 방식을 따른다.

```bash
sudo apt update
sudo apt install -y ca-certificates curl unzip python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
# Ubuntu24.04 ARM 고정 조건
printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nArchitectures: arm64\nSigned-By: /etc/apt/keyrings/docker.asc\n' | sudo tee /etc/apt/sources.list.d/docker.sources
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
# 여기서 SSH를 나갔다 다시 들어온다. docker 그룹은 서버 관리자 수준 권한이다.
```

```bash
# ARM용 AWS CLI. 인증은 EC2 role이 자동 제공한다.
curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
sudo /tmp/aws/install
mkdir -p "$HOME/bizaid/transfer" "$HOME/bizaid/certs"
cd "$HOME/bizaid"
export TRANSFER_S3_URI='s3://기존버킷/biz-aid/deploy/20261005-01'
aws s3 cp "$TRANSFER_S3_URI/deploy-kit.tar.gz" ./deploy-kit.tar.gz
# 맥북에서 기록한 bundle SHA와 반드시 대조한다.
sha256sum deploy-kit.tar.gz
tar -xzf deploy-kit.tar.gz
for file in programs.sql v2.snapshot models.tar.gz data-manifest.json; do
  aws s3 cp "$TRANSFER_S3_URI/$file" "transfer/$file"
done
```

## 4. RDS 인증서와 운영 설정

CA(서버 인증기관 인증서)는 공개 파일이다. [AWS RDS TLS 안내](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)를 참고한다.
아래는 서울 RDS의 공개 CA bundle이다. RDS가 다른 지역이면 해당 지역 bundle을 받는다.

```bash
curl -fsSL https://truststore.pki.rds.amazonaws.com/ap-northeast-2/ap-northeast-2-bundle.pem -o certs/rds-ca.pem
# Java 신뢰저장소에는 bundle의 인증서 각각을 넣는다(첫 인증서만 넣지 않음).
awk '/BEGIN CERTIFICATE/{n++} n{print > ("certs/rds-" n ".pem")}' certs/rds-ca.pem
read -rsp '신뢰저장소 비밀번호: ' RDS_STORE_PASSWORD; echo
export RDS_STORE_PASSWORD
docker run --rm -e RDS_STORE_PASSWORD -v "$PWD/certs:/certs" eclipse-temurin:21-jre sh -c \
  'for certificate in /certs/rds-[0-9]*.pem; do keytool -importcert -noprompt -alias "$(basename "$certificate")" -file "$certificate" -keystore /certs/rds-ca.p12 -storetype PKCS12 -storepass:env RDS_STORE_PASSWORD; done'
unset RDS_STORE_PASSWORD
cp .env.prod.example .env.prod
chmod 600 .env.prod
nano .env.prod
```

**본인 값은 직접 입력하며 config 전체를 출력하거나 공유하지 않는다.** `docker compose config --quiet`는 확인만 한다.

| 설정 | 넣을 값의 의미 |
| --- | --- |
| BIZAID_IMAGE_REPO / BIZAID_IMAGE_TAG | 맥북 push와 같은 Hub 저장소/이번 태그 |
| MYSQL_HOST / PORT / DATABASE / USER / PASSWORD | RDS endpoint /3306/빈 DB/앱 사용자/사용자 비밀번호 |
| MYSQL_SSL_MODE | VERIFY_IDENTITY |
| MYSQL_TLS_CERTS_PATH | 서버 절대 경로 /home/ubuntu/bizaid/certs |
| MYSQL_SSL_CA | 컨테이너 경로 /certs/rds-ca.pem |
| MYSQL_TRUSTSTORE_URL / TYPE / PASSWORD | file:/certs/rds-ca.p12 /PKCS12/위 keytool에 입력한 비밀번호 |
| BIZAID_MODEL_PATH | 서버 절대 모델 경로 /home/ubuntu/bizaid/models |
| QDRANT_URL / QDRANT_COLLECTION | http://qdrant:6333 / bizaid_v2_chunks_v1_228acdd12220 |
| JWT_SECRET / INTERNAL_AI_API_KEY | 사용자가 관리하는 충분히 긴 서로 다른 비밀값 |
| BEDROCK_MODEL_ID / REGION | global.anthropic.claude-haiku-4-5-20251001-v1:0 / ap-northeast-2 |
| FASTAPI_WORKERS | 1(ARM 서버 실제 처리량은 미검증) |
| CADDY_SITE / HTTP_BIND / HTTPS_BIND | biz-aid.cloud / 0.0.0.0:80 / 0.0.0.0:443 |
| BIZAID_TRIAL_ENABLED | true |
| BIZAID_AI_DAILY_LIMIT / PER_IP / GLOBAL_DAILY_LIMIT | 10 /30 /300 |
| BIZAID_SIGNUP_PER_IP_PER_DAY | 5 |

## 5. 이미지 받기 → 빈 저장소 복원 → 시작

빈 Qdrant에 FastAPI부터 올리면 startup 검사가 정상적으로 거부한다. 다음 순서를 따른다.

```bash
cd "$HOME/bizaid"
docker login --username 'DockerHub사용자명'
# 단축함수: 항상 명시한 운영 env만 선택한다.
prod() { docker compose --env-file .env.prod -f docker-compose.prod.yml "$@"; }
prod config --quiet
prod pull
scripts/restore_deploy_data.sh models transfer --model-path "$PWD/models"
# backend만 독립 시작해 Flyway schema를 만든다. FastAPI 의존 실행은 잠시 생략한다.
prod up -d --no-deps qdrant backend
# 최대3분 backend health를 기다린다. 성공 후에만 덤프를 넣는다.
for attempt in $(seq 1 36); do
  if docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.restore.yml --profile tools run --rm --no-deps -T http-tools --fail --silent --max-time 5 http://backend:8080/api/health >/dev/null; then break; fi
  sleep 5
done
scripts/restore_deploy_data.sh programs transfer
scripts/restore_deploy_data.sh qdrant transfer
prod up -d
scripts/smoke_prod.sh https://biz-aid.cloud
```

복원 script는 SHA검증 → 빈 목적지 확인 → 복원 → 개수/모델 파일 checksum 대조 순서다.
공고는 backend health+schema 확인 후6개 테이블 모두 빈 경우에만 INSERT한다. 개수가 기대값과 다르면 COMMIT 전 임시 CHECK로 실패시켜 rollback한다.
Qdrant는 **같은 collection이 존재하면 point0이어도 거절**한다. 복원 실패한 collection은 증거로 남기고 자동 삭제/재복원하지 않는다.
모델도 비어 있는 목적지만 허용한다. manifest는 맥북 실측 개수를 사용하며 이번 V2 기대 point는60,362다.
복원 script는 서버에 mysql 프로그램을 설치하지 않고 mysql:8.4 일회성 client 컨테이너를 쓴다.
smoke는 체험 생성·실제 Bedrock 질문1회와 횟수 조회를 한다. 배포 담당 사용자가 실행하며 개발 Agent의 이번 검증에는 포함하지 않는다.

## 6. 업데이트·백업·문제 대응

- 업데이트: 맥북 새 태그 build/push → 서버 `.env.prod`의 BIZAID_IMAGE_TAG만 새 태그로 → `prod pull` → `prod up -d` → 사용자 smoke1회. 기존 데이터 복원 script는 재실행하지 않는다.
- rollback(이전 버전으로): 이전 태그로 돌아가 `prod pull; prod up -d`. 이미 적용된 Flyway는 되돌리지 않으므로 코드/DB 호환을 먼저 확인한다.
- 백업: RDS는 AWS 화면에서 자동 백업/수동 snapshot을 설정한다. 회원 데이터가 생긴 후의 백업은 공고용 덤프와 별개이며 공개하지 않는다. V2는 아래 명령으로 새 snapshot을 만든다(응답의 name을 다음 명령에 입력).

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.restore.yml --profile tools run --rm --no-deps -T http-tools --fail --silent --max-time 180 -X POST http://qdrant:6333/collections/bizaid_v2_chunks_v1_228acdd12220/snapshots
# 실제 반환된 snapshot name을 아래 변수에 넣는다. 기존 백업 파일을 덮어쓰지 않는다.
export SNAPSHOT_NAME='반환된-name.snapshot'
mkdir -p backups
(set -o noclobber; docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.restore.yml --profile tools run --rm --no-deps -T http-tools --fail --silent --max-time 300 "http://qdrant:6333/collections/bizaid_v2_chunks_v1_228acdd12220/snapshots/$SNAPSHOT_NAME" > "backups/$SNAPSHOT_NAME")
sha256sum "backups/$SNAPSHOT_NAME"
```

모델·전달 자료의 SHA와 원본은 보존한다.
- 상태: `prod ps`; 재시작: `prod restart backend fastapi`. 모델 변경은 worker 메모리/collection 계약을 다시 확인한다.
- 로그: `prod logs --tail 100 backend fastapi`; 전체 `config`, inspect 환경, 로그인 응답, 개인정보 포함 로그를 붙여넣지 않는다.
- 이미지 오류: Hub login/태그/ARM 확인. RDS 오류:보안그룹/DB이름/CA/인증서 경로. FastAPI 시작 거부: 모델 경로·V2 collection/point 수 확인. Bedrock 오류:role/global profile 권한·region·IMDSv2 확인. 같은 실패를 자동 반복하지 않는다.
- 운영 volume을 지우는 `down -v`, collection 삭제, DB reset은 금지한다. 개발 환경을 운영 Compose로 건드리지 않는다.
- 실제 서버의 TLS·HTTPS·IAM·부하/CPU credit는 배포 후 확인해야 한다. 맥북 ARM build 성공은 실제 AWS E2E 완료가 아니다.

[전체 프로젝트 설명](../PROJECT_MASTER_GUIDE.md) · [README](../README.md)
