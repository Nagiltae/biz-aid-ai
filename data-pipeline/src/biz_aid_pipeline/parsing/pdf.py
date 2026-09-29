import io
import json
import threading
from functools import lru_cache

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.io import DocumentStream

from biz_aid_pipeline.parsing.models import docling_artifacts_path, model_artifacts_sha256, pipeline_identity


_CONVERSION_LOCK = threading.Lock()


class PdfConversionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@lru_cache(maxsize=2)
def _converter(identity_json, artifacts_path):
    # 모델 적재 비용이 커서 같은 설정의 변환기만 재사용한다. 설정이 다르면 다른 인스턴스다.
    identity = json.loads(identity_json)
    # BOUNDARY: 표 구조는 PP-TableMagic이 맡으므로 Docling은 layout·읽기 순서만 만들고 TableFormer를 실행하지 않는다.
    options = PdfPipelineOptions(**identity["docling_options"], artifacts_path=artifacts_path)
    spec = options.layout_options.model_spec
    options.layout_options.model_spec = spec.model_copy(update={"revision": identity["layout_model_revision"]})
    return DocumentConverter(allowed_formats=[InputFormat.PDF],
                             format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def converter(contract):
    # 모델을 적재하기 전에 artifact identity를 확인한다. 전체 hash는 경로별로 한 번만 계산된다.
    model_artifacts_sha256(contract)
    return _converter(json.dumps(pipeline_identity(contract), sort_keys=True), str(docling_artifacts_path(contract)))


def convert_pdf(pdf_bytes, source_sha256, contract):
    """PDF byte를 Docling으로 DoclingDocument backbone과 page 수로 바꾼다. 표 구조는 parse_pdf에서 PP가 채운다."""
    stream = DocumentStream(name=f"{source_sha256}.pdf", stream=io.BytesIO(pdf_bytes))
    # RISK: Docling pipeline은 내부 thread를 쓰므로 한 process의 변환을 직렬화한다.
    with _CONVERSION_LOCK:
        try:
            # EXCEPTION: 손상 PDF는 Docling 예외 종류가 넓어 raises_on_error=False의 상태로만 판정한다.
            outcome = converter(contract).convert(stream, raises_on_error=False,
                                                  max_file_size=contract["input"]["max_source_bytes"])
        except Exception as error:
            raise PdfConversionError("docling_conversion_error:" + type(error).__name__) from None
    if outcome.status == ConversionStatus.PARTIAL_SUCCESS:
        # RISK: 일부 page 실패 결과를 성공으로 받으면 누락 page가 조용히 사라지므로 실패로 드러낸다.
        raise PdfConversionError("docling_partial_conversion")
    if outcome.status != ConversionStatus.SUCCESS or outcome.document is None:
        raise PdfConversionError("docling_conversion_failed")
    page_count = len(outcome.document.pages)
    if page_count < 1:
        raise PdfConversionError("pdf_no_pages")
    return outcome.document, page_count


def parse_pdf(pdf_bytes, source_sha256, contract, result):
    """PDF production 경계: Docling backbone → PP-TableMagic 표 → 같은 DoclingDocument로 조립. HWP→PDF도 재사용한다."""
    import pypdfium2
    from biz_aid_pipeline.parsing.pdf_assembly import assemble
    from biz_aid_pipeline.parsing.pdf_tables import PdfTableError, detect_tables
    from biz_aid_pipeline.parsing.quality import text_chars
    document, page_count = convert_pdf(pdf_bytes, source_sha256, contract)
    if text_chars(document) / page_count <= contract["document_gate"]["pdf_ocr_required_max_chars_per_page"]:
        # BOUNDARY: native text가 부족한 문서는 apply_gate가 OCR_REQUIRED로 분리한다. 표 cell text의 출처가 없으므로 PP를 실행하지 않는다.
        return document, page_count
    try:
        tables, table_pages = detect_tables(pdf_bytes, contract)
    except PdfTableError as error:
        # BOUNDARY: 표 engine 실패는 다른 표 parser로 넘기지 않고 문서 실패로 드러낸다.
        raise PdfConversionError(error.code) from None
    if table_pages != page_count:
        raise PdfConversionError("pdf_page_count_mismatch")
    pdf = pypdfium2.PdfDocument(pdf_bytes)
    try:
        assemble(document, pdf, tables, source_sha256, contract, result)
    finally:
        pdf.close()
    return document, page_count
