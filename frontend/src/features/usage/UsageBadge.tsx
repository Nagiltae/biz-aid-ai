import { useQuery } from "@tanstack/react-query";
import { USAGE_KEY, usageApi } from "./usageApi";

/** AI 입력칸 아래의 "오늘 남은 횟수". AI 요청이 끝날 때마다 USAGE_KEY를 다시 읽는다. */
export function UsageBadge() {
  const usage = useQuery({ queryKey: USAGE_KEY, queryFn: usageApi.get });
  if (!usage.data) return null;
  const { remaining, dailyLimit } = usage.data;
  return (
    <p className={remaining === 0 ? "usage-badge empty" : "usage-badge"} role="status" aria-label="오늘 남은 AI 사용 횟수">
      오늘 남은 AI 사용 <strong>{remaining}</strong> / {dailyLimit}회
      {remaining === 0 && <span> · 한국 시간 자정에 다시 채워집니다.</span>}
    </p>
  );
}
