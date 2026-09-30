import type { ReactNode } from "react";
import { ApiError } from "../api/client";

// 화면마다 loading / empty / error 표시가 달라지지 않도록 모양만 공통으로 둔다.

export function Loading({ message = "불러오는 중입니다." }: { message?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {message}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state empty">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

export function ErrorMessage({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.";
  return (
    <div className="alert error" role="alert">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="button small" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}

export function fieldMessage(error: unknown, field: string) {
  return error instanceof ApiError ? error.fieldErrors.find((item) => item.field === field)?.message : undefined;
}

export function FieldMessage({ message }: { message?: string }) {
  return message ? <small className="field-error">{message}</small> : null;
}
