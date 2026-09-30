import { CitationList } from "./CitationList";
import type { CriterionResult, EligibilityResult, EligibilityStatus } from "./aiApi";

// 화면은 한글을 우선하고 원래 상태 코드를 작게 함께 보여 준다(문의·로그 대조용).
export const STATUS_TEXT: Record<EligibilityStatus, { label: string; tone: string; help: string }> = {
  ELIGIBLE: { label: "지원 가능", tone: "good", help: "공고문에서 찾은 조건을 모두 충족합니다." },
  INELIGIBLE: { label: "지원 불가", tone: "bad", help: "충족하지 못하는 조건이 있습니다." },
  NEEDS_MORE_INFO: { label: "추가 정보 필요", tone: "warn", help: "기업정보가 부족해 판단하지 못한 조건이 있습니다." },
  INSUFFICIENT_EVIDENCE: { label: "공고 근거 부족", tone: "neutral", help: "공고문에서 자격 조건 근거를 찾지 못했습니다." },
};

const RESULT_TEXT: Record<CriterionResult, string> = { MET: "충족", NOT_MET: "미충족", UNKNOWN: "판단 불가" };

export function EligibilityResultView({ result }: { result: EligibilityResult }) {
  const status = STATUS_TEXT[result.status];
  return (
    <section className="eligibility-result" aria-label="지원 자격 판정 결과">
      <div className={`status-box tone-${status.tone}`}>
        <strong className="status-label">{status.label}</strong>
        <span className="status-code">{result.status}</span>
        <p>{status.help}</p>
      </div>
      {result.criteria.length > 0 && (
        <ol className="criteria">
          {result.criteria.map((item, index) => (
            <li key={index} className="criterion">
              <div className="criterion-head">
                <span className={`badge result-${item.result.toLowerCase()}`}>{RESULT_TEXT[item.result]}</span>
                <strong>{item.criterion}</strong>
              </div>
              <p>{item.reason}</p>
              <CitationList citations={item.citations} />
            </li>
          ))}
        </ol>
      )}
      {result.missingInformation.length > 0 && (
        <p className="alert warn">추가로 필요한 정보: {result.missingInformation.join(", ")}</p>
      )}
      <p className="muted small">{result.disclaimer}</p>
    </section>
  );
}
