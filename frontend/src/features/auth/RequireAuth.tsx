import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Loading } from "../../shared/components/StateViews";
import { useAuth } from "./AuthContext";

/** 로그인이 필요한 화면. 로그인하지 않았거나 세션이 만료되면 원래 가려던 주소를 기억한 채 /login으로 보낸다. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, initializing } = useAuth();
  const location = useLocation();
  if (initializing) return <Loading message="로그인 상태를 확인하고 있습니다." />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
