import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import metadata
from pathlib import Path

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
    # 변환 경로(HWP→PDF)에서만 채운다. 중간 PDF는 저장하지 않고 SHA·크기·변환기 identity만 남긴다.
    derivation: dict | None = None

    def warn(self, code, count=1):
        self.warnings[code] = self.warnings.get(code, 0) + count

    def summary(self):
        return {"source_sha256": self.source_sha256, "detected_format": self.detected_format,
                "route": self.route, "parse_key": self.parse_key, "status": self.status,
                "failure_code": self.failure_code, "text_chars": self.text_chars,
                "unit_count": self.unit_count, "warnings": dict(sorted(self.warnings.items())),
                "derivation": self.derivation}


def installed_version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def pipeline_config(contract):
    config = dict(contract["routes"]["PDF"]["docling_options"])
    # BOUNDARY: OCR baseline은 이번 Phase 범위 밖이므로 설정이 바뀌어도 OCR이 켜진 변환기를 만들지 않는다.
    if config.get("do_ocr") is not False:
        raise ValueError("pdf_ocr_must_be_disabled")
    return config


def pipeline_identity(contract):
    revision = contract["routes"]["PDF"]["layout_model_revision"]
    # RISK: Docling 기본 layout 모델 revision은 "main"이라 새 환경에서 다른 가중치를 받을 수 있으므로 commit hash만 허용한다.
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("layout_model_revision_must_be_commit")
    engine = dict(contract["routes"]["PDF"]["table_engine"])
    # BOUNDARY: 표 engine 설정도 parser identity라서 바뀌면 PDF 문서만 새 parse_key를 받는다. OCR 모델은 허용하지 않는다.
    if engine.get("use_ocr_model") is not False or any(module == "text_recognition" for module, _ in engine["submodules"].values()):
        raise ValueError("pdf_table_engine_ocr_must_be_disabled")
    return {"docling_options": pipeline_config(contract), "layout_model_revision": revision, "table_engine": engine}


def artifact_files(contract):
    spec = contract["dependencies"]["docling"]["model_artifacts"]
    return tuple((model["folder"], name) for model in spec["models"] for name in model["files"])


def docling_artifacts_path(contract, environ=None):
    # BOUNDARY: test·실행 중 모델 자동 다운로드를 막기 위해 미리 준비한 명시적 경로만 쓰고 없으면 변환 전에 멈춘다.
    spec = contract["dependencies"]["docling"]["model_artifacts"]
    value = (os.environ if environ is None else environ).get(spec["artifacts_path_env"], "").strip()
    if not value:
        raise PipelineError("docling_artifacts_path_required:" + spec["artifacts_path_env"])
    path = Path(value).expanduser().resolve()
    missing = [f"{folder}/{name}" for folder, name in artifact_files(contract) if not (path / folder / name).is_file()]
    if missing:
        raise PipelineError("docling_artifacts_missing:" + ",".join(missing))
    return path


@lru_cache(maxsize=4)
def artifacts_manifest_sha256(path, files):
    # 같은 tag라도 실제 가중치가 다르면 결과가 달라지므로 Contract가 지정한 파일의 경로와 내용 hash를 parser identity로 쓴다.
    # 목록 밖 파일(README·다운로드 metadata)은 모델 입력이 아니므로 제공 방식이 달라도 identity가 같아야 한다.
    digest = hashlib.sha256()
    for folder, name in sorted(files):
        with (Path(path) / folder / name).open("rb") as stream:
            digest.update(f"{folder}/{name}\0{hashlib.file_digest(stream, 'sha256').hexdigest()}\n".encode())
    return digest.hexdigest()


def model_artifacts_sha256(contract, environ=None):
    actual = artifacts_manifest_sha256(str(docling_artifacts_path(contract, environ)), artifact_files(contract))
    # RISK: cache 복원·수동 복사된 artifact를 그대로 믿으면 다른 가중치로 같은 설정의 결과를 만들 수 있다.
    if actual != contract["dependencies"]["docling"]["model_artifacts"]["expected_manifest_sha256"]:
        raise PipelineError("docling_artifacts_identity_mismatch")
    return actual


def artifacts_cache_key(contract):
    # 모델 identity만 key에 넣어 Contract의 무관한 문서 수정으로 대용량 cache가 무효화되지 않게 한다.
    spec = contract["dependencies"]["docling"]["model_artifacts"]
    identity = {"schema": spec["cache_key_schema"], "expected_manifest_sha256": spec["expected_manifest_sha256"],
                "models": [{key: model[key] for key in ("repo_id", "folder", "resolved_snapshot", "files")}
                           for model in spec["models"]]}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    revisions = "-".join(model["resolved_snapshot"][:12] for model in spec["models"])
    return f"docling-artifacts-v{spec['cache_key_schema']}-{revisions}-{digest[:16]}"


def pipeline_config_sha256(contract):
    return hashlib.sha256(json.dumps(pipeline_identity(contract), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def parse_key(source_sha256, route, contract, converter_version=None):
    # 부품 버전이 바뀐 route의 문서만 새 key를 받아 선택적으로 재처리되고 과거 결과는 덮어쓰지 않는다.
    versioning = contract["versioning"]
    identity = {
        "source_sha256": source_sha256,
        "route": route,
        "adapter_version": versioning["adapter_version"],
        "normalizer_version": versioning["normalizer_version"],
        "docling_core_version": installed_version("docling-core"),
        "docling_version": None,
        "docling_parse_version": None,
        "docling_ibm_models_version": None,
        "pipeline_config_sha256": None,
        "model_artifacts_sha256": None,
        "converter_version": converter_version,
        "paddlepaddle_version": None,
        "paddlex_version": None,
    }
    # HWP route의 Docling identity는 변환기 버전이 정해져 route가 활성화될 때 함께 채운다.
    if route == "DOCLING_PDF" or (route == "HWP_PDF_DOCLING" and converter_version is not None):
        # Docling 배포는 docling-slim이고 표는 PP-TableMagic이 맡으므로 두 쪽의 설치 버전과 모델 identity를 모두 넣는다.
        identity.update(docling_version=installed_version("docling-slim"),
                        docling_parse_version=installed_version("docling-parse"),
                        docling_ibm_models_version=installed_version("docling-ibm-models"),
                        pipeline_config_sha256=pipeline_config_sha256(contract),
                        model_artifacts_sha256=model_artifacts_sha256(contract),
                        paddlepaddle_version=installed_version("paddlepaddle"),
                        paddlex_version=installed_version("paddlex"))
    if sorted(identity) != sorted(versioning["parse_key_inputs"]):
        raise PipelineError("parse_key_contract_drift")
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()
