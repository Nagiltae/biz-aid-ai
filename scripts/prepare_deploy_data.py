"""맥북 이사 자료와 공개 데이터 checksum 준비. 업로드·credential 열람은 하지 않는다."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("support_programs", "support_program_sync_history", "document_acquisition_runs", "document_sources", "document_parse_results", "document_archive_members")


def digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--mysql-container", default="biz-aid-ai-mysql-1")
    parser.add_argument("--collection", default="bizaid_v2_chunks_v1_228acdd12220")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    args = parser.parse_args()
    if not re.fullmatch(r"bizaid_v2_[a-zA-Z0-9_-]+", args.collection): raise ValueError("v2_only")
    args.directory.mkdir(parents=True, exist_ok=False)
    outputs = ["programs.sql", "v2.snapshot", "models.tar.gz"]
    calls = [["scripts/export_program_data.sh", args.mysql_container, str(args.directory / outputs[0])],
        ["scripts/snapshot_v2_qdrant.sh", args.qdrant_url, args.collection, str(args.directory / outputs[1])],
        ["scripts/prepare_model_bundle.sh", str(args.model_path), str(args.directory / outputs[2])]]
    for call in calls:
        result = subprocess.run(call, cwd=ROOT, capture_output=True)
        if result.returncode: raise ValueError("preparation_failed; raw output withheld")
    query = " UNION ALL ".join(f"SELECT '{table}',COUNT(*) FROM {table}" for table in TABLES)
    result = subprocess.run(["docker", "exec", args.mysql_container, "sh", "-c",
        'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u "$MYSQL_USER" "$MYSQL_DATABASE" --batch --skip-column-names -e "$1"', "sh", query], capture_output=True)
    if result.returncode: raise ValueError("source_count_failed")
    tables = {name: int(count) for name, count in (line.split("\t") for line in result.stdout.decode().splitlines())}
    with urllib.request.urlopen(args.qdrant_url + "/collections/" + args.collection) as reply:
        point_count = json.load(reply)["result"]["points_count"]
    hashes = {}
    for name in outputs:
        with (args.directory / name).open("rb") as stream: hashes[name] = digest(stream)
    model_files = {}
    with tarfile.open(args.directory / "models.tar.gz", "r:gz") as archive:
        for member in archive:
            if member.isfile():
                with archive.extractfile(member) as stream: model_files[member.name] = digest(stream)
    manifest = {"tables": tables, "collection": args.collection, "point_count": point_count, "sha256": hashes, "model_files": model_files}
    (args.directory / "data-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"directory": str(args.directory), "tables": tables, "point_count": point_count,
        "sizes": {name:(args.directory/name).stat().st_size for name in outputs}, "sha256": hashes},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    try: main()
    except (ValueError, OSError, tarfile.TarError):
        print("FAIL: preparation stopped; partial outputs preserved; raw errors withheld")
        raise SystemExit(1) from None
