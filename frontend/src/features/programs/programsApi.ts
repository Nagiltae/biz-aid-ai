import { apiRequest } from "../../shared/api/client";

export type RecruitmentStatus = "OPEN" | "UPCOMING" | "CLOSED" | "UNDATED";

export interface ProgramSummary {
  pblancId: string;
  name: string | null;
  category: string | null;
  target: string | null;
  jurisdictionName: string | null;
  applicationStartDate: string | null;
  applicationEndDate: string | null;
  applicationPeriodRaw: string | null;
  recruitmentStatus: RecruitmentStatus;
  recruitmentStatusLabel: string;
}

export interface ProgramDetail extends ProgramSummary {
  executingOrgName: string | null;
  summary: string | null;
  applicationMethod: string | null;
  announcementUrl: string | null;
  applicationUrl: string | null;
}

export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

export interface FilterOptions {
  categories: string[];
  targets: string[];
  jurisdictions: string[];
  statuses: { value: RecruitmentStatus; label: string }[];
}

export interface ProgramFilters {
  keyword: string;
  category: string;
  target: string;
  jurisdiction: string;
  status: string;
  page: number;
}

export const PAGE_SIZE = 12;

export const programsApi = {
  search: (filters: ProgramFilters) =>
    apiRequest<Page<ProgramSummary>>("/api/programs", { query: { ...filters, size: PAGE_SIZE } }),
  filterOptions: () => apiRequest<FilterOptions>("/api/programs/filter-options"),
  get: (pblancId: string) => apiRequest<ProgramDetail>(`/api/programs/${encodeURIComponent(pblancId)}`),
};

/** 신청기간 표시: 파생 날짜가 있으면 날짜 범위, 없으면 기업마당 원문(예: "예산 소진시까지")을 그대로 보여 준다. */
export function periodText(program: Pick<ProgramSummary, "applicationStartDate" | "applicationEndDate" | "applicationPeriodRaw">) {
  if (program.applicationStartDate || program.applicationEndDate) {
    return `${program.applicationStartDate ?? "?"} ~ ${program.applicationEndDate ?? "?"}`;
  }
  return program.applicationPeriodRaw ?? "기간 정보 없음";
}
