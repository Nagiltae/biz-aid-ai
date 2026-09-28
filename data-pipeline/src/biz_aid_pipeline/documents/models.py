import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from biz_aid_pipeline.config.settings import PipelineError


@dataclass(frozen=True)
class DocumentCandidate:
    candidate_key: str
    pblanc_id: str
    source_role: str
    source_url_field: str
    source_filename_field: str
    source_token_index: int
    source_url: str
    source_url_sha256: str
    original_filename: str | None
    pairing_status: str
    declared_extension: str

    def value(self):
        return asdict(self)


def extension(filename):
    if not isinstance(filename, str) or not filename.strip():
        return "UNKNOWN"
    suffix = PurePosixPath(filename).suffix.removeprefix(".").upper()
    return suffix if suffix in ("PDF", "HWP", "HWPX", "ZIP", "XLSX") else "OTHER" if suffix else "UNKNOWN"


def candidates(pblanc_id, print_url, print_name, attachment_urls, attachment_names):
    result = []
    definitions = (
        ("PRINT_CANDIDATE", "printFlpthNm", "printFileNm", print_url, print_name),
        ("ATTACHMENT_CANDIDATE", "flpthNm", "fileNm", attachment_urls, attachment_names),
    )
    for role, url_field, filename_field, raw_urls, raw_names in definitions:
        urls = [] if raw_urls is None or not raw_urls.strip() else raw_urls.split("@")
        names = [] if raw_names is None or not raw_names.strip() else raw_names.split("@")
        for index, source_url in enumerate(urls):
            if not source_url.strip():
                continue
            filename = names[index] if index < len(names) and names[index].strip() else None
            identity = {"pblanc_id": pblanc_id, "source_url_field": url_field,
                        "source_token_index": index, "source_url": source_url}
            key = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                             separators=(",", ":")).encode()).hexdigest()
            result.append(DocumentCandidate(key, pblanc_id, role, url_field, filename_field, index,
                source_url, hashlib.sha256(source_url.encode()).hexdigest(), filename,
                "MATCHED" if len(urls) == len(names) and filename is not None else "UNPAIRED", extension(filename)))
    if len({item.candidate_key for item in result}) != len(result):
        raise PipelineError("duplicate_document_candidate_key")
    return result
