import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../shared/api/client";
import { ErrorMessage, FieldMessage, Loading, fieldMessage } from "../../shared/components/StateViews";
import { companyApi, type Company, type CompanyInput } from "./companyApi";

// 입력 form은 문자열로 다루고 저장할 때만 숫자·boolean·null로 바꾼다. 빈 칸은 "입력하지 않음(null)"이다.
type FormState = Record<keyof CompanyInput, string>;

const EMPTY: FormState = {
  companyName: "", businessEntityType: "", companySize: "", region: "", industry: "", businessStartDate: "",
  businessStatus: "", employeeCount: "", annualRevenueKrw: "", ventureCertified: "", researchInstitute: "", exporter: "",
};

function toForm(company: Company): FormState {
  const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));
  return Object.fromEntries(Object.keys(EMPTY).map((key) => [key, text(company[key as keyof CompanyInput])])) as FormState;
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

export function CompanyPage() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["company"], queryFn: companyApi.get, retry: false });
  const notRegistered = query.error instanceof ApiError && query.error.code === "company_not_registered";
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (query.data) setForm(toForm(query.data));
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: (input: CompanyInput) => (query.data ? companyApi.update(input) : companyApi.create(input)),
    onSuccess: (company) => {
      queryClient.setQueryData(["company"], company);
      setSaved(true);
    },
  });

  if (query.isPending) return <Loading />;
  if (query.isError && !notRegistered) return <ErrorMessage error={query.error} onRetry={() => query.refetch()} />;

  const error = mutation.error;
  const set = (name: keyof FormState) => (event: { target: { value: string } }) => {
    setSaved(false);
    setForm((current) => ({ ...current, [name]: event.target.value }));
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate(toInput(form));
  };
  const input = (name: keyof FormState, label: string, props: Record<string, string> = {}) => (
    <label className="field">
      <span>{label}</span>
      <input value={form[name]} onChange={set(name)} {...props} />
      <FieldMessage message={fieldMessage(error, name)} />
    </label>
  );
  const select = (name: keyof FormState, label: string, options: [string, string][]) => (
    <label className="field">
      <span>{label}</span>
      <select value={form[name]} onChange={set(name)}>
        <option value="">선택 안 함</option>
        {options.map(([value, text]) => (
          <option key={value} value={value}>{text}</option>
        ))}
      </select>
      <FieldMessage message={fieldMessage(error, name)} />
    </label>
  );
  const yesNo: [string, string][] = [["true", "예"], ["false", "아니오"]];

  return (
    <div className="page narrow">
      <h1>내 기업정보</h1>
      <p className="muted">
        지원 자격 판정에 쓰는 기본정보입니다. 모르는 항목은 비워 두세요. 비운 항목과 관련된 조건은 "추가 정보 필요"로 표시됩니다.
      </p>
      {notRegistered && <p className="alert info">아직 등록된 기업정보가 없습니다. 아래에서 등록해 주세요.</p>}
      <form className="card form-grid" onSubmit={submit} noValidate>
        {input("companyName", "회사명 *", { "aria-required": "true", maxLength: "100" })}
        {select("businessEntityType", "사업자 형태", [["개인사업자", "개인사업자"], ["법인", "법인"]])}
        {input("companySize", "기업 규모", { placeholder: "예: 소상공인, 중소기업" })}
        {input("region", "사업장 소재지", { placeholder: "예: 경기도 광명시" })}
        {input("industry", "업종", { placeholder: "예: 식료품 제조업" })}
        {input("businessStartDate", "개업일", { type: "date" })}
        {select("businessStatus", "영업 상태", [["영업중", "영업중"], ["휴업", "휴업"], ["폐업", "폐업"]])}
        {input("employeeCount", "상시근로자 수(명)", { type: "number", min: "0", inputMode: "numeric" })}
        {input("annualRevenueKrw", "최근 연 매출(원)", { type: "number", min: "0", inputMode: "numeric" })}
        {select("ventureCertified", "벤처기업 확인", yesNo)}
        {select("researchInstitute", "기업부설연구소 보유", yesNo)}
        {select("exporter", "수출 실적 보유", yesNo)}
        <div className="form-actions">
          {error && !(error instanceof ApiError && error.fieldErrors.length > 0) && <ErrorMessage error={error} />}
          {saved && <p className="alert success" role="status">저장했습니다.</p>}
          <button className="button primary" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "저장 중..." : query.data ? "수정 저장" : "등록"}
          </button>
        </div>
      </form>
    </div>
  );
}
