import { Link } from "react-router-dom";
import { periodText } from "../programs/programsApi";
import { CitationList } from "./CitationList";
import type { AiQueryResult } from "./aiApi";

// 상태 코드의 화면 문구. AI 답변을 지어내는 것이 아니라 FastAPI 상태를 한국어로 표시하는 고정 라벨이다.
const EMPTY_STATUS: Record<string, string> = {
  NO_CANDIDATES: "조건에 맞는 공고가 없습니다.",
  NO_INDEXED_PROGRAMS: "조건에 맞는 공고는 있지만 아직 공고문 분석이 끝나지 않았습니다.",
};

function AppliedFilter({ result }: { result: AiQueryResult }) {
  const applied = result.naturalFilter?.applied ?? {};
  const values = Object.values(applied).flatMap((value) => (Array.isArray(value) ? value : value ? [String(value)] : []));
  if (values.length === 0 && result.candidateCount == null) return null;
  return (
    <p className="muted small">
      {values.length > 0 && <>적용된 조건: {values.join(", ")} · </>}
      {result.candidateCount != null && <>후보 공고 {result.candidateCount}건</>}
    </p>
  );
}

/**
 * AI 검색 결과: 공고 목록(SEARCH_LIST) 또는 근거 기반 답변(DOCUMENT_QA).
 * 목록은 FastAPI 순위 그대로 보여 준다(화면에서 다시 정렬하지 않는다).
 */
export function AiQueryResultView({ result }: { result: AiQueryResult }) {
  if (result.requestMode === "SEARCH_LIST") {
    const programs = result.programs ?? [];
    return (
      <section className="ai-result" aria-label="AI 검색 결과">
        <AppliedFilter result={result} />
        {programs.length === 0 ? (
          <p className="muted">{EMPTY_STATUS[result.status] ?? "조건에 맞는 지원사업이 없습니다."}</p>
        ) : (
          <ol className="program-grid ranked">
            {programs.map((program) => (
              <li key={program.pblancId} className="card program-card">
                <div className="card-top">
                  <span className="badge rank">{program.rank}위</span>
                  {program.category && <span className="tag">{program.category}</span>}
                  {program.target && <span className="tag">{program.target}</span>}
                </div>
                <h3 className="program-title">
                  <Link to={`/programs/${program.pblancId}`}>{program.name ?? program.pblancId}</Link>
                </h3>
                <dl className="meta">
                  <dt>소관기관</dt>
                  <dd>{program.jurisdictionName ?? "-"}</dd>
                  <dt>신청기간</dt>
                  <dd>{periodText(program)}</dd>
                </dl>
                <Link className="button small" to={`/programs/${program.pblancId}`}>상세 보기</Link>
              </li>
            ))}
          </ol>
        )}
      </section>
    );
  }
  return (
    <section className="ai-result" aria-label="AI 답변">
      <AppliedFilter result={result} />
      {result.status !== "ANSWERED" && <span className="badge status-undated">근거 부족</span>}
      <p className="prewrap">{result.answer ?? EMPTY_STATUS[result.status] ?? "답변이 없습니다."}</p>
      <CitationList citations={result.citations} />
    </section>
  );
}
