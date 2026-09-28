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
Phase 1A는 source_payload JSON에 실제 source field를 보존한다. Raw snapshot metadata 전용 DB 모델은 향후 계획이다.
실제 upstream 응답을 확인하지 않고 필수 field나 envelope를 확정하지 않는다.

Local Probe는 Git Branch와 별개인 --profile dev / prod를 명시한다. 선택한 Secret 파일만 읽고 fallback하지 않는다.
.env.dev / .env.prod는 사용자 관리 파일로 수정·삭제·stage·값 출력하지 않는다. .env.example만 추적한다.
현재 Task는 dev Live만 허용하며 prod 설정은 합성 데이터의 오프라인 Test로만 검증한다.

승인된 Phase 0 API 품질 Batch는 dev만 선택하며 5 Page × 20건으로 제한한다. 재시도·prod 요청·다운로드는 없다.
수집 시점 API 기본 정렬 기준 선두 100건을 표본으로 사용한다. 공식 최신순 보장은 추정하지 않는다.
품질 분모는 성공 Envelope의 실제 Item 수이며 중복 행·null·blank·누락을 제거하지 않는다.

승인된 Document Download Gate는 기존 api-quality-dev-20260928-01의 동일 100개 printFlpthNm만 순차 요청한다.
Supplementary는 token 수만 측정하고 원본은 다운로드하지 않는다. dev key는 반사 검출만 수행하며 문서 요청에 전달하지 않는다.
data/downloaded 원본·manifest·metadata/checksum은 Git에서 제외하고 최종 해석 Report / Checkpoint는 non-gating Generated Output으로 보존하며 Git 추적을 요구하지 않는다.
재개는 검증된 확정 결과를 건너뛰며 실패 자동 재시도·원본 overwrite·본문 Parsing을 포함하지 않는다.

## Phase 1B FULL 안전 규칙

FULL은 명시적 dev 실행이며 실행 첫 정상 Page의 totalCount를 기대 전체 건수로 고정한다. Dataset 숫자를 하드코딩하지 않는다.
전체 pagination / 각 Raw byte·SHA-256·수집시각·인증 없는 request metadata / 실행 Evidence를 보존한다.
API key 반사·응답 크기 초과는 저장을 거부한다. 실패 원문과 완료된 Page를 보존하고 자동 retry·기존 run overwrite를 하지 않는다.

모든 Page 성공, 일관된 totalCount, 연속 Page·마지막 정확한 잔여 건수·빈 Page 이상 없음,
유효 pblancId 전체 unique(duplicate=0), 실제 Raw Item/unique 수=기대 totalCount, Raw checksum 확인이 completeness 조건이다.
하나라도 실패하면 FULL FAIL이며 DB 공고 mutation / reconciliation에 진입하지 않는다.
완전성 통과 후 모든 Item의 정규화를 먼저 검증한다. 적재 오류·transaction 실패는 FAIL이며 전체 mutation을 rollback한다.
SAMPLE/PARTIAL absence와 실패/불완전한 FULL은 삭제 근거가 아니다. 관측 record의 REACTIVATE는 기존 의미를 유지한다.

첫 Live FULL은 soft-delete 후보 DRY_RUN만 계산하며 실제 soft-delete/physical DELETE는 금지한다.
현재 dev Repository의 적용 reconciliation은 비활성이고 controlled test DB에서만 기존 APPLY 회귀를 수행한다.
실제 적용은 별도 사용자 승인 Task, 새 성공 FULL, Raw/ID/count/정규화/DB 품질과 후보 목록의 Human Review가 필요하다.
이전 DRY_RUN 목록을 나중에 그대로 삭제에 사용하지 않는다. totalCount 일치는 API universe의 atomic snapshot 보장을 뜻하지 않는다.
updtPnttm은 저장만 하며 미확정 incremental query 기준으로 사용하지 않는다. 공식 newest-first는 UNCONFIRMED다.

API 대기와 원문 검증은 DB transaction 밖에서 수행한다. dev 실행은 DB-only atomic transaction / 동일 advisory lock,
cooperative 60초 budget와 기존 query timeout을 사용한다. Snapshot 검증/정규화 후 적재하며 실패 시 부분 commit하지 않는다.
이 budget은 공급자 제한이 아니며 blocking SQL을 즉시 중단시키는 hard deadline도 아니다. 대규모 실행이 초과하면 rollback 후 별도 설계 Task로 검토한다.
중단 Run의 Raw/실패 Page는 Evidence에 보존한다. 새로운 live acquisition은 새 run-id로 시작해 서로 다른 관측 기간의 Page를 이어 붙이지 않는다.
