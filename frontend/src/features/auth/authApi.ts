import { apiRequest, type TokenResponse } from "../../shared/api/client";

export type User = TokenResponse["user"];

export const authApi = {
  /** 필수 동의(이용약관·개인정보처리방침)가 없으면 서버가 가입하지 않는다. */
  signup: (body: { email: string; password: string; displayName: string; agreeTerms: boolean; agreePrivacy: boolean }) =>
    apiRequest<TokenResponse>("/api/auth/signup", { method: "POST", body }),
  login: (body: { email: string; password: string }) => apiRequest<TokenResponse>("/api/auth/login", { method: "POST", body }),
  /** 체험하기 사용 가능 여부(운영 설정). */
  trialStatus: () => apiRequest<{ enabled: boolean }>("/api/auth/trial"),
  /** 체험하기: 누를 때마다 합성 기업정보가 든 새 임시 계정을 만들고 로그인한다. */
  startTrial: () => apiRequest<TokenResponse>("/api/auth/trial", { method: "POST" }),
  logout: () => apiRequest<void>("/api/auth/logout", { method: "POST" }),
  /** 회원 탈퇴. 비밀번호를 다시 확인하고, 성공하면 서버가 Refresh Cookie도 지운다. */
  withdraw: (password: string) => apiRequest<void>("/api/account/withdraw", { method: "POST", body: { password } }),
  /** 비밀번호 변경. 다른 기기 로그인은 끊기고 지금 화면에는 새 토큰이 온다. */
  changePassword: (body: { currentPassword: string; newPassword: string }) =>
    apiRequest<TokenResponse>("/api/account/password", { method: "PUT", body }),
};
