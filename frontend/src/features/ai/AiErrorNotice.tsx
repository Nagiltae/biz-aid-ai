import { ApiError } from "../../shared/api/client";
import { ErrorMessage } from "../../shared/components/StateViews";
import { AI_ERROR_TITLE } from "./aiApi";

/** AI 호출 실패 안내. 제한시간 초과·연결 불가는 사용자가 직접 다시 시도한다(자동 재시도 없음). */
export function AiErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!(error instanceof ApiError) || !AI_ERROR_TITLE[error.code]) return <ErrorMessage error={error} onRetry={onRetry} />;
  return (
    <div className="alert error" role="alert">
      <strong>{AI_ERROR_TITLE[error.code]}</strong>
      <span>{error.message}</span>
      {onRetry && (
        <button type="button" className="button small" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}
