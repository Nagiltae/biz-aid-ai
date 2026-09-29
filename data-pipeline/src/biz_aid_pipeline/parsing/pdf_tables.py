"""PDF 표 engine. 표 검출·구조는 PP-TableMagic, cell text는 PDF native text layer가 맡는다.

3-B.2~3-B.4에서 검증한 rectangle 주입 + 검출 box 경계 grid adapter + 표 품질 Gate만 제품 경로로 옮겼다.
증명되지 않은 표는 구조를 만들지 않고 TABLE_QUALITY_FAILED로 돌려 조립 단계가 native text로 보존한다.
"""
import json
import os
import re
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from biz_aid_pipeline.parsing.models import docling_artifacts_path, model_artifacts_sha256

TABLE_VALID = "TABLE_VALID"
TABLE_QUALITY_FAILED = "TABLE_QUALITY_FAILED"
# 금액·비율·날짜 같은 값이 cell 밖으로 빠지면 표를 믿을 수 없으므로 이 token의 손실만 실패 사유로 본다.
TOKEN_PATTERNS = (
    ("date", re.compile(r"\d{4}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}\s*일?|\d{1,2}\s*[./]\s*\d{1,2}\s*\.?\s*\([월화수목금토일]\)")),
    ("period", re.compile(r"\d+(?:\.\d+)?\s*(?:개월|년간|주간|일간|시간|년|주)")),
    ("amount", re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:조|억|천만|백만|만|천)?\s*원")),
    ("percent", re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|퍼센트)")),
    ("number", re.compile(r"\d[\d,]*(?:\.\d+)?")),
)
# RISK: PaddlePaddle predictor는 thread 안전성이 보장되지 않아 한 process 안의 표 추론을 직렬화한다.
_PP_LOCK = threading.Lock()


class PdfTableError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass
class PdfTable:
    """PP 표 영역 하나. bbox는 page 좌상단 원점 point 좌표이며 cells는 VALID일 때만 채운다."""

    page: int
    bbox: list
    verdict: str
    reasons: list = field(default_factory=list)
    cells: list | None = None


