"""자연어 query → BGE-M3 dense·sparse query vector → 기존 Qdrant collection 검색 → SearchResult[].

read-only 경로다. 문서 parsing·chunking·적재·stale 정리를 호출하지 않고 collection을 만들거나 바꾸지 않는다.
"""
from dataclasses import asdict, dataclass

from biz_aid_pipeline.config.settings import ROOT, PipelineError, read_json
from biz_aid_pipeline.indexing import qdrant_store

CONTRACT_PATH = ROOT / "contracts/schemas/document-retrieval.contract.json"
MODES = ("dense", "sparse", "hybrid")
# payload(FinalChunk.payload())에서 그대로 옮기는 근거 field. 별도 metadata 저장소를 만들지 않는다.
PAYLOAD_FIELDS = ("chunk_id", "pblanc_id", "title", "text", "heading_path", "source_sha256", "source_format", "route",
                  "parse_key", "chunk_set_key", "chunk_index", "pages", "provenance", "embedding_key")


def retrieval_contract(path=CONTRACT_PATH):
    return read_json(path)


@dataclass
class SearchResult:
    rank: int
    mode: str
    score: float
    chunk_id: str
    pblanc_id: str
    title: str | None
    text: str
    heading_path: list
    source_sha256: str
    source_format: str
    route: str
    parse_key: str
    chunk_set_key: str
    chunk_index: int
    pages: list
    provenance: list
    embedding_key: str
    dense_rank: int | None = None
    dense_score: float | None = None
    sparse_rank: int | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None

    def to_dict(self):
        return asdict(self)


def rrf(ranked_lists, rrf_k, limit):
    """mode별 순위 목록(point id 순서)을 Reciprocal Rank Fusion으로 합친다. 반환: (point id, rrf 점수) 목록.

    WHY: dense cosine과 sparse dot 점수는 척도가 달라 더하면 한쪽이 결과를 지배한다. 순위만 쓰는 RRF는 척도와 무관하다.
    동점은 더 좋은 최고 순위, 그다음 point id 오름차순으로 정해 실행마다 같은 순서를 낸다.
    """
    scores, best = {}, {}
    for ranked in ranked_lists:
        for rank, point_id in enumerate(ranked, 1):
            scores[point_id] = scores.get(point_id, 0.0) + 1.0 / (rrf_k + rank)
            best[point_id] = min(rank, best.get(point_id, rank))
    ordered = sorted(scores, key=lambda point_id: (-scores[point_id], best[point_id], point_id))
    return [(point_id, scores[point_id]) for point_id in ordered[:limit]]


