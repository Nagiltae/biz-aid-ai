"""SEARCH_LIST: MySQL 후보 안에서 질문과 가까운 공고를 찾아 공고 단위 목록으로 돌려준다. 답변 생성 LLM을 쓰지 않는다.

Qdrant(Hybrid Retriever)는 후보 공고의 순위만 정한다. 목록에 보이는 정형 정보는 MySQL 값이다.
"""
from dataclasses import asdict, dataclass

from biz_aid_pipeline.config.settings import PipelineError


@dataclass
class ProgramListItem:
    rank: int
    pblanc_id: str
    name: str | None
    category: str | None
    target: str | None
    jurisdiction_name: str | None
    executing_org_name: str | None
    application_start_date: str | None
    application_end_date: str | None
    application_period_raw: str | None
    announcement_url: str | None
    best_chunk_rank: int
    best_chunk_score: float


def dedupe_programs(results, limit):
    """chunk 결과를 첫 등장(가장 좋은 순위) 기준 pblanc_id 목록으로 줄인다. 같은 공고는 한 칸만 차지한다."""
    seen = {}
    for result in results:
        if result.pblanc_id not in seen:
            seen[result.pblanc_id] = result
        if len(seen) == limit:
            break
    return list(seen.values())


class ProgramDiscoveryService:
    def __init__(self, repository, retriever, contract):
        self.repository, self.retriever = repository, retriever
        self.spec = contract["discovery"]

    def discover(self, query, candidate_pblanc_ids):
        candidates = tuple(candidate_pblanc_ids)
        if not candidates:
            return []
        # BOUNDARY: 순위용 검색도 MySQL 후보 scope 안에서만 한다. 목록 전용 fetch 크기는 RAG top_k와 분리한다.
        results = self.retriever.search(query, self.spec["mode"], self.spec["fetch_chunks"], pblanc_ids=candidates)
        allowed = set(candidates)
        if any(result.pblanc_id not in allowed for result in results):
            raise PipelineError("retrieval_scope_violation")
        best = dedupe_programs(results, self.spec["max_programs"])
        metadata = self.repository.program_metadata([result.pblanc_id for result in best])
        items = []
        for result in best:
            row = metadata.get(result.pblanc_id)
            if row is None:
                continue
            items.append(ProgramListItem(len(items) + 1, row["pblanc_id"], row["name"], row["category"], row["target"],
                                         row["jurisdiction_name"], row["executing_org_name"],
                                         str(row["application_start_date"]) if row["application_start_date"] else None,
                                         str(row["application_end_date"]) if row["application_end_date"] else None,
                                         row["application_period_raw"], row["announcement_url"], result.rank, result.score))
        return [asdict(item) for item in items]
