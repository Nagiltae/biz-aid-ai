"""SEARCH_LIST: MySQL 후보 안에서 질문과 가까운 공고를 찾아 공고 단위 목록으로 돌려준다. 답변 생성 LLM을 쓰지 않는다.

Qdrant(Hybrid Retriever)는 후보 공고의 순위만 정한다. 목록에 보이는 정형 정보는 MySQL 값이다.
순위 단위는 조각이 아니라 공고다. 의미·단어 검색마다 공고별 최고 조각 하나만 받아 공고 순위를 RRF로 합친다(IMP-014).
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
    rrf_score: float                # 공고 단위 순위 결합 점수(목록 순위의 근거)
    dense_rank: int | None          # 의미 검색에서 이 공고(최고 조각)의 공고 순위
    sparse_rank: int | None         # 단어 검색에서 이 공고(최고 조각)의 공고 순위
    evidence_chunk_id: str | None   # 순위 근거가 된 대표 문서 조각


class ProgramDiscoveryService:
    def __init__(self, repository, retriever, contract):
        self.repository, self.retriever = repository, retriever
        self.spec = contract["discovery"]

    def discover(self, query, candidate_pblanc_ids, limit=None):
        """limit을 주면 최대 그 수까지만(V2 개인화 검색 Top 3). 없으면 계약의 max_programs다."""
        candidates = tuple(candidate_pblanc_ids)
        if not candidates:
            return []
        # BOUNDARY: 순위용 검색도 MySQL 후보 scope 안에서만 한다. 목록 설정은 RAG top_k와 분리한다.
        # 목록을 채우려고 후보 밖 공고나 검색 근거가 없는 공고를 넣지 않는다. 근거가 있는 공고만 최대 max_programs개다.
        size = min(limit, self.spec["group_limit_per_mode"]) if limit is not None else self.spec["max_programs"]
        best = self.retriever.search_programs(query, size, candidates, self.spec["group_limit_per_mode"])
        allowed = set(candidates)
        if any(result.pblanc_id not in allowed for result in best):
            raise PipelineError("retrieval_scope_violation")
        if len({result.pblanc_id for result in best}) != len(best):
            raise PipelineError("discovery_duplicate_program")
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
                                         row["application_period_raw"], row["announcement_url"], result.score,
                                         result.dense_rank, result.sparse_rank, result.chunk_id))
        return [asdict(item) for item in items]
