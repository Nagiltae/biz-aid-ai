"""dev Qdrant collection 준비·batch upsert·stale 정리. collection은 embedding_key마다 하나다."""
import os
from urllib.parse import urlparse

from biz_aid_pipeline.config.settings import ROOT, PipelineError, profile_values

DEFAULT_URL = "http://127.0.0.1:6333"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def qdrant_url(profile, root=ROOT, environ=None):
    # BOUNDARY: 이 단계의 index는 dev 파생 데이터다. prod나 원격 Qdrant에는 쓰지 않는다.
    if profile != "dev":
        raise PipelineError("indexing_requires_dev_profile")
    url = profile_values(root, profile, {"QDRANT_URL"}, os.environ if environ is None else environ).get("QDRANT_URL") or DEFAULT_URL
    if urlparse(url).hostname not in LOOPBACK:
        raise PipelineError("qdrant_url_not_loopback")
    return url


def collection_name(contract, embedding_key):
    return f"bizaid_chunks_v{contract['qdrant']['schema_version']}_{embedding_key[:12]}"


def collection_metadata(contract, identity):
    return {"schema_version": contract["qdrant"]["schema_version"], "embedding_key": identity["embedding_key"],
            "embedding_model": {"repo_id": identity["model_repo_id"], "revision": identity["model_revision"]}}


def schema_differences(contract, identity, info):
    """기존 collection 설정과 Contract의 차이 목록. 비어 있어야 재사용한다."""
    spec = contract["qdrant"]
    params = info.config.params
    vectors = params.vectors if isinstance(params.vectors, dict) else {}
    sparse = params.sparse_vectors or {}
    differences = []
    if set(vectors) != set(spec["vectors"]):
        differences.append("dense_vector_names")
    for name, expected in spec["vectors"].items():
        actual = vectors.get(name)
        if actual is not None and (actual.size != expected["size"] or actual.distance.value != expected["distance"]):
            differences.append("dense_vector_config:" + name)
    if set(sparse) != set(spec["sparse_vectors"]):
        differences.append("sparse_vector_names")
    for name, expected in spec["sparse_vectors"].items():
        actual = sparse.get(name)
        modifier = actual.modifier.value if actual is not None and actual.modifier is not None else "none"
        if actual is not None and modifier != expected["modifier"]:
            differences.append("sparse_vector_config:" + name)
    metadata = info.config.metadata or {}
    for key, value in collection_metadata(contract, identity).items():
        if metadata.get(key) != value:
            differences.append("metadata:" + key)
    schema = info.payload_schema or {}
    for field, kind in spec["payload_indexes"].items():
        if field in schema and schema[field].data_type.value != kind:
            differences.append("payload_index:" + field)
    return differences


def ensure_collection(client, contract, identity):
    """없으면 만들고, 있으면 schema가 같을 때만 재사용한다. 반환: (이름, created 여부)."""
    from qdrant_client import models
    spec = contract["qdrant"]
    name = collection_name(contract, identity["embedding_key"])
    created = not client.collection_exists(name)
    if created:
        client.create_collection(
            name, vectors_config={key: models.VectorParams(size=value["size"], distance=models.Distance(value["distance"]))
                                  for key, value in spec["vectors"].items()},
            sparse_vectors_config={key: models.SparseVectorParams(modifier=None if value["modifier"] == "none"
                                                                   else models.Modifier(value["modifier"]))
                                   for key, value in spec["sparse_vectors"].items()},
            metadata=collection_metadata(contract, identity))
    else:
        differences = schema_differences(contract, identity, client.get_collection(name))
        # RISK: 조용히 재생성하면 다른 설정의 vector와 섞이거나 기존 index가 사라진다. 사람이 결정하도록 멈춘다.
        if differences:
            raise PipelineError("qdrant_collection_schema_mismatch:" + name + ":" + ",".join(differences))
    existing = client.get_collection(name).payload_schema or {}
    for field, kind in spec["payload_indexes"].items():
        if field not in existing:
            client.create_payload_index(name, field_name=field, field_schema=models.PayloadSchemaType(kind), wait=True)
    return name, created


def point(chunk, vector, identity):
    from qdrant_client import models
    dense, sparse = vector
    payload = dict(chunk.payload(), embedding_key=identity["embedding_key"])
    return models.PointStruct(id=chunk.chunk_id, payload=payload,
                              vector={"dense": dense, "sparse": models.SparseVector(**sparse)})


def upsert(client, name, points, batch_size):
    # 같은 chunk_id는 같은 point를 덮어쓰므로 재실행해도 point가 늘지 않는다.
    for start in range(0, len(points), batch_size):
        client.upsert(name, points=points[start:start + batch_size], wait=True)


def source_filter(source_sha256):
    from qdrant_client import models
    return models.Filter(must=[models.FieldCondition(key="source_sha256", match=models.MatchValue(value=source_sha256))])


def delete_stale(client, name, source_sha256, current_ids):
    """같은 source의 point 중 이번 chunk 집합에 없는 것(이전 parse·chunk 결과, 끊긴 공고 relation)을 지운다."""
    from qdrant_client import models
    selector = models.Filter(must=source_filter(source_sha256).must,
                             must_not=[models.HasIdCondition(has_id=list(current_ids))])
    before = client.count(name, count_filter=selector, exact=True).count
    if before:
        client.delete(name, points_selector=models.FilterSelector(filter=selector), wait=True)
    return before
