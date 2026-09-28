import hashlib
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote

from botocore.exceptions import ClientError

from biz_aid_pipeline.bizinfo.raw_snapshot import safe_path, valid_run_id, write_json_new
from biz_aid_pipeline.config.settings import DbConfig, PipelineError, S3Config, profile_values, read_json
from biz_aid_pipeline.documents.client import transfer
from biz_aid_pipeline.documents.formats import actual_format
from biz_aid_pipeline.documents.models import candidates
from biz_aid_pipeline.documents.repository import DocumentRepository, utc_datetime
from biz_aid_pipeline.storage import S3DocumentStore

ARTIFACT_ROOT = "harness/workspace/artifacts/codex/phase2-document-acquisition"


def now():
    return datetime.now(timezone.utc).isoformat()


def contract(root):
    value = read_json(Path(root) / "contracts/schemas/document-acquisition.contract.json")
    if (value["profile"] != "dev" or value["automatic_retries"] != 0
            or value["max_redirects"] != 3 or value["max_file_bytes"] != 104857600
            or value["timeout_seconds"] != 15 or value["pause_seconds"] != 0.25):
        raise PipelineError("unsafe_document_acquisition_policy")
    return value


def build_plan(repository):
    rows, relations = repository.source_rows(), []
    snapshot_rows = []
    for row in rows:
        extracted = candidates(row["pblanc_id"], row["primary_url_raw"], row["primary_filename_raw"],
                               row["attachment_urls_raw"], row["attachment_names_raw"])
        relations.extend(extracted)
        snapshot_rows.append({"pblanc_id": row["pblanc_id"], "source_fingerprint": row["source_fingerprint"],
                              "primary_url_raw": row["primary_url_raw"], "primary_filename_raw": row["primary_filename_raw"],
                              "attachment_urls_raw": row["attachment_urls_raw"], "attachment_names_raw": row["attachment_names_raw"]})
    raw = json.dumps(snapshot_rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    return {"source_snapshot_sha256": hashlib.sha256(raw).hexdigest(), "support_program_count": len(rows),
            "candidates": [candidate.value() for candidate in relations]}


def _s3_store(root):
    config = S3Config.load(Path(root), "dev")
    return S3DocumentStore(
        bucket=config.bucket,
        region=config.region,
        prefix=config.prefix,
    )


def store_acquired_body(raw, store):
    digest = hashlib.sha256(raw).hexdigest()

    with TemporaryDirectory(prefix="biz-aid-document-") as directory:
        path = Path(directory) / f"{digest}.bin"
        path.write_bytes(raw)

        try:
            object_key = store.put(
                file_path=path,
                sha256_hex=digest,
                byte_size=len(raw),
            )
            if not store.verify(
                    sha256_hex=digest,
                    byte_size=len(raw),
            ):
                raise PipelineError("s3_document_integrity_failure")
        except (ClientError, RuntimeError):
            raise PipelineError("s3_document_storage_failure") from None

    return {
        "content_sha256": digest,
        "storage_path": object_key,
        "s3_region": store.region,
        "s3_bucket_name": store.bucket,
        "s3_object_key": object_key,
        "s3_verified_at": utc_datetime(),
    }


def verify_stored(root, row, store=None, check_format=True):
    if row["download_status"] != "ACQUIRED":
        return True

    if row["byte_size"] is None or not row["content_sha256"]:
        return False

    s3_fields = (
        row.get("s3_region"),
        row.get("s3_bucket_name"),
        row.get("s3_object_key"),
        row.get("s3_verified_at"),
    )

    if any(value is not None for value in s3_fields):
        if not all(value is not None for value in s3_fields):
            return False

        store = store or _s3_store(root)

        if (
                row["s3_region"] != store.region
                or row["s3_bucket_name"] != store.bucket
                or row["s3_object_key"] != store.object_key(row["content_sha256"])
        ):
            return False

        try:
            if not store.verify(
                    sha256_hex=row["content_sha256"],
                    byte_size=row["byte_size"],
            ):
                return False

            if not check_format:
                return True

            raw = store.read(
                sha256_hex=row["content_sha256"],
                byte_size=row["byte_size"],
            )
        except (ClientError, RuntimeError, OSError, ValueError):
            return False

        return actual_format(raw) == row["detected_format"]

    # S3 migration 전의 legacy row만 로컬 저장소로 검증한다.
    if not row["storage_path"]:
        return False

    path = safe_path(root, row["storage_path"])
    if not path.is_file() or path.is_symlink():
        return False

    raw = path.read_bytes()
    return (
            len(raw) == row["byte_size"]
            and hashlib.sha256(raw).hexdigest() == row["content_sha256"]
            and actual_format(raw) == row["detected_format"]
    )


def relation_value(candidate, run_id, result, raw, path, digest, action, requests,
                   acquired_at=None, s3_metadata=None):
    detected = result["detected_format"]
    acquired = result["failure_category"] is None
    s3_metadata = s3_metadata or {}

    return {**candidate, "download_status": "ACQUIRED" if acquired else "FAILED",
            "failure_category": result["failure_category"], "http_status": result["http_status"],
            "redirect_count": result["redirect_count"], "content_type": result["content_type"],
            "detected_format": detected, "format_mismatch": (candidate["declared_extension"] not in ("UNKNOWN", "OTHER")
                                                             and candidate["declared_extension"] != detected), "invalid_response": result["invalid_response"],
            "byte_size": len(raw) if raw is not None else None, "content_sha256": digest,
            # V3의 ACQUIRED storage_path NOT NULL 경계를 유지하기 위해 S3 object key를 compatibility locator로 저장한다.
            "storage_path": path,
            "s3_region": s3_metadata.get("s3_region"),
            "s3_bucket_name": s3_metadata.get("s3_bucket_name"),
            "s3_object_key": s3_metadata.get("s3_object_key"),
            "s3_verified_at": s3_metadata.get("s3_verified_at"),
            "last_run_id": run_id, "last_run_action": action,
            "last_http_requests": requests, "last_seen_at": utc_datetime(),
            "last_attempted_at": utc_datetime() if requests else None,
            "acquired_at": acquired_at or (utc_datetime() if acquired else None)}


def checkpoint(root, run_id, started_at, total, processed, failures, sequence, final=False):
    value = {"run_id": run_id, "task": "Phase 2 Full Document Acquisition", "started_at": started_at,
             "updated_at": now(), "total_target": total, "completed_count": processed - len(failures),
             "failed_count": len(failures), "failed_items": failures, "current_stage": "DOCUMENT_ACQUISITION",
             "last_processed_item": processed - 1 if processed else None,
             "next_action": None if final else "저장 byte와 DB metadata를 확인한 뒤 같은 run-id를 resume한다",
             "resume_command": None if final else f"python3 -B scripts/run_document_acquisition.py collect --profile dev --run-id {run_id} --resume",
             "notes": ["집계 단위는 source provenance를 보존한 candidate relation이다.",
                       "실패 relation은 같은 run에서 자동 재시도하지 않는다. 새 run은 검증된 성공을 재사용하고 실패 URL만 다시 시도한다.",
                       "Checkpoint 완료는 품질 PASS나 문서 의미 확정을 뜻하지 않는다."],
             "status": "completed" if final else "running"}
    path = safe_path(root, f"harness/workspace/checkpoints/{run_id}-documents-{sequence:04d}.md")
    raw = "# Document Acquisition Checkpoint\n\n```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(raw)
    return str(path.relative_to(root))


def quality_report(root, repository, run_id, plan, runtime, store=None):
    keys = [candidate["candidate_key"] for candidate in plan["candidates"]]
    rows = repository.rows_for_keys(keys)
    by_key = {row["candidate_key"]: row for row in rows}
    failures, integrity_failures = [], []
    verification_cache = {}
    for candidate in plan["candidates"]:
        row = by_key.get(candidate["candidate_key"])
        if row is None or any(row[name] != candidate[name] for name in candidate):
            integrity_failures.append(candidate["candidate_key"])
            continue

        if row["download_status"] == "ACQUIRED":
            cache_key = (row["content_sha256"], row["byte_size"], row["detected_format"])
            if cache_key not in verification_cache:
                verification_cache[cache_key] = verify_stored(root, row, store)
            stored_ok = verification_cache[cache_key]
        else:
            stored_ok = verify_stored(root, row, store)

        if not stored_ok:
            integrity_failures.append(candidate["candidate_key"])
        if row["download_status"] != "ACQUIRED":
            failures.append({"candidate_key": row["candidate_key"], "pblanc_id": row["pblanc_id"],
                             "failure_category": row["failure_category"]})
    acquired = [row for row in rows if row["download_status"] == "ACQUIRED"]
    hashes = Counter(row["content_sha256"] for row in acquired)
    urls = Counter(candidate["source_url"] for candidate in plan["candidates"])
    formats = Counter(row["detected_format"] for row in acquired)
    current = build_plan(repository)
    programs = {candidate["pblanc_id"] for candidate in plan["candidates"]}
    status = "PASS" if (not failures and not integrity_failures and len(rows) == len(keys)
                        and current["source_snapshot_sha256"] == plan["source_snapshot_sha256"]) else "FAIL"
    return {"run_id": run_id, "phase": "phase2-document-acquisition", "profile": "dev", "status": status,
            "source_snapshot_sha256": plan["source_snapshot_sha256"],
            "source_snapshot_unchanged": current["source_snapshot_sha256"] == plan["source_snapshot_sha256"],
            "support_program_count": plan["support_program_count"], "programs_with_document_candidate": len(programs),
            "programs_without_document_candidate": plan["support_program_count"] - len(programs),
            "total_candidate_relations": len(keys), "unique_source_url_count": len(urls),
            "duplicate_url_count": sum(count - 1 for count in urls.values()),
            "attempted_downloads": sum(row["last_http_requests"] > 0 and row["last_run_id"] == run_id for row in rows),
            "http_request_count": sum(row["last_http_requests"] for row in rows if row["last_run_id"] == run_id),
            "reused_relation_count": sum(row["last_run_id"] == run_id and row["last_run_action"].startswith("REUSED") for row in rows),
            "success_count": len(acquired), "failed_count": len(failures), "format_counts": dict(formats),
            "pdf_count": formats["PDF"], "hwp_count": formats["HWP"], "hwpx_count": formats["HWPX"],
            "other_unknown_count": formats["OTHER"] + formats["UNKNOWN"] + formats["ZIP"] + formats["XLSX"],
            "duplicate_content_sha_count": sum(count - 1 for count in hashes.values()),
            "invalid_response_count": sum(bool(row["invalid_response"]) for row in rows),
            "format_mismatch_count": sum(bool(row["format_mismatch"]) for row in rows),
            "total_downloaded_bytes": sum(next(row["byte_size"] for row in acquired if row["content_sha256"] == digest) for digest in hashes),
            "persisted_metadata_count": len(rows), "integrity_failure_count": len(integrity_failures),
            "failure_candidates": failures, "failure_category_counts": dict(Counter(item["failure_category"] for item in failures)),
            "http_status_distribution": dict(Counter(str(row["http_status"]) for row in rows if row["http_status"] is not None)),
            "content_type_distribution": dict(Counter(row["content_type"] or "ABSENT" for row in rows)),
            "started_at": runtime["started_at"], "finished_at": now(), "elapsed_seconds": runtime["elapsed_seconds"],
            "automatic_retries": 0, "parser_scope": False,
            "gate_rule": contract(root)["gate_pass"]}


def validate_report(root, report):
    spec = contract(root)
    if any(name not in report for name in spec["required_report_fields"]):
        raise PipelineError("document_report_missing_field")
    integers = ("support_program_count", "programs_with_document_candidate", "programs_without_document_candidate",
                "total_candidate_relations", "unique_source_url_count", "duplicate_url_count", "attempted_downloads",
                "http_request_count", "reused_relation_count", "success_count", "failed_count", "pdf_count", "hwp_count",
                "hwpx_count", "other_unknown_count", "duplicate_content_sha_count", "invalid_response_count",
                "format_mismatch_count", "total_downloaded_bytes", "persisted_metadata_count", "integrity_failure_count")
    if (report["phase"] != "phase2-document-acquisition" or report["profile"] != "dev"
            or report["status"] not in ("PASS", "FAIL") or type(report["source_snapshot_unchanged"]) is not bool
            or report["automatic_retries"] != 0 or report["parser_scope"] is not False
            or any(type(report[name]) is not int or report[name] < 0 for name in integers)
            or not isinstance(report["failure_candidates"], list)):
        raise PipelineError("document_report_invalid")
    if (report["programs_with_document_candidate"] + report["programs_without_document_candidate"]
            != report["support_program_count"] or report["success_count"] + report["failed_count"]
            != report["persisted_metadata_count"] or report["persisted_metadata_count"] > report["total_candidate_relations"]
            or sum(report["format_counts"].values()) != report["success_count"]):
        raise PipelineError("document_report_count_invalid")
    expected = (report["support_program_count"] > 0 and report["total_candidate_relations"] > 0
                and report["source_snapshot_unchanged"] and report["failed_count"] == 0
                and report["integrity_failure_count"] == 0
                and report["success_count"] == report["total_candidate_relations"]
                and report["persisted_metadata_count"] == report["total_candidate_relations"])
    if (report["status"] == "PASS") != expected:
        raise PipelineError("document_report_false_status")
    return report


def verify_run(root, run_id, repository_factory=DocumentRepository, store=None):
    root = Path(root).resolve()
    valid_run_id(run_id)
    store = store or _s3_store(root)
    repository = repository_factory(DbConfig.load(root, "dev"))
    try:
        manifest = read_json(safe_path(root, f"{ARTIFACT_ROOT}/{run_id}/manifest.json"))
        stored = read_json(safe_path(root, f"{ARTIFACT_ROOT}/{run_id}/result.json"))
        database = repository.run(run_id)
        if (manifest["run_id"] != run_id or manifest["profile"] != "dev" or database["status"] != "COMPLETED"
                or database["report_json"] != stored or database["gate_status"] != stored["status"]):
            raise PipelineError("document_run_evidence_mismatch")
        fresh = quality_report(root, repository, run_id, manifest["plan"],
                               {"started_at": stored["started_at"], "elapsed_seconds": stored["elapsed_seconds"]}, store)
        for name, value in stored.items():
            if name not in ("finished_at",) and fresh[name] != value:
                raise PipelineError("document_run_quality_changed")
        validate_report(root, stored)
        return stored
    finally:
        repository.close()


def run(root, profile, run_id, *, resume=False, fetch=None, pause=time.sleep, stop_after=None,
        repository_factory=DocumentRepository, progress=None, store=None):
    root = Path(root).resolve()
    if profile != "dev":
        raise PipelineError("prod_document_acquisition_forbidden")
    valid_run_id(run_id)
    spec = contract(root)
    store = store or _s3_store(root)
    configured = profile_values(root, "dev", {"BIZINFO_SERVICE_KEY"})
    api_key = unquote(configured.get("BIZINFO_SERVICE_KEY", "").strip())
    if any(ord(character) < 32 for character in api_key):
        raise PipelineError("invalid_credential_format")
    repository = repository_factory(DbConfig.load(root, "dev"))
    artifact = safe_path(root, f"{ARTIFACT_ROOT}/{run_id}")
    started = time.monotonic()
    try:
        with repository.acquisition_lock():
            current_plan = build_plan(repository)
            manifest_path = artifact / "manifest.json"
            if resume:
                manifest = read_json(manifest_path)
                if manifest["run_id"] != run_id or manifest["profile"] != "dev" or manifest["plan"] != current_plan:
                    raise PipelineError("document_resume_source_mismatch")
                repository.resume_run(run_id, current_plan["source_snapshot_sha256"])
            else:
                if artifact.exists():
                    raise PipelineError("document_artifact_run_exists")
                artifact.mkdir(parents=True)
                manifest = {"version": 1, "run_id": run_id, "profile": "dev", "evidence_kind": "SYNTHETIC_MOCK" if fetch else "LIVE_HTTP",
                            "started_at": now(), "safety": spec, "plan": current_plan}
                write_json_new(root, manifest_path, manifest, (api_key,))
                repository.create_run(run_id, current_plan["source_snapshot_sha256"])
            plan = manifest["plan"]
            groups = defaultdict(list)
            for candidate in plan["candidates"]:
                groups[candidate["source_url"]].append(candidate)
            existing = {row["candidate_key"]: row for row in repository.rows_for_keys(
                [candidate["candidate_key"] for candidate in plan["candidates"]]) if row["last_run_id"] == run_id}
            processed = len(existing)
            sequence = len(list((root / "harness/workspace/checkpoints").glob(f"{run_id}-documents-*.md")))
            failures = [{"item_id": row["candidate_key"], "stage": "document-download",
                         "reason": row["failure_category"], "attempts": row["last_http_requests"], "evidence": None}
                        for row in existing.values() if row["download_status"] != "ACQUIRED"]
            checkpoint(root, run_id, manifest["started_at"], len(plan["candidates"]), processed, failures, sequence)
            sequence += 1
            for url, group in groups.items():
                if all(candidate["candidate_key"] in existing for candidate in group):
                    continue
                if stop_after is not None and processed >= stop_after:
                    break
                cached = repository.acquired_for_url(group[0]["source_url_sha256"], url)
                if cached is not None:
                    # 캐시 재사용은 HTTP 요청을 줄이지만 저장 byte 검증까지 생략할 근거는 아니다.
                    # 실제 S3 body의 SHA와 format을 확인한 relation만 재사용한다.
                    if not verify_stored(root, cached, store, check_format=True):
                        raise PipelineError("cached_document_integrity_failure")
                    result = {"http_status": cached["http_status"], "http_requests": 0,
                              "redirect_count": cached["redirect_count"], "content_type": cached["content_type"],
                              "detected_format": cached["detected_format"], "invalid_response": False,
                              "failure_category": None, "complete_body": True}
                    raw, path, digest, acquired_at = (
                        None,
                        cached.get("s3_object_key")
                        or cached["storage_path"],
                        cached["content_sha256"],
                        cached["acquired_at"],
                    )
                    size, action = cached["byte_size"], "REUSED_EXISTING"
                    s3_metadata = {
                        "s3_region": cached.get("s3_region"),
                        "s3_bucket_name": cached.get("s3_bucket_name"),
                        "s3_object_key": cached.get("s3_object_key"),
                        "s3_verified_at": cached.get("s3_verified_at"),
                    }
                else:
                    result, raw = transfer(url, api_key, spec, fetch)
                    acquired = result["failure_category"] is None
                    path = digest = None
                    s3_metadata = {}

                    if raw is not None:
                        digest = hashlib.sha256(raw).hexdigest()

                    if raw is not None and acquired:
                        stored = store_acquired_body(raw, store)
                        digest = stored["content_sha256"]
                        path = stored["storage_path"]
                        s3_metadata = stored

                    size = len(raw) if raw is not None else None
                    acquired_at = None
                    action = "DOWNLOADED" if acquired else "FAILED"

                values = []
                for index, candidate in enumerate(group):
                    value = relation_value(candidate, run_id, result, raw, path, digest,
                                           action if index == 0 else "REUSED_URL", result["http_requests"] if index == 0 else 0,
                                           acquired_at, s3_metadata)
                    if raw is None and cached is not None:
                        value["byte_size"] = size
                    values.append(value)
                repository.persist_group(values)
                processed += len(group)
                if result["failure_category"]:
                    failures.extend({"item_id": candidate["candidate_key"], "stage": "document-download",
                                     "reason": result["failure_category"], "attempts": result["http_requests"] if index == 0 else 0,
                                     "evidence": path} for index, candidate in enumerate(group))
                if progress:
                    progress(processed, len(plan["candidates"]), result["failure_category"] or "ACQUIRED")
                if processed % 50 < len(group) or result["failure_category"]:
                    checkpoint(root, run_id, manifest["started_at"], len(plan["candidates"]), processed, failures, sequence)
                    sequence += 1
                if cached is None and processed < len(plan["candidates"]):
                    pause(spec["pause_seconds"])
            if processed < len(plan["candidates"]):
                return {"run_id": run_id, "status": "PARTIAL", "processed": processed,
                        "total_candidate_relations": len(plan["candidates"])}
            runtime = {"started_at": manifest["started_at"], "elapsed_seconds": round(time.monotonic() - started, 6)}
            report = quality_report(root, repository, run_id, plan, runtime, store)
            validate_report(root, report)
            repository.finish_run(run_id, report)
            checkpoint(root, run_id, manifest["started_at"], len(plan["candidates"]), processed, failures, sequence, final=True)
            write_json_new(root, artifact / "result.json", report, (api_key, DbConfig.load(root, "dev").password))
            return report
    finally:
        repository.close()
