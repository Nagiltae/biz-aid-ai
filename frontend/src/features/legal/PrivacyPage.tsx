import { Link } from "react-router-dom";
import { PRIVACY_VERSION } from "./legalVersions";

// RISK: 개인 포트폴리오 서비스 기준 초안이다. 운영 전 사용자가 문구·문의처를 검토하고 채운다(보고서 기재).
export function PrivacyPage() {
  return (
    <article className="page narrow legal" aria-label="개인정보처리방침">
      <h1>개인정보처리방침</h1>
      <p className="muted small">시행일 {PRIVACY_VERSION} · 초안</p>
      <p>BizAid(이하 "서비스")는 이용자의 개인정보를 아래와 같이 처리합니다.</p>

      <h2>1. 수집하는 정보</h2>
      <ul>
        <li>회원 정보: 이메일, 이름(닉네임), 비밀번호(복원할 수 없는 해시 값으로만 저장)</li>
        <li>기업정보: 회사명, 사업자 형태, 기업 규모, 지역, 업종, 개업일, 영업 상태, 직원 수, 매출 등 이용자가 입력한 값</li>
        <li>AI 이용 기록: AI 검색 질문과 답변, 맞춤 추천 진행 기록</li>
        <li>약관 동의 기록(문서 버전·동의 시각), 하루 AI 사용 횟수</li>
      </ul>
      <p className="muted small">자격 판정 때 입력하는 신용점수·체납 여부는 그 요청에만 쓰고 저장하지 않습니다.</p>

      <h2>2. 이용 목적</h2>
      <ul>
        <li>로그인과 계정 관리</li>
        <li>기업정보에 맞는 지원사업 검색·추천과 공고문 근거 자격 확인</li>
        <li>서비스 안정 운영(로그인 시도 제한, 하루 사용 제한, 오류 확인)</li>
      </ul>

      <h2>3. 보관 기간</h2>
      <ul>
        <li>회원 탈퇴 시 계정·기업정보·AI 대화·추천 기록·동의 기록을 즉시 삭제합니다.</li>
        <li>활동 기록(언제 어떤 기능을 썼는지)은 누구인지 알 수 없게 바꾼 뒤 운영 통계로만 남깁니다.</li>
        <li>체험 계정은 만든 뒤 24시간이 지나면 모든 데이터와 함께 자동 삭제됩니다.</li>
      </ul>

      <h2>4. 처리 위탁</h2>
      <ul>
        <li>Amazon Web Services(AWS): 서버와 데이터베이스 운영</li>
        <li>Amazon Bedrock(AWS): AI 처리. 이용자의 질문, 기업정보, 공개된 공고문 내용이 AI 답변·자격 판정을 만드는 데 사용됩니다.</li>
      </ul>

      <h2>5. 이용자의 권리</h2>
      <p>
        이용자는 언제든지 <Link to="/account">계정 화면</Link>에서 회원 탈퇴로 개인정보 삭제를 요청할 수 있습니다.
        기업정보는 <Link to="/company">내 기업정보</Link>에서 고칠 수 있습니다.
      </p>

      <h2>6. 문의처</h2>
      <p>개인정보 관련 문의: [문의처 이메일을 입력하세요]</p>
    </article>
  );
}
