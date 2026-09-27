# Data Feasibility Report 양식

상태: NOT_MEASURED. Gate: PENDING. 이 문서는 측정 결과가 아니다.
기계 기록은 scripts/phase0.py init-report로 생성하고 validate-report로 검사한다.

## 표본과 수집

run-id / 수집 시각 / 공식 Source / credential 없는 snapshot 경로 / SHA-256:
최근 약 100건 선정·정렬·pagination 방식:
요청·시도·정상 응답·공고 수 및 중복 수:
주요 field 목록과 null / blank / invalid 정의:
각 비율의 분자·분모·제외 기준:

## 지표와 초기 기준

| 지표 | 초기 기준 (§53) | 결과 |
| --- | --- | --- |
| 표본 | 100개 공고 | 미측정 |
| API 정상 수집률 | >=99%, 분모 확정 필요 | 미측정 |
| pblancId 존재율 / 중복 | 존재율 100%, unique 확인 | 미측정 |
| 주요 필드 유효율 / Null 비율 | 유효율 >=95%, 필드 정의 필요 | 미측정 |
| 공고문 URL 확보율 | >=90%, 상세 URL과 구분 | 미측정 |
| 확장자 PDF / HWPX / HWP / ZIP / 기타 | 분포 기록 | 미측정 |
| 공고문 다운로드 성공률 | >=95%, 시도/분모 확정 필요 | 미측정 |
| 문서 Text Extraction 성공률 | >=90%, 대상/분모 확정 필요 | 미측정 |
| 형식별 Parsing / Scan / 표 / Heading | PDF·HWPX·HWP 별 증거 | 미측정 |
| 평균 페이지 / 근거 위치 추적 | 형식별 기준 확정 필요 | 미측정 |
| 신청기간 Parsing / 수정 추적 / URL 안정성 | 예외 기록 | 미측정 |
| API 대비 추가정보 / RAG 가치 / 자동화 | 실제 대조 근거 | 미측정 |

## API와 문서 비교

pblancId / document checksum / page 또는 section / API에 있는 정보 /
문서에만 있는 자격·제외·중복지원·지원금·자부담·선정·서류·예외·주의사항 /
추출 가능 여부와 실패 이유를 기록한다.

## 예외·판단·다음 단계

실패 입력과 원문 보존 경로 / 재현 명령 / 수동 작업량:
미결정 사항과 적용한 측정 정의:
GO / DROP 근거와 사용자 판단:
모든 지표와 RAG 가치가 확인되기 전에는 PENDING을 유지한다.
자동 계약 통과만으로 GO를 결정하지 않는다.
