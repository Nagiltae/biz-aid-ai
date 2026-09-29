"""한 문서를 한 표 engine으로 실행해 비교용 표 JSON을 남긴다. 문서마다 별도 process로 호출해 peak RSS를 분리한다."""
import argparse
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import OUTPUT_ROOT, html_cells, make_table, read_json, sha256_file, write_json

PADDLE_MODELS = {
    "LayoutDetection": ("layout_detection", "PP-DocLayout-L"),
    "TableClassification": ("table_classification", "PP-LCNet_x1_0_table_cls"),
    "WiredTableStructureRecognition": ("table_structure_recognition", "SLANeXt_wired"),
    "WirelessTableStructureRecognition": ("table_structure_recognition", "SLANeXt_wireless"),
    "WiredTableCellsDetection": ("table_cells_detection", "RT-DETR-L_wired_table_cell_det"),
    "WirelessTableCellsDetection": ("table_cells_detection", "RT-DETR-L_wireless_table_cell_det"),
}
RENDER_SCALE = 2.0


def page_heights(path):
    import pypdfium2
    document = pypdfium2.PdfDocument(str(path))
    try:
        return [document[index].get_size()[1] for index in range(len(document))]
    finally:
        document.close()


def run_docling(path, sha):
    sys.path.insert(0, str(ROOT / "data-pipeline/src"))
    from biz_aid_pipeline.parsing.models import ParseResult, parsing_contract
    from biz_aid_pipeline.parsing.pdf import convert_pdf
    contract = parsing_contract()
    result = ParseResult(sha, "PDF", "DOCLING_PDF", "", "ROUTE_NOT_ENABLED")
    document, _ = convert_pdf(path.read_bytes(), sha, contract)
    tables = []
    for item in document.tables:
        prov = item.prov[0]
        height = document.pages[prov.page_no].size.height
        box = prov.bbox.to_top_left_origin(page_height=height)
        cells = [{"row": c.start_row_offset_idx, "col": c.start_col_offset_idx, "rowspan": c.row_span,
                  "colspan": c.col_span, "text": c.text} for c in item.data.table_cells]
        tables.append(make_table(prov.page_no, (box.l, box.t, box.r, box.b), cells,
                                 item.data.num_rows, item.data.num_cols))
    return tables, {"warnings": result.warnings}


def native_text_lines(page, scale, height):
    """PDF text layer의 좌표를 OCR 결과 형식으로 넘겨 PP-TableMagic이 OCR 모델 없이 cell text를 채우게 한다."""
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
    """글자 단위로 읽어 단어 box를 만든다. 사각형 단위 추출은 겹치는 italic 사각형에서 이웃 글자를 중복시킨다."""
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
    return [w["box"] for w in words], [w["text"] for w in words]


def merge_lines(boxes, texts):
    """pdfium text 조각은 단어보다 잘게 나뉘므로 OCR 검출기처럼 같은 줄의 가까운 조각을 한 줄 box로 합친다."""
    order = sorted(range(len(boxes)), key=lambda i: (round(boxes[i][1]), boxes[i][0]))
    lines = []
    for index in order:
        x1, y1, x2, y2 = boxes[index]
        last = lines[-1] if lines else None
        if last:
            lx1, ly1, lx2, ly2 = last["box"]
            height = min(y2 - y1, ly2 - ly1)
            overlap = min(y2, ly2) - max(y1, ly1)
            # BOUNDARY: 간격이 글자 높이보다 넓으면 다른 cell일 가능성이 커서 합치지 않는다.
            if height > 0 and overlap >= 0.5 * height and 0 <= x1 - lx2 <= max(y2 - y1, ly2 - ly1):
                last["box"] = [lx1, min(y1, ly1), max(x2, lx2), max(y2, ly2)]
                last["text"] += (" " if x1 - lx2 > 0.15 * height else "") + texts[index]
                continue
        lines.append({"box": [x1, y1, x2, y2], "text": texts[index]})
    return [line["box"] for line in lines], [line["text"] for line in lines]


