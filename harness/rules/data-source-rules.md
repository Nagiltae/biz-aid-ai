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
.env.dev / .env.prod는 사용자 관리 파일로 수정·삭제·stage·값 출력하지 않는다. .env.dev.example·.env.prod.example은 비밀값 없는 설정 이름/설명 예시만 추적한다.
원본 수집·적재는 dev Live만 허용한다. 명시 운영 질문 서버의 읽기 전용 DB/TLS·검색 연결은 묶음5-2 사용자 승인 범위이며, 실제 운영 배포는 별도 승인한다.

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
Production orchestration은 호출자가 명시한 unique content SHA만 조회한다. 한 실행은 1~3개로 제한하고 SHA 오름차순으로 순차 처리하며,
DB에서 대상을 자동 발견하거나 전체 corpus를 암묵적으로 순회하지 않는다. 한 source 실패는 해당 결과로 격리하고 다른 명시 source의 결과를 되돌리지 않는다.
같은 SHA relation의 format·크기·S3 위치가 모두 일치해야 하고, 재실행 판단은 별도 우회 없이 persistence의 parse_key idempotency에 맡긴다.
route는 `detected_format`만 따른다. 파일명 확장자·declared_extension·Content-Type은 route 근거가 아니다.
결과는 content SHA 단위로 만들고 relation provenance는 `document_sources.content_sha256` join으로 모두 유지한다.
모든 parsing 수치는 unique content SHA 기준인지 source relation 기준인지 명시하며 두 값을 합치거나 바꿔 쓰지 않는다.
표본 관찰값은 분자/분모로 기록하고 표본 추출 방법의 대표성이 검증되기 전에는 corpus prevalence를 UNMEASURED로 둔다.
PDF/HWP/HWPX의 구조화 표현은 DoclingDocument 하나다. 자체 canonical document tree를 만들지 않으며 BizAid 추적 정보는 결과 봉투에 둔다.
정규화는 Contract의 NFC·줄바꿈·제어문자·줄 끝 공백만 수행하고 추출 원문은 TextItem.orig에 남긴다.

