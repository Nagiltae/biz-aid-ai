import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, setAccessToken } from "../../shared/api/client";
import { companyApi } from "../company/companyApi";
import { MY_COMPANY_KEY } from "../company/useMyCompany";
import { FieldMessage, fieldMessage } from "../../shared/components/StateViews";
import { authApi } from "./authApi";
import { useAuth } from "./AuthContext";

type Mode = "login" | "signup";

export function LoginPage() {
  const { user, accept } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/ai";
  const [mode, setMode] = useState<Mode>("login");
  const [form, setForm] = useState({ email: "", password: "", displayName: "" });

  const mutation = useMutation({
    mutationFn: async () => {
      const response = mode === "login"
        ? await authApi.login({ email: form.email, password: form.password })
        : await authApi.signup(form);
      // 로그인 직후 기업정보 등록 여부를 확인한다. 조회가 실패해도 로그인은 성공이므로 이동 뒤 보호 routing이 다시 확인한다.
      setAccessToken(response.accessToken);
      const company = await companyApi.find().catch(() => undefined);
      return { response, company };
    },
    onSuccess: ({ response, company }) => {
      if (company !== undefined) queryClient.setQueryData(MY_COMPANY_KEY, company);
      accept(response);
      // 기업정보가 없으면 다른 기능을 쓸 수 없으므로 바로 등록 화면으로 보낸다(가입 직후는 항상 이 경우).
      if (company === null) navigate("/company", { replace: true, state: { from, needCompany: true } });
      else navigate(from, { replace: true });
    },
  });

  if (user) {
    // 로그인 성공 직후의 다시 그리기도 여기로 온다. 기업정보가 없다고 확인됐으면 원래 화면 대신 등록 화면으로 보낸다
    // (onSuccess의 이동과 같은 목적지라 어느 쪽이 먼저 실행돼도 결과가 같다).
    if (queryClient.getQueryData(MY_COMPANY_KEY) === null) {
      return <Navigate to="/company" replace state={{ from, needCompany: true }} />;
    }
    return <Navigate to={from} replace />;
  }

  const error = mutation.error instanceof ApiError ? mutation.error : null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };
  const update = (name: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [name]: event.target.value }));
  const switchMode = (next: Mode) => {
    setMode(next);
    mutation.reset();
  };

  return (
    <div className="auth-page">
      <section className="card auth-card">
        <h1 className="auth-title">BizAid</h1>
        <p className="muted">기업정보와 공고문 근거로 우리 회사에 맞는 지원사업을 찾습니다.</p>
        <div className="tabs" role="tablist">
          <button type="button" role="tab" aria-selected={mode === "login"} className={mode === "login" ? "tab active" : "tab"} onClick={() => switchMode("login")}>
            로그인
          </button>
          <button type="button" role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "tab active" : "tab"} onClick={() => switchMode("signup")}>
            회원가입
          </button>
        </div>
        <form onSubmit={submit} noValidate>
          <label className="field">
            <span>이메일</span>
            <input type="email" autoComplete="email" value={form.email} onChange={update("email")} required />
            <FieldMessage message={fieldMessage(error, "email")} />
          </label>
          <label className="field">
            <span>비밀번호</span>
            <input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={form.password} onChange={update("password")} required />
            {mode === "signup" && <small className="muted">8~64자</small>}
            <FieldMessage message={fieldMessage(error, "password")} />
          </label>
          {mode === "signup" && (
            <label className="field">
              <span>이름</span>
              <input autoComplete="name" value={form.displayName} onChange={update("displayName")} required />
              <FieldMessage message={fieldMessage(error, "displayName")} />
            </label>
          )}
          {error && error.fieldErrors.length === 0 && <p className="alert error" role="alert">{error.message}</p>}
          {mutation.error && !error && <p className="alert error" role="alert">요청을 처리하지 못했습니다.</p>}
          <button className="button primary full" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "처리 중..." : mode === "login" ? "로그인" : "가입하고 시작하기"}
          </button>
        </form>
      </section>
    </div>
  );
}
