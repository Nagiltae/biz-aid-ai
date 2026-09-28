from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, create_engine, func, select, text, update
from sqlalchemy.engine import URL

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.quality.structured_data_gate import reconciliation_reasons


def utc_datetime():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MysqlRepository:
    def __init__(self, config):
        if (config.profile != "dev" or config.database not in ("biz_aid_dev", "biz_aid_test")
                or config.host not in ("localhost", "127.0.0.1", "mysql") or config.port != 3306):
            raise PipelineError("dev_database_boundary")
        self.database = config.database
        self.engine = create_engine(URL.create("mysql+pymysql", username=config.user,
            password=config.password, host=config.host, port=config.port, database=config.database,
            query={"charset": "utf8mb4"}), hide_parameters=True, echo=False, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "read_timeout": 30, "write_timeout": 30})
        metadata = MetaData()
        try:
            self.programs = Table("support_programs", metadata, autoload_with=self.engine)
            self.runs = Table("support_program_sync_history", metadata, autoload_with=self.engine)
        except Exception:
            self.engine.dispose()
            raise PipelineError("database_schema_unavailable_run_flyway") from None

    @contextmanager
    def transaction(self, run_id):
        with self.engine.connect() as connection:
            lock = "biz-aid-sync:" + self.database
            # FULL 미관측 판정과 다른 실행의 관측이 교차하지 않도록 같은 연결에서 DB 실행 lock을 유지한다.
            acquired = connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": lock}).scalar()
            connection.commit()
            if acquired != 1:
                raise PipelineError("sync_already_running")
            try:
                with connection.begin():
                    if connection.execute(select(self.runs.c.run_id).where(self.runs.c.run_id == run_id)).first():
                        raise PipelineError("run_id_already_exists")
                    yield connection
            finally:
                if connection.in_transaction():
                    connection.rollback()
                try:
                    connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock})
                    connection.commit()
                except Exception:
                    # commit 후 lock 해제 실패를 원본 롤백으로 오인하지 않도록 연결을 폐기해 lock을 해제한다.
                    connection.invalidate()

    def start(self, connection, report):
        connection.execute(self.runs.insert().values(run_id=report["run_id"], sync_scope=report["sync_scope"],
            profile="dev", status="RUNNING", started_at=utc_datetime()))

    def upsert(self, connection, normalized, run_id):
        table = self.programs
        existing = connection.execute(select(table).where(table.c.pblanc_id == normalized.pblanc_id)
            .with_for_update()).mappings().first()
        observed = utc_datetime()
        lifecycle = dict(last_seen_at=observed, last_seen_run_id=run_id,
                         source_active=True, source_deleted=False, source_deleted_at=None)
        source = dict(normalized.content, source_payload=normalized.source_payload,
                      source_fingerprint=normalized.source_fingerprint, fingerprint_version=1)
        if existing is None:
            connection.execute(table.insert().values(pblanc_id=normalized.pblanc_id,
                **source, **lifecycle, created_at=observed, updated_at=observed))
            return "inserted", False
        reactivated = bool(existing["source_deleted"])
        changed = existing["source_fingerprint"] != normalized.source_fingerprint
        # 동일 원본의 content는 UPDATE하지 않는다. 관측 시각과 복원은 content 변경과 별개다.
        values = dict(lifecycle, **source, updated_at=observed) if changed else lifecycle
        connection.execute(update(table).where(table.c.pblanc_id == normalized.pblanc_id).values(**values))
        return "updated" if changed else "noop", reactivated

    def verify(self, connection, records):
        rows = connection.execute(select(self.programs).where(
            self.programs.c.pblanc_id.in_([item.pblanc_id for item in records]))).mappings().all()
        by_id = {row["pblanc_id"]: row for row in rows}
        for item in records:
            row = by_id.get(item.pblanc_id)
            if row is None or row["source_payload"] != item.source_payload or row["source_fingerprint"] != item.source_fingerprint:
                raise PipelineError("persistence_roundtrip_mismatch")
            if any(row[name] != value for name, value in item.content.items()):
                raise PipelineError("derived_content_roundtrip_mismatch")

    def authorize_reconciliation(self, connection, report, batch):
        # FULL 지정만으로 삭제할 수 없다. 완전성 검증과 영속 실행 상태가 모두 필요하다.
        row = connection.execute(select(self.runs).where(self.runs.c.run_id == report["run_id"])).mappings().one()
        seen = connection.execute(select(func.count()).select_from(self.programs).where(
            self.programs.c.last_seen_run_id == report["run_id"])).scalar_one()
        if (row["status"] != "SUCCESS" or row["sync_scope"] != "FULL" or report["reconciliation_skipped_reason"]
                or reconciliation_reasons(batch, report) or seen != report["unique_pblanc_id_count"]
                or row["report_json"] != report):
            raise PipelineError("reconciliation_not_authorized")

    def soft_delete_candidates(self, connection, report, batch):
        self.authorize_reconciliation(connection, report, batch)
        return connection.execute(select(self.programs.c.pblanc_id).where(
            self.programs.c.source_active.is_(True), self.programs.c.last_seen_run_id != report["run_id"]
        ).order_by(self.programs.c.pblanc_id)).scalars().all()

    def row_count(self, connection):
        return connection.execute(select(func.count()).select_from(self.programs)).scalar_one()

    def reconcile(self, connection, report, batch):
        if self.database != "biz_aid_test":
            raise PipelineError("live_soft_delete_not_enabled")
        self.authorize_reconciliation(connection, report, batch)
        # DRY_RUN으로 기록된 실행은 직접 Repository를 호출해도 soft-delete를 적용하지 못한다.
        if report.get("soft_delete_mode") == "DRY_RUN":
            raise PipelineError("dry_run_cannot_apply_soft_delete")
        result = connection.execute(update(self.programs).where(
            self.programs.c.source_active.is_(True), self.programs.c.last_seen_run_id != report["run_id"]
        ).values(source_active=False, source_deleted=True, source_deleted_at=utc_datetime()))
        return result.rowcount

    def finish(self, connection, report):
        connection.execute(update(self.runs).where(self.runs.c.run_id == report["run_id"]).values(
            status="SUCCESS" if report["status"] == "PASS" else "FAILED", finished_at=utc_datetime(), report_json=report))

    def close(self):
        self.engine.dispose()