parse_key는 source SHA·route·adapter/normalizer/docling-core/docling/converter 버전으로 계산한다.
parse identity는 route 의존 범위와 같다. HWPX adapter는 HWPX만, PDF parser·PP·OCR은 PDF와 이를 재사용하는 HWP만, HWP 변환기는 HWP만, normalizer·docling-core는 모든 route key를 바꾼다.
corpus 실행 단위는 검증된 unique content SHA이고 enabled route format만 자동 대상이다. 비활성 format은 집계만 하며 성공으로 기록하지 않는다.
corpus 실행은 dev 전용·순차이며 현재 parse_key 결과가 있으면 재처리하지 않고, source별 실패를 격리하고, progress·result 파일로 관찰·재개할 수 있어야 한다. 기존 artifact·row는 지우거나 덮어쓰지 않는다.
corpus runner는 명시적 상한(--max-completed)과 종료 요청을 source 경계에서만 반영한다. 실행 중 source를 강제 종료해 반쯤 기록된 artifact·row를 만들지 않는다.
Chunking 입력은 source의 현재 parse_key로 저장된 canonical DoclingDocument이며 Markdown은 입력이 아니다. format별로 다시 분기하거나 parsing하지 않는다.
Chunk 크기는 embedding 모델과 같은 tokenizer(repo·revision)로 센다. tokenizer·max_tokens·chunking 정책 변경은 chunk identity를 바꾼다.
FinalChunk는 pblanc_id·source SHA·parse_key·page 또는 HWPX 위치 provenance를 잃지 않는다. item meta는 metadata로만 옮기고 chunk text에 넣지 않는다.
공고명 같은 검색 전용 context는 embedding_text에만 넣고 근거 본문(chunk text)은 바꾸지 않는다. 공고명은 MySQL support_programs.name만 쓴다.
embedding_text 의미를 바꾸는 변경은 re-index 전에 기존 chunk identity(chunker_version·chunker 설정 → chunk_set_key)에 반영한다.
Embedding 모델은 chunk tokenizer와 같은 repo·revision이며 가중치는 고정 artifact(scope embedding)에서만 읽는다. 실행 중 Hub 다운로드와 입력 truncation은 없다.
Qdrant point id는 chunk_id, payload는 FinalChunk.payload()다. collection은 embedding_key마다 따로 두고 dense·sparse schema나 metadata가 다르면 재생성하지 않고 실패한다.
모델·설정·artifact·runtime 변경은 embedding_key를 바꾼다. 재실행은 같은 point를 덮어쓰고 같은 source의 현재 chunk가 아닌 point만 지운다.
corpus indexing은 명시한 source 목록만 순차 처리하고, 모든 target이 현재 parse_key PARSED인지 먼저 확인한 뒤 시작하며, parser 실행과 동시에 돌리지 않는다. 종료 요청은 source 경계에서만 반영한다.
chunking·indexing CLI는 source 단위 실패를 안정적 code의 PipelineError로만 격리한다. 하위 모듈 예외(예: HwpConversionError)는 단계 경계에서 PipelineError로 바꿔 한 source가 batch 전체를 멈추지 않게 한다.
조립에서 native 단어 하나는 한 곳에만 속한다. PP 영역 안 단어는 PP 결과가, 영역에 걸친 native item은 영역 밖 단어만 가진다. OCR 부족 page는 warning·metadata로 드러내고 문서 status는 문서 text Gate가 정한다.
native text가 조금이라도 있고 raster image가 없는 low-text page는 OCR하지 않고 native text를 유지한다(OCR은 같은 글자를 다시 읽을 뿐이다).
같은 parse_key와 무결성이 재확인된 artifact만 재사용하고, 버전 변경은 해당 route 문서만 새 key로 재처리한다. 과거 결과는 덮어쓰지 않는다.
parser 호출이 예외 없이 끝났다는 사실만으로 PARSED가 아니다. DoclingDocument 재적재와 text 양 Gate를 통과해야 한다.
일반 PDF는 native text가 우선이다. 문서 평균이 아니라 각 page를 독립 판정해 native text가 기준 이하인 page만 OCR하고, 기준을 넘는 page는 OCR하지 않는다.
OCR은 PaddleX PP-OCRv5(한국어 인식) 일반 OCR이며 Docling 자체 OCR은 끈다. OCR text도 원본 SHA·page·bbox·confidence·engine identity를 남기고 최종 표현은 DoclingDocument다.
OCR engine 오류는 PARSE_FAILED, OCR 후에도 text가 기준 이하면 OCR_REQUIRED + OCR_TEXT_INSUFFICIENT다. Visual VLM 해석은 OCR이 아니며 production 보류다.
PDF route는 Docling DocumentConverter를 `do_ocr=false`, `do_table_structure=false`로만 만들고 OCR engine을 설치하지 않는다. 입력은 DocumentStream으로 메모리에서 넘긴다.
HWP는 전용 Docker 변환 이미지(host 설치 없음, 네트워크 없음)로 PDF를 만든 뒤 production PDF parser를 그대로 재사용한다. HWP 전용 문서·표 parser를 두지 않고 HWPX는 native adapter를 유지한다.
HWPX 구조는 XML의 명시 정보(header.xml의 문단 모양 heading OUTLINE/NUMBER/BULLET, 내장 개요 스타일, 머리말·꼬리말·각주 control)만 쓴다.
글자 크기·layout·사용자 정의 스타일 이름으로 heading을 추측하지 않고, 문서 SHA·파일명별 예외를 두지 않는다.
표현할 수 없는 구조는 버리지 않고 text와 warning·provenance로 남긴다. HWPX에는 page·좌표가 없으므로 가짜 page/bbox를 만들지 않는다.
변환 실패는 CONVERSION_FAILED이며 다른 변환기·parser로 넘어가지 않는다. provenance의 source는 원본 HWP SHA이고 중간 PDF는 저장하지 않는다.
Docling 부분 성공(PARTIAL_SUCCESS)은 page 누락 위험이 있으므로 PARSE_FAILED다. status는 결과 분류, failure_code는 Contract에 등록한 구체 원인이다.
PARSED는 실행·재적재·text 양 Gate 통과이며 본문·표의 의미상 완전성을 보장하지 않는다. 소비자는 warning을 함께 읽는다.
PDF 표 engine은 PP-TableMagic(2026-09-29 사용자 결정)이며 Docling은 layout·읽기 순서 backbone으로 남는다. TableFormer는 실행하지 않는다.
PP는 OCR 모델 없이 native text 사각형을 주입해 실행하고 cell text는 native 단어로 채운다. 표 engine 설정 변경은 evidence와 새 pipeline_config_sha256 없이 하지 않는다.
Docling layout·PP 표·OCR·BGE-M3 모델은 저장소 밖 명시적 `BIZAID_DOCLING_ARTIFACTS_PATH`의 고정 snapshot만 사용한다. 전체 manifest가 기대값과 같아야 실행한다.
각 identity에는 자기 단계 scope(parsing→parse_key, chunking→chunk_set_key, embedding→embedding_key)의 manifest만 넣는다. 다른 단계 모델 추가가 상위 key를 바꾸면 안 된다.
네트워크 provisioning은 `provision --allow-network` 명령과 CI cache miss step에서만 허용하고 resolved commit으로 받는다.
parsing·test runtime의 모델 네트워크 다운로드는 금지하며 artifact가 없으면 변환 전에 실패한다. 모델·cache를 저장소·data/에 두지 않는다.

