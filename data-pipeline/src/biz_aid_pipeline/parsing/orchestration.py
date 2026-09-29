from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from botocore.exceptions import ClientError

from biz_aid_pipeline.config.settings import DbConfig, PipelineError, S3Config
from biz_aid_pipeline.documents.repository import DocumentRepository
from biz_aid_pipeline.parsing.models import ParseRequest, parsing_contract
from biz_aid_pipeline.parsing.persistence import S3ParsedArtifactStore, persist_parse_result
from biz_aid_pipeline.parsing.repository import ParseResultRepository
from biz_aid_pipeline.parsing.router import parse_document
from biz_aid_pipeline.storage import S3DocumentStore

BATCH_MAX_SOURCES = 3


@dataclass(frozen=True)
class ParseExecution:
    source_sha256: str
    detected_format: str
    parse_key: str
    status: str
    failure_code: str | None
    persistence_action: str
    artifact_s3_key: str | None
    artifact_sha256: str | None
    artifact_byte_size: int | None

    def summary(self):
        return {"source_sha256": self.source_sha256, "detected_format": self.detected_format,
                "parse_key": self.parse_key, "status": self.status, "failure_code": self.failure_code,
                "persistence_action": self.persistence_action, "artifact_s3_key": self.artifact_s3_key,
                "artifact_sha256": self.artifact_sha256, "artifact_byte_size": self.artifact_byte_size}


@dataclass(frozen=True)
class BatchItem:
    source_sha256: str
    status: str
    failure_code: str | None
    persistence_action: str | None
    artifact_s3_key: str | None
    elapsed_seconds: float

    def summary(self):
        return {"source_sha256": self.source_sha256, "status": self.status,
                "failure_code": self.failure_code, "persistence_action": self.persistence_action,
                "artifact_s3_key": self.artifact_s3_key, "elapsed_seconds": self.elapsed_seconds}


@dataclass(frozen=True)
class BatchExecution:
    status: str
    source_count: int
    inserted: int
    reused: int
    updated: int
    failed: int
    non_parsed: int
    elapsed_seconds: float
    items: tuple[BatchItem, ...]

    def summary(self):
        return {"status": self.status, "source_count": self.source_count, "inserted": self.inserted,
                "reused": self.reused, "updated": self.updated, "failed": self.failed,
                "non_parsed": self.non_parsed, "elapsed_seconds": self.elapsed_seconds,
                "items": [item.summary() for item in self.items]}


def orchestrate_source(source_sha256, source_repository, source_store, result_repository,
                       artifact_store, contract=None, parser=parse_document, persister=persist_parse_result):
    """검증된 unique content SHA 하나를 읽어 기존 parser와 persistence 경계를 순서대로 호출한다."""
    contract = contract or parsing_contract()
    source = source_repository.verified_source(source_sha256)
    if source["s3_region"] != source_store.region or source["s3_bucket_name"] != source_store.bucket:
        raise PipelineError("document_source_storage_mismatch")
    expected_key = source_store.object_key(source_sha256)
    if source["s3_object_key"] != expected_key:
        raise PipelineError("document_source_object_key_mismatch")
    # BOUNDARY: 원본 S3 GET에서 size·SHA 검증을 마친 byte만 parser로 전달한다.
    try:
        raw = source_store.read_key(source["s3_object_key"], source_sha256, source["byte_size"],
                                    max_bytes=contract["input"]["max_source_bytes"])
    except (ClientError, OSError, RuntimeError, ValueError):
        raise PipelineError("document_source_s3_read_failure") from None
    result = parser(ParseRequest(source_sha256, source["detected_format"], source["byte_size"]), raw, contract)
    persisted = persister(result, result_repository, artifact_store, contract)
    return ParseExecution(source_sha256, source["detected_format"], result.parse_key, result.status,
                          result.failure_code, persisted.action, persisted.artifact_s3_key,
                          persisted.artifact_sha256, persisted.artifact_byte_size)


def run_source(root, profile, source_sha256):
    """dev profile의 단일 SHA 실행에 필요한 기존 DB/S3 adapter를 조립한다."""
    root = Path(root)
    db_config = DbConfig.load(root, profile)
    s3_config = S3Config.load(root, profile)
    source_repository = DocumentRepository(db_config)
    try:
        result_repository = ParseResultRepository(db_config)
        try:
            source_store = S3DocumentStore(s3_config.bucket, s3_config.region, s3_config.prefix)
            artifact_store = S3ParsedArtifactStore(s3_config.bucket, s3_config.region, client=source_store.client)
            return orchestrate_source(source_sha256, source_repository, source_store,
                                      result_repository, artifact_store)
        finally:
            result_repository.close()
    finally:
        source_repository.close()


def run_batch(root, profile, source_sha256s, runner=run_source):
    """명시된 최대 3개 unique SHA를 정렬해 순차 실행하고 source별 결과를 격리해 집계한다."""
    if profile != "dev":
        raise PipelineError("prod_parsing_access_forbidden")
    sources = tuple(source_sha256s)
    if not sources or len(sources) > BATCH_MAX_SOURCES:
        raise PipelineError("parsing_batch_source_limit")
    if len(set(sources)) != len(sources):
        raise PipelineError("duplicate_parsing_batch_source")
    if any(len(source) != 64 or any(character not in "0123456789abcdef" for character in source)
           for source in sources):
        raise PipelineError("invalid_source_sha256")
    started = monotonic()
    items = []
    for source_sha256 in sorted(sources):
        item_started = monotonic()
        try:
            execution = runner(root, profile, source_sha256)
            item = BatchItem(source_sha256, execution.status, execution.failure_code,
                             execution.persistence_action, execution.artifact_s3_key,
                             round(monotonic() - item_started, 3))
        except PipelineError as error:
            item = BatchItem(source_sha256, "EXECUTION_FAILED", str(error), None, None,
                             round(monotonic() - item_started, 3))
        except Exception:
            # RISK: provider·DB 예외 원문은 credential을 포함할 수 있어 batch 결과에는 고정 코드만 남긴다.
            item = BatchItem(source_sha256, "EXECUTION_FAILED", "unexpected_execution_failure", None, None,
                             round(monotonic() - item_started, 3))
        items.append(item)
    actions = [item.persistence_action for item in items]
    failed = sum(item.persistence_action is None for item in items)
    non_parsed = sum(item.status != "PARSED" for item in items)
    return BatchExecution("PASS" if not failed and not non_parsed else "FAIL", len(items),
                          actions.count("INSERTED"), actions.count("REUSED"), actions.count("UPDATED"),
                          failed, non_parsed, round(monotonic() - started, 3), tuple(items))
