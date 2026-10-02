import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ErrorMessage, Loading } from "../../shared/components/StateViews";
import { useMyCompany } from "./useMyCompany";

/**
 * 기업정보가 있어야 쓰는 화면(맞춤 추천). RequireAuth 안쪽에 둔다. 서버도 같은 규칙으로 막는다(company_not_registered).
 * 기업정보가 없으면 화면 자리에 "기업정보를 먼저 입력해 주세요" 안내와 등록 버튼(원래 주소 기억)을 보여 준다.
 * AI 검색은 입력칸을 보여 준 채 잠그는 방식이라 화면 안에서 직접 처리한다. 지원사업 목록·상세는 공개 공고라 검사하지 않는다.
 */
export function RequireCompany({ children, notice }: { children: ReactNode; notice: { title: string; description: string } }) {
  const company = useMyCompany();
  const location = useLocation();
  if (company.isPending) return <Loading message="기업정보를 확인하고 있습니다." />;
  if (company.isError) return <ErrorMessage error={company.error} onRetry={() => company.refetch()} />;
  if (company.data === null) {
    return (
      <div className="page narrow">
        <h1>{notice.title}</h1>
        <section className="card company-required" aria-label="기업정보 입력 필요">
          <p className="alert warn" role="status">기업정보를 먼저 입력해 주세요.</p>
          <p>{notice.description}</p>
          <Link className="button primary" to="/company" state={{ from: location.pathname, needCompany: true }}>기업정보 입력하기</Link>
        </section>
      </div>
    );
  }
  return <>{children}</>;
}