Container는 풀어서 디스크에 쓰지 않고 메모리에서 제한적으로 읽는다. 절대·상위 경로, 중복 entry, 암호화 entry,
entry 수·전체 해제 크기·압축비·XML 크기 한도 초과는 REJECTED_UNSAFE 또는 ENCRYPTED다. XML은 DTD·entity를 거부한다.
압축 container는 판별 단계에서 HWPX·XLSX·DOCX·PPTX·ODT를 각자의 형식으로 나누고 나머지만 ZIP(일반 압축)으로 둔다. OLE는 HWP·DOC·XLS·PPT를 stream 이름으로, 이미지는 PNG·JPEG로 나눈다. HTML은 OTHER, XML 기반 한글은 HWPML로 판별만 한다.
새 형식의 route는 Contract에 정의하되 단계별 승인 전에는 켜지 않는다.
일반 ZIP(2026-10-02 사용자 결정, 4단계)은 압축 자체를 파싱하지 않고(POLICY_PENDING 유지) 내부 파일을 각각 문서로 펼친다. 깊이 1이며 압축 안 압축은 열지 않고 상태만 남긴다.
압축은 메모리에서만 열고 안전 한도는 위 container 규칙(hwpx_container_limits)을 그대로 쓴다. 한도 위반·암호화·경로 탈출이면 압축 전체를 거부하고 내부 파일을 하나도 기록하지 않는다.
내부 파일마다 archive source SHA·member path(원래 이름 byte 포함)·member SHA·member detected format·archive depth·parent member provenance·처리 상태·사유를 `document_archive_members`(V10)에 남긴다.
이름은 UTF-8 플래그가 있으면 UTF-8, 없으면 CP949로 읽고, 실패하면 원래 byte만 기록한다. 형식은 확장자가 아니라 내용으로 판별한다(실제 PDF인 `.ai`는 PDF route).
처리 제외(상태만 기록): OS 메타 파일(Thumbs.db 등), 빈·자리표시 txt, 압축 안 압축, HWPML(보류), XLSX·DOC·XLS·PPT(의도적 제외), 켜진 route가 없는 형식.
단독 첨부와 같은 SHA인 내부 파일은 다시 저장·파싱하지 않고 연결만 남긴다. 처리할 내부 파일은 원본과 같은 S3 prefix·content SHA key에 덮어쓰기 없이 저장·검증한 뒤 행을 기록한다.
공고 relation은 복사하지 않고 압축 첨부의 relation을 물려받는다. 내부 파일 파싱은 실제 형식의 기존 route를 쓰며 새 parser를 만들지 않는다. 출처 종류는 내부 파일명으로 정한다.
판별 규칙이 바뀌어도 저장된 detected_format은 자동으로 고치지 않는다. 재분류는 미리보기(전후 값·행 수)를 남기고 사용자 승인 뒤 한 트랜잭션으로 적용한다.
Parsed artifact의 영구 저장소는 S3이며 로컬 filesystem은 fixture·scratch·임시 처리만 허용한다.
DoclingDocument는 결정론적 JSON byte로 직렬화하고 source SHA·parse_key 주소의 immutable S3 object로 저장한다.
S3 checksum과 실제 byte readback이 모두 성공한 뒤에만 MySQL 성공 metadata를 commit한다. 동일 source SHA·parse_key는 검증 후
재사용하며 새 parse_key는 기존 artifact를 덮어쓰지 않는다. 비성공 결과는 artifact 없이 상태 metadata만 보존한다.
### PDF Table Engine 규칙 (3-B.1부터)

