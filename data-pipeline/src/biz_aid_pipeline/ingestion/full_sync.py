import math
import time
from pathlib import Path

from biz_aid_pipeline.bizinfo.client import BizinfoClient
from biz_aid_pipeline.bizinfo.raw_snapshot import FullSnapshots, safe_path, valid_run_id, verify_full_snapshot, write_json_new
from biz_aid_pipeline.config.settings import ApiConfig, DbConfig, PipelineError, credential_echo, read_json
from biz_aid_pipeline.ingestion.service import ingest, prepare_ingestion
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository
from biz_aid_pipeline.quality.structured_data_gate import now, quality_report, reconciliation_reasons, validate_report

ARTIFACT_ROOT = "harness/workspace/artifacts/codex/phase1b-full-sync"


def full_contract(root):
    spec = read_json(root / "contracts/schemas/full-structured-sync.contract.json")
    if (spec["profile"] != "dev" or spec["soft_delete_mode"] != "DRY_RUN"
            or spec["rows_per_page"] != 20 or type(spec["max_pages"]) is not int or not 1 <= spec["max_pages"] <= 1000
            or type(spec["transaction_seconds"]) is not int or not 1 <= spec["transaction_seconds"] <= 60):
        raise PipelineError("unsafe_full_sync_policy")
    return spec


def preflight(batch, identifier):
    report = quality_report(batch, identifier)
    report["status"] = "PASS"
    reasons = reconciliation_reasons(batch, report)
    if reasons:
        report.update(status="FAIL", failed=max(1, len(report["failed_pages"]) + report["duplicate_count"] + report["invalid_pblanc_id_count"]),
                      reconciliation_skipped_reason=reasons, finished_at=now())
        return report
    report, records = prepare_ingestion(batch, identifier)
    report["finished_at"] = now()
    return report


