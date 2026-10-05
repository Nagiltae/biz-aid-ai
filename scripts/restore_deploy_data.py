"""서버 배포 데이터 복원. Compose client만 사용하고 Secret·원본 SQL 오류는 출력하지 않는다."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("support_programs", "support_program_sync_history", "document_acquisition_runs",
          "document_sources", "document_parse_results", "document_archive_members")


class RestoreFailure(ValueError):
    """고정 오류 코드만 CLI로 내보낸다. 외부 client 원문은 사용하지 않는다."""


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(args, source, payload=None):
    environment = dict(os.environ, COMPOSE_DISABLE_ENV_FILE="1", BIZAID_RESTORE_PATH=str(source.resolve()))
    result = subprocess.run(["docker", "compose", "--env-file", str(ROOT / ".env.prod"),
        "-f", str(ROOT / "docker-compose.prod.yml"), "-f", str(ROOT / "docker-compose.restore.yml"),
        "--profile", "tools", "run", "--rm", "--no-deps", "-T"] + args,
        input=payload, capture_output=True, env=environment)
    if result.returncode:
        # BOUNDARY: DB/HTTP 원문 오류는 credential·공고 본문을 반사할 수 있다.
        raise RestoreFailure("restore_client_failed; raw output withheld")
    return result.stdout


def counts(raw):
    return {name: int(value) for name, value in (line.split("\t") for line in raw.decode().splitlines())}


def count_query():
    return " UNION ALL ".join(f"SELECT '{table}',COUNT(*) FROM {table}" for table in TABLES) + ";"


def restore_programs(source, manifest):
    if set(manifest["tables"]) != set(TABLES) or any(type(n) is not int or n < 0 for n in manifest["tables"].values()):
        raise RestoreFailure("invalid_table_counts")
    health = json.loads(command(["http-tools", "--fail", "--silent", "--max-time", "15", "http://backend:8080/api/health"], source))
    if health.get("status") != "ok":
        raise RestoreFailure("backend_schema_health_required")
    before = counts(command(["mysql-tools", "-e", count_query()], source))
    if set(before) != set(TABLES) or any(before.values()):
        raise RestoreFailure("existing_program_data_overwrite_forbidden")
    content = (source / "programs.sql").read_bytes()
    if re.search(rb"(?im)^\s*(?:/\*!\d+\s*)?(?:ALTER|CREATE|DROP|TRUNCATE|DELETE|LOCK|UNLOCK|COMMIT|START\s+TRANSACTION)\b", content):
        raise RestoreFailure("dump_must_be_insert_only_no_implicit_commit")
    condition = " AND ".join(f"(SELECT COUNT(*) FROM {table})={manifest['tables'][table]}" for table in TABLES)
    # WHY: session 임시 CHECK로 개수 오류도 COMMIT 전에 중단한다. 영구 schema를 만들거나 migration을 바꾸지 않는다.
    payload = ("CREATE TEMPORARY TABLE restore_guard (ok INT CHECK(ok=1));\nSTART TRANSACTION;\n").encode() + content + (
        f"\nINSERT INTO restore_guard VALUES(IF({condition},1,0));\nCOMMIT;\n" + count_query()).encode()
    after = counts(command(["mysql-tools"], source, payload))
    if after != manifest["tables"]:
        raise RestoreFailure("restored_counts_mismatch")
    return {"tables": after}


def restore_qdrant(source, manifest):
    collection = manifest["collection"]
    if not re.fullmatch(r"bizaid_v2_[a-zA-Z0-9_-]+", collection):
        raise RestoreFailure("v2_collection_required")
    listed = json.loads(command(["http-tools", "--fail", "--silent", "--max-time", "15", "http://qdrant:6333/collections"], source))
    if collection in {item["name"] for item in listed["result"]["collections"]}:
        raise RestoreFailure("existing_collection_overwrite_forbidden")
    result = json.loads(command(["http-tools", "--fail", "--silent", "--max-time", "600", "-X", "POST",
        f"http://qdrant:6333/collections/{collection}/snapshots/upload?priority=snapshot&wait=true",
        "-F", "snapshot=@/transfer/v2.snapshot"], source))
    if result.get("status") != "ok":
        raise RestoreFailure("qdrant_restore_failed")
    count = json.loads(command(["http-tools", "--fail", "--silent", "--max-time", "30", "-H", "Content-Type: application/json",
        "-d", '{"exact":true}', f"http://qdrant:6333/collections/{collection}/points/count"], source))["result"]["count"]
    if count != manifest["point_count"]:
        raise RestoreFailure("qdrant_point_count_mismatch; restored collection retained for diagnosis")
    return {"collection": collection, "point_count": count}


def restore_models(source, manifest, target):
    target = Path(target).resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise RestoreFailure("existing_models_overwrite_forbidden")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bizaid-model-", dir=target.parent) as temporary:
        scratch = Path(temporary)
        with tarfile.open(source / "models.tar.gz", "r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts or not name.parts or name.parts[0] not in {"BAAI--bge-m3", "BAAI--bge-m3-embedding"}:
                    raise RestoreFailure("unsafe_model_archive")
            archive.extractall(scratch, filter="data")
        for name, expected in manifest["model_files"].items():
            path = (scratch / name).resolve()
            if not path.is_relative_to(scratch) or not path.is_file() or sha(path) != expected:
                raise RestoreFailure("extracted_model_checksum_mismatch")
        if target.exists():
            target.rmdir()  # BOUNDARY: 빈 목적지만 교체한다. 기존 corpus/모델을 삭제하지 않는다.
        scratch.rename(target)
    return {"model_directory": str(target), "verified_files": len(manifest["model_files"])}


def main():
    parser = argparse.ArgumentParser(description="빈 운영 저장소에만 복원")
    parser.add_argument("kind", choices=["programs", "qdrant", "models"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model-path", type=Path)
    args = parser.parse_args()
    source = args.directory.resolve()
    manifest = json.loads((source / "data-manifest.json").read_text())
    name = {"programs": "programs.sql", "qdrant": "v2.snapshot", "models": "models.tar.gz"}[args.kind]
    if sha(source / name) != manifest["sha256"][name]:
        raise RestoreFailure("input_checksum_mismatch")
    if args.kind == "programs": result = restore_programs(source, manifest)
    elif args.kind == "qdrant": result = restore_qdrant(source, manifest)
    else:
        if not args.model_path: raise RestoreFailure("model_path_required")
        result = restore_models(source, manifest, args.model_path)
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except RestoreFailure as error:
        print("FAIL: " + str(error))
        raise SystemExit(1) from None
    except (ValueError, OSError, KeyError, tarfile.TarError):
        print("FAIL: restore rejected or failed; check empty target, checksums, service health and settings")
        raise SystemExit(1) from None