def reassemble_cells(cells, cell_boxes, boxes, texts, table_box):
    """PP의 구조와 cell box는 쓰되 cell text는 native 조각을 읽기 순서로 다시 조립한다. 표 전용 adapter 후보의 동작이다."""
    flat = []
    for box in cell_boxes:
        values = [float(v) for v in (box.tolist() if hasattr(box, "tolist") else box)]
        xs, ys = values[0::2], values[1::2]
        flat.append([min(xs), min(ys), max(xs), max(ys)])
    if len(flat) != len(cells):
        return cells, {"box_count_mismatch": 1, "unassigned_segments": 0}
    assigned = [[] for _ in cells]
    unassigned = 0
    for (x1, y1, x2, y2), text in zip(boxes, texts):
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if not (table_box[0] <= cx <= table_box[2] and table_box[1] <= cy <= table_box[3]):
            continue
        owners = [i for i, (l, t, r, b) in enumerate(flat) if l <= cx <= r and t <= cy <= b]
        if owners:
            assigned[min(owners, key=lambda i: (flat[i][2] - flat[i][0]) * (flat[i][3] - flat[i][1]))].append(
                (cy, x1, y2 - y1, text))
        else:
            unassigned += 1
    rebuilt = []
    for cell, parts in zip(cells, assigned):
        lines = []
        for cy, x1, height, text in sorted(parts):
            if lines and abs(lines[-1][0] - cy) <= 0.5 * max(height, 1):
                lines[-1][1].append((x1, text))
            else:
                lines.append([cy, [(x1, text)]])
        rebuilt.append(dict(cell, text="\n".join(" ".join(t for _, t in sorted(items)) for _, items in lines)))
    return rebuilt, {"box_count_mismatch": 0, "unassigned_segments": unassigned}


def native_ocr_result(image, boxes, texts):
    import numpy
    polys = [numpy.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=float) for x1, y1, x2, y2 in boxes]
    return {"rec_boxes": numpy.array(boxes, dtype=float).reshape(-1, 4), "rec_texts": texts,
            "rec_scores": [1.0] * len(texts), "rec_polys": polys, "dt_polys": polys,
            "doc_preprocessor_res": {"output_img": image}}


def paddle_pipeline(model_root):
    from paddlex import create_pipeline
    submodules = {name: {"module_name": module, "model_name": model, "model_dir": str(Path(model_root) / model)}
                  for name, (module, model) in PADDLE_MODELS.items()}
    # BOUNDARY: OCR·문서 전처리·방향 분류 모델은 config에서 빼서 적재 자체를 막는다. OCR이 호출되면 실행이 실패한다.
    config = {"pipeline_name": "table_recognition_v2", "use_doc_preprocessor": False, "use_layout_detection": True,
              "use_ocr_model": False, "SubModules": submodules}
    return create_pipeline(config=config, device="cpu")


def run_pp_tablemagic(path, sha, model_root, granularity):
    import numpy
    import pypdfium2
    pipeline = paddle_pipeline(model_root)
    document = pypdfium2.PdfDocument(str(path))
    tables = []
    try:
        for index in range(len(document)):
            page = document[index]
            height = page.get_size()[1]
            image = numpy.ascontiguousarray(page.render(scale=RENDER_SCALE).to_numpy()[:, :, :3])
            boxes, texts = native_text_lines(page, RENDER_SCALE, height)
            if granularity == "lines":
                boxes, texts = merge_lines(boxes, texts)
            ocr = native_ocr_result(image, boxes, texts)
            for output in pipeline.predict(image, use_ocr_model=False, overall_ocr_res=ocr,
                                           use_table_orientation_classify=False,
                                           use_ocr_results_with_table_cells=False):
                data = output
                layout = [box for box in data.get("layout_det_res", {}).get("boxes", []) if box.get("label") == "table"]
                for position, table in enumerate(data.get("table_res_list", [])):
                    # table_region_id는 layout 표 box 순서의 1부터 시작하는 번호다.
                    region = int(table.get("table_region_id", position + 1)) - 1
                    if not 0 <= region < len(layout):
                        raise ValueError("pp_tablemagic_table_region_unmapped")
                    box = layout[region]["coordinate"]
                    cells, stats = html_cells(table.get("pred_html", "")), {}
                    if granularity == "cells":
                        cells, stats = reassemble_cells(cells, table.get("cell_box_list", []), boxes, texts, box)
                    tables.append(make_table(index + 1, [value / RENDER_SCALE for value in box], cells,
                                             source=dict(stats, pred_html=table.get("pred_html", ""))))
    finally:
        document.close()
    return tables, {"render_scale": RENDER_SCALE, "text_source": "pdfium native text layer", "granularity": granularity}


