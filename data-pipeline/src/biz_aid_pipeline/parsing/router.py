import hashlib

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing.hwpx import HwpxDoclingAdapter, HwpxError
from biz_aid_pipeline.parsing.models import ParseResult, parse_key, parsing_contract
from biz_aid_pipeline.parsing.quality import apply_gate, normalize_document


def route_for(detected_format, contract):
    # BOUNDARY: 파일명 확장자·Content-Type은 관찰값이므로 Phase 2 signature 판별 결과만 route를 결정한다.
    spec = contract["routes"].get(detected_format)
    return (spec["route"], spec["enabled"]) if spec else ("UNSUPPORTED", False)


def parse_document(request, raw, contract=None):
    contract = contract or parsing_contract()
    # 입력 byte가 DB metadata와 다르면 parser 결과가 아니라 저장소 무결성 사고이므로 결과를 만들지 않는다.
    if len(raw) != request.byte_size or hashlib.sha256(raw).hexdigest() != request.source_sha256:
        raise PipelineError("parse_input_integrity_mismatch")
    if request.byte_size > contract["input"]["max_source_bytes"]:
        raise PipelineError("parse_input_size_exceeded")
    route, enabled = route_for(request.detected_format, contract)
    result = ParseResult(request.source_sha256, request.detected_format, route,
                         parse_key(request.source_sha256, route, contract), "ROUTE_NOT_ENABLED")
    if route == "UNSUPPORTED":
        result.status, result.failure_code = "UNSUPPORTED_FORMAT", "unknown_detected_format"
        return result
    if not enabled:
        result.failure_code = "policy_pending" if route == "POLICY_PENDING" else "route_not_enabled"
        return result
    page_count = None
    if route == "HWPX_DOCLING_ADAPTER":
        try:
            document = HwpxDoclingAdapter(contract).convert(raw, request.source_sha256, result)
        except HwpxError as error:
            result.status, result.failure_code = error.status, error.code
            return result
    elif route == "DOCLING_PDF":
        # BOUNDARY: torch·paddle을 포함한 Docling·PP 본체는 PDF route에서만 적재해 HWPX 경로가 모델 환경에 의존하지 않게 한다.
        from biz_aid_pipeline.parsing.pdf import PdfConversionError, parse_pdf
        try:
            document, page_count = parse_pdf(raw, request.source_sha256, contract, result)
        except PdfConversionError as error:
            result.status, result.failure_code = "PARSE_FAILED", error.code
            return result
        result.unit_count = page_count
    else:
        raise PipelineError("enabled_route_without_handler")
    normalize_document(document, result)
    return apply_gate(result, document, contract, page_count=page_count)
