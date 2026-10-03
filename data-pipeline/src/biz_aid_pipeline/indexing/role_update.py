"""승인된 V2 document_role 정정만 수행한다. 원본·식별값·벡터를 다시 적재하지 않는다."""
import copy
import hashlib
import json

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.indexing.document_role import document_role
from biz_aid_pipeline.indexing.embedder import indexing_contract


def point_digest(point):
    payload = dict(point.payload)
    payload.pop("document_role", None)
    return hashlib.sha256(json.dumps({"id": str(point.id), "vector": {key: value.model_dump() if hasattr(value, "model_dump") else value for key, value in point.vector.items()} if isinstance(point.vector, dict) else point.vector, "payload": payload},
                                    ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def update_internal_roles(client, collection, filenames, apply=False):
    """기존 BODY를 내부 지급 규정 UNKNOWN으로만 정정하며 전후 나머지 payload·벡터를 확인한다."""
    from qdrant_client import models
    if not collection.startswith("bizaid_v2_"):
        raise PipelineError("role_update_v2_only")
    old = copy.deepcopy(indexing_contract())
    old["document_role"].pop("internal_policy_cues", None)
    changed, offset = [], None
    count = client.count(collection, exact=True).count
    while True:
        points, offset = client.scroll(collection, limit=128, offset=offset, with_vectors=False, with_payload=True)
        for point in points:
            payload = point.payload
            names = filenames.get(payload.get("source_sha256"), ())
            fmt = payload.get("source_format")
            if payload.get("document_role") != "BODY" or not names:
                continue
            before, after = document_role(fmt, names, old), document_role(fmt, names)
            if before == after:
                continue
            original = client.retrieve(collection, ids=[point.id], with_vectors=True, with_payload=True)[0]
            digest = point_digest(original)
            if apply:
                client.set_payload(collection, payload={"document_role": after}, points=[point.id], wait=True)
                verified = client.retrieve(collection, ids=[point.id], with_vectors=True, with_payload=True)[0]
                if digest != point_digest(verified) or verified.payload.get("document_role") != after:
                    raise PipelineError("role_update_integrity_failure")
            changed.append({"point_id": str(point.id), "source_sha256": payload["source_sha256"], "before": before,
                            "after": after, "identity_vector_payload_unchanged": True if apply else None})
        if offset is None:
            break
    if client.count(collection, exact=True).count != count:
        raise PipelineError("role_update_count_changed")
    return {"collection": collection, "apply": apply, "point_count": count, "changed_point_count": len(changed), "changes": changed}


def main(argv=None):
    import argparse
    from pathlib import Path
    from sqlalchemy import select
    from qdrant_client import QdrantClient
    from biz_aid_pipeline.config.settings import ROOT, DbConfig
    from biz_aid_pipeline.documents.archive import member_basename
    from biz_aid_pipeline.parsing.repository import ParseResultRepository
    from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
    parser = argparse.ArgumentParser(description="V2 payload-only internal-policy role correction; no embedding")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    repository = ParseResultRepository(DbConfig.load(ROOT, args.profile))
    names = {}
    try:
        with repository.engine.connect() as connection:
            sources = repository.sources.c
            for sha, name in connection.execute(select(sources.content_sha256, sources.original_filename).where(sources.download_status == "ACQUIRED")):
                names.setdefault(sha, set()).add(name)
            if repository.members is not None:
                members = repository.members.c
                for sha, path in connection.execute(select(members.member_sha256, members.member_path).where(members.processing_status.in_(("STORED", "DUPLICATE_SOURCE")))):
                    names.setdefault(sha, set()).add(member_basename(path))
    finally:
        repository.close()
    client = QdrantClient(url=qdrant_url(args.profile))
    try:
        result = update_internal_roles(client, args.collection, names, args.apply)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({key: value for key, value in result.items() if key != "changes"}))
    finally:
        client.close()
    return 0
