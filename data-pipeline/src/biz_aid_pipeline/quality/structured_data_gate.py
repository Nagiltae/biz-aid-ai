from collections import Counter
from datetime import datetime, timezone

from biz_aid_pipeline.bizinfo.models import SyncScope
from biz_aid_pipeline.config.settings import ROOT, PipelineError, read_json

ERROR_OUTCOMES = ("TRANSPORT_ERROR", "API_ERROR", "CONTRACT_ERROR")


def now():
    return datetime.now(timezone.utc).isoformat()


def page_valid(page):
    return (type(page.number) is int and page.number > 0 and type(page.requested_rows) is int
            and page.requested_rows > 0 and len(page.items) <= page.requested_rows and page.echo_matches
            and page.http_status == 200 and page.result_code == "00" and isinstance(page.result_message, str)
            and bool(page.result_message.strip()) and type(page.total_count) is int and page.total_count >= 0)


def quality_report(batch, run_id):
    identifiers = [item.get("pblancId") for item in batch.items]
    valid = [i for i in identifiers if isinstance(i, str) and i.strip()]
    unique = len(set(valid))
    outcomes = Counter(p.outcome for p in batch.pages)
    total_counts = [p.total_count for p in batch.pages if p.outcome == "SUCCESS"]
    return {"run_id": run_id, "sync_scope": batch.scope.value, "profile": "dev", "source_sample": batch.sample,
            "source_evidence": batch.provenance, "input_count": len(identifiers), "unique_pblanc_id_count": unique,
            "expected_total_count": total_counts[0] if total_counts else None, "observed_count": len(identifiers),
            "inserted": 0, "updated": 0, "noop": 0, "reactivated": 0, "soft_deleted": 0, "failed": 0,
            "duplicate_count": len(valid) - unique, "required_field_failures": 0,
            "date_parse_success": 0, "date_free_text": 0, "date_unavailable": 0, "date_invalid_range": 0,
            "invalid_url_count": 0, "source_timestamp_unparsed": 0,
            "transport_errors": outcomes["TRANSPORT_ERROR"], "api_errors": outcomes["API_ERROR"],
            "contract_errors": outcomes["CONTRACT_ERROR"] + sum(p.outcome == "SUCCESS" and not page_valid(p) for p in batch.pages),
            "normalization_fatal_errors": 0, "persistence_fatal_errors": 0,
            "pagination_terminated": batch.pagination_terminated, "observed_total_counts": total_counts,
            "successful_pages": [p.number for p in batch.pages if p.outcome == "SUCCESS"],
            "failed_pages": [p.number for p in batch.pages if p.outcome != "SUCCESS"],
            "reconciliation_attempted": False, "reconciliation_executed": False,
            "reconciliation_skipped_reason": [], "started_at": now(), "finished_at": None, "status": "FAIL",
            "error_codes": []}


def reconciliation_reasons(batch, report):
    reasons = []
    if batch.scope != SyncScope.FULL:
        reasons.append("scope_is_not_FULL")
    if report["status"] != "PASS":
        reasons.append("run_not_SUCCESS")
    if not batch.pages or report["failed_pages"] or any(p.outcome != "SUCCESS" for p in batch.pages):
        reasons.append("pagination_requests_not_all_successful")
    for key in ("transport_errors", "api_errors", "contract_errors", "normalization_fatal_errors", "persistence_fatal_errors", "duplicate_count"):
        if report[key]:
            reasons.append(key)
    if not batch.pagination_terminated:
        reasons.append("pagination_not_normally_terminated")
    counts = report["observed_total_counts"]
    if (not counts or any(type(c) is not int or c < 0 for c in counts) or len(set(counts)) != 1):
        reasons.append("totalCount_not_consistent")
    if report["expected_total_count"] != report["unique_pblanc_id_count"]:
        reasons.append("unique_count_totalCount_mismatch")
    if [p.number for p in batch.pages] != list(range(1, len(batch.pages) + 1)):
        reasons.append("page_sequence_incomplete")
    if any(p.outcome == "SUCCESS" and not page_valid(p) for p in batch.pages):
        reasons.append("page_contract_invalid")
    # 빈 source universe의 공식 동작은 미확정이므로 빈 응답만으로 전체 행을 삭제하지 않는다.
    if report["unique_pblanc_id_count"] == 0:
        reasons.append("empty_universe_unconfirmed")
    return reasons


def render_report(report):
    import json
    return ("# Phase 1A Structured Data Quality Report\n\n"
            "Source presence는 접수 상태와 별개다. SAMPLE의 미관측은 soft-delete 근거가 아니다.\n\n"
            "```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n")


def validate_report(report, root=ROOT):
    spec = read_json(root / "contracts/schemas/structured-data-quality.contract.json")
    if (report["profile"] not in spec["profiles"] or report["sync_scope"] not in spec["sync_scopes"]
            or report["status"] not in spec["statuses"] or not isinstance(report["source_evidence"], dict)):
        raise PipelineError("structured_report_invalid")
    for category, expected in (("integer_fields", int), ("boolean_fields", bool), ("list_fields", list), ("string_fields", str)):
        for name in spec[category]:
            if type(report[name]) is not expected or (expected is int and report[name] < 0):
                raise PipelineError("structured_report_field_invalid")
    if report["expected_total_count"] is not None and (type(report["expected_total_count"]) is not int or report["expected_total_count"] < 0):
        raise PipelineError("structured_report_total_invalid")
    if report["observed_count"] != report["input_count"] or report["unique_pblanc_id_count"] > report["input_count"]:
        raise PipelineError("structured_report_count_invalid")
    if report["status"] == "PASS" and (report["inserted"] + report["updated"] + report["noop"] != report["input_count"]
            or report["failed"] or report["duplicate_count"] or report["required_field_failures"]
            or any(report[name] for name in ("transport_errors", "api_errors", "contract_errors", "normalization_fatal_errors", "persistence_fatal_errors"))):
        raise PipelineError("structured_report_false_pass")
    if report["reactivated"] > report["updated"] + report["noop"]:
        raise PipelineError("structured_report_reactivation_invalid")
    if report["reconciliation_executed"] and (report["sync_scope"] != "FULL" or report["status"] != "PASS"
            or not report["reconciliation_attempted"] or report["reconciliation_skipped_reason"]):
        raise PipelineError("structured_report_reconciliation_invalid")
    if not report["reconciliation_executed"] and report["soft_deleted"]:
        raise PipelineError("structured_report_unexecuted_delete")
    return report
