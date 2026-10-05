# BizAid 운영 배포 설명서

실제 서버는 **Ubuntu24.04 x86_64(linux/amd64), 메모리8GB + swap2GB, Docker29 / Compose5**다.
EC2·RDS·S3는 **시드니(ap-southeast-2)**, DB는 **RDS MySQL8.4.9**다. Bedrock 호출만 서울(ap-northeast-2)의 global 추론 프로필을 사용한다. 저장소 전체를 서버에 복사하지 않는다.
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

새 태그를 쓴다. 기존 ARM 이미지와 태그를 재사용하지 않는다. 데이터는 CPU 종류와 무관하므로 이미 만든02자료를 그대로 사용한다.

```bash
export BIZAID_IMAGE_REPO='DockerHub사용자명/비공개저장소명'
export BIZAID_IMAGE_TAG='20261005-03'
export DEPLOY_DATA_DIR='/private/tmp/bizaid-deploy-data-20261005-02'
export DEPLOY_KIT='/private/tmp/bizaid-deploy-kit-20261005-04.tar.gz'
export AWS_REGION='ap-southeast-2'
export AWS_S3_BUCKET='amazon-s3-biz-aid-bucket-695694684371-ap-southeast-2-an'
export TRANSFER_S3_URI="s3://${AWS_S3_BUCKET}/deploy/${BIZAID_IMAGE_TAG}"

# 기존 데이터 재생성 없음. 배포 묶음만 이번 수정으로 새로 만든다(같은 출력 파일이면 생성 생략).
scripts/make_deploy_bundle.sh "$DEPLOY_KIT"
shasum -a 256 "$DEPLOY_KIT" "$DEPLOY_DATA_DIR/programs.sql" \
  "$DEPLOY_DATA_DIR/v2.snapshot" "$DEPLOY_DATA_DIR/models.tar.gz" "$DEPLOY_DATA_DIR/data-manifest.json"
# macOS 임시 자료는 영구 보관되지 않는다. 파일이 없다면 새 디렉터리에 준비하되 기존02자료를 덮어쓰지 않는다.
# .venv/bin/python scripts/prepare_deploy_data.py <새 디렉터리> --model-path "$HOME/.cache/biz-aid/docling-artifacts"

# 로컬 AWS profile은 위 prefix에 PutObject 권한이 있어야 한다(서버 role은 읽기만 가능).
aws login --profile bizaid-dev
for file in programs.sql v2.snapshot models.tar.gz data-manifest.json; do
  aws s3 cp "$DEPLOY_DATA_DIR/$file" "$TRANSFER_S3_URI/$file" --region "$AWS_REGION" --profile bizaid-dev
done
aws s3 cp "$DEPLOY_KIT" "$TRANSFER_S3_URI/deploy-kit.tar.gz" --region "$AWS_REGION" --profile bizaid-dev

# build-only는 push하지 않는다. Docker Desktop의 기존 buildx에서 ARM 맥북도 amd64를 만들 수 있다.
scripts/push_images.sh "$BIZAID_IMAGE_REPO" "$BIZAID_IMAGE_TAG" --build-only
# 사용자가 비공개 Hub 저장소를 만든 뒤 직접 로그인·push한다. login 입력창에만 토큰을 입력한다.
docker login --username 'DockerHub사용자명'
scripts/push_images.sh "$BIZAID_IMAGE_REPO" "$BIZAID_IMAGE_TAG"
```

