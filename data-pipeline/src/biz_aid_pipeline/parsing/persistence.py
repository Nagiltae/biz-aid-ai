import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from botocore.exceptions import ClientError
from docling_core.types.doc import DoclingDocument

from biz_aid_pipeline.config.settings import PipelineError, S3Config
from biz_aid_pipeline.parsing.models import parse_identity, parse_key, parsing_contract
from biz_aid_pipeline.parsing.quality import artifact_bytes
from biz_aid_pipeline.storage import S3DocumentStore

PARSED_ARTIFACT_PREFIX = "biz-aid/parsed/docling-json"


def utc_datetime():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class PersistedParseResult:
    action: str
    source_sha256: str
    parse_key: str
    status: str
    artifact_s3_key: str | None
    artifact_sha256: str | None
    artifact_byte_size: int | None


class S3ParsedArtifactStore:
    """DoclingDocument JSON을 source와 parse_key로 주소화하고 기존 S3 무결성 경계를 재사용한다."""

    def __init__(self, bucket, region, client=None, prefix=PARSED_ARTIFACT_PREFIX):
        self.bucket, self.region, self.prefix = bucket, region, prefix.strip("/")
        self.objects = S3DocumentStore(bucket=bucket, region=region, prefix=self.prefix, client=client)

    def object_key(self, source_sha256, result_parse_key):
        self.objects._validate_sha256(source_sha256)
        self.objects._validate_sha256(result_parse_key)
        return (f"{self.prefix}/sha256/{source_sha256[:2]}/{source_sha256[2:4]}/"
                f"{source_sha256}/{result_parse_key}.json")

    def put(self, raw, source_sha256, result_parse_key):
        if not raw:
            raise ValueError("parsed artifact must not be empty")
        digest, size = hashlib.sha256(raw).hexdigest(), len(raw)
        key = self.object_key(source_sha256, result_parse_key)
        # BOUNDARY: local filesystem은 S3 SDK 전송을 위한 수명 제한 temp file일 뿐 영구 artifact가 아니다.
        with TemporaryDirectory(prefix="biz-aid-parsed-") as directory:
            path = Path(directory) / "document.json"
            path.write_bytes(raw)
            self.objects.put_key(path, key, digest, size, "application/json")
        if not self.objects.verify_key(key, digest, size):
            raise RuntimeError("parsed S3 artifact verification failed")
        # RISK: HEAD checksum만 통과한 상태에서 DB를 확정하지 않도록 실제 byte도 다시 읽어 동일성을 확인한다.
        if self.objects.read_key(key, digest, size, max_bytes=size) != raw:
            raise RuntimeError("parsed S3 artifact readback mismatch")
        return {"key": key, "sha256": digest, "byte_size": size, "verified_at": utc_datetime()}


def parsed_artifact_store(root, profile, client=None):
    """기존 dev S3 profile 경계를 재사용해 production parsed artifact store를 만든다."""
    config = S3Config.load(Path(root), profile)
    return S3ParsedArtifactStore(config.bucket, config.region, client=client)


def persist_parse_result(result, repository, store, contract=None):
    """S3 artifact를 검증한 뒤에만 MySQL metadata를 확정한다. 비성공 결과는 metadata만 기록한다."""
    contract = contract or parsing_contract()
    if result.status not in contract["parse_statuses"]:
        raise PipelineError("unknown_parse_status")
    converter = (result.derivation or {}).get("converter_version")
    identity = parse_identity(result.source_sha256, result.route, contract, converter)
    if parse_key(result.source_sha256, result.route, contract, converter) != result.parse_key:
        raise PipelineError("parse_result_key_mismatch")
    repository.require_source(result.source_sha256)
    values = {"source_sha256": result.source_sha256, "parse_key": result.parse_key,
              "detected_format": result.detected_format, "route": result.route, "parse_status": result.status,
              "artifact_s3_region": None, "artifact_s3_bucket_name": None, "artifact_s3_object_key": None,
              "artifact_sha256": None, "artifact_byte_size": None, "artifact_verified_at": None,
              "parser_identity_json": identity, "warnings_json": result.warnings,
              "failure_code": result.failure_code, "text_chars": result.text_chars,
              "unit_count": result.unit_count, "derivation_json": result.derivation,
              "ocr_json": result.ocr, "parsed_at": utc_datetime()}
    if result.status == "PARSED":
        if result.document is None or result.failure_code is not None:
            raise PipelineError("parsed_result_document_required")
        raw = artifact_bytes(result.document)
        try:
            DoclingDocument.model_validate_json(raw)
        except ValueError:
            raise PipelineError("parsed_artifact_reload_failed") from None
        try:
            # S3 PUT·HEAD·GET 검증이 모두 끝나기 전에는 repository transaction을 시작하지 않는다.
            artifact = store.put(raw, result.source_sha256, result.parse_key)
        except (ClientError, OSError, RuntimeError, ValueError):
            raise PipelineError("parsed_artifact_storage_failure") from None
        values.update(artifact_s3_region=store.region, artifact_s3_bucket_name=store.bucket,
                      artifact_s3_object_key=artifact["key"], artifact_sha256=artifact["sha256"],
                      artifact_byte_size=artifact["byte_size"], artifact_verified_at=artifact["verified_at"])
    action = repository.persist(values)
    return PersistedParseResult(action, result.source_sha256, result.parse_key, result.status,
                                values["artifact_s3_object_key"], values["artifact_sha256"],
                                values["artifact_byte_size"])
