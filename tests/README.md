# 현재 테스트

contract/test_phase0.py: 로컬 도구 Unit / Contract, 잘못된 측정·metadata·경로·hash 거부.
integration/test_phase0_cli.py: 임시 디렉터리에서 실제 CLI 전체 흐름과 실패 종료 확인.
contract/test_harness_policy.py: 격리된 Git 저장소에서 링크·CI·브랜치·ignore·주석·범위 오류와
check-all 실패 전파를 검증한다.
AGY Lifecycle·자기 승인/잘못된 metadata 거부와 독립 원문/검토 대상 변조의 non-gating 미검증 상태도 검사한다.
Workspace 생성물의 hygiene는 non-gating이며 current-task/정적 README/제품/Rule의 strict 회귀를 검사한다.
실 API·네트워크·DB·Parser·제품 E2E는 실행하지 않는다.
로컬 기록 Fixture는 합성 metadata / report이며 실제 데이터 성공률의 근거가 아니다.
fixtures/external-api/bizinfo-user-sample.json은 사용자 제공 실제 sanitized 10건 Sample이다.
contract/test_bizinfo_probe.py는 이 Sample 계약·Raw 예외·mock HTTP·unknown field·secret 비노출·충돌을 검사한다.
integration/test_bizinfo_probe_cli.py는 격리 CLI의 NOT_RUN / help / Profile 선택 오류 / 설정 실패 비노출을 검사한다.
Probe Profile 테스트는 합성 .env.dev / .env.prod에서 선택 파일·fallback 금지·OS 우선·비실행·비노출을 검사한다.
Harness 테스트는 실제 사용자 Secret을 복사하지 않고 격리 Git에서 Secret 추적 / ignore 정책 오류를 거부한다.
Live Probe는 CI가 호출하지 않으며 별도 Local 명령과 ignored Evidence로 구분한다.

contract/test_phase0_api_quality.py는 합성 5×20 응답으로 중복·5종 field 상태·기간·확장자·정렬·부분 실패·Raw/Secret 경계를 검사한다.
integration/test_phase0_api_quality_cli.py는 credential 없는 CLI의 NOT_RUN·dev 제한·재현·출력 경계·overwrite 금지를 검사한다.
Live Batch와 offline mock 결과는 분리하며 GitHub CI는 API를 호출하지 않는다.

contract/test_phase0_document_download.py는 합성 PDF/CFB/ZIP와 mock HTTP로 Download Gate의 제한·형식·실패·재개·checksum·Secret을 검증한다.
integration/test_phase0_document_download_cli.py는 dev 제한·출력·분석/overwrite·실패 종료를 검사하며 Live 요청은 없다.

contract/test_document_parsing.py는 합성 HWPX로 detected-format router, HwpxDoclingAdapter의 DoclingDocument 재적재·표·정규화,
container/XML 안전 한도, 빈 text 비성공, parse_key 재처리 규칙을 검증한다. 실제 corpus·S3·Docling 변환은 사용하지 않는다.

contract/test_document_parsing_pdf.py는 합성 PDF로 Docling PDF route의 PARSED / OCR_REQUIRED / PARSE_FAILED 구분,
PDF handler 호출 경계, OCR 비활성과 parse_key 버전 추적을 검증한다. 실제 corpus·S3는 사용하지 않는다.
