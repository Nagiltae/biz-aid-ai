"""일반 ZIP 첨부 펼치기(4단계, 깊이 1). 내부 파일을 각각 문서로 기록하고 처리할 파일만 S3에 저장한다.

- 압축은 메모리에서만 연다. 내부 파일을 로컬 디스크에 풀지 않는다. 안전 한도는 hwpx_container_limits를 그대로 쓴다.
- 압축 안의 압축은 열지 않고 상태(EXCLUDED nested_archive)만 남긴다.
- 내부 파일 이름은 UTF-8 플래그가 있으면 UTF-8, 없으면 CP949로 읽고, 실패하면 원래 byte만 믿는다.
- 공고 relation은 복사하지 않는다. 읽을 때 압축 첨부의 document_sources 행에서 물려받는다.
- 내부 파일 파싱은 실제 형식의 기존 route를 그대로 쓴다(새 parser 없음). 이 모듈은 파싱하지 않는다.
"""
import argparse
import hashlib
import io
import json
import struct
import time
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.engine import URL

from biz_aid_pipeline.config.settings import ROOT, PipelineError
from biz_aid_pipeline.documents.formats import actual_format

MEMBER_TABLE = "document_archive_members"
RUNS = Path("data/parsed/archive-runs")
STATUSES = ("STORED", "DUPLICATE_SOURCE", "EXCLUDED", "FAILED")


@dataclass(frozen=True)
class MemberPlan:
    member_key: str
    member_index: int
    path_raw: bytes
    path: str | None
    encoding: str
    byte_size: int
    sha256: str | None
    detected_format: str | None
    status: str
    reason: str | None
    unicode_extra_path: str | None = None
    raw: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def basename(self):
        return member_basename(self.path)


@dataclass(frozen=True)
class ArchivePlan:
    archive_sha256: str
    failure_code: str | None
    members: tuple = ()
    directories: int = 0


def member_key(archive_sha256, path_raw):
    return hashlib.sha256(archive_sha256.encode("ascii") + b"\0" + path_raw).hexdigest()


