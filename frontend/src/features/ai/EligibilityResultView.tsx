import { Link } from "react-router-dom";
import { CitationList } from "./CitationList";
import type { CriterionResult, EligibilityResult, EligibilityStatus } from "./aiApi";

// 화면은 한글을 우선하고 원래 상태 코드를 작게 함께 보여 준다(문의·로그 대조용). 판정 자체는 FastAPI 값 그대로다.
export const STATUS_TEXT: Record<EligibilityStatus, { label: string; tone: string; help: string }> = {
  ELIGIBLE: { label: "지원 가능", tone: "good", help: "공고문에서 찾은 조건을 모두 충족합니다." },
  INELIGIBLE: { label: "지원 불가", tone: "bad", help: "충족하지 못하는 조건이 있습니다." },
  NEEDS_MORE_INFO: { label: "추가 정보 필요", tone: "warn", help: "기업정보가 부족해 판단하지 못한 조건이 있습니다." },
  INSUFFICIENT_EVIDENCE: { label: "공고 근거 부족", tone: "neutral", help: "공고문에서 자격 조건 근거를 찾지 못했습니다." },
};

const RESULT_TEXT: Record<CriterionResult, string> = { MET: "충족", NOT_MET: "미충족", UNKNOWN: "판단 불가" };

// FastAPI 기업 정보 field 이름 → 화면 이름. 이 판정에서 직접 입력하는 값과 기업정보에서 고칠 값을 나눈다.
const TEMPORARY_FIELDS: Record<string, string> = { credit_score: "대표자 신용점수", tax_delinquent: "국세·지방세 체납 여부" };
const COMPANY_FIELDS: Record<string, string> = {
  company_name: "회사명", business_entity_type: "사업자 형태", company_size: "기업 규모", region: "사업장 소재지",
  industry: "업종", business_start_date: "개업일", business_age_months: "업력(개업일로 계산)", business_status: "영업 상태",
  employee_count: "상시근로자 수", annual_revenue_krw: "연 매출", venture_certified: "벤처기업 확인",
  research_institute: "기업부설연구소", exporter: "수출 실적",
};

export function fieldLabel(name: string) {
  if (name.startsWith("additional_facts.")) return name.slice("additional_facts.".length);
  return TEMPORARY_FIELDS[name] ?? COMPANY_FIELDS[name] ?? name;
}

export function EligibilityResultView({ result }: { result: EligibilityResult }) {
  const status = STATUS_TEXT[result.status];
  const temporary = result.missingInformation.filter((name) => name in TEMPORARY_FIELDS);
  const company = result.missingInformation.filter((name) => !(name in TEMPORARY_FIELDS));
  return (
    <section className="eligibility-result" aria-label="지원 자격 판정 결과">
      <div className={`status-box tone-${status.tone}`}>
        <strong className="status-label">{status.label}</strong>
        <span className="status-code">{result.status}</span>
        <p>{status.help}</p>
      </div>
      {result.missingInformation.length > 0 && (
        <div className="alert warn">
          <strong>추가로 필요한 정보</strong>
          {temporary.length > 0 && <span>위 입력칸: {temporary.map(fieldLabel).join(", ")} → 입력 후 다시 확인하세요.</span>}
          {company.length > 0 && (
            <span>
              기업정보: {company.map(fieldLabel).join(", ")} → <Link to="/company">기업정보 수정</Link>
            </span>
          )}
        </div>
      )}
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
      <p className="muted small">{result.disclaimer}</p>
    </section>
  );
}
