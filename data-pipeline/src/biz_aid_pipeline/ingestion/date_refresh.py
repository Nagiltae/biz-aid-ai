"""기존 period normalizer로 신청기간 파생 날짜만 갱신한다. Raw·fingerprint·lifecycle은 건드리지 않는다."""
import argparse
import json
from pathlib import Path

from sqlalchemy import select, update, text
from biz_aid_pipeline.config.settings import ROOT, DbConfig, PipelineError
from biz_aid_pipeline.ingestion.normalizer import period
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository


def refresh_dates(repository, apply=False):
    table = repository.programs
    with repository.engine.connect() as connection:
        acquired = connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": "biz-aid-sync:" + repository.database}).scalar()
        connection.commit()
        if acquired != 1:
            raise PipelineError("sync_already_running")
        try:
            with connection.begin():
                rows = connection.execute(select(table).with_for_update()).mappings().all()
                before = sum(row["application_end_date"] is not None for row in rows)
                changes = []
                for row in rows:
                    start, end, _ = period(row["application_period_raw"])
                    # WHY: 새로운 근거를 읽지 않고 기존 원문의 명시 날짜만 보강한다. 기존 파생값을 자유문구 때문에 지우지 않는다.
                    if end is not None and (start, end) != (row["application_start_date"], row["application_end_date"]):
                        changes.append({"pblanc_id": row["pblanc_id"], "start": str(start), "end": str(end)})
                        if apply:
                            connection.execute(update(table).where(table.c.pblanc_id == row["pblanc_id"]).values(
                                application_start_date=start, application_end_date=end))
                if apply:
                    after_rows = connection.execute(select(table).order_by(table.c.pblanc_id)).mappings().all()
                    unchanged = {row["pblanc_id"]: {k: v for k, v in row.items() if k not in ("application_start_date", "application_end_date")}
                                 for row in rows}
                    if any(unchanged[row["pblanc_id"]] != {k: v for k, v in row.items() if k not in ("application_start_date", "application_end_date")}
                           for row in after_rows):
                        raise PipelineError("date_refresh_source_preservation_failed")
                return {"rows": len(rows), "parsed_before": before, "parsed_after": before + sum(
                    row["application_end_date"] is None and any(c["pblanc_id"] == row["pblanc_id"] for c in changes) for row in rows),
                    "changed_rows": len(changes), "applied": apply, "changes": changes, "raw_fingerprint_lifecycle_preserved": True}
        finally:
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": "biz-aid-sync:" + repository.database})
            connection.commit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only raw-preserving application date refresh")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    repository = MysqlRepository(DbConfig.load(ROOT, args.profile))
    try:
        result = refresh_dates(repository, args.apply)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({k: v for k, v in result.items() if k != "changes"}))
        return 0
    finally:
        repository.close()
