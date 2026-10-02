"""PNG·JPEG 첨부(IMAGE_OCR route). 이미지를 세로 타일로 나눠 PDF route와 같은 고정 PP-OCRv5(한국어 인식)로 읽는다.

- 그림의 의미를 해석하지 않는다(VLM 없음). 글자 줄만 읽는다.
- 각 타일은 DoclingDocument의 page다. page 크기는 원본 이미지 전체 크기로 두어 bbox가 원본 이미지 좌표(px)로 남는다.
- 폭은 줄이지 않는다. 전체 픽셀이 상한을 넘으면 잘라 읽지 않고 문서 단위 실패로 기록한다.
- 타일 경계의 겹친 영역에서 같은 줄을 두 번 넣지 않는다(중심이 속한 타일만 줄을 가진다 + 같은 글자·같은 위치 제거).
"""
import io
import re

from docling_core.types.doc import DocItemLabel, DoclingDocument, Size
from docling_core.types.doc.document import DocumentOrigin

from biz_aid_pipeline.parsing.pdf_assembly import bizaid_meta, ocr_reading_order, provenance
from biz_aid_pipeline.parsing.pdf_ocr import _OCR_LOCK, OcrLine, PdfOcrError, ocr_identity, ocr_text_chars, pipeline

MIMETYPES = {"PNG": "image/png", "JPEG": "image/jpeg"}
SPACES = re.compile(r"\s+")


class ImageOcrError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def tile_ranges(height, spec):
    """세로 타일의 (시작 y, 끝 y). 마지막 타일도 같은 높이로 맞춰 아래쪽이 짧은 조각으로 남지 않게 한다."""
    tile = spec["tile_height_px"]
    if height <= tile:
        return [(0, height)]
    step = tile - round(tile * spec["tile_overlap_ratio"])
    starts = list(range(0, height - tile, step)) + [height - tile]
    return [(start, start + tile) for start in sorted(set(starts))]


def ownership_bounds(tiles):
    """타일별로 줄을 가질 세로 구간. 이웃 타일이 겹친 영역은 가운데에서 나눈다."""
    bounds = []
    for index, (start, end) in enumerate(tiles):
        upper = 0 if index == 0 else (tiles[index - 1][1] + start) / 2
        lower = tiles[-1][1] if index == len(tiles) - 1 else (end + tiles[index + 1][0]) / 2
        bounds.append((upper, lower))
    return bounds


