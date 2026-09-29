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
    elif route in ("DOCLING_PDF", "HWP_PDF_DOCLING"):
        # BOUNDARY: torch·paddle을 포함한 Docling·PP 본체는 PDF 계열 route에서만 적재해 HWPX 경로가 모델 환경에 의존하지 않게 한다.
        from biz_aid_pipeline.parsing.pdf import PdfConversionError, parse_pdf
        pdf_bytes = raw
        if route == "HWP_PDF_DOCLING":
            # HWP는 PDF로 변환한 뒤 같은 production PDF parser를 쓴다. HWP 전용 문서·표 parser는 없다.
            from biz_aid_pipeline.parsing.hwp_pdf import HwpConversionError, convert_hwp, converter_version
            try:
                version = converter_version(contract)
                result.parse_key = parse_key(request.source_sha256, route, contract, version)
                pdf_bytes = convert_hwp(raw, contract)
            except HwpConversionError as error:
                result.status, result.failure_code = "CONVERSION_FAILED", error.code
                return result
            result.derivation = {"intermediate_format": "PDF", "intermediate_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                                 "intermediate_bytes": len(pdf_bytes), "converter_version": version, "persisted": False}
        try:
            # provenance의 source는 항상 원본 byte의 SHA다. 변환 PDF의 SHA는 derivation에만 남는다.
            document, page_count = parse_pdf(pdf_bytes, request.source_sha256, contract, result)
        except PdfConversionError as error:
            result.status, result.failure_code = "PARSE_FAILED", error.code
            return result
        result.unit_count = page_count
    else:
        raise PipelineError("enabled_route_without_handler")
    normalize_document(document, result)
    gated = apply_gate(result, document, contract, page_count=page_count)
    if gated.ocr and (gated.status == "OCR_REQUIRED" or gated.ocr["insufficient_pages"]):
        # BOUNDARY: OCR 부족 page는 warning과 insufficient_pages metadata로 드러내고, 문서 status는 문서 text Gate가 정한다.
        # WHY: OCR은 "읽을 것이 없는 page"(빈 쪽·쪽 번호만 있는 쪽)와 "읽지 못한 scan page"를 추측 없이 구분할 근거가 없다.
        # page 하나로 문서 전체를 OCR_REQUIRED로 두면 PARSED artifact가 저장되지 않아 나머지 본문이 사라진다(3-B.13 HWP 2건).
        gated.warn("OCR_TEXT_INSUFFICIENT")
    return gated
