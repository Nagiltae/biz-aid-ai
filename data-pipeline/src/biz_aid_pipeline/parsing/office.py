"""DOCX·PPTX 첨부(DOCLING_DOCX·DOCLING_PPTX route). Docling Word·PowerPoint backend가 OOXML을 직접 읽는다.

- 그림의 의미를 해석하지 않는다(VLM 없음). OCR도 쓰지 않는다.
- DOCX에는 page가 없다. 가짜 page를 만들지 않고 문서 순서·제목 경로를 bizaid__office meta로 남긴다(HWPX와 같은 방식).
- PPTX는 Docling이 슬라이드를 page로 둔다(위치 단위 EMU). 그 출력은 바꾸지 않고 슬라이드 번호를 meta에도 남긴다.
- Docling은 실행 환경에 LibreOffice가 있으면 도형(DrawingML)을 그림으로 바꾸려고 외부 프로그램을 부른다.
  같은 원본이 환경에 따라 다른 결과가 되지 않게 그 변환을 항상 끈다(도형 안 글자·텍스트 상자는 Docling이 XML에서 읽는다).
"""
import io
import json
from functools import lru_cache

from docling_core.types.doc import DocItemLabel
from docling_core.types.doc.document import DocumentOrigin

from biz_aid_pipeline.parsing.pdf_assembly import bizaid_meta

FORMATS = {"DOCX": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
           "PPTX": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
HEADING_LABELS = (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER)


class OfficeError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@lru_cache(maxsize=1)
def _converter():
    from docling.backend.msword_backend import MsWordDocumentBackend
    from docling.backend.mspowerpoint_backend import MsPowerpointDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PowerpointFormatOption, WordFormatOption

    class WordBackend(MsWordDocumentBackend):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # BOUNDARY: 외부 LibreOffice로 도형을 렌더링하지 않는다(결과가 설치 여부에 따라 달라지는 것을 막음).
            self.docx_to_pdf_converter, self.docx_to_pdf_converter_init = None, True

    class PowerpointBackend(MsPowerpointDocumentBackend):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.pptx_to_pdf_converter, self.pptx_to_pdf_converter_init = None, True

    return DocumentConverter(allowed_formats=[InputFormat.DOCX, InputFormat.PPTX], format_options={
        InputFormat.DOCX: WordFormatOption(backend=WordBackend),
        InputFormat.PPTX: PowerpointFormatOption(backend=PowerpointBackend)})


def annotate(document, source_sha256, detected_format):
    """모든 item에 원본 SHA·문서 순서·제목 경로(·슬라이드 번호)를 남긴다. 새 위치를 만들지 않고 Docling 구조에서만 읽는다."""
    headings = {}
    for order, (item, _) in enumerate(document.iterate_items(traverse_pictures=True)):
        if item.label in HEADING_LABELS:
            level = 0 if item.label == DocItemLabel.TITLE else getattr(item, "level", 1)
            headings = {key: value for key, value in headings.items() if key < level}
            headings[level] = item.text
        # WHY: Word의 굵게·기울임 서식이 남으면 chunk serializer가 "**…**" 표시를 본문·embedding 입력에 넣는다.
        # PDF·HWPX에는 서식 정보가 없어 생기지 않는 잡음이므로 Office 문서에서만 서식 정보를 지운다(글자·링크는 그대로).
        if getattr(item, "formatting", None) is not None:
            item.formatting = None
        value = {"source_sha256": source_sha256, "format": detected_format, "order": order, "label": item.label.value,
                 "heading_path": [headings[key] for key in sorted(headings)]}
        if detected_format == "PPTX" and getattr(item, "prov", None):
            value["slide"] = item.prov[0].page_no
        if getattr(item, "meta", None) is None:
            item.meta = bizaid_meta("office", value)
        else:
            # Docling이 이미 둔 meta(그림 설명 등)는 지우지 않고 BizAid 위치만 더한다.
            item.meta.set_custom_field("bizaid", "office", json.loads(json.dumps(value, sort_keys=True)))


def parse_office(raw, source_sha256, detected_format, contract, result):
    """DoclingDocument. 문서 상태는 router의 공통 text Gate가 page 없이(HWPX와 같은 문서 단위 글자 기준) 정한다."""
    from docling.datamodel.base_models import ConversionStatus, DocumentStream
    extension, mimetype = FORMATS[detected_format]
    try:
        converted = _converter().convert(DocumentStream(name=f"{source_sha256}.{extension}", stream=io.BytesIO(raw)),
                                         raises_on_error=False)
    except Exception as error:
        raise OfficeError("office_conversion_error:" + type(error).__name__) from None
    if converted.status == ConversionStatus.PARTIAL_SUCCESS:
        raise OfficeError("office_partial_conversion")
    if converted.status != ConversionStatus.SUCCESS or converted.document is None:
        raise OfficeError("office_conversion_failed")
    document = converted.document
    # HWPX와 같은 규칙으로 문서 이름·origin을 원본 SHA 기준으로 고정한다(입력 파일명이 결과에 들어가지 않게).
    document.name = source_sha256
    document.origin = DocumentOrigin(mimetype=mimetype, binary_hash=int(source_sha256[:16], 16), filename=f"{source_sha256}.{extension}")
    annotate(document, source_sha256, detected_format)
    if detected_format == "PPTX":
        result.unit_count = len(document.pages)
    return document
