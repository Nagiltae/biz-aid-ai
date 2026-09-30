import { apiRequest, type TokenResponse } from "../../shared/api/client";

export type User = TokenResponse["user"];

export const authApi = {
  signup: (body: { email: string; password: string; displayName: string }) =>
    apiRequest<TokenResponse>("/api/auth/signup", { method: "POST", body }),
  login: (body: { email: string; password: string }) => apiRequest<TokenResponse>("/api/auth/login", { method: "POST", body }),
  logout: () => apiRequest<void>("/api/auth/logout", { method: "POST" }),
};
