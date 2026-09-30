import type { Citation } from "./aiApi";

/** 근거 위치 표시: 공고명 · 위치(자격 판정은 location, 문서 질문은 page) · 문단 제목 경로. 근거가 없으면 아무것도 그리지 않는다. */
export function CitationList({ citations }: { citations: Citation[] | null }) {
  if (!citations || citations.length === 0) return null;
  const where = (citation: Citation) =>
    citation.location ?? (citation.pages && citation.pages.length > 0 ? `p.${citation.pages.join(", ")}` : "위치 정보 없음");
  return (
    <ul className="citations" aria-label="공고문 근거">
      {citations.map((citation) => (
        <li key={`${citation.evidenceId}-${citation.pblancId}`} className="citation">
          <span className="citation-id">{citation.evidenceId}</span>
          <span className="citation-title">{citation.title ?? citation.pblancId}</span>
          <span className="muted">{where(citation)}</span>
          {citation.headingPath && citation.headingPath.length > 0 && (
            <span className="muted citation-path">{citation.headingPath.join(" > ")}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
