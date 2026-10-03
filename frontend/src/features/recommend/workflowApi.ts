import { apiRequest } from "../../shared/api/client";
import type { AiProgramItem, Citation, CriterionResult, EligibilityResult, EligibilityStatus } from "../ai/aiApi";

// V2 맞춤 추천 흐름(workflow) API. 항상 Spring(/api)만 호출한다.
// 타입은 Spring AiDtos.WorkflowResponse와 같다. 다음에 무엇을 할지(nextAction)·공고 순서·판정 상태는 서버 값만 쓰고 화면이 계산하지 않는다.

export type WorkflowStatus = "IN_PROGRESS" | "WAITING_FOR_USER" | "COMPLETED" | "FAILED";
export type NextAction = "CONTINUE" | "ANSWER" | "NONE";

export interface WorkflowEvaluation {
  rank: number;
  pblancId: string;
  program: (AiProgramItem & { announcementUrl?: string | null }) | null;
  evaluationStatus: "PENDING" | "COMPLETED" | "FAILED";
  eligibility: EligibilityResult | null;
  errorCode: string | null;
  attempts: number | null;
}

export interface MissingField {
  fieldId: string;
  sourceFields: string[];
  programs: string[];
}

export interface FinalItem {
  rank: number;
  pblancId: string;
  program: (AiProgramItem & { announcementUrl?: string | null }) | null;
  eligibilityStatus: EligibilityStatus | null;
  reasonCode: "all_criteria_met" | "criteria_not_met" | "insufficient_evidence" | "evaluation_failed" | "missing_information_unresolved";
  errorCode: string | null;
  reasons: { criterion: string; result: CriterionResult; reason: string; evidenceIds: string[] }[];
  missingInformation: string[];
  citations: Citation[];
}

export interface FinalResult {
  recommended: FinalItem[];
  excluded: FinalItem[];
  unresolved: FinalItem[];
  counts: { recommended: number; excluded: number; unresolved: number };
  disclaimer: string | null;
}

export interface WorkflowResponse {
  workflowId: number;
  status: WorkflowStatus;
  currentStep: string;
  nextAction: NextAction;
  progress: { total: number; completed: number; failed: number; pending: number; round: number };
  search: {
    status: string;
    candidateCount: number | null;
    programs: AiProgramItem[] | null;
    unappliedConditions: { source: string; field: string; value: string; reason: string }[] | null;
    appliedConditions?: { company?: { region?: string | null; excludedJurisdictions?: string[] | null } | null } | null;
    /** CONDITION_CONFLICT일 때 FastAPI가 준 충돌 내용 그대로(kind: target | region). */
    conflict?: { kind?: string; company_region?: string; query_jurisdictions?: string[] } | null;
  } | null;
  evaluations: WorkflowEvaluation[];
  missingInformation: MissingField[];
  temporaryCompanyFacts: Record<string, unknown>;
  failureCode: string | null;
  finalResult: FinalResult | null;
  pendingPblancIds: string[];
}

export type AnswerValue = string | number | boolean;

/** 지난 맞춤 추천 목록 한 줄(최근 20건). recommendedCount는 판정이 끝난 흐름만 값이 있다. */
export interface WorkflowSummary {
  workflowId: number;
  query: string;
  status: WorkflowResponse["status"];
  currentStep: string;
  recommendedCount: number | null;
  createdAt: string;
  updatedAt: string;
}

export const workflowApi = {
  list: () => apiRequest<WorkflowSummary[]>("/api/ai/workflows"),
  start: (query: string) => apiRequest<WorkflowResponse>("/api/ai/workflows", { method: "POST", body: { query } }),
  get: (id: number) => apiRequest<WorkflowResponse>(`/api/ai/workflows/${id}`),
  advance: (id: number) => apiRequest<WorkflowResponse>(`/api/ai/workflows/${id}/continue`, { method: "POST" }),
  answer: (id: number, answers: Record<string, AnswerValue>) =>
    apiRequest<WorkflowResponse>(`/api/ai/workflows/${id}/answers`, { method: "POST", body: { answers } }),
};

/**
 * 추가 질문 field ID별 입력 형식. FastAPI CompanyProfileSnapshot 검증 규칙(정수·참거짓·날짜·허용값)과 같다.
 * 무엇을 물을지는 서버의 missingInformation이 정하고, 여기는 입력칸 모양만 정한다.
 */
export type AnswerKind = "integer" | "boolean" | "date" | "text" | "choice";
export const ANSWER_FIELDS: Record<string, { label: string; kind: AnswerKind; choices?: string[]; unit?: string; help?: string }> = {
  credit_score: { label: "대표자 개인신용점수", kind: "integer", unit: "점", help: "NCB 등 신용평가사 점수" },
  tax_delinquent: { label: "국세·지방세 체납 중인가요?", kind: "boolean" },
  business_entity_type: { label: "사업자 형태", kind: "choice", choices: ["개인사업자", "법인"] },
  business_status: { label: "영업 상태", kind: "choice", choices: ["영업중", "휴업", "폐업"] },
  company_size: { label: "기업 규모", kind: "text", help: "예: 소상공인, 중소기업" },
  region: { label: "사업장 소재지", kind: "text", help: "예: 경기도 광명시" },
  industry: { label: "업종", kind: "text", help: "업종명 또는 표준산업분류 코드" },
  business_start_date: { label: "개업일", kind: "date", help: "업력은 개업일로 계산합니다" },
  employee_count: { label: "상시근로자 수", kind: "integer", unit: "명" },
  annual_revenue_krw: { label: "최근 1년 매출액", kind: "integer", unit: "원" },
  venture_certified: { label: "벤처기업 확인을 받았나요?", kind: "boolean" },
  research_institute: { label: "기업부설연구소(전담부서)가 있나요?", kind: "boolean" },
  exporter: { label: "수출 실적이 있나요?", kind: "boolean" },
};

/** 입력 문자열 → 서버로 보낼 값. 비어 있으면 undefined(보내지 않음), 형식이 틀리면 오류 문구. */
export function parseAnswer(fieldId: string, raw: string): { value?: AnswerValue; error?: string } {
  const spec = ANSWER_FIELDS[fieldId];
  const text = raw.trim();
  if (text === "") return {};
  // 형식표에 없는 field는 글자 그대로 보내고 형식 검증은 서버(기업정보 검증 규칙)에 맡긴다.
  if (!spec) return { value: text };
  if (spec.kind === "integer") {
    return /^\d+$/.test(text) && Number.isSafeInteger(Number(text)) ? { value: Number(text) } : { error: "0 이상의 정수로 입력해 주세요." };
  }
  if (spec.kind === "boolean") return { value: text === "true" };
  if (spec.kind === "date") return /^\d{4}-\d{2}-\d{2}$/.test(text) ? { value: text } : { error: "날짜를 선택해 주세요." };
  if (spec.kind === "choice") return spec.choices?.includes(text) ? { value: text } : { error: "목록에서 선택해 주세요." };
  return { value: text };
}

export const WORKFLOW_ERROR_TITLE: Record<string, string> = {
  workflow_busy: "이미 다음 단계를 진행 중입니다",
  workflow_invalid_state: "지금 상태에서는 진행할 수 없습니다",
  workflow_not_found: "추천 흐름을 찾을 수 없습니다",
};
