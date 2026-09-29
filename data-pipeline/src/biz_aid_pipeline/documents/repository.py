from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, create_engine, select, text, update
from sqlalchemy.engine import URL

from biz_aid_pipeline.config.settings import PipelineError


def utc_datetime():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DocumentRepository:
    def __init__(self, config):
        if (config.profile != "dev" or config.database not in ("biz_aid_dev", "biz_aid_test")
                or config.host not in ("localhost", "127.0.0.1", "mysql") or config.port != 3306):
            raise PipelineError("dev_database_boundary")
        self.database = config.database
        self.engine = create_engine(URL.create("mysql+pymysql", username=config.user, password=config.password,
            host=config.host, port=config.port, database=config.database, query={"charset": "utf8mb4"}),
            hide_parameters=True, echo=False, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "read_timeout": 30, "write_timeout": 30})
        metadata = MetaData()
        try:
            self.programs = Table("support_programs", metadata, autoload_with=self.engine)
            self.runs = Table("document_acquisition_runs", metadata, autoload_with=self.engine)
            self.sources = Table("document_sources", metadata, autoload_with=self.engine)
        except Exception:
            self.engine.dispose()
            raise PipelineError("document_schema_unavailable_run_flyway") from None

    @contextmanager
    def acquisition_lock(self):
        connection = self.engine.connect()
        name = "biz-aid-document-acquisition:" + self.database
        try:
            acquired = connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": name}).scalar()
            connection.commit()
            if acquired != 1:
                raise PipelineError("document_acquisition_already_running")
            yield
        finally:
            try:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
                connection.commit()
            except Exception:
                connection.invalidate()
            connection.close()

    def source_rows(self):
        with self.engine.connect() as connection:
            return connection.execute(select(
                self.programs.c.pblanc_id, self.programs.c.source_fingerprint,
                self.programs.c.primary_url_raw, self.programs.c.primary_filename_raw,
                self.programs.c.attachment_urls_raw, self.programs.c.attachment_names_raw,
            ).where(self.programs.c.source_active.is_(True), self.programs.c.source_deleted.is_(False))
             .order_by(self.programs.c.pblanc_id)).mappings().all()

    def create_run(self, run_id, snapshot):
        with self.engine.begin() as connection:
            if connection.execute(select(self.runs.c.run_id).where(self.runs.c.run_id == run_id)).first():
                raise PipelineError("document_run_id_already_exists")
            connection.execute(self.runs.insert().values(run_id=run_id, profile="dev", status="RUNNING",
                gate_status="PENDING", source_snapshot_sha256=snapshot, started_at=utc_datetime()))

    def resume_run(self, run_id, snapshot):
        with self.engine.connect() as connection:
            row = connection.execute(select(self.runs).where(self.runs.c.run_id == run_id)).mappings().one_or_none()
        if row is None or row["status"] != "RUNNING" or row["source_snapshot_sha256"] != snapshot:
            raise PipelineError("document_run_not_resumable")

    def acquired_for_url(self, url_hash, url):
        with self.engine.connect() as connection:
            rows = connection.execute(select(self.sources).where(
                self.sources.c.source_url_sha256 == url_hash,
                self.sources.c.download_status == "ACQUIRED")).mappings().all()
        return next((row for row in rows if row["source_url"] == url), None)

    def persist_group(self, values):
        with self.engine.begin() as connection:
            for value in values:
                existing = connection.execute(select(self.sources).where(
                    self.sources.c.candidate_key == value["candidate_key"]).with_for_update()).mappings().one_or_none()
                if existing is None:
                    connection.execute(self.sources.insert().values(**value, first_seen_at=utc_datetime()))
                else:
                    if value["last_attempted_at"] is None:
                        value = {name: field for name, field in value.items() if name != "last_attempted_at"}
                    connection.execute(update(self.sources).where(self.sources.c.candidate_key == value["candidate_key"])
                                       .values(**value))

    def rows_for_keys(self, keys):
        rows = []
        with self.engine.connect() as connection:
            for offset in range(0, len(keys), 500):
                rows.extend(connection.execute(select(self.sources).where(
                    self.sources.c.candidate_key.in_(keys[offset:offset + 500]))).mappings().all())
        return rows

    def verified_source(self, content_sha256):
        """같은 content SHA를 가진 relation을 하나의 검증된 parser 입력 descriptor로 수렴한다."""
        with self.engine.connect() as connection:
            rows = connection.execute(select(
                self.sources.c.content_sha256, self.sources.c.detected_format,
                self.sources.c.byte_size, self.sources.c.s3_region,
                self.sources.c.s3_bucket_name, self.sources.c.s3_object_key,
                self.sources.c.s3_verified_at,
            ).where(
                self.sources.c.content_sha256 == content_sha256,
                self.sources.c.download_status == "ACQUIRED",
            )).mappings().all()
        if not rows or any(row[name] is None for row in rows for name in (
                "byte_size", "s3_region", "s3_bucket_name", "s3_object_key", "s3_verified_at")):
            raise PipelineError("verified_document_source_required")
        identity_names = ("content_sha256", "detected_format", "byte_size", "s3_region",
                          "s3_bucket_name", "s3_object_key")
        identities = {tuple(row[name] for name in identity_names) for row in rows}
        # RISK: 같은 byte가 relation마다 다른 format이나 S3 위치를 가리키면 임의의 한 row를 골라 parsing하지 않는다.
        if len(identities) != 1:
            raise PipelineError("document_source_metadata_conflict")
        return dict(zip(identity_names, identities.pop()), relation_count=len(rows))

    def finish_run(self, run_id, report, failed=False):
        with self.engine.begin() as connection:
            result = connection.execute(update(self.runs).where(
                self.runs.c.run_id == run_id, self.runs.c.status == "RUNNING").values(
                    status="FAILED" if failed else "COMPLETED", gate_status=report["status"],
                    finished_at=utc_datetime(), report_json=report))
            if result.rowcount != 1:
                raise PipelineError("document_run_finish_conflict")

    def run(self, run_id):
        with self.engine.connect() as connection:
            return connection.execute(select(self.runs).where(self.runs.c.run_id == run_id)).mappings().one()

    def close(self):
        self.engine.dispose()
