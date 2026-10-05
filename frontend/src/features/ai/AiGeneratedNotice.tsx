import { Link } from "react-router-dom";

/** 원문과 AI가 생성한 안내의 경계를 표시한다. 원문 URL이 없는 응답은 원문 링크가 있는 공고 상세로 연결한다. */
export function AiGeneratedNotice({ ids }: { ids: string[] }) {
  return <aside className="alert info small" aria-label="AI 안내와 원문 구분">
    <span>AI가 공고문을 참고해 만든 안내이며 공고 원문이 아닙니다. 판정은 참고용이며 최종 자격은 공고 원문과 주관기관에 확인하세요.</span>
    {[...new Set(ids)].map((id) => <Link key={id} to={`/programs/${encodeURIComponent(id)}`}>공고 원문 확인(상세)</Link>)}
  </aside>;
}
