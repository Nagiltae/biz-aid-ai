# 기업마당 지원사업 API Raw Contract

## 근거와 확인 수준

- **CONFIRMED**: 사용자가 확인한 공식 Request 정보는 Endpoint·Method·Parameter 이름과 serviceKey 필수 여부다.
  이 Task에서 공급자 명세 전체를 독립 확보한 것은 아니다. 명시되지 않은 default·형식·제한을 추정하지 않는다.
- **OBSERVED**: 사용자 실제 sanitized Sample 10건과 별도 dev Live 4요청을 구분한다. 상세 관찰은 아래와 Report를 따른다.
- **UNCONFIRMED**: 오류·빈 결과의 일반 보장, 정렬 보장, ID 필터의 모든 경우, 날짜 필터 의미, field 필수성·null 보장이다.

[기계 계약](bizinfo.contract.json)은 공급자 JSON Schema가 아닌 이 프로젝트의 근거·관찰 타입·Probe 설정이다.
[실제 Sample Fixture](../../tests/fixtures/external-api/bizinfo-user-sample.json)는 Synthetic 데이터가 아니다.
사용자 메시지의 10건 전체를 UTF-8 / JSON indent 2로 저장했으며 field 값·null·HTML·개행·Unicode를 보존한다.
전송 당시 wire byte는 제공되지 않았다. Fixture checksum은 저장된 파일의 무결성만 나타낸다.
SHA-256: `e544fe5e7463687472ce28ea01ea81efbd471fdba49b7dc5f6f977884148aa5a`.
인증키와 serviceKey query는 Fixture에 없다. Tests의 변경 응답은 별도의 Synthetic 사례다.

## Request — 사용자 확인 공식 정보

`GET https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService`

공공데이터포털 인증키를 query `serviceKey`로 전달한다. Local 환경변수는 `BIZINFO_SERVICE_KEY`다.
인증키를 명령 인수·로그·Report·Test에 넣지 않는다.

| Parameter | 필수 여부 | 제공된 의미 |
| --- | --- | --- |
| serviceKey | Required | 공공데이터포털 인증키 |
| dataType | 미확정 | 응답 데이터 형식; 이번 Probe는 json 지정 |
| pageNo | 미확정 | 페이지 번호 |
| numOfRows | 미확정 | 한 페이지 결과 수 |
| searchLclasId | 미확정 | 분야 조회 설정값 |
| hashtags | 미확정 | 해시태그 조회 |
| pblancId | 미확정 | 공고 조회용 고유 식별값 |
| registDe | 미확정 | 공고 등록 일자 |
| updtPnttm | 미확정 | 공고 수정 일자 |

serviceKey 외 Optional 여부·기본값·최대값·날짜 형식·필터 결합·시간대·key encoding 요구는 미확정이다.
Probe 지정값과 안전 제한은 공급자 정책이 아니다. registDe와 creatPnttm의 동일 의미도 단정하지 않는다.

## Response — Sample 관찰 계약

```text
response
  header
    resultCode: string (Sample "00")
    resultMsg: string (Sample "NORMAL_SERVICE")
  body
    items
      item: object[] (Sample 10건)
    numOfRows: integer (Sample 10)
    pageNo: integer (Sample 1)
    totalCount: integer (Sample 1518)
```

성공 Probe는 resultCode="00"와 비어 있지 않은 문자열 resultMsg를 요구한다.
resultMsg의 Sample 문구를 공급자의 고정 상수로 요구하지 않는다.
Pagination은 bool이 아닌 정수이며 로컬 검사에서 pageNo / numOfRows >=1, totalCount >=0을 요구한다.
요청 pageNo / numOfRows echo 일치도 관찰한다. 필드 이름만으로 실제 Pagination 동작을 확정하지 않는다.

### 관찰된 Item Field

| Field | Sample 타입 | Sample null 관찰 |
| --- | --- | --- |
| pblancNm | string | 없음 |
| pblancUrl | string | 없음 |
| pblancId | string | 없음 |
| jrsdInsttNm | string | 없음 |
| excInsttNm | string | 없음 |
| bsnsSumryCn | string | 없음 |
| pldirSportRealmLclasCodeNm | string | 없음 |
| creatPnttm | string | 없음 |
| reqstBeginEndDe | string | 없음 |
| updtPnttm | string | 없음 |
| trgetNm | string | 없음 |
| inqireCo | integer | 없음 |
| flpthNm | string 또는 null | 있음 |
| fileNm | string 또는 null | 있음 |
| printFlpthNm | string | 없음 |
| printFileNm | string | 없음 |
| hashtags | string | 없음 |
| reqstMthPapersCn | string | 없음 |
| refrncNm | string | 없음 |
| rceptEngnHmpgUrl | string 또는 null | 있음 |