PDF 문서 parser는 Docling이며 표 engine이 바뀌어도 최종 구조화 표현은 DoclingDocument다. 별도 CanonicalDocument·문서 tree를 만들지 않는다.
다른 표 engine은 표 변환만 책임지는 adapter로 DoclingDocument의 TableItem에 수렴한다.
실제 BizAid corpus benchmark evidence와 사용자 결정 없이 primary table engine을 바꾸지 않는다. 현재 primary는 PP-TableMagic이다.
engine routing은 변환 전에 알 수 있는 source·표 특성의 결정적 규칙이어야 하며 "실패하면 다른 engine으로 재시도"는 primary 해결책으로 인정하지 않는다.
PP-TableMagic 후보는 표 검출과 구조를 함께 소유하는 구조로 검증한다. Docling 표 bbox를 PP 입력 gate로 쓰는 방식은 귀속 측정용이며 기본안이 아니다.
구조 cell을 논리 TableCell로 옮기는 매핑은 증명된 규칙으로만 하며 증명되지 않으면 조용한 fallback이 아니라 TABLE_QUALITY_FAILED다.
TABLE_QUALITY_FAILED 표는 표 구조(TableItem 행·열·span)로 Chunking·indexing에 들어가지 않는다. 보존된 native text만 일반 text로 chunk되고 provenance에 table_verdict가 남는다. 이 표 품질 evidence는 기존 ParseStatus를 늘리지 않는다.
TABLE_QUALITY_FAILED 표는 행·열·span 구조를 만들지 않고 bbox 안 native text를 손실 없이 보존하며 page·bbox·source SHA·실패 사유·parser identity를 남긴다.
서로 겹친 PP 표 영역(container·duplicate 후보)은 검증된 규칙 전까지 하나를 고르지 않고 합친 영역을 TABLE_QUALITY_FAILED native text로 보존한다.
DoclingDocument 조립은 교체한 item의 caption·footnote 자식, VALID 표의 cell 밖 단어, 영역에 일부만 걸친 text, PP 영역 밖 Docling 표 text를 버리지 않는다.
손실은 쪽 단위로 baseline과 비교하며 PP 표와 Docling picture가 겹친 영역은 사람 검토 대상으로 기록한다.
PDF visual 해석(PaddleOCR-VL)은 production에서 보류다. 제품 코드는 이를 import하지 않고 Docling picture item을 그대로 둔다. 평가 출력은 native source text가 아니다.
benchmark 후보 engine은 제품 manifest·`.venv`와 분리된 저장소 밖 환경에서 명시 버전·명시 모델 경로로 실행하고 실행 중 모델 자동 다운로드를 하지 않는다.
benchmark 산출물·GT·렌더링 evidence는 공고 첨부에서 파생된 내용이므로 ignored `data/parsed/`에만 두고 Git에 넣지 않는다.
GT는 source SHA·page·bbox와 사람이 검토할 수 있는 crop evidence를 함께 남기며 검토 주체와 상태를 기록한다. 추정 결과를 정답으로 가정하지 않는다.

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
