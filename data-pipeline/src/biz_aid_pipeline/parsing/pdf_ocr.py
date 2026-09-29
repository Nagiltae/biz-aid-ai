"""OCR_REQUIRED PDF의 text layer. native text가 부족한 page만 PaddleX PP-OCRv5(한국어 인식)로 읽는다.

결과는 native text layer와 같은 모양(point 좌표의 줄·단어)으로 돌려주어 기존 PP 표·조립 코드가 그대로 쓴다.
Visual VLM이 아니며 문서 구조를 해석하지 않는다.
"""
import json
import os
import re
import threading
from dataclasses import dataclass
from functools import lru_cache

from biz_aid_pipeline.parsing.models import docling_artifacts_path, installed_version, model_artifacts_sha256
from biz_aid_pipeline.parsing.pdf_tables import paddlex_create_pipeline

WHITESPACE = re.compile(r"\s")
# RISK: PaddlePaddle predictor의 thread 안전성이 보장되지 않아 OCR 추론을 직렬화한다.
_OCR_LOCK = threading.Lock()


class PdfOcrError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass
class OcrLine:
    page: int
    bbox: list
    text: str
    confidence: float


def ocr_identity(contract):
    spec = contract["routes"]["PDF"]["ocr"]
    models = " + ".join(folder.split("--", 1)[1] for _, folder in spec["submodules"].values())
    return f"paddlex {installed_version('paddlex')} {spec['pipeline']} ({models}) + paddlepaddle {installed_version('paddlepaddle')}"


def page_native_chars(pdf):
    """page별 native 글자 수. OCR할 page를 고르는 기준이며 공백은 세지 않는다."""
    counts = {}
    for index in range(len(pdf)):
        text_page = pdf[index].get_textpage()
        try:
            counts[index + 1] = len(WHITESPACE.sub("", text_page.get_text_range()))
        finally:
            text_page.close()
    return counts


RASTER_IMAGE = 3  # pdfium page object 종류 중 raster image(FPDF_PAGEOBJ_IMAGE) 값이다.


def page_raster_images(pdf):
    """page별 raster image 객체 수(form XObject 안 포함). OCR이 새 text를 얻을 수 있는 입력인지 판단하는 PDF 구조 정보다."""
    return {index + 1: sum(1 for item in pdf[index].get_objects(max_depth=8) if item.type == RASTER_IMAGE)
            for index in range(len(pdf))}


def select_ocr_pages(native_chars, raster_images, threshold):
    """native text가 기준 이하인 page 중 OCR할 page. native text가 있고 raster image가 없는 page는 native를 유지한다."""
    # WHY: 그런 page의 글자는 모두 native text이므로 OCR은 같은 글자를 오인식 위험과 함께 다시 읽을 뿐이다(native 우선).
    # 3-C 100건에서 HWP 25건·PDF 2건, 77쪽의 정확한 native text가 OCR 결과로 교체됐다. native text가 0인 page는 벡터 글꼴일 수 있어 OCR한다.
    return [page for page, chars in native_chars.items()
            if chars <= threshold and (chars == 0 or raster_images.get(page, 0) > 0)]


def ocr_text_chars(lines):
    """한 page OCR 결과의 공백 제외 글자 수. native page 선택과 같은 기준으로 결과 충분성을 판정한다."""
    return sum(len(WHITESPACE.sub("", line.text)) for line in lines)


def line_words(line):
    """OCR 줄을 공백 기준 단어로 나누고 글자 수 비율로 x 범위를 나눈다. 표 cell text 배정에 쓰는 근사 위치다."""
    # RISK: 글자 폭이 고르지 않으면 단어 경계가 몇 pt 어긋날 수 있다. 줄 전체 text는 조립 단계에서 손실 없이 보존된다.
    parts = line.text.split()
    total = sum(len(part) for part in parts) + max(len(parts) - 1, 0)
    left, top, right, bottom = line.bbox
    width, cursor, words = right - left, 0, []
    for part in parts:
        start, end = cursor / max(total, 1), (cursor + len(part)) / max(total, 1)
        words.append(([left + width * start, top, left + width * end, bottom], part))
        cursor += len(part) + 1
    return words


@lru_cache(maxsize=1)
def _pipeline(spec_json, runtime_json, artifacts_path):
    spec = json.loads(spec_json)
    create_pipeline = paddlex_create_pipeline(json.loads(runtime_json))
    if create_pipeline is None:
        raise PdfOcrError("ocr_engine_error:RuntimeFlagsNotApplied")
    submodules = {name: dict(spec["module_options"].get(name, {}), module_name=module,
                             model_name=folder.split("--", 1)[1], model_dir=os.path.join(artifacts_path, folder))
                  for name, (module, folder) in spec["submodules"].items()}
    # BOUNDARY: 문서 방향·왜곡 보정·줄 방향 모델은 쓰지 않는다. 검출과 한국어 인식 두 모델만 적재한다.
    config = {"pipeline_name": spec["pipeline"], "text_type": spec["text_type"], "use_doc_preprocessor": False,
              "use_textline_orientation": False, "SubModules": submodules}
    return create_pipeline(config=config, device=spec["device"])


def pipeline(contract):
    model_artifacts_sha256(contract)
    spec = contract["routes"]["PDF"]["ocr"]
    runtime = contract["routes"]["PDF"]["table_engine"]["runtime_environment"]
    return _pipeline(json.dumps(spec, sort_keys=True), json.dumps(runtime, sort_keys=True), str(docling_artifacts_path(contract)))


def ocr_pages(pdf, pages, contract):
    """지정한 page를 렌더링해 OCR한다. 좌표는 page 좌상단 원점 point다. 실패는 PdfOcrError로 올린다."""
    import numpy
    scale = contract["routes"]["PDF"]["ocr"]["render_scale"]
    with _OCR_LOCK:
        try:
            model = pipeline(contract)
            lines = {}
            for page_no in pages:
                image = numpy.ascontiguousarray(pdf[page_no - 1].render(scale=scale).to_numpy()[:, :, :3])
                output = list(model.predict(image))[0]
                lines[page_no] = [OcrLine(page_no, [float(v) / scale for v in box], text, float(score))
                                  for text, score, box in zip(output["rec_texts"], output["rec_scores"], output["rec_boxes"])
                                  if text.strip()]
            return lines
        except PdfOcrError:
            raise
        except Exception as error:
            raise PdfOcrError("ocr_engine_error:" + type(error).__name__) from None