def camelot_cells(table):
    """lattice는 선 정보로 병합 cell을 복원하고 선이 없는 flavor는 모든 cell을 1x1로 둔다."""
    grid = table.cells
    owner = {}
    for r, row in enumerate(grid):
        for c, _ in enumerate(row):
            owner[(r, c)] = (r, c)

    def find(key):
        while owner[key] != key:
            owner[key] = owner[owner[key]]
            key = owner[key]
        return key

    if table.flavor == "lattice":
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if c + 1 < len(row) and not cell.right:
                    owner[find((r, c + 1))] = find((r, c))
                if r + 1 < len(grid) and not cell.bottom:
                    owner[find((r + 1, c))] = find((r, c))
    groups = {}
    for key in owner:
        groups.setdefault(find(key), []).append(key)
    cells = []
    for members in groups.values():
        rows = [r for r, _ in members]
        cols = [c for _, c in members]
        text = " ".join(grid[r][c].text.strip() for r, c in sorted(members) if grid[r][c].text.strip())
        cells.append({"row": min(rows), "col": min(cols), "rowspan": max(rows) - min(rows) + 1,
                      "colspan": max(cols) - min(cols) + 1, "text": text})
    return cells


def run_camelot(path, sha, flavor):
    import camelot
    heights = page_heights(path)
    found = camelot.read_pdf(str(path), pages="all", flavor=flavor)
    tables = []
    for table in found:
        page = int(table.page)
        left, bottom, right, top = table._bbox
        height = heights[page - 1]
        tables.append(make_table(page, (left, height - top, right, height - bottom), camelot_cells(table),
                                 source={"accuracy": table.accuracy, "whitespace": table.whitespace}))
    return tables, {"flavor": flavor}


def main(argv=None):
    parser = argparse.ArgumentParser(description="3-B.1 표 engine 한 문서 실행")
    parser.add_argument("--engine", required=True, choices=["docling_tableformer", "pp_tablemagic", "camelot"])
    parser.add_argument("--variant", default="default")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--paddle-models", default=os.path.expanduser("~/.cache/biz-aid/bench/table-engine/models"))
    args = parser.parse_args(argv)
    corpus = read_json(ROOT / "evals/table_engine/corpus.json")
    entry = next(d for d in corpus["documents"] if d["sha256"] == args.sha)
    path = ROOT / entry["storage_path"]
    if sha256_file(path) != args.sha:
        raise SystemExit("local_blob_sha_mismatch")
    started = time.perf_counter()
    error = None
    try:
        if args.engine == "docling_tableformer":
            tables, extra = run_docling(path, args.sha)
        elif args.engine == "pp_tablemagic":
            # default는 pdfium 조각 그대로, lines는 같은 줄 조각을 합친 입력이다.
            granularity = {"lines": "lines", "cells": "cells"}.get(args.variant, "segments")
            tables, extra = run_pp_tablemagic(path, args.sha, args.paddle_models, granularity)
        else:
            tables, extra = run_camelot(path, args.sha, args.variant)
    except Exception as exc:  # 비교 실험이므로 engine 실패도 결과 유형으로 남긴다.
        tables, extra, error = [], {}, f"{type(exc).__name__}: {exc}"[:500]
    seconds = time.perf_counter() - started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = peak / 1048576 if sys.platform == "darwin" else peak / 1024
    write_json(OUTPUT_ROOT / args.run_id / "engines" / f"{args.engine}-{args.variant}" / f"{args.sha}.json",
               {"sha256": args.sha, "engine": args.engine, "variant": args.variant, "seconds": round(seconds, 2),
                "peak_rss_mb": round(peak_mb), "error": error, "extra": extra, "tables": tables})
    print(f"{args.engine}-{args.variant} {args.sha[:12]} tables={len(tables)} seconds={seconds:.1f} error={bool(error)}")


if __name__ == "__main__":
    main()
