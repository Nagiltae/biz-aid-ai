import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../shared/api/client";
import { DemoCompanyNotice } from "../../shared/components/DemoCompanyNotice";
import { ErrorMessage, FieldMessage, Loading, fieldMessage } from "../../shared/components/StateViews";
import { COMPANY_SIZES, companyApi, type Company, type CompanyInput } from "./companyApi";
import { useAuth } from "../auth/AuthContext";
import { MY_COMPANY_KEY, useMyCompany } from "./useMyCompany";

// 입력 form은 문자열로 다루고 저장할 때만 숫자·boolean·null로 바꾼다. 빈 칸은 "입력하지 않음(null)"이다.
type FormState = Record<keyof CompanyInput, string>;

const EMPTY: FormState = {
  companyName: "", businessEntityType: "", companySize: "", region: "", industry: "", businessStartDate: "",
  businessStatus: "", employeeCount: "", annualRevenueKrw: "", ventureCertified: "", researchInstitute: "", exporter: "",
};

function toForm(company: Company): FormState {
  const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));
  const form = Object.fromEntries(Object.keys(EMPTY).map((key) => [key, text(company[key as keyof CompanyInput])])) as FormState;
  // 선택지 밖의 예전 자유 입력 값은 선택 상자에 둘 수 없으므로 비우고, 화면에 다시 고르라고 안내한다.
  if (!isSizeOption(form.companySize)) form.companySize = "";
  return form;
}

function isSizeOption(value: string | null) {
  return value === null || value === "" || (COMPANY_SIZES as readonly string[]).includes(value);
}

function toInput(form: FormState): CompanyInput {
  const text = (value: string) => (value.trim() === "" ? null : value.trim());
  const number = (value: string) => (value.trim() === "" ? null : Number(value));
  const flag = (value: string) => (value === "" ? null : value === "true");
  return {
    companyName: form.companyName.trim(),
    businessEntityType: text(form.businessEntityType) as CompanyInput["businessEntityType"],
    companySize: text(form.companySize),
    region: text(form.region),
    industry: text(form.industry),
    businessStartDate: text(form.businessStartDate),
    businessStatus: text(form.businessStatus) as CompanyInput["businessStatus"],
    employeeCount: number(form.employeeCount),
    annualRevenueKrw: number(form.annualRevenueKrw),
    ventureCertified: flag(form.ventureCertified),
    researchInstitute: flag(form.researchInstitute),
    exporter: flag(form.exporter),
  };
}

const YES_NO: [string, string][] = [["true", "예"], ["false", "아니오"]];

