import hashlib
import json
import re
from dataclasses import dataclass, field
from importlib import metadata

from docling_core.types.doc import DoclingDocument

from biz_aid_pipeline.config.settings import ROOT, PipelineError, read_json

CONTRACT_PATH = ROOT / "contracts/schemas/document-parsing.contract.json"
SHA256 = re.compile(r"[0-9a-f]{64}")


def parsing_contract(path=CONTRACT_PATH):
    return read_json(path)


@dataclass(frozen=True)
class ParseRequest:
    source_sha256: str
    detected_format: str
    byte_size: int

    def __post_init__(self):
        if not SHA256.fullmatch(self.source_sha256):
            raise PipelineError("invalid_source_sha256")
        if self.byte_size <= 0:
            raise PipelineError("invalid_source_byte_size")


@dataclass
class ParseResult:
    """BizAid 추적 정보만 담는 봉투다. 문서 구조의 표현은 DoclingDocument 하나로 유지한다."""

    source_sha256: str
    detected_format: str
    route: str
    parse_key: str
    status: str
    document: DoclingDocument | None = None
    warnings: dict = field(default_factory=dict)
    failure_code: str | None = None
    text_chars: int = 0
    unit_count: int = 0

    def warn(self, code, count=1):
        self.warnings[code] = self.warnings.get(code, 0) + count

    def summary(self):
        return {"source_sha256": self.source_sha256, "detected_format": self.detected_format,
                "route": self.route, "parse_key": self.parse_key, "status": self.status,
                "failure_code": self.failure_code, "text_chars": self.text_chars,
                "unit_count": self.unit_count, "warnings": dict(sorted(self.warnings.items()))}


def installed_version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def parse_key(source_sha256, route, contract, converter_version=None):
    # 부품 버전이 바뀐 route의 문서만 새 key를 받아 선택적으로 재처리되고 과거 결과는 덮어쓰지 않는다.
    versioning = contract["versioning"]
    identity = {
        "source_sha256": source_sha256,
        "route": route,
        "adapter_version": versioning["adapter_version"],
        "normalizer_version": versioning["normalizer_version"],
        "docling_core_version": installed_version("docling-core"),
        "docling_version": installed_version("docling") if route in ("DOCLING_PDF", "HWP_PDF_DOCLING") else None,
        "converter_version": converter_version,
    }
    if sorted(identity) != sorted(versioning["parse_key_inputs"]):
        raise PipelineError("parse_key_contract_drift")
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()
