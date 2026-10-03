import { apiRequest, type TokenResponse } from "../../shared/api/client";

export type User = TokenResponse["user"];

export const authApi = {
  signup: (body: { email: string; password: string; displayName: string }) =>
    apiRequest<TokenResponse>("/api/auth/signup", { method: "POST", body }),
  login: (body: { email: string; password: string }) => apiRequest<TokenResponse>("/api/auth/login", { method: "POST", body }),
  logout: () => apiRequest<void>("/api/auth/logout", { method: "POST" }),
  /** 회원 탈퇴. 비밀번호를 다시 확인하고, 성공하면 서버가 Refresh Cookie도 지운다. */
  withdraw: (password: string) => apiRequest<void>("/api/account/withdraw", { method: "POST", body: { password } }),
  /** 비밀번호 변경. 다른 기기 로그인은 끊기고 지금 화면에는 새 토큰이 온다. */
  changePassword: (body: { currentPassword: string; newPassword: string }) =>
    apiRequest<TokenResponse>("/api/account/password", { method: "PUT", body }),
};
