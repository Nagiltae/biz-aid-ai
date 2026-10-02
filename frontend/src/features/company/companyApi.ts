import { ApiError, apiRequest } from "../../shared/api/client";

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

/** 기업 규모 선택지. 맞춤 추천의 기업규모 → 지원대상 매핑과 같고, 서버(CompanyRequest)도 같은 값만 받는다. 비우면 "모름·해당 없음". */
export const COMPANY_SIZES = ["소상공인", "중소기업", "중견기업"] as const;

export const companyApi = {
  get: () => apiRequest<Company>("/api/company"),
  /** 내 기업정보. 아직 등록하지 않았으면 오류 대신 null(화면이 "등록 필요"로 분기하는 정상 상태다). */
  find: () =>
    apiRequest<Company>("/api/company").catch((error: unknown) => {
      if (error instanceof ApiError && error.code === "company_not_registered") return null;
      throw error;
    }),
  create: (body: CompanyInput) => apiRequest<Company>("/api/company", { method: "POST", body }),
  update: (body: CompanyInput) => apiRequest<Company>("/api/company", { method: "PUT", body }),
};
