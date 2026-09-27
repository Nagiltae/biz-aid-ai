# 실제 데이터 검증 절차

Gate 실행 전에 주요 필드·분모·샘플 선정·근거 위치 기준을 사용자와 확정한다.
공식 API 약 100건의 원문과 실패 응답을 보존하고 pblancId / 필드 품질을 검사한다.
공고문 URL·확장자·다운로드·형식별 Parser 결과를 분리하고 checksum으로 연결한다.
API보다 상세한 정보와 page / section 근거를 수동 대조한다.
미측정은 not_measured, 실패는 실패로 기록하며 자동 계약 검증을 GO로 해석하지 않는다.
[보고서 양식](../../../../evals/phase0-report-template.md)에 수치·예외·자동화·GO / DROP 판단을 남긴다.
