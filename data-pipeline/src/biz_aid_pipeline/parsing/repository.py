from sqlalchemy import MetaData, Table, create_engine, select, update
from sqlalchemy.engine import URL

from biz_aid_pipeline.config.settings import PipelineError


class ParseResultRepository:
    """MySQL parse metadata 저장소. DoclingDocument JSON byte는 받거나 저장하지 않는다."""

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
            self.results = Table("document_parse_results", metadata, autoload_with=self.engine)
        except Exception:
            self.engine.dispose()
            raise PipelineError("parse_result_schema_unavailable_run_flyway") from None

    def require_source(self, source_sha256):
        with self.engine.connect() as connection:
            exists = connection.execute(select(self.sources.c.content_sha256).where(
                self.sources.c.content_sha256 == source_sha256,
                self.sources.c.download_status == "ACQUIRED",
                self.sources.c.s3_object_key.is_not(None)).limit(1)).first()
        if exists is None:
            raise PipelineError("verified_document_source_required")

    @staticmethod
    def _same(existing, values):
        ignored = {"parsed_at", "artifact_verified_at"}
        return all(existing[name] == value for name, value in values.items() if name not in ignored)

    def persist(self, values):
        identity = (self.results.c.source_sha256 == values["source_sha256"],
                    self.results.c.parse_key == values["parse_key"])
        with self.engine.begin() as connection:
            existing = connection.execute(select(self.results).where(*identity).with_for_update()).mappings().one_or_none()
            if existing is None:
                connection.execute(self.results.insert().values(**values))
                return "INSERTED"
            if self._same(existing, values):
                return "REUSED"
            # BOUNDARY: 검증된 성공 row는 같은 parse_key의 실패나 다른 artifact metadata로 덮어쓰지 않는다.
            if existing["parse_status"] == "PARSED":
                raise PipelineError("parse_result_conflict")
            connection.execute(update(self.results).where(*identity).values(**values))
            return "UPDATED"

    def verified_source_formats(self):
        """검증된 원본의 (content SHA, detected_format) 목록. corpus 대상 선택에만 쓴다."""
        with self.engine.connect() as connection:
            return [tuple(row) for row in connection.execute(select(
                self.sources.c.content_sha256, self.sources.c.detected_format).where(
                self.sources.c.download_status == "ACQUIRED", self.sources.c.s3_object_key.is_not(None),
                self.sources.c.s3_verified_at.is_not(None)).distinct())]

    def get(self, source_sha256, result_parse_key):
        with self.engine.connect() as connection:
            return connection.execute(select(self.results).where(
                self.results.c.source_sha256 == source_sha256,
                self.results.c.parse_key == result_parse_key)).mappings().one_or_none()

    def close(self):
        self.engine.dispose()
