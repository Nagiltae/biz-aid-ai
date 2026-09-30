import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { refreshAccessToken, setAccessToken, setSessionHandlers, type TokenResponse } from "../../shared/api/client";
import { authApi, type User } from "./authApi";

// 로그인 사용자는 여러 화면(헤더·보호 routing·자격 판정 버튼)이 함께 쓰는 유일한 client 상태다.
// 값이 하나뿐이라 별도 상태관리 라이브러리(Zustand) 없이 React Context로 충분하다.
interface AuthState {
  user: User | null;
  initializing: boolean;
  accept: (response: TokenResponse) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);
  const queryClient = useQueryClient();

  const accept = useCallback((response: TokenResponse) => {
    setAccessToken(response.accessToken);
    setUser(response.user);
  }, []);

  useEffect(() => {
    setSessionHandlers({
      expired: () => {
        setAccessToken(null);
        setUser(null);
        queryClient.clear();
      },
      refreshed: (response) => setUser(response.user),
    });
    // 새로고침하면 메모리의 Access Token이 사라진다. HttpOnly Cookie의 Refresh Token으로 로그인 상태를 복원한다.
    refreshAccessToken().finally(() => setInitializing(false));
  }, [queryClient]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setAccessToken(null);
      setUser(null);
      queryClient.clear();
    }
  }, [queryClient]);

  const value = useMemo(() => ({ user, initializing, accept, logout }), [user, initializing, accept, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is missing");
  return value;
}
