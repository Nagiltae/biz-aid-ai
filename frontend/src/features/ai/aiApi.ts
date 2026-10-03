import { apiRequest } from "../../shared/api/client";
import type { Message } from "./conversationApi";

// AI 요청도 항상 Spring(/api)으로 보낸다. Spring이 FastAPI 내부 API를 대신 호출한다.
// 타입은 Spring AiDtos와 같다. 값은 AI 서비스(FastAPI)가 계산한 그대로이며 화면에서 판정·순위를 바꾸지 않는다.

/** 공고문 근거(Citation): AI 답변·판정이 공고문의 어느 위치를 근거로 했는지. 실제로 온 field만 쓴다. */
export interface Citation {
  evidenceId: string;
  rank: number | null;
  pblancId: string;
  title: string | null;
  pages: number[] | null;
  location: string | null;
  headingPath: string[] | null;
}

export interface AiProgramItem {
  originalScore?: number;
  regionBonus?: number;
  finalScore?: number;
  originalRank?: number;
  rank: number;
  pblancId: string;
  name: string | null;
  category: string | null;
  target: string | null;
  jurisdictionName: string | null;
  executingOrgName: string | null;
  applicationStartDate: string | null;
  applicationEndDate: string | null;
  applicationPeriodRaw: string | null;
}

export interface AiQueryResult {
  requestMode: "SEARCH_LIST" | "DOCUMENT_QA";
  status: string;
  candidateCount: number | null;
  programs: AiProgramItem[] | null;
  answer: string | null;
  citations: Citation[] | null;
  query?: string;
  selectedPblancId?: string | null;
  selectionCandidates?: { pblancId: string; name: string; jurisdictionName: string | null; applicationPeriodRaw: string | null }[];
  naturalFilter: { applied?: Record<string, string[] | string | null> } | null;
}

export interface AiQueryResponse {
  conversationId: number;
  userMessage: Message;
  assistantMessage: Message;
  result: AiQueryResult;
}

export type EligibilityStatus = "ELIGIBLE" | "INELIGIBLE" | "NEEDS_MORE_INFO" | "INSUFFICIENT_EVIDENCE";
export type CriterionResult = "MET" | "NOT_MET" | "UNKNOWN";

export interface EligibilityResult {
  pblancId: string;
  programName: string;
  asOf: string | null;
  status: EligibilityStatus;
  criteria: {
    criterion: string;
    result: CriterionResult;
    reason: string;
    profileFields: string[] | null;
    missingProfileFields: string[] | null;
    citations: Citation[] | null;
  }[];
  missingInformation: string[];
  disclaimer: string;
}

/** 판정 때만 보내는 일시 정보(저장하지 않음). */
export interface EligibilityRequest {
  creditScore: number | null;
  taxDelinquent: boolean | null;
}

export const aiApi = {
  query: (query: string, conversationId: number | null, selectedPblancId?: string) =>
    apiRequest<AiQueryResponse>("/api/ai/query", { method: "POST", body: { query, conversationId, selectedPblancId } }),
  eligibility: (pblancId: string, body: EligibilityRequest) =>
    apiRequest<EligibilityResult>(`/api/programs/${encodeURIComponent(pblancId)}/eligibility`, { method: "POST", body }),
};

/** AI 호출 실패 code를 사용자가 할 일 중심의 안내로 바꾼다(서버 message가 기본, 여기는 제목만). */
export const AI_ERROR_TITLE: Record<string, string> = {
  ai_service_timeout: "AI 응답 시간이 초과됐습니다",
  ai_service_unavailable: "AI 서비스에 연결할 수 없습니다",
  ai_service_auth_failed: "AI 서비스 연결 설정 오류",
  ai_response_invalid: "AI 응답을 표시할 수 없습니다",
  ai_service_error: "AI 서비스 오류",
};