// WHY: 표시만 바꾸고 form에는 숫자 문자열을 보존한다. 쉼표가 API 숫자에 섞이지 않는다.
function commaAmount(value: string) {
  return value.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function readableAmount(value: string) {
  if (!value) return "금액을 입력하면 읽기 쉬운 단위로 보여 드려요.";
  let remaining = BigInt(value);
  const parts: string[] = [];
  for (const [size, name] of [[1000000000000n, "조"], [100000000n, "억"], [10000n, "만"], [1n, ""]] as const) {
    const amount = remaining / size;
    if (amount) parts.push(`${amount.toLocaleString("ko-KR")}${name}`);
    remaining %= size;
  }
  return `${parts.join(" ") || "0"} 원`;
}

/**
 * 내 기업정보.
 * - 없으면: 등록 form. 다른 기능(AI 검색·맞춤 추천)은 등록 뒤에 쓸 수 있다.
 * - 있으면: 읽기 전용 정보와 [수정] 버튼. [수정]을 눌러야 form이 열리고, 저장·취소 뒤에는 다시 보기 화면이다.
 */
export function CompanyPage() {
  const query = useMyCompany();
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as { from?: string; needCompany?: boolean } | null;
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  // 체험 계정은 미리 넣은 예시 회사 정보만 쓴다(서버도 trial_account_restricted로 막는다).
  const trial = useAuth().user?.trial === true;

  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorMessage error={query.error} onRetry={() => query.refetch()} />;
  const company = query.data;

  return (
    <div className="page narrow">
      <div className="page-head">
        <h1>내 기업정보</h1>
        {company && !editing && !trial && (
          <button type="button" className="button" onClick={() => { setSaved(false); setEditing(true); }}>수정</button>
        )}
      </div>
      {(company === null || editing) && <DemoCompanyNotice />}
      {company === null ? (
        <>
          <p className={state?.needCompany ? "alert warn" : "alert info"} role="status">
            기업정보를 등록하면 지역 기반 AI 검색과 맞춤 추천을 쓸 수 있습니다. 회사명만 넣어도 등록되며, 모르는 항목은 비워 두세요.
          </p>
          <CompanyForm
            company={null}
            onSaved={() => {
              // 다른 기능을 쓰려다 넘어왔다면 등록 뒤 그 화면으로 돌려보낸다.
              if (state?.from && state.from !== "/company") navigate(state.from, { replace: true });
              else setSaved(true);
            }}
          />
        </>
      ) : editing ? (
        <CompanyForm company={company} onSaved={() => { setEditing(false); setSaved(true); }} onCancel={() => setEditing(false)} />
      ) : (
        <>
          {saved && <p className="alert success" role="status">저장했습니다.</p>}
          {trial && (
            <p className="alert info" role="status">
              체험 계정은 아래 예시 회사 정보로만 이용할 수 있어요. 우리 회사 정보로 확인하려면 회원가입해 주세요.
            </p>
          )}
          <CompanyView company={company} />
        </>
      )}
    </div>
  );
}

/** 지역 선택지. 바뀌지 않는 공통 계약 값이라 화면을 쓰는 동안 다시 받지 않는다. */
function useRegions() {
  return useQuery({ queryKey: ["company-regions"], queryFn: companyApi.regions, staleTime: Infinity });
}

function CompanyView({ company }: { company: Company }) {
  const regions = useRegions();
  const legacyRegion = company.region && regions.data && !regions.data.regions.includes(company.region) ? company.region : null;
  const show = (value: unknown, suffix = "") => {
    if (value === null || value === undefined || value === "") return <span className="muted">입력 안 함</span>;
    if (value === true) return "예";
    if (value === false) return "아니오";
    return typeof value === "number" ? `${value.toLocaleString("ko-KR")}${suffix}` : `${value}${suffix}`;
  };
  return (
    <section className="card" aria-label="등록된 기업정보">
      <p className="muted small">지원 자격 판정에 쓰는 기본정보입니다. 비운 항목과 관련된 조건은 "추가 정보 필요"로 표시됩니다.</p>
      <dl className="meta wide company-view">
        <dt>회사명</dt><dd>{company.companyName}</dd>
        <dt>사업자 형태</dt><dd>{show(company.businessEntityType)}</dd>
        <dt>기업 규모</dt>
        <dd>
          {show(company.companySize)}
          {!isSizeOption(company.companySize) && <span className="muted small"> (선택지에 없는 예전 값입니다. 수정할 때 다시 골라 주세요)</span>}
        </dd>
        <dt>사업장 소재지</dt>
        <dd>
          {show(company.region)}
          {legacyRegion && <span className="muted small"> (선택지에 없는 예전 값입니다. 수정할 때 광역 지자체를 다시 골라 주세요)</span>}
        </dd>
        <dt>업종</dt><dd>{show(company.industry)}</dd>
        <dt>개업일</dt><dd>{show(company.businessStartDate)}</dd>
        <dt>영업 상태</dt><dd>{show(company.businessStatus)}</dd>
        <dt>상시근로자 수</dt><dd>{show(company.employeeCount, "명")}</dd>
        <dt>최근 연 매출</dt><dd>{show(company.annualRevenueKrw, "원")}</dd>
        <dt>벤처기업 확인</dt><dd>{show(company.ventureCertified)}</dd>
        <dt>기업부설연구소 보유</dt><dd>{show(company.researchInstitute)}</dd>
        <dt>수출 실적 보유</dt><dd>{show(company.exporter)}</dd>
      </dl>
    </section>
  );
}

function CompanyForm({ company, onSaved, onCancel }: { company: Company | null; onSaved: () => void; onCancel?: () => void }) {
  const queryClient = useQueryClient();
  const regions = useRegions();
  const regionOptions = regions.data?.regions ?? [];
  const [form, setForm] = useState<FormState>(company ? toForm(company) : EMPTY);
  useEffect(() => {
    setForm(company ? toForm(company) : EMPTY);
  }, [company]);

  const mutation = useMutation({
    mutationFn: (input: CompanyInput) => (company ? companyApi.update(input) : companyApi.create(input)),
    onSuccess: (saved) => {
      // 메뉴·보호 routing이 같은 값을 보므로 등록 즉시 다른 기능이 열린다.
      queryClient.setQueryData(MY_COMPANY_KEY, saved);
      onSaved();
    },
  });
  const error = mutation.error;
  const set = (name: keyof FormState) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [name]: event.target.value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const input = toInput(form);
    // 선택지 밖의 예전 지역 값은 서버가 받지 않으므로, 다시 고르지 않았으면 "모름"(null)으로 저장한다.
    if (input.region && !regionOptions.includes(input.region)) input.region = null;
    mutation.mutate(input);
  };
  const input = (name: keyof FormState, label: string, props: Record<string, string> = {}) => (
    <label className="field">
      <span>{label}</span>
      <input value={form[name]} onChange={set(name)} {...props} />
      <FieldMessage message={fieldMessage(error, name)} />
    </label>
  );
  const select = (name: keyof FormState, label: string, options: [string, string][], empty = "선택 안 함") => (
    <label className="field">
      <span>{label}</span>
      <select value={form[name]} onChange={set(name)}>
        <option value="">{empty}</option>
        {options.map(([value, text]) => (
          <option key={value} value={value}>{text}</option>
        ))}
      </select>
      <FieldMessage message={fieldMessage(error, name)} />
    </label>
  );
  const legacySize = company && !isSizeOption(company.companySize) ? company.companySize : null;
  const legacyRegion = company?.region && regions.data && !regionOptions.includes(company.region) ? company.region : null;

  return (
    <form className="card form-grid" onSubmit={submit} noValidate aria-label={company ? "기업정보 수정" : "기업정보 등록"}>
      {input("companyName", "회사명 *", { "aria-required": "true", maxLength: "100" })}
      {select("businessEntityType", "사업자 형태", [["개인사업자", "개인사업자"], ["법인", "법인"]])}
      {select("companySize", "기업 규모", COMPANY_SIZES.map((size) => [size, size]), "모름·해당 없음")}
      {select("region", "사업장 소재지(광역 지자체)", regionOptions.map((region) => [region, region]), "모름")}
      {input("industry", "업종", { placeholder: "예: 식료품 제조업" })}
      {input("businessStartDate", "개업일", { type: "date" })}
      {select("businessStatus", "영업 상태", [["영업중", "영업중"], ["휴업", "휴업"], ["폐업", "폐업"]])}
      {input("employeeCount", "상시근로자 수(명)", { type: "number", min: "0", inputMode: "numeric" })}
      <label className="field">
        <span id="annual-revenue-label">최근 연 매출(원)</span>
        <input type="text" inputMode="numeric" value={commaAmount(form.annualRevenueKrw)} aria-labelledby="annual-revenue-label" aria-describedby="annual-revenue-help"
               onChange={(event) => {
                 const digits = event.target.value.replace(/,/g, "");
                 if (/^\d*$/.test(digits)) setForm((current) => ({ ...current, annualRevenueKrw: digits }));
               }} />
        <small id="annual-revenue-help" className="muted">{readableAmount(form.annualRevenueKrw)}</small>
        <FieldMessage message={fieldMessage(error, "annualRevenueKrw")} />
      </label>
      {select("ventureCertified", "벤처기업 확인", YES_NO)}
      {select("researchInstitute", "기업부설연구소 보유", YES_NO)}
      {select("exporter", "수출 실적 보유", YES_NO)}
      <div className="form-note muted small">
        맞춤 추천은 기업 지역과 전국 공고를 기준으로 찾습니다. 제목의 지역 표시와 소관기관을 함께 확인합니다.
        {legacySize && <p>예전에 입력한 "{legacySize}"는 선택지에 없습니다. 다시 골라 주세요.</p>}
        {legacyRegion && <p>예전에 입력한 "{legacyRegion}"는 선택지에 없습니다. 광역 지자체를 다시 골라 주세요.</p>}
      </div>
      {error && !(error instanceof ApiError && error.fieldErrors.length > 0) && <div className="form-note"><ErrorMessage error={error} /></div>}
      <div className="form-actions">
        {onCancel && (
          <button type="button" className="button" onClick={onCancel} disabled={mutation.isPending}>취소</button>
        )}
        <button className="button primary" type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "저장 중..." : company ? "저장" : "등록"}
        </button>
      </div>
    </form>
  );
}
