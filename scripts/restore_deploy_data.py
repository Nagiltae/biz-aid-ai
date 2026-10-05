"""서버 배포 데이터 복원. Compose client만 사용하고 Secret·원본 SQL 오류는 출력하지 않는다."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
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


def command(args, source, payload=None, *, overrides=None, permission_service=None):
    environment = dict(os.environ, COMPOSE_DISABLE_ENV_FILE="1", BIZAID_RESTORE_PATH=str(source.resolve()))
    environment.update(overrides or {})
    result = subprocess.run(["docker", "compose", "--env-file", str(ROOT / ".env.prod"),
        "-f", str(ROOT / "docker-compose.prod.yml"), "-f", str(ROOT / "docker-compose.restore.yml"),
        "--profile", "tools", "run", "--rm", "--no-deps", "-T"] + args,
        input=payload, capture_output=True, env=environment)
    if result.returncode:
        if permission_service:
            # BOUNDARY: 자체 검사에서 정한 코드·파일 경로만 허용한다. Docker 원문과 설정값은 출력하지 않는다.
            reason = "container_check_failed; image, mount and Docker access must be checked"
            for line in result.stdout.decode("utf-8", errors="replace").splitlines():
                if re.fullmatch(r"(?:unreadable_file|unreadable_directory):/(?:models|certs)/?[a-zA-Z0-9_./-]*", line):
                    reason = line
                    break
                elif line in {"image_user_must_not_be_root", "no_files", "directory_required", "scan_failed"}:
                    reason = line
            raise RestoreFailure(f"permission_check_failed:{permission_service}:{reason}")
        # BOUNDARY: DB/HTTP 원문 오류는 credential·공고 본문을 반사할 수 있다.
        raise RestoreFailure("restore_client_failed; raw output withheld")
    return result.stdout


def normalize_permissions(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise RestoreFailure("permission_directory_required")
    # WHY: TemporaryDirectory의 700이 복원 목적지에 남으면 이미지의 일반 사용자가 폴더에 들어가지 못한다.
    directory.chmod(0o755)
    def walk_error(error):
        raise error
    for parent, directories, files in os.walk(directory, onerror=walk_error):
        for name in directories + files:
            path = Path(parent) / name
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                path.chmod(0o755)
            elif stat.S_ISREG(mode):
                path.chmod(0o644)
            else:
                raise RestoreFailure("permission_symlink_or_special_file_forbidden")


READ_CHECK = '''set -eu
folder=$1
uid=$(id -u)
[ "$uid" != 0 ] || { echo image_user_must_not_be_root; exit 1; }
[ -d "$folder" ] || { echo directory_required; exit 1; }
[ -r "$folder" ] && [ -x "$folder" ] || { echo unreadable_directory:$folder; exit 1; }
# 일반 사용자로 모든 파일을 끝까지 읽어 실제 mount 권한을 검사한다. 내용은 버린다.
find "$folder" -type d -exec sh -c 'for p do [ -r "$p" ] && [ -x "$p" ] || { echo unreadable_directory:$p; exit 1; }; done' sh {} + 2>/dev/null || { echo scan_failed; exit 1; }
find "$folder" -type f -exec sh -c 'for p do cat "$p" >/dev/null 2>&1 || { echo unreadable_file:$p; exit 1; }; done' sh {} + 2>/dev/null || exit 1
count=$(find "$folder" -type f 2>/dev/null | wc -l)
[ "$count" -gt 0 ] || { echo no_files; exit 1; }
printf 'uid=%s\\nfiles=%s\\n' "$uid" "$count"
'''


def check_readable(service, directory, mount):
    setting = "BIZAID_MODEL_PATH" if mount == "/models" else "MYSQL_TLS_CERTS_PATH"
    raw = command(["--entrypoint", "sh", service, "-c", READ_CHECK, "sh", mount], Path(directory),
                  overrides={setting: str(Path(directory).resolve())}, permission_service=service)
    match = re.fullmatch(rb"uid=([1-9][0-9]*)\nfiles=([1-9][0-9]*)\n", raw)
    if not match:
        raise RestoreFailure(f"permission_check_failed:{service}:invalid_check_result")
    return {"service": service, "uid": int(match[1]), "readable_files": int(match[2]), "mount": mount}


def verify_permissions(directory, *, certs=False):
    normalize_permissions(directory)
    services = ("backend", "fastapi") if certs else ("fastapi",)
    mount = "/certs" if certs else "/models"
    return {"permissions": "directories=755,files=644", "read_checks": [check_readable(service, directory, mount) for service in services]}


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
                if not (member.isdir() or member.isfile()):
                    raise RestoreFailure("model_archive_links_or_special_files_forbidden")
            archive.extractall(scratch, filter="data")
        for name, expected in manifest["model_files"].items():
            path = (scratch / name).resolve()
            if not path.is_relative_to(scratch) or not path.is_file() or sha(path) != expected:
                raise RestoreFailure("extracted_model_checksum_mismatch")
        if target.exists():
            target.rmdir()  # BOUNDARY: 빈 목적지만 교체한다. 기존 corpus/모델을 삭제하지 않는다.
        scratch.rename(target)
    return {"model_directory": str(target), "verified_files": len(manifest["model_files"]), **verify_permissions(target)}


def main():
    parser = argparse.ArgumentParser(description="빈 운영 저장소에만 복원")
    parser.add_argument("kind", choices=["programs", "qdrant", "models", "models-check", "certs"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model-path", type=Path)
    args = parser.parse_args()
    source = args.directory.resolve()
    if args.kind in {"models-check", "certs"}:
        result = verify_permissions(source, certs=args.kind == "certs")
        print(json.dumps({"status": "PASS", **result}, ensure_ascii=False))
        return
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
    except PermissionError:
        print("FAIL: filesystem_permission_denied; host owner must be able to set directory=755 and file=644")
        raise SystemExit(1) from None
    except (ValueError, OSError, KeyError, tarfile.TarError):
        print("FAIL: restore rejected or failed; check empty target, checksums, service health and settings")
        raise SystemExit(1) from None
