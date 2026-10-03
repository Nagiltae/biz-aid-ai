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
    # OCR한 page가 있을 때만 채운다. engine identity와 OCR한 page 및 결과 부족 page를 남긴다.
    ocr: dict | None = None

    def warn(self, code, count=1):
        self.warnings[code] = self.warnings.get(code, 0) + count

    def summary(self):
        return {"source_sha256": self.source_sha256, "detected_format": self.detected_format,
                "route": self.route, "parse_key": self.parse_key, "status": self.status,
                "failure_code": self.failure_code, "text_chars": self.text_chars,
                "unit_count": self.unit_count, "warnings": dict(sorted(self.warnings.items())),
                "derivation": self.derivation, "ocr": self.ocr}


def installed_version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def pipeline_config(contract):
    config = dict(contract["routes"]["PDF"]["docling_options"])
    # BOUNDARY: BizAid page OCR은 별도 layer로 결합하므로 Docling 내장 OCR은 켜지 않는다.
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
    return {"docling_options": pipeline_config(contract), "layout_model_revision": revision, "table_engine": engine,
            "ocr": dict(contract["routes"]["PDF"]["ocr"])}


def artifact_files(contract, scope=None):
    """Contract의 모델 파일 목록. scope(문자열 또는 묶음)를 주면 그 단계(parsing / chunking / embedding)가 쓰는 모델만 고른다."""
    spec = contract["dependencies"]["docling"]["model_artifacts"]
    scopes = None if scope is None else {scope} if isinstance(scope, str) else set(scope)
    return tuple((model["folder"], name) for model in spec["models"]
                 if scopes is None or model.get("scope", "parsing") in scopes for name in model["files"])


def docling_artifacts_path(contract, environ=None, scope=None):
    # BOUNDARY: test·실행 중 모델 자동 다운로드를 막기 위해 미리 준비한 명시적 경로만 쓰고 없으면 변환 전에 멈춘다.
    # scope를 주면 그 단계 모델 파일만 있어도 된다(질문 서버). 기본값은 전체 목록이다.
    spec = contract["dependencies"]["docling"]["model_artifacts"]
    value = (os.environ if environ is None else environ).get(spec["artifacts_path_env"], "").strip()
    if not value:
        raise PipelineError("docling_artifacts_path_required:" + spec["artifacts_path_env"])
    path = Path(value).expanduser().resolve()
    missing = [f"{folder}/{name}" for folder, name in artifact_files(contract, scope) if not (path / folder / name).is_file()]
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


def scoped_artifacts_sha256(contract, scope):
    """전체 artifact identity를 검증한 뒤 한 단계가 쓰는 모델 파일만의 manifest SHA를 돌려준다."""
    # WHY: 같은 artifact 경로에 chunking tokenizer를 추가해도 parse_key가 바뀌지 않게 identity를 단계별로 나눈다.
    model_artifacts_sha256(contract)
    return artifacts_manifest_sha256(str(docling_artifacts_path(contract)), artifact_files(contract, scope))


def verified_scope_artifacts_sha256(contract, scope, environ=None):
    """질문 서버용: 한 단계(scope) 모델 파일만 있는지 보고 그 manifest가 계약의 단계별 기대값과 같은지 확인한다.

    WHY(IMP-005): 질문 처리는 BGE-M3 tokenizer·가중치만 쓴다. 파싱 모델까지 전체 hash하면 시작이 느리고 컨테이너에 쓰지 않는 모델이 필요하다.
    돌려주는 값은 scoped_artifacts_sha256과 같은 단계별 manifest라 chunk·embedding identity는 바뀌지 않는다.
    """
    path = docling_artifacts_path(contract, environ, scope)
    actual = artifacts_manifest_sha256(str(path), artifact_files(contract, scope))
    # RISK: 단계별 기대값이 없으면 가중치를 검증하지 못한 채 실행하게 되므로 실패한다.
    if actual != contract["dependencies"]["docling"]["model_artifacts"]["expected_scope_manifest_sha256"].get(scope):
        raise PipelineError("docling_artifacts_scope_identity_mismatch:" + scope)
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


def folder_artifacts_sha256(contract, folders):
    """지정한 모델 폴더 파일만의 manifest SHA. 전체 artifact identity를 먼저 검증한다."""
    model_artifacts_sha256(contract)
    files = tuple((folder, name) for folder, name in artifact_files(contract) if folder in folders)
    return artifacts_manifest_sha256(str(docling_artifacts_path(contract)), files)


def config_identity(contract, section):
    """설정 hash 입력: 살아 있는 계약 구역이 아니라 그 구역이 가리키는 고정 snapshot(IMP-026).

    WHY: 계약 구역에는 설명 문구도 있어, 구역 전체를 hash하면 문구만 고쳐도 parse_key가 바뀐다. snapshot은 예전에 hash하던
    구역을 그대로 복사해 둔 값이라 기존 key가 그대로이고, 이후 설명 수정은 key에 영향을 주지 않는다.
    """
    return contract["config_identity_snapshots"][contract[section]["identity_snapshot"]]


