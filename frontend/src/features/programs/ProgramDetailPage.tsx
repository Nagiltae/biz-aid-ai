import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ErrorMessage, Loading } from "../../shared/components/StateViews";
import { EligibilityPanel } from "../ai/EligibilityPanel";
import { periodText, programsApi } from "./programsApi";
import { StatusBadge } from "./StatusBadge";

/** 외부 원문 링크는 http(s)만 연다. javascript: 같은 주소가 섞여 있어도 실행되지 않게 한다. */
function safeUrl(value: string | null) {
  const url = value?.trim() ?? "";
  const lower = url.toLowerCase();
  return lower.startsWith("https://") || lower.startsWith("http://") ? url : null;
}

export function ProgramDetailPage() {
  const { pblancId = "" } = useParams();
  const query = useQuery({ queryKey: ["program", pblancId], queryFn: () => programsApi.get(pblancId), retry: false });

  if (query.isPending) return <Loading />;
  if (query.isError) {
    return (
      <div className="page narrow">
        <ErrorMessage error={query.error} />
        <Link to="/programs">목록으로</Link>
      </div>
    );
  }
  const program = query.data;
  const announcement = safeUrl(program.announcementUrl);
  const application = safeUrl(program.applicationUrl);

  return (
    <div className="page detail-layout">
      <article className="detail-main">
        <Link to="/programs" className="back-link">← 지원사업 목록</Link>
        <div className="card-top">
          <StatusBadge status={program.recruitmentStatus} label={program.recruitmentStatusLabel} />
          {program.category && <span className="tag">{program.category}</span>}
        </div>
        <h1>{program.name ?? program.pblancId}</h1>
        <section className="card">
          <dl className="meta wide">
            <dt>소관기관</dt>
            <dd>{program.jurisdictionName ?? "-"}</dd>
            <dt>수행기관</dt>
            <dd>{program.executingOrgName ?? "-"}</dd>
            <dt>지원대상</dt>
            <dd>{program.target ?? "-"}</dd>
            <dt>지원분야</dt>
            <dd>{program.category ?? "-"}</dd>
            <dt>신청기간</dt>
            <dd>
              {periodText(program)}

            </dd>
            <dt>공고 ID</dt>
            <dd className="muted">{program.pblancId}</dd>
          </dl>
        </section>
        <section className="card">
          <h2>지원 내용</h2>
          <p className="prewrap">{program.summary ?? "요약 정보가 없습니다. 원문 공고를 확인해 주세요."}</p>
        </section>
        <section className="card">
          <h2>신청방법</h2>
          <p className="prewrap">{program.applicationMethod ?? "신청방법 정보가 없습니다."}</p>
          <div className="link-row">
            {announcement && <a className="button" href={announcement} target="_blank" rel="noopener noreferrer">공고 원문 보기</a>}
            {application && <a className="button" href={application} target="_blank" rel="noopener noreferrer">신청 페이지</a>}
          </div>
        </section>
      </article>
      <aside className="detail-side">
        <EligibilityPanel pblancId={program.pblancId} />
      </aside>
    </div>
  );
}
