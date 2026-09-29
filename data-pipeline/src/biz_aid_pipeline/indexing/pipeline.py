import time

from biz_aid_pipeline.config.settings import ROOT, PipelineError
from biz_aid_pipeline.chunking.cli import chunk_source
from biz_aid_pipeline.indexing import qdrant_store


def unique_texts(chunks):
    """content_key별 embedding 입력. 같은 key는 한 번만 추론한다."""
    texts = {}
    for chunk in chunks:
        # RISK: key가 같은데 입력이 다르면 재사용한 vector가 다른 text를 대표하게 된다.
        if texts.setdefault(chunk.content_key, chunk.embedding_text) != chunk.embedding_text:
            raise PipelineError("content_key_text_conflict:" + chunk.content_key)
    return texts


def index_chunks(chunks, source_sha256, embedder, client, contract):
    identity = embedder.identity
    expected = {"repo_id": identity["model_repo_id"], "revision": identity["model_revision"]}
    # BOUNDARY: chunk 크기를 잰 tokenizer와 embedding 모델이 다르면 token 한도와 vector 의미가 어긋난다.
    if any(chunk.embedding_model != expected for chunk in chunks):
        raise PipelineError("chunk_embedding_model_mismatch")
    name, created = qdrant_store.ensure_collection(client, contract, identity)
    texts = unique_texts(chunks)
    started = time.monotonic()
    vectors = dict(zip(texts, embedder.encode(list(texts.values()))))
    embed_seconds = time.monotonic() - started
    points = [qdrant_store.point(chunk, vectors[chunk.content_key], identity) for chunk in chunks]
    qdrant_store.upsert(client, name, points, contract["qdrant"]["upsert_batch_size"])
    stale = qdrant_store.delete_stale(client, name, source_sha256, {chunk.chunk_id for chunk in chunks})
    stored = client.count(name, count_filter=qdrant_store.source_filter(source_sha256), exact=True).count
    return {"source_sha256": source_sha256, "status": "INDEXED", "collection": name, "collection_created": created,
            "embedding_key": identity["embedding_key"], "chunks": len(chunks), "embedded": len(texts),
            "embed_seconds": round(embed_seconds, 1), "upserted": len(points), "stale_deleted": stale,
            "source_points": stored}


def index_source(source_sha256, embedder, client, contract, profile="dev", root=ROOT, explicit_parse_key=None):
    """source SHA 하나: 현재 parse 결과 → FinalChunk → dense·sparse → Qdrant."""
    chunks = chunk_source(root, profile, source_sha256, explicit_parse_key)
    if not chunks:
        raise PipelineError("no_chunks")
    return index_chunks(chunks, source_sha256, embedder, client, contract)
