import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../../shared/api/client";
import { Loading } from "../../shared/components/StateViews";
import { useAuth } from "../auth/AuthContext";
import { AiErrorNotice } from "./AiErrorNotice";
import { aiApi } from "./aiApi";
import { EligibilityResultView } from "./EligibilityResultView";

/**
 * 공고 상세의 "우리 회사 지원 가능 여부 확인".
 * 저장된 기업정보는 Spring이 읽고, 신용점수·체납 여부 같은 민감한 일시 정보만 여기서 입력받아 이번 요청에만 쓴다.
 */
export function EligibilityPanel({ pblancId }: { pblancId: string }) {
  const { user } = useAuth();
  const location = useLocation();
  const [creditScore, setCreditScore] = useState("");
  const [taxDelinquent, setTaxDelinquent] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      aiApi.eligibility(pblancId, {
        creditScore: creditScore.trim() === "" ? null : Number(creditScore),
        taxDelinquent: taxDelinquent === "" ? null : taxDelinquent === "true",
      }),
  });

  if (!user) {
    return (
      <section className="card">
        <h2>우리 회사 지원 가능 여부</h2>
        <p className="muted">로그인하고 기업정보를 등록하면 이 공고의 자격 조건과 비교할 수 있습니다.</p>
        <Link className="button primary full" to="/login" state={{ from: location.pathname }}>로그인하고 확인하기</Link>
      </section>
    );
  }

  const error = mutation.error instanceof ApiError ? mutation.error : null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <section className="card">
      <h2>우리 회사 지원 가능 여부</h2>
      <p className="muted small">등록한 기업정보와 공고문의 자격 조건을 비교합니다. 아래 정보는 저장하지 않고 이번 확인에만 씁니다.</p>
      <form onSubmit={submit}>
        <label className="field compact">
          <span>대표자 신용점수 (선택)</span>
          <input type="number" min="0" max="1000" inputMode="numeric" value={creditScore} onChange={(event) => setCreditScore(event.target.value)} />
        </label>
        <label className="field compact">
          <span>국세·지방세 체납 (선택)</span>
          <select value={taxDelinquent} onChange={(event) => setTaxDelinquent(event.target.value)}>
            <option value="">선택 안 함</option>
            <option value="false">체납 없음</option>
            <option value="true">체납 있음</option>
          </select>
        </label>
        <button className="button primary full" type="submit" disabled={mutation.isPending}>
          {mutation.data ? "입력한 정보로 다시 확인" : "우리 회사 지원 가능 여부 확인"}
        </button>
      </form>
      <div className="panel-result">
        {mutation.isPending && <Loading message="공고문과 기업정보를 비교하고 있습니다. 30초 이상 걸릴 수 있습니다." />}
        {error?.code === "company_not_registered" && (
          <p className="alert info">
            {error.message} <Link to="/company">기업정보 등록하기</Link>
          </p>
        )}
        {mutation.isError && error?.code !== "company_not_registered" && <AiErrorNotice error={mutation.error} />}
        {mutation.data && <EligibilityResultView result={mutation.data} />}
      </div>
    </section>
  );
}