def member_basename(path):
    return (path or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def decode_name(info):
    """(원래 byte, 사람이 읽는 경로 또는 None, 해석 방식). zipfile은 UTF-8 플래그가 없으면 cp437로 읽으므로 그대로 되돌려 원래 byte를 얻는다."""
    if info.flag_bits & 0x800:
        return info.orig_filename.encode("utf-8"), info.orig_filename, "UTF8_FLAG"
    raw = info.orig_filename.encode("cp437")
    try:
        return raw, raw.decode("cp949"), "CP949"
    except UnicodeDecodeError:
        return raw, None, "RAW_BYTES"


def unicode_path_extra(info):
    """Info-ZIP Unicode Path extra field(0x7075)의 UTF-8 이름. 이름 결정에는 쓰지 않고 미리보기 대조 근거로만 쓴다."""
    extra, offset = info.extra, 0
    while offset + 4 <= len(extra):
        tag, size = struct.unpack_from("<HH", extra, offset)
        data = extra[offset + 4:offset + 4 + size]
        if tag == 0x7075 and len(data) >= 5 and data[0] == 1:
            try:
                return data[5:].decode("utf-8")
            except UnicodeDecodeError:
                return None
        offset += 4 + size
    return None


def unsafe_reason(infos, names, limits):
    """압축 전체를 거부할 사유. 하나라도 걸리면 내부 파일을 하나도 기록하지 않는다(부분 펼치기 없음)."""
    if len(infos) > limits["max_entries"]:
        return "archive_unsafe:entry_limit"
    if sum(info.file_size for info in infos) > limits["max_total_uncompressed_bytes"]:
        return "archive_unsafe:total_size"
    if any(info.flag_bits & 0x1 for info in infos):
        return "archive_encrypted"
    if len(set(names)) != len(names):
        return "archive_unsafe:duplicate_name"
    if any(len(name) > 1024 for name in names):
        return "archive_unsafe:name_too_long"
    for info in infos:
        # BOUNDARY: Windows 압축의 역슬래시 경로도 같은 경로 탈출 검사를 받는다.
        path = PurePosixPath(info.orig_filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or (path.parts and path.parts[0].endswith(":")):
            return "archive_unsafe:path"
        if (info.file_size >= limits["compression_ratio_min_entry_bytes"]
                and info.file_size > limits["max_compression_ratio"] * max(info.compress_size, 1)):
            return "archive_unsafe:compression_ratio"
    return None


def placeholder_text(data, spec):
    """빈 txt이거나 한 줄짜리 자리표시 문장("사업자등록증 사본(pdf로 제출)" 등)이면 True."""
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = data.decode(encoding).strip()
            break
        except UnicodeDecodeError:
            continue
    else:
        return False
    return not text or ("\n" not in text and len(text) <= spec["text_placeholder_max_chars"])


def processable_formats(contract):
    spec = contract["generic_zip"]
    enabled = {fmt for fmt, route in contract["routes"].items() if route["enabled"]}
    return enabled - set(spec["intentionally_excluded_formats"]) - set(spec["on_hold_formats"]) - {"ZIP"}


def classify(path, data, detected, spec, processable, attachment_exists):
    """(처리 상태, 사유). 계약 generic_zip.member_rules_in_order 순서 그대로다."""
    name = member_basename(path).lower()
    normalized = (path or "").replace("\\", "/")
    extension = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if name in spec["os_metadata_files"] or any(normalized.startswith(prefix) or f"/{prefix}" in normalized
                                                  for prefix in spec["os_metadata_path_prefixes"]):
        return "EXCLUDED", "os_metadata_file"
    if extension in spec["text_extensions"] and detected == "UNKNOWN" and placeholder_text(data, spec):
        return "EXCLUDED", "empty_or_placeholder_text"
    if not data:
        return "EXCLUDED", "empty_member"
    if detected == "ZIP" or (detected == "UNKNOWN" and extension in spec["archive_extensions"]):
        return "EXCLUDED", "nested_archive"
    if detected in spec["on_hold_formats"]:
        return "EXCLUDED", "hwpml_on_hold"
    if detected in spec["intentionally_excluded_formats"]:
        return "EXCLUDED", "intentionally_excluded_format"
    if detected not in processable:
        return "EXCLUDED", "unsupported_format"
    sha = hashlib.sha256(data).hexdigest()
    if attachment_exists(sha):
        return "DUPLICATE_SOURCE", "same_sha_as_attachment"
    return "STORED", None


def plan_archive(raw, archive_sha256, contract, attachment_exists):
    """압축 하나의 내부 파일 처리 계획. DB·S3에 쓰지 않는다. STORED 항목만 저장용 byte를 들고 있다."""
    spec, limits = contract["generic_zip"], contract["hwpx_container_limits"]
    max_bytes = contract["input"]["max_source_bytes"]
    processable = processable_formats(contract)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError, RuntimeError):
        return ArchivePlan(archive_sha256, "archive_unreadable")
    files = [info for info in infos if not info.is_dir()]
    decoded = [decode_name(info) for info in infos]
    failure = unsafe_reason(infos, [item[0] for item in decoded], limits)
    if failure:
        return ArchivePlan(archive_sha256, failure, (), len(infos) - len(files))
    members = []
    for index, (info, (path_raw, path, encoding)) in enumerate(zip(infos, decoded)):
        if info.is_dir():
            continue
        common = dict(member_key=member_key(archive_sha256, path_raw), member_index=index, path_raw=path_raw, path=path,
                      encoding=encoding, byte_size=info.file_size, unicode_extra_path=unicode_path_extra(info))
        if info.file_size > max_bytes:
            members.append(MemberPlan(**common, sha256=None, detected_format=None, status="FAILED", reason="member_too_large"))
            continue
        try:
            with archive.open(info) as handle:
                # 선언 크기 + 1 byte까지만 읽는다. 끝까지 읽어야 zipfile이 CRC를 검사한다.
                data = handle.read(info.file_size + 1)
        except (zipfile.BadZipFile, NotImplementedError, OSError, EOFError, zlib.error, RuntimeError, ValueError) as error:
            members.append(MemberPlan(**common, sha256=None, detected_format=None, status="FAILED",
                                      reason="member_read_failed:" + type(error).__name__))
            continue
        if len(data) != info.file_size:
            members.append(MemberPlan(**common, sha256=None, detected_format=None, status="FAILED", reason="member_size_mismatch"))
            continue
        detected = actual_format(data)
        status, reason = classify(path if path is not None else path_raw.decode("latin-1"), data, detected, spec,
                                  processable, attachment_exists)
        members.append(MemberPlan(**common, sha256=hashlib.sha256(data).hexdigest(), detected_format=detected,
                                  status=status, reason=reason, raw=data if status == "STORED" else None))
    return ArchivePlan(archive_sha256, None, tuple(members), len(infos) - len(files))


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def member_row(member, archive_sha256, run_id, storage=None):
    """document_archive_members 한 행. storage는 STORED 항목의 검증된 S3 위치(region, bucket, key, 확인 시각)다."""
    region, bucket, key, verified = storage or (None, None, None, None)
    return {"member_key": member.member_key, "archive_source_sha256": archive_sha256, "archive_depth": 1,
            "parent_member_provenance": None, "member_index": member.member_index, "member_path_raw": member.path_raw,
            "member_path": member.path, "member_path_encoding": member.encoding, "member_byte_size": member.byte_size,
            "member_sha256": member.sha256, "member_detected_format": member.detected_format,
            "processing_status": member.status, "status_reason": member.reason, "s3_region": region,
            "s3_bucket_name": bucket, "s3_object_key": key, "s3_verified_at": verified,
            "extraction_run_id": run_id, "recorded_at": utc_now()}


def optional_member_table(engine, metadata):
    """내부 파일 표. V10 적용 전에는 None이라 기존 파싱·인덱싱은 document_sources만으로 그대로 동작한다."""
    if not inspect(engine).has_table(MEMBER_TABLE):
        return None
    return Table(MEMBER_TABLE, metadata, autoload_with=engine)


class ArchiveMemberRepository:
    """압축 첨부 목록 읽기와 내부 파일 행 기록. 원본 byte는 받지 않는다."""

    # 같은 결정인지 비교할 때 실행마다 달라지는 값은 뺀다.
    VOLATILE = {"extraction_run_id", "recorded_at", "s3_verified_at"}

    def __init__(self, config):
        if (config.profile != "dev" or config.database not in ("biz_aid_dev", "biz_aid_test")
                or config.host not in ("localhost", "127.0.0.1", "mysql") or config.port != 3306):
            raise PipelineError("dev_database_boundary")
        self.engine = create_engine(URL.create("mysql+pymysql", username=config.user, password=config.password,
            host=config.host, port=config.port, database=config.database, query={"charset": "utf8mb4"}),
            hide_parameters=True, echo=False, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "read_timeout": 30, "write_timeout": 30})
        metadata = MetaData()
        try:
            self.sources = Table("document_sources", metadata, autoload_with=self.engine)
            self.members = optional_member_table(self.engine, metadata)
        except Exception:
            self.engine.dispose()
            raise PipelineError("document_schema_unavailable_run_flyway") from None

    def archives(self, pblanc_ids=None):
        """검증된 일반 ZIP 첨부 {SHA: {크기·S3 위치·로컬 이관 경로·공고 목록}}. 같은 SHA의 위치가 엇갈리면 실패한다."""
        columns = self.sources.c
        query = select(columns.content_sha256, columns.byte_size, columns.s3_region, columns.s3_bucket_name,
                       columns.s3_object_key, columns.storage_path, columns.pblanc_id).where(
            columns.download_status == "ACQUIRED", columns.detected_format == "ZIP",
            columns.s3_object_key.is_not(None), columns.s3_verified_at.is_not(None))
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        archives = {}
        for row in rows:
            identity = (row["byte_size"], row["s3_region"], row["s3_bucket_name"], row["s3_object_key"])
            entry = archives.setdefault(row["content_sha256"], {"identity": identity, "storage_path": row["storage_path"],
                                                                "programs": set()})
            if entry["identity"] != identity:
                raise PipelineError("document_source_metadata_conflict")
            entry["programs"].add(row["pblanc_id"])
        if pblanc_ids is not None:
            archives = {sha: entry for sha, entry in archives.items() if entry["programs"] & set(pblanc_ids)}
        return dict(sorted(archives.items()))

    def attachment_shas(self):
        """단독 첨부로 이미 확보된 원본 SHA 전체. 같은 SHA 내부 파일은 다시 처리하지 않고 연결만 남긴다."""
        with self.engine.connect() as connection:
            return set(connection.execute(select(self.sources.c.content_sha256).where(
                self.sources.c.download_status == "ACQUIRED", self.sources.c.content_sha256.is_not(None)).distinct()).scalars())

    def persist_archive(self, rows):
        """압축 하나의 모든 내부 파일 행을 한 transaction으로 기록한다. 같은 결정은 재사용하고 다른 결정으로 덮어쓰지 않는다."""
        if self.members is None:
            raise PipelineError("archive_member_schema_unavailable_apply_v10")
        actions = {"INSERTED": 0, "REUSED": 0}
        with self.engine.begin() as connection:
            for values in rows:
                existing = connection.execute(select(self.members).where(
                    self.members.c.member_key == values["member_key"]).with_for_update()).mappings().one_or_none()
                if existing is None:
                    # EXCEPTION: JSON column에 None을 넘기면 SQL NULL이 아니라 JSON null이 들어가 깊이 CHECK와 어긋난다.
                    connection.execute(self.members.insert().values(
                        **{name: value for name, value in values.items() if value is not None or name != "parent_member_provenance"}))
                    actions["INSERTED"] += 1
                    continue
                if any(existing[name] != value for name, value in values.items() if name not in self.VOLATILE):
                    # BOUNDARY: 기록된 처리 결정과 S3 위치는 규칙 변경 결정 없이 바꾸지 않는다.
                    raise PipelineError("archive_member_conflict")
                actions["REUSED"] += 1
        return actions

    def close(self):
        self.engine.dispose()


