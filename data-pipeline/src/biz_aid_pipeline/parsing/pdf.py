import io
import json
import logging
import re
import threading
from contextlib import contextmanager
from functools import lru_cache

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.io import DocumentStream

from biz_aid_pipeline.parsing.models import docling_artifacts_path, model_artifacts_sha256, pipeline_identity


# BOUNDARY: docling-ibm-models 4.0.3은 표 cell 탈락을 구조화 결과로 주지 않고 이 logger의 WARNING으로만 알린다.
TABLE_DROP_LOGGER = "MatchingPostProcessor"
TABLE_DROP_MESSAGE = re.compile(r"(\d+) of (\d+) pdf cells matched neither a row nor a column band")
_CONVERSION_LOCK = threading.Lock()


class _TableDropFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.events = 0
        self.cells = 0
        self.unparsed = 0

    def filter(self, record):
        if record.levelno >= logging.WARNING and "matched neither a row nor a column" in record.getMessage():
            self.events += 1
            match = TABLE_DROP_MESSAGE.search(record.getMessage())
            if match:
                self.cells += int(match[1])
            else:
                self.unparsed += 1
        return True


@contextmanager
def table_drop_capture():
    # handler를 붙이면 docling의 hasHandlers() 분기가 바뀌므로 filter만 붙였다 떼어 전역 logging 설정을 바꾸지 않는다.
    logger = logging.getLogger(TABLE_DROP_LOGGER)
    capture = _TableDropFilter()
    logger.addFilter(capture)
    try:
        yield capture
    finally:
        logger.removeFilter(capture)


class PdfConversionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@lru_cache(maxsize=2)
def _converter(identity_json, artifacts_path):
    # 모델 적재 비용이 커서 같은 설정의 변환기만 재사용한다. 설정이 다르면 다른 인스턴스다.
    identity = json.loads(identity_json)
    options = PdfPipelineOptions(**identity["docling_options"], artifacts_path=artifacts_path)
    # EXCEPTION: dict를 그대로 넘기면 base option class로 변환돼 mode가 사라지므로 구체 class로 만든다.
    options.table_structure_options = TableStructureOptions(**identity["table_structure_options"])
    spec = options.layout_options.model_spec
    options.layout_options.model_spec = spec.model_copy(update={"revision": identity["layout_model_revision"]})
    return DocumentConverter(allowed_formats=[InputFormat.PDF],
                             format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def converter(contract):
    # 모델을 적재하기 전에 artifact identity를 확인한다. 전체 hash는 경로별로 한 번만 계산된다.
    model_artifacts_sha256(contract)
    return _converter(json.dumps(pipeline_identity(contract), sort_keys=True), str(docling_artifacts_path(contract)))


def convert_pdf(pdf_bytes, source_sha256, contract, result=None):
    """PDF byte를 Docling으로 DoclingDocument와 page 수로 바꾼다. HWP→PDF 경로도 이 함수를 그대로 재사용한다."""
    stream = DocumentStream(name=f"{source_sha256}.pdf", stream=io.BytesIO(pdf_bytes))
    # RISK: Docling pipeline은 내부 thread를 쓰므로 변환을 직렬화해야 다른 문서의 탈락 log가 섞이지 않는다.
    with _CONVERSION_LOCK, table_drop_capture() as drops:
        try:
            # EXCEPTION: 손상 PDF는 Docling 예외 종류가 넓어 raises_on_error=False의 상태로만 판정한다.
            outcome = converter(contract).convert(stream, raises_on_error=False,
                                                  max_file_size=contract["input"]["max_source_bytes"])
        except Exception as error:
            raise PdfConversionError("docling_conversion_error:" + type(error).__name__) from None
    if result is not None and drops.events:
        # PARSED 여부와 별개로 표 text 손실 가능성을 결과 evidence에 남긴다.
        result.warn("TABLE_CELL_DROP_DETECTED", drops.events)
        if drops.cells:
            result.warn("TABLE_CELLS_DROPPED", drops.cells)
        if drops.unparsed:
            result.warn("TABLE_CELL_DROP_COUNT_UNPARSED", drops.unparsed)
    if outcome.status == ConversionStatus.PARTIAL_SUCCESS:
        # RISK: 일부 page 실패 결과를 성공으로 받으면 누락 page가 조용히 사라지므로 실패로 드러낸다.
        raise PdfConversionError("docling_partial_conversion")
    if outcome.status != ConversionStatus.SUCCESS or outcome.document is None:
        raise PdfConversionError("docling_conversion_failed")
    page_count = len(outcome.document.pages)
    if page_count < 1:
        raise PdfConversionError("pdf_no_pages")
    return outcome.document, page_count