def center_in(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def word_center(word):
    box = word[0]
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def critical_tokens(text):
    """겹치는 표현은 앞선 종류가 우선한다. 예: '5천만원'은 amount이며 number로 중복 세지 않는다."""
    text = unicodedata.normalize("NFKC", text or "")
    tokens, taken = Counter(), [False] * len(text)
    for kind, pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            if any(taken[match.start():match.end()]):
                continue
            for index in range(match.start(), match.end()):
                taken[index] = True
            tokens[(kind, re.sub(r"\s+", "", unicodedata.normalize("NFKC", match.group())))] += 1
    return tokens


def native_rects(page, scale, height):
    """PP 입력용 text 위치. pdfium 사각형을 OCR 결과 형식으로 넘겨 OCR 모델 없이 표 cell 보정에 쓰게 한다."""
    text_page = page.get_textpage()
    boxes, texts = [], []
    try:
        for index in range(text_page.count_rects()):
            left, bottom, right, top = text_page.get_rect(index)
            text = text_page.get_text_bounded(left, bottom, right, top).strip()
            if text:
                boxes.append([left * scale, (height - top) * scale, right * scale, (height - bottom) * scale])
                texts.append(text)
    finally:
        text_page.close()
    return boxes, texts


def native_words(page, scale, height):
    """cell text용 단어. 글자 단위로 읽어야 겹치는 italic 사각형이 이웃 글자를 중복시키지 않는다."""
    text_page = page.get_textpage()
    words, current = [], None
    try:
        for index in range(text_page.count_chars()):
            char = text_page.get_text_range(index, 1)
            if not char.strip():
                current = None
                continue
            left, bottom, right, top = text_page.get_charbox(index)
            box = [left * scale, (height - top) * scale, right * scale, (height - bottom) * scale]
            if current:
                last = current["box"]
                size = max(last[3] - last[1], 1)
                same_line = box[1] < last[3] + 0.3 * size and box[3] > last[1] - 0.3 * size
                # BOUNDARY: italic 글자 box는 서로 겹치고(간격 약 -0.2×높이) 쉼표 box는 작고 낮으므로
                # 단어 높이 기준 -0.6~+0.5 간격과 위아래 30% 여유로 같은 단어를 판단한다.
                if same_line and -0.6 * size <= box[0] - last[2] <= 0.5 * size:
                    current["box"] = [min(last[0], box[0]), min(last[1], box[1]), max(last[2], box[2]), max(last[3], box[3])]
                    current["text"] += char
                    continue
            current = {"box": box, "text": char}
            words.append(current)
    finally:
        text_page.close()
    return [(w["box"], w["text"]) for w in words]


def reading_order_text(words):
    lines = []
    for (x1, y1, x2, y2), text in sorted(words, key=lambda w: ((w[0][1] + w[0][3]) / 2, w[0][0])):
        cy, height = (y1 + y2) / 2, y2 - y1
        if lines and abs(lines[-1][0] - cy) <= 0.5 * max(height, 1):
            lines[-1][1].append((x1, text))
        else:
            lines.append([cy, [(x1, text)]])
    return "\n".join(" ".join(t for _, t in sorted(items)) for _, items in lines)


def edge_lines(values, tolerance):
    lines = []
    for value in sorted(values):
        if lines and value - lines[-1][-1] <= tolerance:
            lines[-1].append(value)
        else:
            lines.append([value])
    return [sum(group) / len(group) for group in lines]


def grid_cells(detections, tolerance):
    """검출 box 경계만으로 논리 grid를 만든다. 같은 칸을 두 box가 차지하거나 폭 0 box가 있으면 증명 실패다."""
    columns = edge_lines([v for b in detections for v in (b[0], b[2])], tolerance)
    rows = edge_lines([v for b in detections for v in (b[1], b[3])], tolerance)
    nearest = lambda lines, value: min(range(len(lines)), key=lambda i: abs(lines[i] - value))
    cells, owner, conflicts, degenerate = [], set(), 0, 0
    for box in detections:
        c1, c2 = nearest(columns, box[0]), nearest(columns, box[2])
        r1, r2 = nearest(rows, box[1]), nearest(rows, box[3])
        if c2 <= c1 or r2 <= r1:
            degenerate += 1
            continue
        for slot in ((r, c) for r in range(r1, r2) for c in range(c1, c2)):
            conflicts += slot in owner
            owner.add(slot)
        cells.append({"row": r1, "col": c1, "rowspan": r2 - r1, "colspan": c2 - c1, "text": "", "box": box})
    return cells, conflicts == 0 and degenerate == 0


def ragged(cells):
    """행마다 차지한 폭이 다르면 행·열 grid로 표현할 수 없다."""
    widths = Counter()
    for cell in cells:
        for r in range(cell["row"], cell["row"] + cell["rowspan"]):
            widths[r] = max(widths[r], cell["col"] + cell["colspan"])
    return len(set(widths.values())) > 1


def fill_cells(cells, words):
    """단어 중심이 든 가장 작은 cell에 단어를 넣고 cell 안에서는 읽기 순서로 잇는다. cell 밖 단어는 따로 돌려준다."""
    area = lambda b: max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    assigned, unassigned = [[] for _ in cells], []
    for word in words:
        owners = [i for i, cell in enumerate(cells) if center_in(cell["box"], *word_center(word))]
        if owners:
            assigned[min(owners, key=lambda i: area(cells[i]["box"]))].append(word)
        else:
            unassigned.append(word)
    filled = [{k: v for k, v in dict(cell, text=reading_order_text(parts)).items() if k != "box"}
              for cell, parts in zip(cells, assigned)]
    return filled, unassigned


def assess_table(cell_boxes, td_count, table_words, engine):
    """표 하나의 fail-closed 판정. 사유가 하나라도 있으면 구조를 버리고 TABLE_QUALITY_FAILED다."""
    cells, proven = grid_cells(cell_boxes, engine["edge_tolerance_px"]) if cell_boxes else ([], False)
    if not proven:
        return TABLE_QUALITY_FAILED, ["grid_unproven"], None
    reasons = []
    if ragged(cells):
        reasons.append("impossible_row_col_grid")
    filled, unassigned = fill_cells(cells, table_words)
    if critical_tokens(" ".join(text for _, text in unassigned)):
        reasons.append("critical_native_token_unexplained_loss")
    native_chars = len("".join(text for _, text in table_words))
    if td_count <= 1 and native_chars > engine["empty_structure_max_chars"]:
        reasons.append("empty_structure_with_substantial_text")
    return (TABLE_QUALITY_FAILED, reasons, None) if reasons else (TABLE_VALID, [], filled)


@lru_cache(maxsize=1)
def _pipeline(engine_json, artifacts_path):
    # 모델 적재 비용이 커서 같은 설정·경로의 pipeline만 재사용한다.
    engine = json.loads(engine_json)
    # BOUNDARY: 실행 중 모델 원격 확인·다운로드를 막는다. 모델은 준비된 artifact 경로에서만 읽는다.
    os.environ.update(engine["runtime_environment"])
    from paddlex import create_pipeline
    from paddlex.utils import flags
    # RISK: Linux x86 wheel은 oneDNN을 포함해 PaddleX가 기본으로 켜고, Paddle 3.3.1 PIR oneDNN 실행기는 layout 모델에서
    # NotImplementedError를 낸다(macOS arm64 wheel에는 oneDNN이 없어 드러나지 않았다). paddlex가 먼저 import돼 flag가 이미 켜졌다면 멈춘다.
    if flags.ENABLE_MKLDNN_BYDEFAULT or not flags.DISABLE_MODEL_SOURCE_CHECK:
        raise PdfTableError("pp_table_engine_error:RuntimeFlagsNotApplied")
    submodules = {name: {"module_name": module, "model_name": folder.split("--", 1)[1],
                         "model_dir": os.path.join(artifacts_path, folder)}
                  for name, (module, folder) in engine["submodules"].items()}
    # BOUNDARY: OCR·문서 전처리 모델은 config에서 빼서 적재 자체를 막는다. OCR이 호출되면 실행이 실패한다.
    config = {"pipeline_name": engine["pipeline"], "use_doc_preprocessor": engine["use_doc_preprocessor"],
              "use_layout_detection": engine["use_layout_detection"], "use_ocr_model": engine["use_ocr_model"],
              "SubModules": submodules}
    return create_pipeline(config=config, device=engine["device"])


def pipeline(contract):
    model_artifacts_sha256(contract)
    engine = contract["routes"]["PDF"]["table_engine"]
    return _pipeline(json.dumps(engine, sort_keys=True), str(docling_artifacts_path(contract)))


def flat_box(values):
    values = [float(v) for v in (values.tolist() if hasattr(values, "tolist") else values)]
    xs, ys = values[0::2], values[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def page_tables(model, page, page_no, engine):
    """한 page를 PP로 추론해 표 영역마다 판정한다. 좌표는 render px로 계산하고 point로 돌려준다."""
    import numpy
    scale = engine["render_scale"]
    height = page.get_size()[1]
    image = numpy.ascontiguousarray(page.render(scale=scale).to_numpy()[:, :, :3])
    boxes, texts = native_rects(page, scale, height)
    ocr = {"rec_boxes": numpy.array(boxes, dtype=float).reshape(-1, 4), "rec_texts": texts,
           "rec_scores": [1.0] * len(texts), "doc_preprocessor_res": {"output_img": image},
           "rec_polys": [numpy.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=float) for x1, y1, x2, y2 in boxes]}
    ocr["dt_polys"] = ocr["rec_polys"]
    words = native_words(page, scale, height)
    tables = []
    for output in model.predict(image, use_ocr_model=False, overall_ocr_res=ocr,
                                use_table_orientation_classify=engine["use_table_orientation_classify"],
                                use_ocr_results_with_table_cells=engine["use_ocr_results_with_table_cells"]):
        layout = [box["coordinate"] for box in output["layout_det_res"]["boxes"] if box["label"] == "table"]
        for position, result in enumerate(output.get("table_res_list", [])):
            # table_region_id는 layout 표 box 순서의 1부터 시작하는 번호다.
            region = int(result.get("table_region_id", position + 1)) - 1
            if not 0 <= region < len(layout):
                raise PdfTableError("pp_table_engine_error:TableRegionUnmapped")
            box_px = [float(v) for v in layout[region]]
            table_words = [w for w in words if center_in(box_px, *word_center(w))]
            verdict, reasons, cells = assess_table([flat_box(b) for b in result.get("cell_box_list", [])],
                                                   result.get("pred_html", "").count("<td"), table_words, engine)
            tables.append(PdfTable(page_no, [v / scale for v in box_px], verdict, reasons, cells))
    return tables


def detect_tables(pdf_bytes, contract):
    """모든 page의 PP 표 영역. 실패는 PdfTableError로 올리며 다른 표 parser로 넘어가지 않는다."""
    import pypdfium2
    engine = contract["routes"]["PDF"]["table_engine"]
    with _PP_LOCK:
        try:
            model = pipeline(contract)
            document = pypdfium2.PdfDocument(pdf_bytes)
        except PdfTableError:
            raise
        except Exception as error:
            raise PdfTableError("pp_table_engine_error:" + type(error).__name__) from None
        try:
            tables = []
            for index in range(len(document)):
                tables.extend(page_tables(model, document[index], index + 1, engine))
            return tables, len(document)
        except PdfTableError:
            raise
        except Exception as error:
            raise PdfTableError("pp_table_engine_error:" + type(error).__name__) from None
        finally:
            document.close()
