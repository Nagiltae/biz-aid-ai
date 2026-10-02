"""chunk 입력 적재. source의 현재 parse_key PARSED artifact를 S3에서 검증해 읽고 공고 relation을 붙인다.

원본 문서를 다시 parsing하지 않는다. 현재 parse_key 결과가 없으면 오래된 parser 결과로 대체하지 않고 실패한다.
"""
import json
from pathlib import Path

from sqlalchemy import select

from biz_aid_pipeline.config.settings import DbConfig, PipelineError, S3Config
from biz_aid_pipeline.chunking.chunker import ChunkSource
from biz_aid_pipeline.indexing.document_role import document_role
from biz_aid_pipeline.parsing.models import parse_key, parsing_contract
from biz_aid_pipeline.parsing.persistence import PARSED_ARTIFACT_PREFIX
from biz_aid_pipeline.parsing.repository import ParseResultRepository
from biz_aid_pipeline.parsing.router import route_for
from biz_aid_pipeline.storage import S3DocumentStore


def current_parse_key(source_sha256, detected_format, contract):
    route, _ = route_for(detected_format, contract)
    converter = None
    if route == "HWP_PDF_DOCLING":
        from biz_aid_pipeline.parsing.hwp_pdf import HwpConversionError, converter_version
        try:
            converter = converter_version(contract)
        except HwpConversionError as error:
            # BOUNDARY: 변환기 identity 없이는 현재 parse_key를 정할 수 없다. CLI가 이 source만 실패로 격리하도록 PipelineError로 바꾼다.
            raise PipelineError("hwp_converter_identity_unavailable:" + error.code) from None
    return route, parse_key(source_sha256, route, contract, converter)


def announcements(repository, source_sha256):
    """source가 붙은 공고(pblanc_id, 공고명). 같은 SHA가 여러 공고에 붙으면 모두 돌려준다."""
    from sqlalchemy import MetaData, Table
    programs = Table("support_programs", MetaData(), autoload_with=repository.engine)
    sources = repository.sources
    with repository.engine.connect() as connection:
        rows = connection.execute(select(sources.c.pblanc_id, programs.c.name).distinct().join(
            programs, programs.c.pblanc_id == sources.c.pblanc_id).where(
            sources.c.content_sha256 == source_sha256, sources.c.download_status == "ACQUIRED")).all()
    return tuple(sorted((row[0], row[1]) for row in rows))


def original_filenames(repository, source_sha256):
    """원본에 붙은 첨부 파일명들. 출처 종류(document_role) 판정의 단서로만 쓴다."""
    sources = repository.sources
    with repository.engine.connect() as connection:
        rows = connection.execute(select(sources.c.original_filename).distinct().where(
            sources.c.content_sha256 == source_sha256, sources.c.download_status == "ACQUIRED")).all()
    return sorted(row[0] for row in rows if row[0])


def load_chunk_source(root, profile, source_sha256, explicit_parse_key=None):
    """(DoclingDocument, ChunkSource). S3 artifact는 DB에 기록된 크기와 SHA-256으로 검증한 byte만 쓴다."""
    from docling_core.types.doc import DoclingDocument
    if profile != "dev":
        raise PipelineError("prod_chunking_access_forbidden")
    contract = parsing_contract()
    repository = ParseResultRepository(DbConfig.load(Path(root), profile))
    try:
        formats = {sha: fmt for sha, fmt in repository.verified_source_formats() if sha == source_sha256}
        if source_sha256 not in formats:
            raise PipelineError("verified_document_source_required")
        route, key = current_parse_key(source_sha256, formats[source_sha256], contract)
        key = explicit_parse_key or key
        row = repository.get(source_sha256, key)
        # BOUNDARY: 현재 parser 설정의 PARSED 결과만 chunk한다. 이전 parse_key artifact는 명시한 경우에만 쓴다.
        if row is None or row["parse_status"] != "PARSED":
            raise PipelineError("current_parsed_artifact_required")
        linked = announcements(repository, source_sha256)
        role = document_role(formats[source_sha256], original_filenames(repository, source_sha256))
    finally:
        repository.close()
    s3 = S3Config.load(Path(root), profile)
    store = S3DocumentStore(s3.bucket, s3.region, PARSED_ARTIFACT_PREFIX)
    raw = store.read_key(row["artifact_s3_object_key"], row["artifact_sha256"], row["artifact_byte_size"],
                         max_bytes=row["artifact_byte_size"])
    identity = row["parser_identity_json"]
    identity = json.loads(identity) if isinstance(identity, str) else identity
    document = DoclingDocument.model_validate_json(raw)
    return document, ChunkSource(source_sha256, row["detected_format"], row["route"], key, identity, linked, role)
