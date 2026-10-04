import { Link } from "react-router-dom";
import { ApiError } from "../../shared/api/client";
import { useTrial } from "../auth/useTrial";
import { DATA_SOURCE } from "../legal/legalVersions";

const STEPS = [
  { title: "회사 정보 입력", text: "지역, 기업 규모, 업종처럼 공고에 자주 나오는 조건만 적습니다. 모르는 칸은 비워 둬도 됩니다." },
  { title: "말로 물어보기", text: "\"경기도 소상공인 금융 지원사업 찾아줘\"처럼 평소 말투로 묻습니다." },
  { title: "공고문으로 확인", text: "AI가 공고문을 읽고 조건마다 맞음·안 맞음·확인 필요를 근거 문장과 함께 보여 줍니다." },
];

const FEATURES = [
  { title: "AI 검색", text: "흩어진 정부·지자체 지원사업을 한 번에 찾고, 공고 내용도 질문으로 확인합니다." },
  { title: "맞춤 추천", text: "우리 회사 정보로 관련 높은 공고 3건을 고르고 지원 자격을 하나씩 확인합니다." },
  { title: "근거 표시", text: "답변마다 공고문 어느 부분을 보고 판단했는지 함께 보여 줍니다. 원문 공고로 바로 갈 수 있습니다." },
];

/** 로그인하지 않은 사용자의 첫 화면. 서비스가 하는 일과 시작 방법을 쉬운 말로 안내한다. */
export function LandingPage() {
  const trial = useTrial();
  const trialError = trial.start.error instanceof ApiError ? trial.start.error.message : trial.start.error ? "체험을 시작하지 못했습니다." : null;
  return (
    <div className="page landing">
      <section className="landing-hero">
        <h1>우리 회사가 받을 수 있는 정부 지원사업, 공고문 근거로 확인하세요</h1>
        <p className="lead">
          BizAid는 정부·지자체 지원사업을 찾아 주고, 공고문을 읽어 우리 회사가 신청 조건에 맞는지 미리 확인해 주는 서비스입니다.
          중소기업·소상공인 대표님이 긴 공고문을 다 읽지 않아도 핵심 조건을 빠르게 볼 수 있습니다.
        </p>
        <div className="landing-actions">
          {trial.enabled && (
            <button type="button" className="button primary large" disabled={trial.start.isPending} onClick={() => trial.start.mutate()}>
              {trial.start.isPending ? "체험 준비 중..." : "가입 없이 체험하기"}
            </button>
          )}
          <Link className="button large" to="/login">로그인</Link>
          <Link className="button large" to="/login" state={{ mode: "signup" }}>회원가입</Link>
        </div>
        {trial.enabled && (
          <p className="muted small">
            체험하기를 누르면 <Link to="/terms">이용약관</Link>과 <Link to="/privacy">개인정보처리방침</Link>에 동의한 것으로 봅니다.
            체험 계정은 예시 회사 정보(경기도·소상공인)로 만들어지고 24시간 뒤 자동으로 지워집니다.
          </p>
        )}
        {trialError && <p className="alert error" role="alert">{trialError}</p>}
      </section>

      <section aria-label="사용 방법">
        <h2>이렇게 사용해요</h2>
        <ol className="landing-steps">
          {STEPS.map((step, index) => (
            <li key={step.title} className="card">
              <span className="step-number">{index + 1}</span>
              <h3>{step.title}</h3>
              <p className="muted">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-label="주요 기능">
        <h2>할 수 있는 일</h2>
        <div className="landing-features">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="card">
              <h3>{feature.title}</h3>
              <p className="muted">{feature.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card landing-source" aria-label="데이터 출처">
        <h2>공고 정보는 어디서 오나요?</h2>
        <p>
          {DATA_SOURCE.name}이 공공데이터로 제공하는 지원사업 공고를 사용합니다({DATA_SOURCE.portal}).
          공고 상세 화면에서 <a href={DATA_SOURCE.url} target="_blank" rel="noopener noreferrer">기업마당</a> 원문 공고로 바로 이동할 수 있습니다.
        </p>
        <p className="muted small">AI 판정은 참고용입니다. 최종 자격은 공고문과 주관기관에 꼭 확인하세요.</p>
      </section>
    </div>
  );
}
