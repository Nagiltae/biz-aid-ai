import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Empty, ErrorMessage, Loading } from "../../shared/components/StateViews";
import { periodText, programsApi, type ProgramFilters } from "./programsApi";
import { StatusBadge } from "./StatusBadge";

// 필터 값을 URL query에 둔다. 상세에서 뒤로 가기·새로고침을 해도 같은 검색 결과로 돌아오게 하기 위해서다.
function readFilters(params: URLSearchParams): ProgramFilters {
  return {
    keyword: params.get("keyword") ?? "",
    category: params.get("category") ?? "",
    target: params.get("target") ?? "",
    jurisdiction: params.get("jurisdiction") ?? "",
    status: params.get("status") ?? "",
    page: Number(params.get("page") ?? 0) || 0,
  };
}

export function ProgramListPage() {
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const [keyword, setKeyword] = useState(filters.keyword);
  const options = useQuery({ queryKey: ["program-filter-options"], queryFn: programsApi.filterOptions, staleTime: 10 * 60_000 });
  const list = useQuery({
    queryKey: ["programs", filters],
    queryFn: () => programsApi.search(filters),
    placeholderData: keepPreviousData,
  });

  const apply = (changes: Partial<ProgramFilters>) => {
    const next = { ...filters, page: 0, ...changes };
    const search = new URLSearchParams();
    Object.entries(next).forEach(([key, value]) => {
      if (value !== "" && !(key === "page" && value === 0)) search.set(key, String(value));
    });
    setParams(search);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    apply({ keyword: keyword.trim() });
  };
  const select = (name: "category" | "target" | "jurisdiction" | "status", label: string, values: [string, string][]) => (
    <label className="field compact">
      <span>{label}</span>
      <select value={filters[name]} onChange={(event) => apply({ [name]: event.target.value })}>
        <option value="">전체</option>
        {values.map(([value, text]) => (
          <option key={value} value={value}>{text}</option>
        ))}
      </select>
    </label>
  );
  const pairs = (values?: string[]): [string, string][] => (values ?? []).map((value) => [value, value]);

  return (
    <div className="page">
      <h1>지원사업</h1>
      <p className="muted">기업마당에 게시 중인 공고를 조건으로 찾습니다. 문장으로 찾으려면 AI 검색을 이용하세요.</p>
      <section className="card filters" aria-label="검색 조건">
        <form className="search-row" onSubmit={submit}>
          <input aria-label="검색어" placeholder="공고명·키워드 (예: 수출, 스마트공장)" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          <button className="button primary" type="submit">검색</button>
        </form>
        <div className="filter-row">
          {select("category", "지원분야", pairs(options.data?.categories))}
          {select("target", "지원대상", pairs(options.data?.targets))}
          {select("status", "모집 상태", (options.data?.statuses ?? []).map((item) => [item.value, item.label]))}
          {select("jurisdiction", "소관기관", pairs(options.data?.jurisdictions))}
        </div>
      </section>

      {list.isPending && <Loading />}
      {list.isError && <ErrorMessage error={list.error} onRetry={() => list.refetch()} />}
      {list.data && (
        <>
          <p className="muted result-count">총 {list.data.totalElements.toLocaleString()}건</p>
          {list.data.items.length === 0 ? (
            <Empty title="조건에 맞는 지원사업이 없습니다.">
              <span className="muted">검색어를 줄이거나 필터를 "전체"로 바꿔 보세요.</span>
            </Empty>
          ) : (
            <ul className="program-grid">
              {list.data.items.map((program) => (
                <li key={program.pblancId} className="card program-card">
                  <div className="card-top">
                    <StatusBadge status={program.recruitmentStatus} label={program.recruitmentStatusLabel} />
                    {program.category && <span className="tag">{program.category}</span>}
                    {program.target && <span className="tag">{program.target}</span>}
                  </div>
                  <h2 className="program-title">
                    <Link to={`/programs/${program.pblancId}`}>{program.name ?? program.pblancId}</Link>
                  </h2>
                  <dl className="meta">
                    <dt>소관기관</dt>
                    <dd>{program.jurisdictionName ?? "-"}</dd>
                    <dt>신청기간</dt>
                    <dd>{periodText(program)}</dd>
                  </dl>
                </li>
              ))}
            </ul>
          )}
          {list.data.totalPages > 1 && (
            <nav className="pager" aria-label="페이지">
              <button type="button" className="button small" disabled={filters.page === 0} onClick={() => apply({ ...filters, page: filters.page - 1 })}>
                이전
              </button>
              <span>{filters.page + 1} / {list.data.totalPages}</span>
              <button type="button" className="button small" disabled={filters.page + 1 >= list.data.totalPages} onClick={() => apply({ ...filters, page: filters.page + 1 })}>
                다음
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