def read_archive(sha, entry, store=None, local=False):
    """압축 첨부 byte. 기본은 S3 원본(크기·SHA 재검증), local은 로컬 이관 원본(미리보기 전용, SHA 재검증)."""
    if local:
        raw = (ROOT / entry["storage_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha or len(raw) != entry["identity"][0]:
            raise PipelineError("local_archive_integrity_mismatch")
        return raw
    size, _, _, key = entry["identity"]
    return store.read_key(key, sha, size, max_bytes=size)


def summarize(plans, archives):
    """미리보기·실행 결과 집계(형식·처리 결정·사유·이름 해석·중복)."""
    members = [member for plan in plans for member in plan.members]
    count = lambda values: dict(sorted(_tally(values).items()))
    stored = {member.sha256 for member in members if member.status == "STORED"}
    duplicate_programs = {}
    for plan in plans:
        for member in plan.members:
            if member.status == "STORED":
                duplicate_programs.setdefault(member.sha256, set()).update(archives[plan.archive_sha256]["programs"])
    return {"archives": len(plans), "archives_failed": count(plan.failure_code for plan in plans if plan.failure_code),
            "directories_skipped": sum(plan.directories for plan in plans), "members": len(members),
            "by_status": count(member.status for member in members),
            "by_reason": count(f"{member.status}:{member.reason}" for member in members if member.reason),
            "by_format": count(member.detected_format or "-" for member in members),
            "by_format_and_status": count(f"{member.detected_format or '-'}:{member.status}" for member in members),
            "name_encoding": count(member.encoding for member in members),
            "stored_members": sum(member.status == "STORED" for member in members),
            "stored_unique_sha": len(stored),
            "stored_formats_unique_sha": count(next(m.detected_format for m in members if m.sha256 == sha) for sha in stored)}


def _tally(values):
    result = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def run_extraction(root, profile, run_id, pblanc_ids=None, archive_shas=None, dry_run=True, local=False, contract=None):
    """압축 펼치기 실행. dry_run은 DB·S3에 쓰지 않고 계획만 파일로 남긴다. 실제 실행은 STORED byte를 S3에 저장·검증한 뒤 행을 기록한다."""
    from biz_aid_pipeline.config.settings import DbConfig, S3Config
    from biz_aid_pipeline.parsing.models import parsing_contract
    from biz_aid_pipeline.storage import S3DocumentStore
    if profile != "dev":
        raise PipelineError("prod_archive_access_forbidden")
    contract = contract or parsing_contract()
    if not contract["routes"]["ZIP"].get("extraction_enabled"):
        raise PipelineError("archive_extraction_not_enabled")
    repository = ArchiveMemberRepository(DbConfig.load(Path(root), profile))
    store = None
    try:
        if not dry_run and repository.members is None:
            raise PipelineError("archive_member_schema_unavailable_apply_v10")
        archives = repository.archives(pblanc_ids)
        if archive_shas is not None:
            archives = {sha: entry for sha, entry in archives.items() if sha in archive_shas}
        attachments = repository.attachment_shas()
        if not local or not dry_run:
            s3 = S3Config.load(Path(root), profile)
            store = S3DocumentStore(s3.bucket, s3.region, s3.prefix)
        directory = Path(root) / RUNS / run_id
        directory.mkdir(parents=True, exist_ok=True)
        plans, started = [], time.time()
        with (directory / ("plan.jsonl" if dry_run else "results.jsonl")).open("a", encoding="utf-8") as output:
            for sha, entry in archives.items():
                # BOUNDARY: 실제 실행은 S3 원본만 읽는다. 로컬 이관 원본은 쓰기 없는 미리보기에서만 허용한다.
                raw = read_archive(sha, entry, store, local and dry_run)
                plan = plan_archive(raw, sha, contract, attachments.__contains__)
                plans.append(plan)
                action = None
                if not dry_run and plan.failure_code is None:
                    rows = []
                    for member in plan.members:
                        storage = None
                        if member.status == "STORED":
                            key = store.put_bytes(member.raw, member.sha256)
                            if not store.verify_key(key, member.sha256, member.byte_size):
                                raise PipelineError("archive_member_s3_verification_failed")
                            storage = (store.region, store.bucket, key, utc_now())
                        rows.append(member_row(member, sha, run_id, storage))
                    action = repository.persist_archive(rows)
                output.write(json.dumps({"archive_sha256": sha, "failure_code": plan.failure_code, "persist": action,
                                         "programs": sorted(entry["programs"]), "members": [
                    {"index": m.member_index, "path": m.path, "path_raw_hex": m.path_raw.hex() if m.path is None else None,
                     "encoding": m.encoding, "unicode_extra_path": m.unicode_extra_path, "byte_size": m.byte_size,
                     "sha256": m.sha256, "format": m.detected_format, "status": m.status, "reason": m.reason}
                    for m in plan.members]}, ensure_ascii=False) + "\n")
        summary = dict(summarize(plans, archives), run_id=run_id, dry_run=dry_run, read_from="local" if local and dry_run else "s3",
                       elapsed_seconds=round(time.time() - started, 1))
        (directory / ("plan-summary.json" if dry_run else "summary.json")).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return summary, plans
    finally:
        repository.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only generic ZIP member extraction (depth 1)")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--programs-file", help="대상 공고 ID 목록(한 줄에 하나). 이 공고에 붙은 일반 ZIP만 펼친다")
    parser.add_argument("--archives-file", help="대상 압축 SHA 목록(한 줄에 하나)")
    parser.add_argument("--execute", action="store_true", help="S3 저장과 DB 기록을 한다. 없으면 쓰기 없는 미리보기")
    parser.add_argument("--read-local", action="store_true", help="미리보기에서 로컬 이관 원본을 읽는다(SHA 재검증)")
    args = parser.parse_args(argv)
    if args.execute and args.read_local:
        parser.error("--read-local is preview-only")
    read = lambda path: {line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}
    summary, _ = run_extraction(ROOT, args.profile, args.run_id, read(args.programs_file) if args.programs_file else None,
                                read(args.archives_file) if args.archives_file else None, not args.execute, args.read_local)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
