import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../../shared/api/client";
import { FieldMessage, fieldMessage } from "../../shared/components/StateViews";
import { authApi } from "./authApi";
import { useAuth } from "./AuthContext";

type Mode = "login" | "signup";

export function LoginPage() {
  const { user, accept } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/ai";
  const [mode, setMode] = useState<Mode>("login");
  const [form, setForm] = useState({ email: "", password: "", displayName: "" });

  const mutation = useMutation({
    mutationFn: () =>
      mode === "login"
        ? authApi.login({ email: form.email, password: form.password })
        : authApi.signup(form),
    onSuccess: (response) => {
      accept(response);
      navigate(from, { replace: true });
    },
  });

  if (user) return <Navigate to={from} replace />;

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