def add_full_metrics(report, batch, acquisition):
    rows = batch.pages[0].requested_rows if batch.pages else None
    total = report["expected_total_count"]
    report.update(phase="phase1b-full-sync", acquisition_status=acquisition["status"],
        raw_snapshot_validation="PASS", raw_item_count=report["input_count"],
        requested_page_count=len(batch.pages), successful_page_count=len(report["successful_pages"]),
        failed_page_count=len(report["failed_pages"]), planned_page_count=(max(1, (total + rows - 1) // rows) if total is not None else None),
        soft_delete_mode="DRY_RUN", transaction_strategy="DB_ONLY_ATOMIC_BOUNDED",
        soft_delete_candidate_count=report.get("soft_delete_candidate_count"),
        soft_delete_candidate_pblanc_ids=report.get("soft_delete_candidate_pblanc_ids", []),
        reconciliation_dry_run=report.get("reconciliation_dry_run", False),
        mysql_final_row_count=report.get("mysql_final_row_count"))
    return report


def validate_full_report(report, root):
    validate_report(report, root)
    spec = full_contract(root)
    for name in spec["required_fields"]:
        if name not in report:
            raise PipelineError("full_report_missing_field")
    if report["sync_scope"] != "FULL" or report["profile"] != "dev" or report["soft_delete_mode"] != "DRY_RUN" or report["soft_deleted"] or report["reconciliation_executed"]:
        raise PipelineError("full_live_delete_forbidden")
    for name in ("soft_delete_candidate_count", "mysql_final_row_count", "planned_page_count"):
        if report[name] is not None and (type(report[name]) is not int or report[name] < 0):
            raise PipelineError("full_report_count_invalid")
    for name in ("raw_item_count", "requested_page_count", "successful_page_count", "failed_page_count"):
        if type(report[name]) is not int or report[name] < 0:
            raise PipelineError("full_report_count_invalid")
    if (type(report["reconciliation_dry_run"]) is not bool
            or report["transaction_seconds_limit"] != spec["transaction_seconds"]
            or type(report["db_phase_elapsed_seconds"]) not in (int, float)
            or not math.isfinite(report["db_phase_elapsed_seconds"]) or report["db_phase_elapsed_seconds"] < 0):
        raise PipelineError("full_report_policy_invalid")
    if (report["raw_item_count"] != report["input_count"]
            or report["successful_page_count"] != len(report["successful_pages"])
            or report["failed_page_count"] != len(report["failed_pages"])
            or report["requested_page_count"] != report["successful_page_count"] + report["failed_page_count"]
            or not isinstance(report["soft_delete_candidate_pblanc_ids"], list)
            or len(report["soft_delete_candidate_pblanc_ids"]) != len(set(report["soft_delete_candidate_pblanc_ids"]))):
        raise PipelineError("full_report_count_invalid")
    if report["status"] == "PASS" and (report["acquisition_status"] != "PASS" or not report["reconciliation_dry_run"]
            or report["raw_snapshot_validation"] != "PASS" or report["requested_page_count"] != report["planned_page_count"]
            or report["soft_delete_candidate_count"] != len(report["soft_delete_candidate_pblanc_ids"])
            or report["raw_item_count"] != report["unique_pblanc_id_count"] or report["raw_item_count"] != report["expected_total_count"]
            or report["failed_page_count"] or report["invalid_pblanc_id_count"] or not report["pagination_terminated"]
            or len(set(report["observed_total_counts"])) != 1 or report["mysql_final_row_count"] is None
            or report["mysql_final_row_count"] < report["unique_pblanc_id_count"]
            or report["reconciliation_skipped_reason"] != ["dry_run_only"]):
        raise PipelineError("full_report_false_pass")
    return report


def run_full_sync(root, profile, identifier, *, transport=None, repository_factory=MysqlRepository, progress=None):
    root = Path(root).resolve()
    if profile != "dev":
        raise PipelineError("prod_full_sync_forbidden")
    valid_run_id(identifier)
    spec = full_contract(root)
    api = ApiConfig.load(root, "dev")
    if not api.key:
        raise PipelineError("dev_api_credential_required")
    if credential_echo(identifier.encode(), api.key):
        raise PipelineError("credential_reflection_refused")
    artifact = safe_path(root, f"{ARTIFACT_ROOT}/{identifier}")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.mkdir(exist_ok=False)
    snapshots = FullSnapshots(root, identifier, api.key, "LIVE_API_FULL" if transport is None else "SYNTHETIC_MOCK")
    client = BizinfoClient(api, root, transport, snapshots.preserve)
    def completed(page):
        snapshots.page_completed(page)
        if progress:
            progress(page.number, page.outcome, len(page.items), page.total_count)
    collected = client.scan_full(spec["rows_per_page"], spec["max_pages"], completed)
    provenance = snapshots.finish(collected)
    write_json_new(root, artifact / "acquisition.json", provenance, (api.key,))
    snapshots.checkpoint("SNAPSHOT_REVIEW", max(1, (collected.pages[0].total_count + spec["rows_per_page"] - 1) // spec["rows_per_page"]) if collected.pages[0].total_count is not None else 1,
                         sum(page.outcome == "SUCCESS" for page in collected.pages), sum(page.outcome != "SUCCESS" for page in collected.pages),
                         "로컬 snapshot을 검증한다. 중단된 실행의 DB 적재 재개는 자동 지원하지 않는다",
                         f"python3 -B scripts/run_full_sync.py verify --run-id {identifier}")
    batch = verify_full_snapshot(root, identifier, provenance, api.key)
    acquisition = preflight(batch, identifier)
    repository = None
    report = acquisition
    started = time.monotonic()
    try:
        if acquisition["status"] != "PASS":
            report = acquisition
        else:
            # 전체 원문·ID·완전성·정규화 검증 뒤에만 DB에 진입한다. API 대기는 transaction 시간을 늘리지 않는다.
            db = DbConfig.load(root, "dev")
            repository = repository_factory(db)
            report = ingest(repository, batch, identifier, reconciliation_mode="DRY_RUN", transaction_seconds=spec["transaction_seconds"])
            if report["status"] == "PASS":
                with repository.engine.connect() as connection:
                    records = prepare_ingestion(batch, identifier)[1]
                    for offset in range(0, len(records), 100):
                        repository.verify(connection, records[offset:offset + 100])
                    if repository.row_count(connection) != report["mysql_final_row_count"]:
                        raise PipelineError("post_commit_row_count_changed")
    except Exception:
        # commit 뒤 읽기 실패를 rollback으로 기록하지 않는다. 확정 count를 보존하고 Gate 실패를 명시한다.
        report.update(status="FAIL", failed=max(1, report["failed"]))
        if report is acquisition:
            report["persistence_fatal_errors"] = 1
        report["error_codes"].append("database_or_post_commit_verification_failed")
        report["reconciliation_skipped_reason"] = reconciliation_reasons(batch, report)
    finally:
        if repository:
            repository.close()
    report = add_full_metrics(report, batch, acquisition)
    report["db_phase_elapsed_seconds"] = round(time.monotonic() - started, 6)
    report["transaction_seconds_limit"] = spec["transaction_seconds"]
    validate_full_report(report, root)
    secrets = (api.key, DbConfig.load(root, "dev").password) if repository is not None else (api.key,)
    write_json_new(root, artifact / "result.json", report, secrets)
    return report
