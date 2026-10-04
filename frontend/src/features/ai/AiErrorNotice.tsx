import { ApiError } from "../../shared/api/client";
import { ErrorMessage } from "../../shared/components/StateViews";
import { USAGE_LIMIT_CODES } from "../usage/usageApi";
import { AI_ERROR_TITLE } from "./aiApi";

/** AI 호출 실패 안내. 제한시간 초과·연결 불가는 사용자가 직접 다시 시도한다(자동 재시도 없음). */
export function AiErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!(error instanceof ApiError) || !AI_ERROR_TITLE[error.code]) return <ErrorMessage error={error} onRetry={onRetry} />;
  return (
    <div className="alert error" role="alert">
      <strong>{AI_ERROR_TITLE[error.code]}</strong>
      <span>{error.message}</span>
      {/* 하루 사용 제한은 다시 눌러도 같은 결과라 버튼을 보이지 않는다. */}
      {onRetry && !USAGE_LIMIT_CODES.has(error.code) && (
        <button type="button" className="button small" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}
