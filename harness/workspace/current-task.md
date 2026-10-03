# Current Task — IMP-017 FastAPI Compose 통합(+IMP-005)

## Goal / Context

2026-10-03 사용자 요청: FastAPI를 Docker 이미지로 만들어 기존 Compose에 넣고 명령 하나(`scripts/dev.sh`)로 개발 환경 전체를 올리고 내린다. 데이터(MySQL·Qdrant·S3)는 바꾸지 않는다.
사용자 결정:
1. 이미지는 질문 처리 전용이다. requirements를 질문 처리용(`requirements-api.txt`)과 파이프라인 전체용(`requirements.txt`, 앞 파일 포함)으로 나누고, 파싱·인덱싱 배치는 host에서 실행한다.
2. 모델 artifact는 host 폴더를 읽기 전용 mount하고, 질문 서버는 BGE-M3 범위만 검증한다(IMP-005).
3. Qdrant 주소는 loopback에 `http://qdrant:6333`만 추가 허용한다(규칙 변경).
4. Ollama는 host(`host.docker.internal:11434`)를 쓴다.
5. 개발 모드는 소스 읽기 전용 mount + `uvicorn --reload`이고, 의존성을 바꿨을 때만 재빌드한다.
6. `scripts/dev.sh`로 up / down / restart / logs / status / build를 제공한다.
Ollama 컨테이너화, 파싱 의존성을 이미지에 넣기, Qdrant·MySQL 데이터 변경, 재파싱·재적재, V1 collection·baseline, `.env.dev` 읽기·수정, commit/push는 범위가 아니다.

## Next Steps

검토 → 5 화면 완주 + cases-v2 기준점(IMP-024·025·IMP-028 재발 방지 포함) → 6 XLSX(의도적 제외 상태) → 7 옛 오피스. 운영 배포 이미지(코드 포함·reload 없음)는 AWS 설계 때 정한다.

## Read First

[AGENTS](../../AGENTS.md) → [Architecture](../docs/architecture.md) → `docker-compose.yml`·`data-pipeline/Dockerfile`·`scripts/dev.sh` → [Backlog](../docs/improvement-backlog.md)(IMP-005·017).

## Scope / Acceptance

1. 컨테이너 FastAPI의 /health·내부 키 인증·질문 결과가 host 실행과 같다. 같은 질문 3개의 상위 검색 순위를 비교해 보고한다.
2. 기존 원본의 parse_key·chunk_set_key·embedding_key가 그대로이고 컨테이너도 같은 V2 collection(embedding_key `228acdd12220`)을 읽는다.
3. 비밀값은 이미지·로그에 남지 않고 컨테이너에는 필요한 설정만 전달한다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-03-fastapi-compose-imp017.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
