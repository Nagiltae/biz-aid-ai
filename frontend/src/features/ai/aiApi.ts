import { apiRequest } from "../../shared/api/client";

// AI 요청도 항상 Spring(/api)으로 보낸다. Spring이 이후 FastAPI 내부 API를 대신 호출한다.
// 응답 타입은 Spring AiDtos와 같다. 값은 AI 서비스가 계산한 그대로이며 화면에서 판정을 바꾸지 않는다.

/** 공고문 근거 위치(Citation): AI 답변·판정이 공고문의 어느 부분을 근거로 했는지. */
export interface Citation {
  evidenceId: string;
  pblancId: string;
  title: string | null;
  pages: number[];
  location: string | null;
  headingPath: string[];
}

export interface AiProgramItem {
  pblancId: string;
  name: string | null;
  category: string | null;
  target: string | null;
  jurisdictionName: string | null;
  applicationStartDate: string | null;
  applicationEndDate: string | null;
  applicationPeriodRaw: string | null;
}

export interface AiQueryResult {
  requestMode: "SEARCH_LIST" | "DOCUMENT_QA";
  status: string;
  answer: string | null;
  programs: AiProgramItem[];
  citations: Citation[];
}

export type EligibilityStatus = "ELIGIBLE" | "INELIGIBLE" | "NEEDS_MORE_INFO" | "INSUFFICIENT_EVIDENCE";
export type CriterionResult = "MET" | "NOT_MET" | "UNKNOWN";

export interface EligibilityResult {
  pblancId: string;
  programName: string;
  status: EligibilityStatus;
  criteria: { criterion: string; result: CriterionResult; reason: string; citations: Citation[] }[];
  missingInformation: string[];
  disclaimer: string;
}

/** 판정 때만 보내는 일시 정보(저장하지 않음). */
export interface EligibilityRequest {
  creditScore: number | null;
  taxDelinquent: boolean | null;
}

export const aiApi = {
  query: (query: string) => apiRequest<AiQueryResult>("/api/ai/query", { method: "POST", body: { query } }),
  eligibility: (pblancId: string, body: EligibilityRequest) =>
    apiRequest<EligibilityResult>(`/api/programs/${encodeURIComponent(pblancId)}/eligibility`, { method: "POST", body }),
};
