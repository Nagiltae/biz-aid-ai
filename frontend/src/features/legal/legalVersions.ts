// 이용약관·개인정보처리방침 현재 버전(같은 시행일의 개정은 .번호로 구분). 가입·체험 동의 기록에 서버 설정(bizaid.legal.*) 값이 남는다.
// BOUNDARY: backend application.yml의 bizaid.legal.terms-version / privacy-version과 같아야 한다(tests/contract/test_legal_versions.py).
export const TERMS_VERSION = "2026-10-04.3";
export const PRIVACY_VERSION = "2026-10-04.3";

/** 사용자가 공공데이터포털에서 확인한 공공누리 제3유형(출처표시·변경금지)을 안내한다. */
export const DATA_SOURCE = {
  notice: "이 서비스는 중소벤처기업부(기업마당)가 공공누리 제3유형으로 개방한 '기업마당 지원사업정보'를 이용합니다. 원문은 기업마당에서 확인할 수 있습니다.",
  licenseUrl: "https://www.kogl.or.kr/info/licenseType3.do",
  name: "기업마당(중소벤처기업부)",
  url: "https://www.bizinfo.go.kr",
  portal: "공공데이터포털(data.go.kr) 기업마당 지원사업 공고 API",
};
