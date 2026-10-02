import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ErrorMessage, Loading } from "../../shared/components/StateViews";
import { useMyCompany } from "./useMyCompany";

/**
 * 기업정보가 있어야 쓰는 화면(AI 검색·맞춤 추천). RequireAuth 안쪽에 둔다.
 * 없으면 원래 가려던 주소를 기억한 채 기업정보 등록 화면으로 보낸다. 서버도 같은 규칙으로 막는다(company_not_registered).
 * 지원사업 목록·상세는 공개 공고라 이 검사를 하지 않는다.
 */
export function RequireCompany({ children }: { children: ReactNode }) {
  const company = useMyCompany();
  const location = useLocation();
  if (company.isPending) return <Loading message="기업정보를 확인하고 있습니다." />;
  if (company.isError) return <ErrorMessage error={company.error} onRetry={() => company.refetch()} />;
  if (company.data === null) return <Navigate to="/company" replace state={{ from: location.pathname, needCompany: true }} />;
  return <>{children}</>;
}
