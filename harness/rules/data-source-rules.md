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

## Phase 2 Document Acquisition 안전 규칙

Source는 성공한 Phase 1B dev DB의 active `support_programs`다. Phase 2를 위해 API FULL을 다시 실행하지 않는다.
`printFlpthNm`/`printFileNm`은 PRINT_CANDIDATE, `flpthNm`/`fileNm`은 ATTACHMENT_CANDIDATE provenance로 기록한다.
이 이름은 원본 field를 가리키며 실제 본공고/부속 의미를 확정하지 않는다. @ token 위치와 pairing 상태도 보존한다.

문서 URL은 HTTPS `www.bizinfo.go.kr` 공개 파일 경계만 허용한다. API key·Cookie·Authorization·Referer는 전달하지 않는다.
dev key는 응답/redirect에 Secret이 반사됐는지 검사할 때만 사용한다. 순차 요청, redirect 3, 100 MiB, timeout 15초,
candidate 간 0.25초, 자동 retry 0은 공급자 공식 제한이 아닌 로컬 안전 경계다.

확장자와 Content-Type은 관찰값이며 signature/container가 실제 format 판별 기준이다. HTML/error response는 문서 성공이 아니다.
UNKNOWN/OTHER byte도 Evidence로 보존하되 품질 Report에 드러낸다. 원본은 SHA-256 content-addressed 경로에 exclusive write하고
기존 path의 byte가 다르면 중단한다. URL/SHA dedupe 뒤에도 pblancId/source field/token relation은 모두 DB에 남긴다.

중단 run은 source snapshot hash와 이미 저장된 checksum/readback을 확인한 뒤 미처리 relation만 계속한다.
같은 run의 확정 실패는 자동 재시도하지 않는다. 새 run은 검증된 성공을 재사용하고 과거 실패 URL만 다시 요청할 수 있다.
모든 relation metadata/readback과 source snapshot이 일치하고 실패가 0일 때만 품질 PASS다. Parser 의미 검증은 Phase 3 대상이다.

## Phase 2.5 S3 저장 안전 규칙

고정 dev region/bucket/prefix와 content SHA-256 key만 사용한다. AWS key를 설정 파일에 두지 않고 boto3 credential chain을 사용한다.
metadata 연결은 기존 object의 HEAD 크기와 `ChecksumSHA256`을 전수 검증하며 ETag를 checksum으로 사용하지 않는다.
누락·크기·checksum 불일치는 FAIL이고 자동 upload로 복구하지 않는다. 이 단계의 허용 S3 동작은 HEAD와 검증용 GET뿐이다.
모든 object 검증 전 DB를 변경하지 않으며 3,288 relation metadata는 단일 transaction으로 연결한다.
실제 byte GET으로 SHA와 format을 재검증한다. 기존 로컬 corpus와 S3 object 삭제는 AGY와 사용자 승인 전 금지한다.

## Phase 3 Document Parsing 규칙

입력은 ACQUIRED이고 `s3_*`가 검증된 relation의 unique `content_sha256`이다. 원본은 S3에서 읽고 크기·SHA를 다시 확인한다.
route는 `detected_format`만 따른다. 파일명 확장자·declared_extension·Content-Type은 route 근거가 아니다.
결과는 content SHA 단위로 만들고 relation provenance는 `document_sources.content_sha256` join으로 모두 유지한다.
모든 parsing 수치는 unique content SHA 기준인지 source relation 기준인지 명시하며 두 값을 합치거나 바꿔 쓰지 않는다.
표본 관찰값은 분자/분모로 기록하고 표본 추출 방법의 대표성이 검증되기 전에는 corpus prevalence를 UNMEASURED로 둔다.
PDF/HWP/HWPX의 구조화 표현은 DoclingDocument 하나다. 자체 canonical document tree를 만들지 않으며 BizAid 추적 정보는 결과 봉투에 둔다.
정규화는 Contract의 NFC·줄바꿈·제어문자·줄 끝 공백만 수행하고 추출 원문은 TextItem.orig에 남긴다.

parse_key는 source SHA·route·adapter/normalizer/docling-core/docling/converter 버전으로 계산한다.
같은 parse_key와 무결성이 재확인된 artifact만 재사용하고, 버전 변경은 해당 route 문서만 새 key로 재처리한다. 과거 결과는 덮어쓰지 않는다.
parser 호출이 예외 없이 끝났다는 사실만으로 PARSED가 아니다. DoclingDocument 재적재와 text 양 Gate를 통과해야 한다.
native text가 부족한 PDF는 OCR_REQUIRED로 분리한다. OCR 도입은 실제 분포 근거로 별도 Task에서 결정한다.

Container는 풀어서 디스크에 쓰지 않고 메모리에서 제한적으로 읽는다. 절대·상위 경로, 중복 entry, 암호화 entry,
entry 수·전체 해제 크기·압축비·XML 크기 한도 초과는 REJECTED_UNSAFE 또는 ENCRYPTED다. XML은 DTD·entity를 거부한다.
detected ZIP은 DOCX·PPTX·ODT·Generic ZIP을 구분해 다룬다. Generic ZIP은 archive source SHA·member path·member SHA·
member detected format·archive depth·parent/member provenance를 표현하는 Contract 전까지 전개하지 않고 POLICY_PENDING으로 보존한다.
Parsed artifact의 영구 저장소는 S3이며 로컬 filesystem은 fixture·scratch·임시 처리만 허용한다.
Phase 3는 원본 재다운로드·재업로드·S3/로컬 원본 삭제를 하지 않는다. Pilot·Full Parse의 대량 S3 GET/PUT은 실행 전 보고한다.

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
