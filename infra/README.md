# 현재 Infrastructure

docker-compose.yml은 phase0 로컬 파일 도구 Batch만 실행한다.
Python 표준 라이브러리 이미지에 repository를 read-only로 mount하고
data/ 및 workspace/artifacts/만 쓰기 가능하게 둔다.
상시 service·port·DB·vector index·운영 배포 리소스는 없다.
Docker daemon·이미지 네트워크는 Batch 실행에 필요하며 setup / check-all은 config만 검증한다.

향후 실제 코드와 의존성이 생기면 frontend / backend / ai / mysql / qdrant를 함께 추가한다.
운영 인프라는 별도 ADR에서 결정하고 자동 배포 trigger는 op Merge로 유지한다.
