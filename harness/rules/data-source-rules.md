# 데이터 출처와 원문

승인된 공식 중소벤처기업부 지원사업 공고 API와 연결된 공식 공고문만 사용한다.
임의 외부 Source를 추가하지 않는다. pblancId를 source identity로 검증한 후 사용한다.
원문 byte·checksum·수집 시각을 보존하고 정규화 데이터와 구분한다.
원문과 실패 데이터를 임의 삭제·덮어쓰기 하지 않는다.

현재 data/raw/는 개발환경 원본 저장소다. payload·첨부·개인정보는 Git에 넣지 않는다.
이번 승인 Task에서 사용자가 제공한 secret 없는 실제 sanitized Sample만
tests/fixtures/external-api/bizinfo-user-sample.json에 Contract Evidence로 추적한다.
이 예외는 임의 Live 응답·첨부·개인정보의 Git 추가를 허용하지 않는다.
증거는 credential 없는 상대 경로·checksum·수집 run-id로 연결한다.
Raw metadata / 필요 JSON의 MySQL JSON column 관리는 향후 계획이다.
실제 upstream 응답을 확인하지 않고 필수 field나 envelope를 확정하지 않는다.

Local Probe는 Git Branch와 별개인 --profile dev / prod를 명시한다. 선택한 Secret 파일만 읽고 fallback하지 않는다.
.env.dev / .env.prod는 사용자 관리 파일로 수정·삭제·stage·값 출력하지 않는다. .env.example만 추적한다.
현재 Task는 dev Live만 허용하며 prod 설정은 합성 데이터의 오프라인 Test로만 검증한다.

승인된 Phase 0 API 품질 Batch는 dev만 선택하며 5 Page × 20건으로 제한한다. 재시도·prod 요청·다운로드는 없다.
수집 시점 API 기본 정렬 기준 선두 100건을 표본으로 사용한다. 공식 최신순 보장은 추정하지 않는다.
품질 분모는 성공 Envelope의 실제 Item 수이며 중복 행·null·blank·누락을 제거하지 않는다.

승인된 Document Download Gate는 기존 api-quality-dev-20260928-01의 동일 100개 printFlpthNm만 순차 요청한다.
Supplementary는 token 수만 측정하고 원본은 다운로드하지 않는다. dev key는 반사 검출만 수행하며 문서 요청에 전달하지 않는다.
data/downloaded 원본·manifest·metadata/checksum은 Git에서 제외하고 최종 해석 Report / Checkpoint만 추적한다.
재개는 검증된 확정 결과를 건너뛰며 실패 자동 재시도·원본 overwrite·본문 Parsing을 포함하지 않는다.
