// 이용약관·개인정보처리방침 현재 버전(시행일). 가입·체험 동의 기록에 서버 설정(bizaid.legal.*) 값이 남는다.
// BOUNDARY: backend application.yml의 bizaid.legal.terms-version / privacy-version과 같아야 한다(tests/contract/test_legal_versions.py).
export const TERMS_VERSION = "2026-10-04";
export const PRIVACY_VERSION = "2026-10-04";

/** 원천 데이터 안내. 확인된 사실만 적는다(이용허락 조건 문구는 사용자 확인 뒤 추가). */
export const DATA_SOURCE = {
  name: "기업마당(중소벤처기업부)",
  url: "https://www.bizinfo.go.kr",
  portal: "공공데이터포털(data.go.kr) 기업마당 지원사업 공고 API",
};