공급자의 Required / Optional은 모두 미확정이다. Probe는 item의 pblancId만 nonblank string으로 요구한다.
다른 알려진 field가 없으면 허용하고, 존재하면 위 관찰 타입을 검사한다. 관찰하지 않은 null / 타입은
계약 차이로 실패·원문 보존한다. 이 실패가 공급자의 응답 오류임을 뜻하지 않는다.
Unknown field는 어느 계층에서도 제거하지 않는다. DB Schema·Normalize는 만들지 않는다.

### Raw 예외와 가설

- reqstBeginEndDe의 날짜 범위와 "예산 소진시까지" 모두 Raw string으로 보존한다.
- bsnsSumryCn의 HTML·Unicode·공백과 신청 방법의 개행을 보존한다. HTML 제거·날짜 변환은 하지 않는다.
- flpthNm / fileNm의 null과 `@` 연결 문자열을 보존한다. URL·이름 positional pairing은 다음 Parser Task에서 검증한다.
- rceptEngnHmpgUrl의 null을 허용한다.
- Sample에서 PDF / HWP / HWPX / ZIP을 관찰했다. 확장자 비율·다운로드 성공률은 측정하지 않았다.
- printFlpthNm / printFileNm은 **Primary Notice Candidate**, flpthNm / fileNm은
  **Supplementary Attachment Candidate**라는 가설이다. 이름·확장자로 주 공고문 역할을 확정하지 않는다.
- Sample creatPnttm은 내림차순으로 관찰된다. timezone과 API newest-first 보장은 미확정이다.

### Error / Empty Envelope — 일부 관찰 / 일반 보장 미확정

초기 제공 Sample에는 오류가 없다. 이번 dev Live의 Synthetic presumed-missing ID 요청에서는
HTTP 200, resultCode="03", resultMsg="NODATA_ERROR", body.items={}, pageNo=1, numOfRows=0, totalCount=0을 관찰했다.
item key는 없었다. 성공의 빈 item[]을 반환했다고 기록하지 않는다. 모든 미존재 ID의 보장은 아직 미확정이다.
Probe는 non-00을 api_error로 분류하며 이 음성 관찰도 실패 원문으로 보존한다.
다른 오류 body 존재·형태는 단정하지 않는다. HTTP 오류·비JSON·XML·잘못된 Envelope도 실패로 기록한다.
빈 item 배열은 로컬 성공 계약에서 허용하지만 이번 미존재 요청의 실제 형태와는 다르다.
item 단일 object / null, items 빈 문자열 등은 현재 관찰 계약과 달라 실패하고 원문을 보존한다.
응답 원문에 인증키가 반사되면 변조 저장 대신 저장을 거부한다.

## 명시적인 Local Probe

[Probe](../../scripts/bizinfo_probe.py)는 stdlib만 사용하며 CI / check-all에서 Live 호출하지 않는다.
인증키가 있으면 아래 고정 계획을 최대 4회, 재시도 없이 실행한다.

| 요청 | pageNo | numOfRows | pblancId |
| --- | --- | --- | --- |
| page1 | 1 | 10 | 지정하지 않음 |
| page2 | 2 | 10 | 지정하지 않음 |
| known_id | 1 | 10 | Sample의 PBLN_000000000126771 |
| presumed_missing_id | 1 | 10 | Synthetic PBLN_999999999999999 |

Synthetic ID의 미존재는 사전 보장하지 않는다. 실제 응답 ID·건수·일치 / 빈 결과를 관찰한다.
페이지별 / 페이지 간 ID 중복, Item 수, totalCount 일관성, creatPnttm 순서를 기록한다.
요청 시점 사이 데이터 변경 가능성이 있어 차이는 관찰로 남기며 자동 GO / DROP을 만들지 않는다.

Environment Profile은 dev / prod 두 개이며 Git Branch와 별개다. Probe의 `--profile`은 필수다.
dev는 `.env.dev`, prod는 `.env.prod`만 읽으며 다른 Profile이나 legacy `.env`로 fallback하지 않는다.
`.env.example`은 APP_PROFILE=dev와 세 BIZINFO 설정의 예시다. APP_PROFILE은 Probe의 자동 선택자가 아니다.
실제 사용자 Secret 파일은 수정·삭제·stage하지 않는다. `.env.*` ignore / `!.env.example` 추적 정책을 유지한다.
우선순위는 Process / OS Environment → 선택된 파일 → 비밀이 아닌 Endpoint / json default다. key의 기본값은 없다.
선택된 파일이 없어도 OS Environment로 설정할 수 있어 향후 GitHub Environment / Secrets의 runtime 주입을 지원한다.
현재 운영 배포는 구현하지 않으며 이번 Task는 dev만 실행했다. 실제 사용자 prod 파일을 읽거나 호출하지 않았다.
최소 설정 reader는 NAME=value / export NAME=value와 전체 quoted value만 처리한다.
셸 실행·보간·inline comment는 지원하지 않는다. key는 percent decoding 한 번 뒤 query encoding한다.
`+`를 공백으로 해석하지 않는다. Endpoint는 위 주소와 dataType=json만 허용하며 Redirect를 따르지 않는다.