class Retriever:
    """문서 적재와 같은 embedder(같은 embedding_key)로 query를 만들고 그 identity의 collection만 읽는다."""

    def __init__(self, embedder, client, index_contract, contract=None, namespace=None, collection=None):
        self.embedder, self.client = embedder, client
        self.contract = contract or retrieval_contract()
        identity = embedder.identity
        # BOUNDARY: collection 이름은 현재 embedding identity + 적재 범위 namespace(V1은 없음)로만 정한다. 다른 vector 공간을 읽을 수 없다.
        self.collection = collection or qdrant_store.collection_name(index_contract, identity["embedding_key"], namespace)
        if not client.collection_exists(self.collection):
            # RISK: 여기서 만들면 빈 collection이 "검색 결과 없음"처럼 보인다. 적재가 먼저다.
            raise PipelineError("retrieval_collection_missing:" + self.collection)
        differences = qdrant_store.schema_differences(index_contract, identity, client.get_collection(self.collection))
        if differences:
            raise PipelineError("retrieval_collection_schema_mismatch:" + ",".join(differences))

    def _filter(self, pblanc_id, source_sha256, pblanc_ids=None, exclude_roles=()):
        from qdrant_client import models
        conditions = [models.FieldCondition(key=key, match=models.MatchValue(value=value))
                      for key, value in (("pblanc_id", pblanc_id), ("source_sha256", source_sha256)) if value]
        if pblanc_ids is not None:
            # BOUNDARY: MySQL이 정한 후보 밖 point는 Qdrant 검색 후보 자체가 되지 않는다(검색 뒤 자르기가 아니다).
            conditions.append(models.FieldCondition(key="pblanc_id", match=models.MatchAny(any=list(pblanc_ids))))
        excluded = [models.FieldCondition(key="document_role", match=models.MatchAny(any=list(exclude_roles)))] if exclude_roles else []
        # BOUNDARY: FORM만 제외한다. 역할이 없거나 UNKNOWN인 기존 원본은 그대로 남긴다.
        return models.Filter(must=conditions, must_not=excluded) if conditions or excluded else None

    def _query(self, vector, using, limit, query_filter):
        points = self.client.query_points(self.collection, query=vector, using=using, limit=limit,
                                          query_filter=query_filter, with_payload=True).points
        return [(str(point.id), point.score, point.payload) for point in points]

    def search(self, query, mode="hybrid", top_k=None, pblanc_id=None, source_sha256=None, pblanc_ids=None, exclude_roles=()):
        """pblanc_ids(후보 scope)를 주면 그 공고의 chunk 안에서만 찾는다. 빈 scope는 embedding·검색 없이 빈 결과다."""
        from qdrant_client import models
        options, fusion = self.contract["options"], self.contract["fusion"]
        top_k = options["top_k_default"] if top_k is None else top_k
        if mode not in MODES:
            raise PipelineError("retrieval_mode_invalid:" + str(mode))
        if not isinstance(top_k, int) or not 1 <= top_k <= options["top_k_max"]:
            raise PipelineError("retrieval_top_k_out_of_range")
        if not query or not query.strip():
            raise PipelineError("retrieval_query_empty")
        if pblanc_ids is not None and not pblanc_ids:
            return []
        dense, sparse = self.embedder.encode([query])[0]
        query_filter = self._filter(pblanc_id, source_sha256, pblanc_ids, exclude_roles)
        limit = top_k if mode != "hybrid" else max(top_k, fusion["candidate_limit"])
        hits = {}
        if mode in ("dense", "hybrid"):
            hits["dense"] = self._query(dense, "dense", limit, query_filter)
        if mode in ("sparse", "hybrid"):
            hits["sparse"] = self._query(models.SparseVector(**sparse), "sparse", limit, query_filter)
        ranks = {name: {point_id: (rank, score) for rank, (point_id, score, _) in enumerate(found, 1)}
                 for name, found in hits.items()}
        payloads = {point_id: payload for found in hits.values() for point_id, _, payload in found}
        if mode == "hybrid":
            ordered = rrf([[point_id for point_id, _, _ in hits[name]] for name in ("dense", "sparse")], fusion["rrf_k"], top_k)
        else:
            ordered = [(point_id, score) for point_id, score, _ in hits[mode][:top_k]]
        results = []
        for rank, (point_id, score) in enumerate(ordered, 1):
            payload = payloads[point_id]
            dense_hit, sparse_hit = ranks.get("dense", {}).get(point_id), ranks.get("sparse", {}).get(point_id)
            results.append(SearchResult(
                rank=rank, mode=mode, score=score, **{name: payload.get(name) for name in PAYLOAD_FIELDS},
                dense_rank=dense_hit[0] if dense_hit else None, dense_score=dense_hit[1] if dense_hit else None,
                sparse_rank=sparse_hit[0] if sparse_hit else None, sparse_score=sparse_hit[1] if sparse_hit else None,
                rrf_score=score if mode == "hybrid" else None))
        return results

    def search_programs(self, query, limit, pblanc_ids, group_limit):
        """공고 단위 hybrid 순위. 의미·단어 검색마다 공고별 최고 조각 하나만 받아(Qdrant group 검색) 공고 순위를 RRF로 합친다.

        WHY: 목록의 출력 단위는 공고다. 조각 상위 N개를 자른 뒤 중복을 지우면 한 공고의 여러 조각이 목록 자리를 독점한다(IMP-014).
        반환 SearchResult는 각 공고의 대표 조각이며 rank·score는 공고 순위·RRF 점수, dense_rank·sparse_rank는 모드별 공고 순위다.
        """
        from qdrant_client import models
        if not pblanc_ids:
            return []
        if not query or not query.strip():
            raise PipelineError("retrieval_query_empty")
        dense, sparse = self.embedder.encode([query])[0]
        query_filter = self._filter(None, None, pblanc_ids)
        ranked = {}
        for name, vector in (("dense", dense), ("sparse", models.SparseVector(**sparse))):
            groups = self.client.query_points_groups(self.collection, query=vector, using=name, group_by="pblanc_id", group_size=1,
                                                     limit=group_limit, query_filter=query_filter, with_payload=True).groups
            ranked[name] = [(str(group.id), group.hits[0]) for group in groups if group.hits]
        positions = {name: {pblanc: (rank, hit) for rank, (pblanc, hit) in enumerate(found, 1)} for name, found in ranked.items()}
        ordered = rrf([[pblanc for pblanc, _ in ranked[name]] for name in ("dense", "sparse")], self.contract["fusion"]["rrf_k"], limit)
        results = []
        for rank, (pblanc, score) in enumerate(ordered, 1):
            dense_hit, sparse_hit = positions["dense"].get(pblanc), positions["sparse"].get(pblanc)
            # 대표 조각은 두 검색 중 더 높은 순위에서 나온 조각이다(동순위면 의미 검색 쪽).
            best = min((hit for hit in (dense_hit, sparse_hit) if hit), key=lambda item: item[0])[1]
            payload = best.payload or {}
            results.append(SearchResult(
                rank=rank, mode="hybrid_program", score=score, **{name: payload.get(name) for name in PAYLOAD_FIELDS},
                dense_rank=dense_hit[0] if dense_hit else None, dense_score=dense_hit[1].score if dense_hit else None,
                sparse_rank=sparse_hit[0] if sparse_hit else None, sparse_score=sparse_hit[1].score if sparse_hit else None,
                rrf_score=score))
        return results
