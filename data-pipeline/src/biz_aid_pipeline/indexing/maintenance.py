"""기준일 전 마감이 확정된 V2 point만 snapshot을 검증한 뒤 정리한다. MySQL row·V1·원본은 보존한다."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import requests
from sqlalchemy import select
from qdrant_client import QdrantClient, models

from biz_aid_pipeline.candidates.service import ProgramCandidateRepository
from biz_aid_pipeline.config.settings import ROOT, DbConfig, PipelineError
from biz_aid_pipeline.indexing.qdrant_store import qdrant_url


def closed_ids(repository, as_of):
    table = repository.programs.c
    with repository.engine.connect() as connection:
        return tuple(connection.execute(select(table.pblanc_id).where(
            table.application_end_date.is_not(None), table.application_end_date < as_of).order_by(table.pblanc_id)).scalars())


def program_filter(ids):
    return models.Filter(must=[models.FieldCondition(key="pblanc_id", match=models.MatchAny(any=list(ids)))])


def prune_closed(client, collection, ids, backup, apply=False):
    if not collection.startswith("bizaid_v2_"):
        raise PipelineError("closed_cleanup_v2_only")
    before = client.count(collection, exact=True).count
    selector = program_filter(ids) if ids else None
    target = client.count(collection, count_filter=selector, exact=True).count if ids else 0
    result = {"collection": collection, "closed_programs_in_mysql": len(ids), "target_program_ids": list(ids),
              "points_before": before, "target_points": target, "deleted_points": 0, "snapshot": None, "applied": apply}
    if apply and target:
        # BOUNDARY: 백업 생성·실제 로컬 byte 검증이 성공하기 전에는 delete를 호출할 수 없다.
        evidence = backup(client, collection)
        if not evidence.get("verified"):
            raise PipelineError("qdrant_snapshot_not_verified")
        result["snapshot"] = evidence
        # WHY: 백업 중 외부 적재로 분모가 바뀌었으면 오래된 대상 수로 삭제하지 않는다.
        if client.count(collection, exact=True).count != before or client.count(collection, count_filter=selector, exact=True).count != target:
            raise PipelineError("qdrant_changed_during_backup")
        client.delete(collection, points_selector=models.FilterSelector(filter=selector), wait=True)
        after = client.count(collection, exact=True).count
        if after != before - target or client.count(collection, count_filter=selector, exact=True).count:
            raise PipelineError("closed_cleanup_readback_failed")
        result["deleted_points"] = target
    result["points_after"] = client.count(collection, exact=True).count
    return result


def snapshot_backup(client, collection, directory, url):
    directory = directory.resolve()
    if directory.exists():
        existing = list(directory.glob("*.snapshot"))
        if len(existing) != 1:
            raise PipelineError("snapshot_backup_directory_not_unique")
        snapshots = [v for v in client.list_snapshots(collection) if v.name == existing[0].name]
        if len(snapshots) != 1:
            raise PipelineError("snapshot_backup_server_evidence_missing")
        snap, path = snapshots[0], existing[0]
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        if path.stat().st_size != snap.size or (getattr(snap, "checksum", None) and snap.checksum != digest.hexdigest()):
            raise PipelineError("snapshot_existing_backup_mismatch")
        evidence = {"verified": True, "snapshot_name": snap.name, "server_path": f"/qdrant/snapshots/{collection}/{snap.name}",
                    "local_path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest.hexdigest(), "reused_backup": True}
        (directory / "snapshot-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        return evidence
    directory.mkdir(parents=True, exist_ok=False)
    snap = client.create_snapshot(collection_name=collection, wait=True)
    path = directory / Path(snap.name).name
    if snap.name != path.name:
        raise PipelineError("snapshot_name_invalid")
    digest, size = hashlib.sha256(), 0
    with requests.get(url + "/collections/" + quote(collection, safe="") + "/snapshots/" + quote(snap.name, safe=""),
                      stream=True, timeout=(5, 120), allow_redirects=False) as response:
        if response.status_code != 200:
            raise PipelineError("snapshot_download_failed")
        with path.open("xb") as file:
            for block in response.iter_content(1024 * 1024):
                size += len(block)
                if size > 8 * 1024 ** 3:
                    raise PipelineError("snapshot_local_size_limit")
                digest.update(block)
                file.write(block)
    if not size or size != snap.size or (getattr(snap, "checksum", None) and snap.checksum != digest.hexdigest()):
        raise PipelineError("snapshot_size_checksum_mismatch")
    # WHY: 디스크에 보존된 byte를 다시 읽어 transfer 중 계산만 성공한 상태를 백업 완료로 오인하지 않는다.
    physical = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            physical.update(block)
    if physical.hexdigest() != digest.hexdigest():
        raise PipelineError("snapshot_local_readback_failed")
    evidence = {"verified": True, "snapshot_name": snap.name, "server_path": f"/qdrant/snapshots/{collection}/{snap.name}",
                "local_path": str(path.relative_to(ROOT)), "bytes": size, "sha256": physical.hexdigest()}
    (directory / "snapshot-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"snapshot_verified": evidence, "next_action": "delete_confirmed_closed_v2_points"}), flush=True)
    return evidence


def main(argv=None):
    from datetime import date
    parser = argparse.ArgumentParser(description="dev V2 confirmed-closed cleanup; snapshot required before deletion")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise PipelineError("cleanup_evidence_overwrite_refused")
    repository = ProgramCandidateRepository.from_config(DbConfig.load(ROOT, args.profile))
    client = QdrantClient(url=qdrant_url(args.profile))
    try:
        ids = closed_ids(repository, args.as_of)
        counts = {hit.value: hit.count for hit in client.facet(args.collection, key="pblanc_id", limit=100000, exact=True).hits}
        print(json.dumps({"as_of": str(args.as_of), "target_programs_with_points": sum(bool(counts.get(v)) for v in ids),
                          "target_points": sum(counts.get(v, 0) for v in ids), "apply": args.apply}), flush=True)
        others = {v.name: client.count(v.name, exact=True).count for v in client.get_collections().collections if v.name != args.collection}
        result = prune_closed(client, args.collection, ids, lambda c, n: snapshot_backup(c, n, args.backup_dir, qdrant_url(args.profile)), args.apply)
        if any(client.count(name, exact=True).count != count for name, count in others.items()):
            raise PipelineError("other_collection_changed")
        result.update(as_of=str(args.as_of), target_programs_with_points=sum(bool(counts.get(v)) for v in ids), other_collection_counts=others)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        repository.close()
        client.close()
