# 데이터 출처와 원문

승인된 공식 중소벤처기업부 지원사업 공고 API와 연결된 공식 공고문만 사용한다.
임의 외부 Source를 추가하지 않는다. pblancId를 source identity로 검증한 후 사용한다.
원문 byte·checksum·수집 시각을 보존하고 정규화 데이터와 구분한다.
원문과 실패 데이터를 임의 삭제·덮어쓰기 하지 않는다.

현재 data/raw/는 개발환경 원본 저장소다. payload·첨부·개인정보는 Git에 넣지 않는다.
증거는 credential 없는 상대 경로·checksum·수집 run-id로 연결한다.
Raw metadata / 필요 JSON의 MySQL JSON column 관리는 향후 계획이다.
실제 upstream 응답을 확인하지 않고 필수 field나 envelope를 확정하지 않는다.
