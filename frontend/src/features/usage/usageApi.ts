import { apiRequest } from "../../shared/api/client";

/** 오늘 AI 사용 현황. resetsAt은 다음 한국 자정. */
export interface AiUsage {
  dailyLimit: number;
  used: number;
  remaining: number;
  resetsAt: string;
}

export const USAGE_KEY = ["ai-usage"] as const;

export const usageApi = {
  get: () => apiRequest<AiUsage>("/api/ai/usage"),
};

/** 하루 사용 제한 오류 코드. 이 오류는 다시 시도해도 같은 결과라 "다시 시도" 버튼을 보이지 않는다. */
export const USAGE_LIMIT_CODES = new Set(["ai_daily_limit_reached", "ai_ip_daily_limit_reached", "ai_trial_pool_exhausted", "ai_service_daily_limit_reached"]);
