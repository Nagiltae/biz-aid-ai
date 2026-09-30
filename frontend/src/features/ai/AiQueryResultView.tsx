import { Link } from "react-router-dom";
import { CitationList } from "./CitationList";
import type { AiQueryResult } from "./aiApi";

/** AI 검색 결과: 공고 목록(SEARCH_LIST) 또는 근거 기반 답변(DOCUMENT_QA). 받은 값만 표시한다. */
export function AiQueryResultView({ result }: { result: AiQueryResult }) {
  return (
    <section className="card" aria-label="AI 검색 결과">
      {result.answer && <p className="prewrap">{result.answer}</p>}
      {result.programs.length > 0 && (
        <ul className="plain-list">
          {result.programs.map((program) => (
            <li key={program.pblancId}>
              <Link to={`/programs/${program.pblancId}`}>{program.name ?? program.pblancId}</Link>
              <span className="muted"> · {program.jurisdictionName ?? "-"}</span>
            </li>
          ))}
        </ul>
      )}
      {result.programs.length === 0 && !result.answer && <p className="muted">조건에 맞는 지원사업을 찾지 못했습니다.</p>}
      <CitationList citations={result.citations} />
    </section>
  );
}