기본 플랫폼은 `linux/amd64`다. 별도 ARM 서버를 쓸 때만 `--platform linux/arm64`와 운영 env의 `BIZAID_IMAGE_PLATFORM=linux/arm64`를 함께 지정한다.
Docker Desktop은 기본으로 CPU 변환 실행을 지원하지만 ARM 맥북의 amd64 컴파일은 느릴 수 있다([Docker 안내](https://docs.docker.com/build/building/multi-platform/)).
자료의 SHA(내용 확인용 지문)는 비밀값이 아니다. 업로드는 `deploy/<태그>/`에만 하고 기존 문서 `biz-aid/documents/`는 변경하지 않는다.
회원·기업·대화·체험·동의·활동·workflow·Flyway 이력·V1 collection은 이사하지 않는다.
덤프는 INSERT만 포함하고 복원 schema는 backend 이미지 안의 기존 Flyway로 만든다.

## 2. 이미 생성한 운영 환경과 남은 준비

- EC2: 시드니 Ubuntu24.04 x86_64,8GB RAM+swap2GB. 서버 홈은 /home/ubuntu다. 저장소 전체를 clone하지 않는다. 실제 부하는 배포 후 확인한다.
- RDS: 시드니 MySQL8.4.9, 호스트 `bizaid-db.cb0ek4accq15.ap-southeast-2.rds.amazonaws.com`,3306, 빈 DB `bizaid`(utf8mb4_0900_ai_ci), 서비스 계정 `bizaid_app`. 암호는 사용자만 .env.prod에 입력한다.
- S3: `amazon-s3-biz-aid-bucket-695694684371-ap-southeast-2-an`,시드니. 전달 경로는 `deploy/<태그>/`다.
- EC2 IAM Role: S3 GetObject·ListBucket, Bedrock Haiku4.5 호출. AWS 키 없이 기존 role을 쓴다. IMDSv2/hop limit2는 설정됨. role로 업로드하려고 하지 않는다.
- 네트워크: RDS3306은 EC2 보안그룹에서만 허용. 서버80/443 공개,22는 사용자 IP만.8080/8000/6333/6334는 공개하지 않는다.
- **DNS 연결은 아직이다.** biz-aid.cloud를 EC2 주소로 연결한 뒤 외부 HTTPS smoke를 실행한다. 연결 전의 Caddy 인증서 발급/공개 화면은 미완료로 구분한다.
- 서버 Docker29/Compose5는 설치됐다. 다음 설치 절차는 새 서버를 준비할 때만 참고한다. 이미 있는 프로그램·volume은 지우지 않는다.

## 3. Ubuntu 처음 설정

새 서버 기준이다. 기존 서비스가 있는 서버의 패키지/volume을 임의 제거하지 않는다.
[Docker 공식 Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)의 apt 저장소 방식을 따른다.

```bash
sudo apt update
sudo apt install -y ca-certificates curl unzip python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
# Ubuntu24.04 x86_64 고정 조건
printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nArchitectures: amd64\nSigned-By: /etc/apt/keyrings/docker.asc\n' | sudo tee /etc/apt/sources.list.d/docker.sources
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
# 여기서 SSH를 나갔다 다시 들어온다. docker 그룹은 서버 관리자 수준 권한이다.
```

```bash
# x86_64용 AWS CLI(이미 설치돼 있으면 설치 단계 생략). 인증은 EC2 role이 자동 제공한다.
curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
sudo /tmp/aws/install
mkdir -p "$HOME/bizaid/transfer" "$HOME/bizaid/certs"
cd "$HOME/bizaid"
export BIZAID_IMAGE_TAG='20261005-03'
export AWS_REGION='ap-southeast-2'
export AWS_S3_BUCKET='amazon-s3-biz-aid-bucket-695694684371-ap-southeast-2-an'
export TRANSFER_S3_URI="s3://${AWS_S3_BUCKET}/deploy/${BIZAID_IMAGE_TAG}"
aws s3 cp "$TRANSFER_S3_URI/deploy-kit.tar.gz" ./deploy-kit.tar.gz --region "$AWS_REGION"
# 맥북에서 기록한 bundle SHA와 반드시 대조한다.
sha256sum deploy-kit.tar.gz
tar -xzf deploy-kit.tar.gz
for file in programs.sql v2.snapshot models.tar.gz data-manifest.json; do
  aws s3 cp "$TRANSFER_S3_URI/$file" "transfer/$file" --region "$AWS_REGION"
done
```

## 4. RDS 인증서와 운영 설정

CA(서버 인증기관 인증서)는 공개 파일이다. [AWS RDS TLS 안내](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)를 참고한다.
아래는 실제 시드니 RDS의 공식 CA bundle이다. Spring은 PKCS12 신뢰저장소, FastAPI와 복원 client는 같은 bundle PEM을 사용한다.
배포 묶음에 이 설명서가 포함돼 서버에서도 그대로 따라 할 수 있다. 비밀값을 만들거나 예시에 적지 않는다.

```bash
# 예시를 복사해 비밀값을 직접 입력한다. 이미 .env.prod가 있으면 복사하지 않고 필요한 공개 값만 확인한다.
if [ ! -e .env.prod ]; then cp .env.prod.example .env.prod; fi
chmod 600 .env.prod
nano .env.prod
# 다음 프롬프트에는 .env.prod의 MYSQL_TRUSTSTORE_PASSWORD와 같은 값을 직접 입력한다.
curl -fsSL https://truststore.pki.rds.amazonaws.com/ap-southeast-2/ap-southeast-2-bundle.pem -o certs/rds-ca.pem
# 기존 truststore는 덮어쓰지 않는다. 실패/재실행 시 원인을 확인한다.
if [ -e certs/rds-ca.p12 ]; then echo "기존 신뢰저장소가 있어 중단합니다"; exit 1; fi
# Java 신뢰저장소에는 bundle의 인증서 각각을 넣는다(첫 인증서만 넣지 않음).
awk '/BEGIN CERTIFICATE/{n++} n{print > ("certs/rds-" n ".pem")}' certs/rds-ca.pem
read -rsp '신뢰저장소 비밀번호: ' RDS_STORE_PASSWORD; echo
export RDS_STORE_PASSWORD
docker run --rm -e RDS_STORE_PASSWORD -v "$PWD/certs:/certs" eclipse-temurin:21-jre sh -c \
  'for certificate in /certs/rds-[0-9]*.pem; do keytool -importcert -noprompt -alias "$(basename "$certificate")" -file "$certificate" -keystore /certs/rds-ca.p12 -storetype PKCS12 -storepass:env RDS_STORE_PASSWORD; done'
unset RDS_STORE_PASSWORD
# 인증서에는 비밀키가 없다. 컨테이너의 일반 사용자(uid10001)가 읽을 수 있게 한다.
chmod 755 certs
chmod 644 certs/*.pem certs/rds-ca.p12
```

**본인 값은 직접 입력하며 config 전체를 출력하거나 공유하지 않는다.** `docker compose config --quiet`는 확인만 한다.

| 설정 | 넣을 값의 의미 |
| --- | --- |
| BIZAID_IMAGE_PLATFORM | linux/amd64(서버 x86_64) |
| AWS_REGION / AWS_S3_BUCKET | ap-southeast-2 / 위 기존 시드니 버킷 |
| BIZAID_IMAGE_REPO / BIZAID_IMAGE_TAG | 맥북 push와 같은 Hub 저장소/이번 태그 |
| MYSQL_HOST / PORT / DATABASE / USER / PASSWORD | 위 시드니 RDS endpoint /3306/bizaid/bizaid_app/사용자 비밀번호 |
| MYSQL_SSL_MODE | VERIFY_IDENTITY |
| MYSQL_TLS_CERTS_PATH | 서버 절대 경로 /home/ubuntu/bizaid/certs |
| MYSQL_SSL_CA | 컨테이너 경로 /certs/rds-ca.pem |
| MYSQL_TRUSTSTORE_URL / TYPE / PASSWORD | file:/certs/rds-ca.p12 /PKCS12/위 keytool에 입력한 비밀번호 |
| BIZAID_MODEL_PATH | 서버 절대 모델 경로 /home/ubuntu/bizaid/models |
| QDRANT_URL / QDRANT_COLLECTION | http://qdrant:6333 / bizaid_v2_chunks_v1_228acdd12220 |
| JWT_SECRET / INTERNAL_AI_API_KEY | 사용자가 관리하는 충분히 긴 서로 다른 비밀값 |
| BEDROCK_MODEL_ID / REGION | global.anthropic.claude-haiku-4-5-20251001-v1:0 / ap-northeast-2 |
| FASTAPI_WORKERS | 1(8GB 서버 실제 처리량은 미검증) |
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
# backend만 독립 시작해 Flyway schema를 만든다. FastAPI 의존 실행은 잠시 생략한다.
prod up -d --no-deps qdrant backend
# 최대3분 backend health를 기다린다. 성공 후에만 덤프를 넣는다.
ready=false
for attempt in $(seq 1 36); do
  if docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.restore.yml --profile tools run --rm --no-deps -T http-tools --fail --silent --max-time 5 http://backend:8080/api/health >/dev/null; then ready=true; break; fi
  sleep 5
done
if [ "$ready" != true ]; then echo "backend health 실패: 복원하지 않음"; exit 1; fi
scripts/restore_deploy_data.sh programs transfer
scripts/restore_deploy_data.sh qdrant transfer
# 출력 point_count=60362를 확인한 뒤 모델을 풀고 모든 파일 checksum을 확인한다.
scripts/restore_deploy_data.sh models transfer --model-path "$PWD/models"
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
- 이미지 오류: Hub login/태그/amd64 확인. RDS 오류:보안그룹/DB이름/CA/인증서 경로. FastAPI 시작 거부: 모델 경로·V2 collection/point 수 확인. Bedrock 오류:role/global profile 권한·region·IMDSv2 확인. 같은 실패를 자동 반복하지 않는다.
- 운영 volume을 지우는 `down -v`, collection 삭제, DB reset은 금지한다. 개발 환경을 운영 Compose로 건드리지 않는다.
- 실제 서버의 TLS·HTTPS·IAM·부하/CPU credit는 배포 후 확인해야 한다. 맥북에서 amd64 build 성공은 실제 AWS E2E 완료가 아니다. swap은 부족한 RAM을 빠르게 늘려 주는 수단이 아니며 worker1을 유지한다.

[전체 프로젝트 설명](../PROJECT_MASTER_GUIDE.md) · [README](../README.md)
