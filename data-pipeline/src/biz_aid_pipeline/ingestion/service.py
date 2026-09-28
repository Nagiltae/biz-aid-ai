import re
from time import monotonic

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.ingestion.normalizer import normalize
from biz_aid_pipeline.quality.structured_data_gate import now, quality_report, reconciliation_reasons, validate_report


def prepare_ingestion(batch, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise PipelineError("invalid_run_id")
    report = quality_report(batch, run_id)
    records = []
    for source in batch.items:
        try:
            item = normalize(source)
            records.append(item)
            report["date_parse_success"] += item.period_class == "DATE_RANGE"
            report["date_free_text"] += item.period_class == "FREE_TEXT"
            report["date_unavailable"] += item.period_class == "UNAVAILABLE"
            report["date_invalid_range"] += item.period_class == "INVALID_DATE_RANGE"
            report["source_timestamp_unparsed"] += sum(
                bool(item.source_payload.get(raw)) and item.content[derived] is None
                for raw, derived in (("creatPnttm", "source_created_at"), ("updtPnttm", "source_updated_at")))
            report["invalid_url_count"] += item.invalid_urls
        except (ValueError, TypeError, OverflowError):
            # 모델 검증 예외는 원본 값을 담으므로 고정 오류 코드와 건수만 보고한다.
            report["required_field_failures"] += 1
            report["normalization_fatal_errors"] += 1
    errors = len(report["failed_pages"]) + report["contract_errors"] + report["normalization_fatal_errors"] + report["duplicate_count"]
    report["failed"] = errors
    report["status"] = "FAIL" if errors else "PASS"
    report["reconciliation_skipped_reason"] = reconciliation_reasons(batch, report)
    if batch.scope.value == "FULL" and report["reconciliation_skipped_reason"]:
        report["status"] = "FAIL"
    report["reconciliation_attempted"] = batch.scope.value == "FULL"
    return report, records


def ingest(repository, batch, run_id, *, reconciliation_mode="APPLY", transaction_seconds=None):
    if reconciliation_mode not in ("APPLY", "DRY_RUN") or (transaction_seconds is not None and
            (type(transaction_seconds) not in (int, float) or transaction_seconds <= 0)):
        raise PipelineError("invalid_ingestion_policy")
    report, records = prepare_ingestion(batch, run_id)
    if reconciliation_mode == "DRY_RUN":
        report.update(soft_delete_mode="DRY_RUN", soft_delete_candidate_count=None,
                      soft_delete_candidate_pblanc_ids=[], reconciliation_dry_run=False, mysql_final_row_count=None)
    def budget(start):
        if transaction_seconds is not None and monotonic() - start >= transaction_seconds:
            raise PipelineError("database_transaction_time_limit")
    try:
        with repository.transaction(run_id) as connection:
            start = monotonic()
            repository.start(connection, report)
            # 검증 불가능한 실행은 원본 행을 부분 변경하지 않고 실패 이력만 보존한다.
            if report["status"] == "PASS":
                for item in records:
                    budget(start)
                    outcome, reactivated = repository.upsert(connection, item, run_id)
                    report[outcome] += 1
                    report["reactivated"] += reactivated
                # 전체 건수의 긴 IN 조건을 피한다. 검증만 나누고 commit은 한 번 수행해 실패 시 모두 rollback한다.
                for offset in range(0, len(records), 100):
                    budget(start)
                    repository.verify(connection, records[offset:offset + 100])
                repository.finish(connection, report)
                if not report["reconciliation_skipped_reason"]:
                    if reconciliation_mode == "DRY_RUN":
                        candidates = repository.soft_delete_candidates(connection, report, batch)
                        report.update(soft_delete_candidate_count=len(candidates), soft_delete_candidate_pblanc_ids=candidates,
                                      reconciliation_dry_run=True, reconciliation_skipped_reason=["dry_run_only"])
                    else:
                        report["soft_deleted"] = repository.reconcile(connection, report, batch)
                        report["reconciliation_executed"] = True
                if reconciliation_mode == "DRY_RUN":
                    report["mysql_final_row_count"] = repository.row_count(connection)
            report["finished_at"] = now()
            budget(start)
            validate_report(report)
            repository.finish(connection, report)
    except PipelineError as error:
        if str(error) in ("run_id_already_exists", "sync_already_running"):
            raise
        report.update(status="FAIL", persistence_fatal_errors=1, failed=max(1, report["failed"]))
    except Exception:
        report.update(status="FAIL", persistence_fatal_errors=1, failed=max(1, report["failed"]))
    if report["persistence_fatal_errors"]:
        # 롤백 후 미반영 건수를 성공으로 보고하지 않는다. SQL 예외 원문은 인증정보 보호를 위해 남기지 않는다.
        for key in ("inserted", "updated", "noop", "reactivated", "soft_deleted"):
            report[key] = 0
        report["reconciliation_executed"] = False
        if reconciliation_mode == "DRY_RUN":
            report.update(reconciliation_dry_run=False, soft_delete_candidate_count=None,
                          soft_delete_candidate_pblanc_ids=[], mysql_final_row_count=None)
        report["reconciliation_skipped_reason"] = reconciliation_reasons(batch, report)
        report["finished_at"] = now()
        report["error_codes"].append("persistence_transaction_rolled_back")
        try:
            with repository.transaction(run_id) as connection:
                repository.start(connection, report)
                repository.finish(connection, report)
        except Exception:
            report["error_codes"].append("failed_history_not_persisted")
    return report
