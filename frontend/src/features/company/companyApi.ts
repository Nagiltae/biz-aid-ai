import { apiRequest } from "../../shared/api/client";

// 서비스에 오래 저장하는 기업 기본정보. 신용점수·체납 등 일시 정보는 여기 없고 자격 판정 요청 때만 보낸다.
export interface CompanyInput {
  companyName: string;
  businessEntityType: "개인사업자" | "법인" | null;
  companySize: string | null;
  region: string | null;
  industry: string | null;
  businessStartDate: string | null;
  businessStatus: "영업중" | "휴업" | "폐업" | null;
  employeeCount: number | null;
  annualRevenueKrw: number | null;
  ventureCertified: boolean | null;
  researchInstitute: boolean | null;
  exporter: boolean | null;
}

export interface Company extends CompanyInput {
  id: number;
  updatedAt: string;
}

export const companyApi = {
  get: () => apiRequest<Company>("/api/company"),
  create: (body: CompanyInput) => apiRequest<Company>("/api/company", { method: "POST", body }),
  update: (body: CompanyInput) => apiRequest<Company>("/api/company", { method: "PUT", body }),
};