```bash
python3 -B scripts/bizinfo_probe.py --profile dev --run-id bizinfo-probe-001
# 필요한 경우 별도 run-id로 범위를 좁힌다.
python3 -B scripts/bizinfo_probe.py --profile dev --run-id bizinfo-pages-001 --mode pages
python3 -B scripts/bizinfo_probe.py --profile dev --run-id bizinfo-id-001 --mode identifier
```

선택 Profile·HTTP status·resultCode/resultMsg·건수·Pagination·ID·순서·실패 이유는 secret 없는 JSON으로 출력하고
`harness/workspace/artifacts/bizinfo-probe-<run-id>.json`에도 보존한다.
비밀 없는 응답 byte는 `data/raw/<run-id>-<request-name>/`에 기존 snapshot 계약·SHA-256으로 보존한다.
동일 run-id·기존 출력·부분 Raw가 있으면 요청 전에 중단하며 덮어쓰지 않는다. 결과는 ignored Artifact다.
timeout 15초 / 응답 최대 5 MiB / 최대 4요청은 Local 비용·실행 범위 제한이다.

종료 코드: 0=모든 Positive SUCCESS와 명시적 Negative EXPECTED_NO_DATA의 예상 결과·Pagination echo 검사 통과,
1=설정·출력·HTTP·관찰 계약 실패, 2=CLI 사용 오류, 3=credential_missing / NOT_RUN.
0은 공급자의 일반적인 ID 필터·정렬 보장 또는 Gate 통과가 아니다. 분석 값을 별도로 Review한다.
인증키가 없으면 요청 0회이고 Pagination / ID / 정렬은 UNCONFIRMED로 남는다.

## dev Live Observation — 2026-09-28 KST

run-id: `bizinfo-dev-20260928-01`, 실제 HTTP 요청 4회, prod / 100건 요청 없음.
수집 시각은 UTC 2026-09-27 15:17:34–35이며 KST 2026-09-28 00:17:34–35다.
Local JSON: `harness/workspace/artifacts/bizinfo-probe-bizinfo-dev-20260928-01.json` (ignored).
Raw 네 개는 `data/raw/<run-id>-<request-name>/`에 byte·수집 시각·checksum으로 보존하고 모두 verify-snapshot을 통과했다.
[작업 Report](../../harness/workspace/reports/2026-09-28-codex-bizinfo-profile-live-probe-report.md)에 Raw hash와 관찰을 기록한다.
공식 Request 근거·제공 Sample·Mock Tests·Live는 별개 Evidence다.

| 요청 | 실제 결과 |
| --- | --- |
| page1 | HTTP 200 / 00 NORMAL_SERVICE; item 10, pageNo=1, numOfRows=10, totalCount=1514 |
| page2 | HTTP 200 / 00 NORMAL_SERVICE; item 10, pageNo=2, numOfRows=10, totalCount=1514 |
| known_id | HTTP 200 / 00 NORMAL_SERVICE; item 1, 요청 ID와 일치, pageNo=1, numOfRows=10, totalCount=1 |
| presumed_missing_id | HTTP 200 / 03 NODATA_ERROR; items={} / item 없음, pageNo=1, numOfRows=0, totalCount=0 |

두 페이지의 내부 / 페이지 간 ID 중복은 없었고 totalCount는 일치했다.
각 페이지와 합친 20건의 creatPnttm은 **Observed descending order**다. API newest-first 보장은 UNCONFIRMED다.
Sample totalCount=1518과 이번 1514는 시점이 다른 관찰이며 감소 원인을 추정하지 않는다.
Probe 종료 **1**은 마지막 요청의 api_error 때문이다. 음성 응답을 성공 / 빈 성공 배열로 바꾸거나 전체 Live PASS로 기록하지 않는다.
페이지 동작·알려진 ID 단건 필터와 위 no-data 형태는 이 run에서 OBSERVED이며 일반 공식 보장으로 승격하지 않는다.

## 주요 Field 기준 — 이번 API 품질 측정 범위

공급자 Required와 측정용 required 후보를 구분한다. 누락 / null / blank는 따로 계수한다.
blank는 `string.strip()==""`의 측정용 분류이며 Raw를 수정하지 않는다. 이번 측정의 VALID는 관찰 타입에 맞는 nonblank 값이다. 의미·URL 접속 성공은 UNMEASURED다.