def overlap_ratio(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return width * height / max(smaller, 1e-9)


def merge_tile_lines(tile_lines, tiles):
    """타일별 줄(원본 좌표)에서 겹친 영역의 중복을 없앤다. 줄의 page는 그 줄을 가진 타일 번호다."""
    kept = []
    for page_no, ((upper, lower), lines) in enumerate(zip(ownership_bounds(tiles), tile_lines), start=1):
        for line in lines:
            center = (line.bbox[1] + line.bbox[3]) / 2
            if not upper <= center < lower and not (page_no == len(tiles) and center == lower):
                continue
            text = SPACES.sub("", line.text)
            # 경계에서 중심이 조금 어긋난 같은 줄이 두 타일에 모두 남는 경우를 한 번 더 막는다.
            if any(SPACES.sub("", other.text) == text and overlap_ratio(other.bbox, line.bbox) >= 0.5 for other in kept):
                continue
            kept.append(OcrLine(page_no, line.bbox, line.text, line.confidence))
    return kept


def load_image(raw, detected_format, spec):
    """이미지를 열어 RGB numpy 배열로 돌려준다. 픽셀 상한은 디코딩 전에 확인한다."""
    import numpy
    from PIL import Image, ImageOps
    try:
        image = Image.open(io.BytesIO(raw))
        width, height = image.size
        if width * height > spec["max_total_pixels"]:
            raise ImageOcrError("image_pixels_exceeded")
        expected = {"PNG": "PNG", "JPEG": "JPEG"}[detected_format]
        if image.format != expected:
            raise ImageOcrError("image_format_mismatch")
        # EXIF 회전 정보가 있으면 사람이 보는 방향으로 돌린다(크기 축소 없음). 투명 배경은 흰색으로 합친다.
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(background, image)
        image = image.convert("RGB")
        return numpy.asarray(image)
    except ImageOcrError:
        raise
    except Exception as error:
        raise ImageOcrError("image_decode_failed:" + type(error).__name__) from None


def ocr_tiles(array, tiles, contract):
    """타일마다 OCR한다. PDF OCR과 같은 모델·옵션이며 입력은 BGR 배열이다(PDF 렌더 결과와 같은 채널 순서)."""
    import numpy
    min_confidence = contract["image_ocr"]["min_line_confidence"]
    results = []
    with _OCR_LOCK:
        try:
            model = pipeline(contract)
            for start, end in tiles:
                tile = numpy.ascontiguousarray(array[start:end, :, ::-1])
                output = list(model.predict(tile))[0]
                results.append([OcrLine(0, [float(box[0]), float(box[1]) + start, float(box[2]), float(box[3]) + start], text, float(score))
                                for text, score, box in zip(output["rec_texts"], output["rec_scores"], output["rec_boxes"])
                                if text.strip() and float(score) >= min_confidence])
            return results
        except PdfOcrError as error:
            raise ImageOcrError(error.code) from None
        except Exception as error:
            raise ImageOcrError("ocr_engine_error:" + type(error).__name__) from None


def parse_image(raw, source_sha256, detected_format, contract, result):
    """(DoclingDocument, 타일 수). 문서 상태는 router의 공통 text Gate가 타일을 page로 보고 정한다."""
    spec = contract["image_ocr"]
    array = load_image(raw, detected_format, spec)
    height, width = array.shape[:2]
    tiles = tile_ranges(height, spec)
    tile_lines = ocr_tiles(array, tiles, contract)
    lines = merge_tile_lines(tile_lines, tiles)
    engine = ocr_identity(contract)
    document = DoclingDocument(name=source_sha256, origin=DocumentOrigin(
        mimetype=MIMETYPES[detected_format], binary_hash=int(source_sha256[:16], 16),
        filename=f"{source_sha256}.{detected_format.lower()}"))
    for page_no in range(1, len(tiles) + 1):
        # BOUNDARY: page 크기를 원본 전체 크기로 두어 chunk provenance의 bbox가 원본 이미지 좌표 그대로 남는다.
        document.add_page(page_no=page_no, size=Size(width=width, height=height))
    by_page = {}
    for line in lines:
        by_page.setdefault(line.page, []).append(line)
    for page_no in sorted(by_page):
        start, end = tiles[page_no - 1]
        for line in ocr_reading_order(by_page[page_no]):
            item = document.add_text(label=DocItemLabel.TEXT, text=line.text, prov=provenance(page_no, line.bbox, line.text))
            # OCR text는 모델 파생 text다. 원본 SHA·타일·원본 좌표(px)·confidence·engine identity를 남긴다.
            item.meta = bizaid_meta("ocr", {"source_sha256": source_sha256, "page": page_no, "tile_y_px": [start, end],
                                            "bbox_px": [round(value, 2) for value in line.bbox], "unit": "px",
                                            "confidence": round(line.confidence, 4), "engine": engine})
    threshold = contract["document_gate"]["pdf_ocr_required_max_chars_per_page"]
    result.ocr = {"engine": engine, "pages": list(range(1, len(tiles) + 1)), "lines": len(lines),
                  "insufficient_pages": [page for page in range(1, len(tiles) + 1) if ocr_text_chars(by_page.get(page, [])) <= threshold],
                  "image_px": [width, height], "tiles_y_px": [list(tile) for tile in tiles],
                  "duplicate_lines_removed": sum(len(page) for page in tile_lines) - len(lines)}
    result.warn("IMAGE_OCR_APPLIED", len(tiles))
    return document, len(tiles)
