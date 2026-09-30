import type { Citation } from "./aiApi";

/** 근거 위치 표시: 공고명 · 페이지(또는 HWPX 구역) · 문단 제목 경로. 근거가 없으면 아무것도 그리지 않는다. */
export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <ul className="citations" aria-label="공고문 근거">
      {citations.map((citation) => (
        <li key={`${citation.evidenceId}-${citation.pblancId}`} className="citation">
          <span className="citation-id">{citation.evidenceId}</span>
          <span className="citation-title">{citation.title ?? citation.pblancId}</span>
          <span className="muted">
            {citation.location ?? (citation.pages.length > 0 ? `p.${citation.pages.join(", ")}` : "위치 정보 없음")}
          </span>
          {citation.headingPath.length > 0 && <span className="muted citation-path">{citation.headingPath.join(" > ")}</span>}
        </li>
      ))}
    </ul>
  );
}