def image_ocr_config_sha256(contract):
    """이미지 OCR 결과를 바꾸는 설정: 공유 OCR engine 설정(모델·검출·인식 옵션)과 이미지 OCR 설정(타일·겹침·픽셀 상한·신뢰도 기준)."""
    return hashlib.sha256(json.dumps({"engine": contract["routes"]["PDF"]["ocr"], "image_ocr": config_identity(contract, "image_ocr"),
                                      "document_gate": contract["document_gate"]["pdf_ocr_required_max_chars_per_page"]},
                                     sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


# parse_key 입력은 코드가 소유한 목록이다. Contract의 parse_key_inputs와 다르면 drift로 실패한다.
PARSE_KEY_INPUTS = ("source_sha256", "route", "hwpx_adapter_version", "normalizer_version", "docling_core_version",
                    "docling_version", "docling_parse_version", "docling_ibm_models_version", "pipeline_config_sha256",
                    "model_artifacts_sha256", "converter_version", "paddlepaddle_version", "paddlex_version")
# BOUNDARY: route 전용 입력은 그 route identity에만 더한다. 공통 목록에 넣으면 모든 route identity에 null key가 생겨 기존 parse_key가 바뀐다.
ROUTE_PARSE_KEY_INPUTS = {"IMAGE_OCR": ("image_ocr_version", "image_ocr_config_sha256"),
                          "DOCLING_DOCX": ("office_parser_version", "office_config_sha256", "python_docx_version"),
                          "DOCLING_PPTX": ("office_parser_version", "office_config_sha256", "python_pptx_version")}


def parse_identity(source_sha256, route, contract, converter_version=None):
    """parse_key 입력과 영구 metadata가 같은 identity를 공유하도록 결정론적 mapping을 만든다.

    각 부품 identity는 그 부품이 결과에 영향을 주는 route에만 넣는다(Contract versioning.route_scope).
    """
    # WHY: 한 route의 부품 변경이 다른 route 문서까지 재처리하게 만들지 않는다(예: HWPX adapter 변경이 PDF key를 바꾸던 문제).
    versioning = contract["versioning"]
    identity = dict.fromkeys(PARSE_KEY_INPUTS + ROUTE_PARSE_KEY_INPUTS.get(route, ()))
    identity.update(source_sha256=source_sha256, route=route, normalizer_version=versioning["normalizer_version"],
                    docling_core_version=installed_version("docling-core"))
    if route == "HWPX_DOCLING_ADAPTER":
        identity["hwpx_adapter_version"] = versioning["hwpx_adapter_version"]
    # HWP route의 PDF identity는 변환기 버전이 정해져 실제 PDF parser를 탈 때 함께 채운다.
    if route == "DOCLING_PDF" or (route == "HWP_PDF_DOCLING" and converter_version is not None):
        # Docling 배포는 docling-slim이고 표·OCR은 PaddleX가 맡으므로 두 쪽의 설치 버전과 모델 identity를 모두 넣는다.
        identity.update(docling_version=installed_version("docling-slim"),
                        docling_parse_version=installed_version("docling-parse"),
                        docling_ibm_models_version=installed_version("docling-ibm-models"),
                        pipeline_config_sha256=pipeline_config_sha256(contract),
                        model_artifacts_sha256=scoped_artifacts_sha256(contract, "parsing"),
                        paddlepaddle_version=installed_version("paddlepaddle"),
                        paddlex_version=installed_version("paddlex"))
    if route == "HWP_PDF_DOCLING":
        identity["converter_version"] = converter_version
    if route == "IMAGE_OCR":
        # 이미지 OCR은 Docling layout·표 engine을 쓰지 않으므로 그 identity는 넣지 않는다. 모델 hash는 OCR 두 모델만이다.
        ocr_folders = {folder for _, folder in contract["routes"]["PDF"]["ocr"]["submodules"].values()}
        identity.update(image_ocr_version=contract["image_ocr"]["image_ocr_version"],
                        image_ocr_config_sha256=image_ocr_config_sha256(contract),
                        model_artifacts_sha256=folder_artifacts_sha256(contract, ocr_folders),
                        paddlepaddle_version=installed_version("paddlepaddle"), paddlex_version=installed_version("paddlex"))
    if route in ("DOCLING_DOCX", "DOCLING_PPTX"):
        # Docling Word·PowerPoint backend와 그 XML 라이브러리만 결과를 바꾼다. layout·표·OCR identity는 넣지 않는다.
        office = contract["office"]
        identity.update(docling_version=installed_version("docling-slim"), office_parser_version=office["office_parser_version"],
                        office_config_sha256=hashlib.sha256(json.dumps({"office": config_identity(contract, "office"), "empty_text_max_chars":
                                                                         contract["document_gate"]["empty_text_max_chars"]},
                                                                        sort_keys=True, separators=(",", ":"),
                                                                        ensure_ascii=False).encode()).hexdigest())
        library = "python-docx" if route == "DOCLING_DOCX" else "python-pptx"
        identity[library.replace("-", "_") + "_version"] = installed_version(library)
    expected = list(versioning["parse_key_inputs"]) + list(versioning.get("route_parse_key_inputs", {}).get(route, []))
    if sorted(identity) != sorted(expected):
        raise PipelineError("parse_key_contract_drift")
    return identity


def parse_key(source_sha256, route, contract, converter_version=None):
    # 부품 버전이 바뀐 route의 문서만 새 key를 받아 선택적으로 재처리되고 과거 결과는 덮어쓰지 않는다.
    identity = parse_identity(source_sha256, route, contract, converter_version)
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()