| Field | 측정용 required 후보 | null 처리 초안 | blank 처리 초안 | invalid 정의 / 남은 결정 |
| --- | --- | --- | --- | --- |
| pblancId | 예 | 유효 ID 아님 | 유효 ID 아님 | nonblank string; 형식·전역 유일성·지속성 검증 필요 |
| pblancNm | 예 | missing quality로 분리 | missing quality로 분리 | 제목 의미·최소 길이 미확정 |
| pblancUrl | 예 | URL 미확보로 분리 | URL 미확보로 분리 | URL 문법·공식 domain·접속 성공 판정 미확정 |
| jrsdInsttNm | 예 | missing quality로 분리 | missing quality로 분리 | 기관 표기·허용값 미확정 |
| excInsttNm | 예 | missing quality로 분리 | missing quality로 분리 | 기관 표기·허용값 미확정 |
| pldirSportRealmLclasCodeNm | 예 | missing quality로 분리 | missing quality로 분리 | 분야 코드 목록·다중값 의미 미확정 |
| creatPnttm | 예 | 날짜 미확보로 분리 | 날짜 미확보로 분리 | 형식·timezone·등록일 의미 미확정 |
| reqstBeginEndDe | 예 | 기간 미확보로 분리 | 기간 미확보로 분리 | 비정형 nonblank Raw 허용; 날짜만 허용하는 invalid 규칙 금지 |
| updtPnttm | 예 | 날짜 미확보로 분리 | 날짜 미확보로 분리 | 형식·timezone·수정 semantics 미확정 |
| trgetNm | 예 | 대상 미확보로 분리 | 대상 미확보로 분리 | 허용값·상세 대상과 차이 미확정 |
| printFlpthNm | 확보율 후보 | 미확보로 허용·별도 계수 | 미확보로 별도 계수 | URL 문법·접속·Primary 역할 미확정 |
| printFileNm | 확보율 후보 | 미확보로 허용·별도 계수 | 미확보로 별도 계수 | 이름·URL 대응·확장자·Primary 역할 미확정 |

print* null 허용은 측정 초안이며 Sample에서 null을 관찰했다는 뜻은 아니다.
이번 사용자 요청의 12개 주요 field·실제 수집 행 분모·5종 상태를 품질 분석에 적용한다. 서비스 필수성·의미 판정은 별도 Review한다.

## 이번 100건 Sample Rule

**CONFIRMED — 사용자 승인 표본 규칙**: 수집 시점 API 기본 정렬 기준 선두 100건.
pageNo 1–5 / numOfRows 20, 총 5요청 / 최대 100개 Item이다. 중복 행을 임의 제거하지 않는다.
공식 newest-first 보장은 **UNCONFIRMED**이며 실제 순서는 **OBSERVED**로만 기록한다.
[로컬 품질 계약](../schemas/phase0-api-quality.contract.json)에 상태·분모·dev 제한·재시도 없음이 정의된다.
전체 Collector·문서 다운로드·Parser·DB·GO / DROP은 포함하지 않는다.

## Probe Expected Negative 경계

SUCCESS / EXPECTED_NO_DATA / API_ERROR / TRANSPORT_ERROR / CONTRACT_ERROR를 구분한다.
`presumed_missing_id` 명시적인 Negative plan에서 요청 ID가 계약의 Synthetic ID와 같고,
HTTP 200 / 03 NODATA_ERROR / items={} / numOfRows=0 / totalCount=0 / pageNo echo가 일치할 때만 EXPECTED_NO_DATA다.
같은 03이라도 page1 / page2 / known_id / Batch Positive 요청은 API_ERROR다.
Negative가 00 성공을 반환하면 실제 outcome=SUCCESS지만 expected outcome 불일치로 전체 종료 1이다.
위 과거 Live run의 exit 1과 Raw Evidence는 당시 동작 그대로 보존한다. 이번 수정으로 과거 결과를 다시 쓰지 않는다.

## dev API 품질 Observation — 2026-09-28 KST

별도 승인 Run `api-quality-dev-20260928-01`은 5×20 / 실제 HTTP 5회 / 100개 Item을 수집했다.
5 Page 모두 200 / 00 NORMAL_SERVICE / echo 일치 / totalCount=1514이며 ID unique=100 / 중복=0이다.
페이지 내부·경계·전체 creatPnttm은 Observed descending order이며 공식 보장은 UNCONFIRMED다.
[재현 가능한 Data Quality Report](../../harness/workspace/reports/2026-09-28-phase0-api-data-quality-report.md)에
12개 주요 field·첨부 metadata·기간·확장자·예외·Raw checksum과 측정 한계를 기록한다.
이 결과는 한 시점의 OBSERVED 표본이며 API 전체 품질·최신순 보장·문서 다운로드 성공·Primary 역할을 확정하지 않는다.
