import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../../shared/api/client";
import { FieldMessage, fieldMessage } from "../../shared/components/StateViews";
import { authApi } from "./authApi";
import { useAuth } from "./AuthContext";

/** 계정 관리: 비밀번호 변경과 회원 탈퇴. 둘 다 현재 비밀번호를 다시 확인한다. */
export function AccountPage() {
  const { user } = useAuth();
  return (
    <div className="page narrow">
      <h1>계정 관리</h1>
      <p className="muted">{user?.email}</p>
      <PasswordChange />
      <Withdraw />
    </div>
  );
}

function PasswordChange() {
  const { accept } = useAuth();
  const [form, setForm] = useState({ currentPassword: "", newPassword: "" });
  const [done, setDone] = useState(false);
  const mutation = useMutation({
    mutationFn: () => authApi.changePassword(form),
    onSuccess: (response) => {
      accept(response);
      setForm({ currentPassword: "", newPassword: "" });
      setDone(true);
    },
  });
  const error = mutation.error instanceof ApiError ? mutation.error : null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setDone(false);
    mutation.mutate();
  };
  return (
    <form className="card" onSubmit={submit} noValidate aria-label="비밀번호 변경">
      <h2>비밀번호 변경</h2>
      <label className="field">
        <span>현재 비밀번호</span>
        <input type="password" autoComplete="current-password" value={form.currentPassword}
               onChange={(event) => setForm((current) => ({ ...current, currentPassword: event.target.value }))} />
        <FieldMessage message={fieldMessage(error, "currentPassword")} />
      </label>
      <label className="field">
        <span>새 비밀번호</span>
        <input type="password" autoComplete="new-password" value={form.newPassword}
               onChange={(event) => setForm((current) => ({ ...current, newPassword: event.target.value }))} />
        <small className="muted">8~64자. 바꾸면 다른 기기의 로그인은 끊깁니다.</small>
        <FieldMessage message={fieldMessage(error, "newPassword")} />
      </label>
      {error && error.fieldErrors.length === 0 && <p className="alert error" role="alert">{error.message}</p>}
      {done && <p className="alert info" role="status">비밀번호를 바꿨습니다.</p>}
      <button className="button primary" type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? "변경 중..." : "비밀번호 변경"}
      </button>
    </form>
  );
}

function Withdraw() {
  const { endSession } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const mutation = useMutation({
    mutationFn: () => authApi.withdraw(password),
    onSuccess: () => {
      endSession("회원 탈퇴가 완료되었습니다. 이용해 주셔서 감사합니다.");
      navigate("/login", { replace: true });
    },
  });
  const error = mutation.error instanceof ApiError ? mutation.error : null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (confirmed) mutation.mutate();
  };
  return (
    <form className="card danger-zone" onSubmit={submit} noValidate aria-label="회원 탈퇴">
      <h2>회원 탈퇴</h2>
      <p className="muted small">
        탈퇴하면 계정·기업정보·AI 대화·맞춤 추천 기록이 바로 지워지고 되돌릴 수 없습니다. 활동 기록은 누구인지 알 수 없는 형태로만 남습니다.
      </p>
      <label className="field">
        <span>비밀번호 확인</span>
        <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
        <FieldMessage message={fieldMessage(error, "password")} />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
        <span>위 내용을 확인했고 탈퇴합니다.</span>
      </label>
      {error && error.fieldErrors.length === 0 && <p className="alert error" role="alert">{error.message}</p>}
      <button className="button danger" type="submit" disabled={!confirmed || !password || mutation.isPending}>
        {mutation.isPending ? "탈퇴 처리 중..." : "회원 탈퇴"}
      </button>
    </form>
  );
}
