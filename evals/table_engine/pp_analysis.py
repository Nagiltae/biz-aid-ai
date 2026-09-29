"""3-B.2 PP-TableMagic 적합성 분석. pp_diagnostics 기록을 제품 venv에서 읽어 adapter·mismatch·오검출·표 품질 Gate를 평가한다.

production parser에 적용하지 않는 평가 도구다. 표 품질 판정은 TABLE_VALID / TABLE_QUALITY_FAILED evidence로만 남긴다.
"""
import argparse
import html
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import (OUTPUT_ROOT, critical_tokens, html_cells, iou, make_table, read_json, table_text,
                                       write_json)
from evals.table_engine.run_engine import native_words

# BOUNDARY: 아래 임계값은 평가용 가설이며 production 규칙이 아니다. 근거는 Report에 분포와 함께 남긴다.
TD_OVERLAP_IOU = 0.5
MATCH_IOU = 0.3
EMPTY_STRUCTURE_CHARS = 200
MODES = ("rows", "grid", "grid_norm_larger", "grid_norm_smaller", "matched", "struct")
CONTAINED_RATIO = 0.9


def center_in(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def grid_conflicts(cells):
    """HTML span이 겹치거나 행 폭이 서로 다르면 논리 grid를 증명할 수 없다."""
    owner, conflicts = {}, 0
    for index, cell in enumerate(cells):
        for r in range(cell["row"], cell["row"] + cell["rowspan"]):
            for c in range(cell["col"], cell["col"] + cell["colspan"]):
                if (r, c) in owner:
                    conflicts += 1
                owner[(r, c)] = index
    widths = Counter()
    for r, c in owner:
        widths[r] = max(widths[r], c + 1)
    return conflicts, len(set(widths.values())) > 1


def structure_boxes(record):
    """SLANeXt 원시 bbox는 두 축 모두 crop 긴 변 L 기준으로 정규화돼 있어 x·w/L, y·h/L로 crop 좌표에 되돌린다.

    RISK: 이 보정은 3-B.2 진단에서 관찰한 규칙이며 scale_check evidence로 표마다 검출 box 범위와 대조한다.
    """
    left, top, right, bottom = record["table_box_px"]
    width, height = right - left, bottom - top
    side = max(width, height)
    return [[left + b[0] * width / side, top + b[1] * height / side, left + b[2] * width / side,
             top + b[3] * height / side] for b in record.get("structure_bbox_crop", [])]


def scale_check(record, boxes):
    detections = record["cell_box_list"]
    if not boxes or not detections:
        return None
    left, top, right, bottom = record["table_box_px"]
    extent = lambda items, k: max(b[k] for b in items)
    width, height = right - left, bottom - top
    return round(max(abs(extent(boxes, 2) - extent(detections, 2)) / width,
                     abs(extent(boxes, 3) - extent(detections, 3)) / height), 3)


ROW_TOLERANCE_PX = 10


def detection_rows(detections):
    """PP의 sort_table_cells_boxes와 같은 규칙: 행 첫 box의 y1에서 10px 안이면 같은 행, 행 안은 x순."""
    rows, current, current_y = [], [], None
    for box in sorted(detections, key=lambda b: b[1]):
        if current_y is None or abs(box[1] - current_y) <= ROW_TOLERANCE_PX:
            current.append(box)
            current_y = box[1] if current_y is None else current_y
        else:
            rows.append(sorted(current, key=lambda b: b[0]))
            current, current_y = [box], box[1]
    if current:
        rows.append(sorted(current, key=lambda b: b[0]))
    return rows


def html_row_counts(tokens):
    counts, inside = [], False
    for token in tokens:
        if token == "<tr>":
            counts.append(0)
        elif token.startswith("<td") and counts:
            counts[-1] += 1
    return counts


EDGE_TOLERANCE_PX = 8


def edge_lines(values):
    lines = []
    for value in sorted(values):
        if lines and value - lines[-1][-1] <= EDGE_TOLERANCE_PX:
            lines[-1].append(value)
        else:
            lines.append([value])
    return [sum(group) / len(group) for group in lines]


def grid_cells(detections):
    """검출 box 경계만으로 논리 grid를 만든다. 같은 칸을 두 box가 차지하거나 폭 0 box가 있으면 증명 실패다."""
    columns = edge_lines([v for b in detections for v in (b[0], b[2])])
    rows = edge_lines([v for b in detections for v in (b[1], b[3])])
    nearest = lambda lines, value: min(range(len(lines)), key=lambda i: abs(lines[i] - value))
    cells, owner, conflicts, degenerate = [], {}, 0, 0
    for index, box in enumerate(detections):
        c1, c2 = nearest(columns, box[0]), nearest(columns, box[2])
        r1, r2 = nearest(rows, box[1]), nearest(rows, box[3])
        if c2 <= c1 or r2 <= r1:
            degenerate += 1
            continue
        for r in range(r1, r2):
            for c in range(c1, c2):
                if (r, c) in owner:
                    conflicts += 1
                owner[(r, c)] = index
        cells.append({"row": r1, "col": c1, "rowspan": r2 - r1, "colspan": c2 - c1, "text": "", "box": box})
    slots = max(len(rows) - 1, 0) * max(len(columns) - 1, 0)
    uncovered = [[columns[c], rows[r], columns[c + 1], rows[r + 1]] for r in range(len(rows) - 1)
                 for c in range(len(columns) - 1) if (r, c) not in owner]
    return cells, {"grid_conflicts": conflicts, "degenerate_boxes": degenerate, "uncovered_slots": slots - len(owner),
                   "uncovered_boxes": uncovered, "grid_shape": [len(rows) - 1, len(columns) - 1]}


def normalize_overlaps(detections, keep):
    """면적 90% 이상이 다른 검출 box 안에 있으면 포함 관계로 본다. larger는 안쪽 box를, smaller는 바깥 box를 버린다."""
    def inter(a, b):
        return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])
    kept = []
    for i, box in enumerate(detections):
        others = [other for j, other in enumerate(detections) if j != i]
        inside = any(inter(box, other) >= CONTAINED_RATIO * area(box) and area(other) > area(box) for other in others)
        container = any(inter(box, other) >= CONTAINED_RATIO * area(other) and area(box) > area(other) for other in others)
        if (keep == "larger" and inside) or (keep == "smaller" and container):
            continue
        kept.append(box)
    return kept


def match_boxes(anchors, detections):
    """<td> 구조 bbox와 검출 box를 IoU 내림차순 1:1로 짝짓는다. 순서 가정 없이 기하로만 대응을 증명한다."""
    pairs = sorted(((iou(a, d), i, j) for i, a in enumerate(anchors) for j, d in enumerate(detections)), reverse=True)
    used_a, used_d, result = set(), set(), {}
    for score, i, j in pairs:
        if score < MATCH_IOU or i in used_a or j in used_d:
            continue
        used_a.add(i)
        used_d.add(j)
        result[i] = j
    return result


def struct_adapter(record, segments, scale, mode="struct"):
    """표 구조 cell과 cell 기하를 정하는 매핑별 adapter.

    struct: <td> 구조 bbox(순서 1:1). matched: 구조 bbox와 검출 box의 IoU 1:1 대응. rows: PP 행 규칙의 행별 개수 일치.
    grid: HTML 없이 검출 box 경계로 만든 grid. 증명되지 않으면 cell을 만들지 않고 사유를 돌려준다.
    """
    cells = html_cells("".join(record["structure_tokens"]))
    boxes = structure_boxes(record)
    evidence = {"scale_check": scale_check(record, boxes), "td_count": record["td_count"],
                "structure_boxes": len(boxes), "parsed_cells": len(cells), "unassigned_segments": 0,
                "unassigned_text": "", "multi_owner_segments": 0, "unmatched_td": 0, "unmatched_detections": 0}
    if not mode.startswith("grid") and not (len(cells) == len(boxes) == record["td_count"]):
        return None, dict(evidence, mapping="count_mismatch")
    if mode.startswith("grid"):
        detections = record["cell_box_list"]
        if mode != "grid":
            detections = normalize_overlaps(detections, mode.rsplit("_", 1)[1])
            evidence["removed_detections"] = len(record["cell_box_list"]) - len(detections)
        grid, stats = grid_cells(detections)
        evidence.update({k: v for k, v in stats.items() if k != "uncovered_boxes"})
        if stats["grid_conflicts"] or stats["degenerate_boxes"]:
            return None, dict(evidence, mapping="grid_unproven")
        cells, boxes = [{k: v for k, v in c.items() if k != "box"} for c in grid], [c["box"] for c in grid]
        evidence.pop("uncovered_boxes", None)
    elif mode == "rows":
        rows = detection_rows(record["cell_box_list"])
        expected = html_row_counts(record["structure_tokens"])
        actual = [len(row) for row in rows]
        evidence["row_counts_expected"], evidence["row_counts_detected"] = expected, actual
        # BOUNDARY: 행 수와 행별 cell 수가 모두 같을 때만 순서 대응이 증명된다. PP처럼 빈 cell을 채우거나 합치지 않는다.
        if expected != actual:
            return None, dict(evidence, mapping="row_alignment_unproven")
        boxes = [box for row in rows for box in row]
    elif mode == "matched":
        detections = record["cell_box_list"]
        pairs = match_boxes(boxes, detections)
        evidence["unmatched_td"] = len(boxes) - len(pairs)
        evidence["unmatched_detections"] = len(detections) - len(pairs)
        # EXCEPTION: 짝 없는 <td>는 구조 bbox로 두되 매핑 미증명 evidence로 남겨 품질 Gate가 판단하게 한다.
        boxes = [detections[pairs[i]] if i in pairs else box for i, box in enumerate(boxes)]
    table_box = record["table_box_px"]
    assigned = [[] for _ in cells]
    for (x1, y1, x2, y2), text in segments:
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if not center_in(table_box, cx, cy):
            continue
        owners = [i for i, box in enumerate(boxes) if center_in(box, cx, cy)]
        if not owners:
            evidence["unassigned_segments"] += 1
            evidence["unassigned_text"] += text + " "
            continue
        if len(owners) > 1:
            evidence["multi_owner_segments"] += 1
        assigned[min(owners, key=lambda i: area(boxes[i]))].append((cy, x1, y2 - y1, text))
    rebuilt = []
    for cell, parts in zip(cells, assigned):
        lines = []
        for cy, x1, height, text in sorted(parts):
            if lines and abs(lines[-1][0] - cy) <= 0.5 * max(height, 1):
                lines[-1][1].append((x1, text))
            else:
                lines.append([cy, [(x1, text)]])
        rebuilt.append(dict(cell, text="\n".join(" ".join(t for _, t in sorted(items)) for _, items in lines)))
    return rebuilt, dict(evidence, mapping=mode)


def page_segments(document, page_no, scale):
    page = document[page_no - 1]
    height = page.get_size()[1]
    boxes, texts = native_words(page, scale, height)
    return list(zip(boxes, texts)), page.get_size()


def native_in(segments, box):
    return " ".join(text for (x1, y1, x2, y2), text in segments if center_in(box, (x1 + x2) / 2, (y1 + y2) / 2))


def mismatch_cause(record, segments):
    """검출 box 경계 grid와 HTML을 비교해 검출 부족의 원인을 정한다. 구조 bbox는 부정확해 원인 판정에 쓰지 않는다."""
    parsed = html_cells("".join(record["structure_tokens"]))
    grid, stats = grid_cells(record["cell_box_list"])
    deficit = record["td_count"] - len(record["cell_box_list"])
    text_slots = sum(1 for box in stats["uncovered_boxes"]
                     if any(center_in(box, (s[0][0] + s[0][2]) / 2, (s[0][1] + s[0][3]) / 2) and s[1].strip()
                            for s in segments))
    merged_html = sum(1 for c in parsed if c["rowspan"] > 1 or c["colspan"] > 1)
    merged_det = sum(1 for c in grid if c["rowspan"] > 1 or c["colspan"] > 1)
    facts = {"deficit": deficit, "uncovered_slots": stats["uncovered_slots"], "text_bearing_uncovered": text_slots,
             "merged_html": merged_html, "merged_detection": merged_det, "grid_conflicts": stats["grid_conflicts"],
             "degenerate_boxes": stats["degenerate_boxes"], "html_shape": [max((c["row"] + c["rowspan"] for c in parsed), default=0),
             max((c["col"] + c["colspan"] for c in parsed), default=0)], "detection_grid_shape": stats["grid_shape"]}
    if stats["grid_conflicts"] or stats["degenerate_boxes"]:
        cause = "overlapping_or_degenerate_detections"
    elif text_slots:
        cause = "text_bearing_cell_not_detected"
    elif stats["uncovered_slots"] >= deficit:
        cause = "empty_cell_not_detected"
    elif merged_det > merged_html:
        cause = "detector_merged_cells"
    else:
        cause = "structure_model_extra_cells"
    return cause, facts


def reading_order_text(parts):
    lines = []
    for (x1, y1, x2, y2), text in sorted(parts, key=lambda s: ((s[0][1] + s[0][3]) / 2, s[0][0])):
        cy, height = (y1 + y2) / 2, y2 - y1
        if lines and abs(lines[-1][0] - cy) <= 0.5 * max(height, 1):
            lines[-1][1].append((x1, text))
        else:
            lines.append([cy, [(x1, text)]])
    return "\n".join(" ".join(t for _, t in sorted(items)) for _, items in lines)


def failed_table_evidence(page, record, segments, scale):
    """TABLE_QUALITY_FAILED 표는 구조 없이 bbox 안 native text만 보존한다. 글자 단위로 손실 여부를 검증한다."""
    box = record["table_box_px"]
    kept = [s for s in segments if center_in(box, (s[0][0] + s[0][2]) / 2, (s[0][1] + s[0][3]) / 2)]
    preserved = reading_order_text(kept)
    height = page.get_size()[1]
    text_page = page.get_textpage()
    reference = Counter()
    try:
        for index in range(text_page.count_chars()):
            char = text_page.get_text_range(index, 1)
            if not char.strip():
                continue
            left, bottom, right, top = text_page.get_charbox(index)
            cx, cy = (left + right) / 2 * scale, (height - (top + bottom) / 2) * scale
            if center_in(box, cx, cy):
                reference[char] += 1
    finally:
        text_page.close()
    actual = Counter(ch for ch in preserved if ch.strip())
    return {"preserved_chars": sum(actual.values()), "reference_chars": sum(reference.values()),
            "missing_chars": sum((reference - actual).values()), "extra_chars": sum((actual - reference).values()),
            "preserved_text_sample": preserved[:160]}


def classify_mismatch(record, cells):
    """검출 cell box와 <td> 구조 bbox를 IoU로 대응시킨 참고 지표다. 구조 bbox가 거칠어 원인 판정에는 쓰지 않는다."""
    tds = structure_boxes(record)
    dets = record["cell_box_list"]
    reasons = Counter()
    if "".join(record["structure_tokens"]).count("<table") > 1:
        reasons["nested_table"] += 1
    for index, box in enumerate(tds):
        if max((iou(box, det) for det in dets), default=0) >= 0.5:
            continue
        cell = cells[index] if index < len(cells) else {"rowspan": 1, "colspan": 1, "row": -1}
        if cell["rowspan"] > 1 or cell["colspan"] > 1:
            reasons["span_cell_split_or_missed"] += 1
        elif cell["row"] == 0:
            reasons["header_cell_missed"] += 1
        else:
            reasons["body_cell_missed"] += 1
    extra = sum(1 for det in dets if max((iou(det, box) for box in tds), default=0) < 0.5)
    if extra:
        reasons["detection_without_td"] += extra
    duplicates = sum(1 for i in range(len(dets)) for j in range(i + 1, len(dets)) if iou(dets[i], dets[j]) > 0.7)
    if duplicates:
        reasons["duplicated_detection"] += duplicates
    return reasons


def quality_gate(record, cells, evidence, native_text, page_size, scale, others):
    """표 단위 fail-closed 판정. 사유가 하나라도 있으면 TABLE_QUALITY_FAILED다."""
    reasons = []
    if cells is None:
        reasons.append(evidence.get("mapping") if evidence.get("mapping") in ("row_alignment_unproven", "grid_unproven")
                       else "invalid_cell_mapping")
    else:
        conflicts, ragged = grid_conflicts(cells)
        if conflicts:
            reasons.append("conflicting_span")
        if ragged:
            reasons.append("impossible_row_col_grid")
        if evidence.get("unmatched_td") or evidence.get("unmatched_detections"):
            reasons.append("structure_detection_mismatch")
        if evidence["unassigned_segments"]:
            lost = critical_tokens(evidence["unassigned_text"])
            if lost:
                reasons.append("critical_native_token_unexplained_loss")
        if record["td_count"] <= 1 and len(native_text.replace(" ", "")) > EMPTY_STRUCTURE_CHARS:
            reasons.append("empty_structure_with_substantial_text")
    features = frame_features(record, page_size, scale, others)
    return ("TABLE_QUALITY_FAILED" if reasons else "TABLE_VALID"), reasons, features


def frame_features(record, page_size, scale, others):
    box = [v / scale for v in record["table_box_px"]]
    width, height = page_size
    other_boxes = [[v / scale for v in other["table_box_px"]] for other in others if other is not record]
    contains = sum(1 for o in other_boxes
                   if area([max(box[0], o[0]), max(box[1], o[1]), min(box[2], o[2]), min(box[3], o[3])]) >= 0.9 * area(o))
    return {"area_ratio": round(area(box) / (width * height), 3),
            "edge_margin_pt": round(min(box[0], box[1], width - box[2], height - box[3]), 1),
            "contains_other_tables": contains, "classification": record.get("classification"),
            "td_count": record["td_count"]}


def analyze(run_id, diag_dir="pp_diag"):
    import pypdfium2
    run_dir = OUTPUT_ROOT / run_id
    corpus = {d["sha256"]: d for d in read_json(ROOT / "evals/table_engine/corpus.json")["documents"]}
    per_variant, rows = defaultdict(list), []
    suffix = "" if diag_dir == "pp_diag" else "-" + diag_dir.rsplit("_", 1)[1]
    for path in sorted((run_dir / diag_dir).glob("*.json")):
        if path.name == "timing.json":
            continue
        diag = read_json(path)
        sha, scale = diag["sha256"], diag["render_scale"]
        document = pypdfium2.PdfDocument(str(ROOT / corpus[sha]["storage_path"]))
        try:
            for page in diag["pages"]:
                segments, page_size = page_segments(document, page["page"], scale)
                layout_scores = [box["score"] for box in page.get("layout_tables", [])]
                for index, record in enumerate(page["tables"]):
                    native = native_in(segments, record["table_box_px"])
                    expected = critical_tokens(native)
                    fallback = critical_tokens(table_text(make_table(page["page"], [0, 0, 0, 0],
                                                                     html_cells(record["pred_html"]))))
                    parsed = html_cells("".join(record["structure_tokens"]))
                    mismatch = len(record["cell_box_list"]) != record["td_count"]
                    box_pt = [v / scale for v in record["table_box_px"]]
                    adapters, quality = {}, {}
                    for mode in MODES:
                        cells, evidence = struct_adapter(record, segments, scale, mode)
                        found = critical_tokens("\n".join(c["text"] for c in cells or []))
                        adapters[mode] = {
                            "proven": cells is not None, "mapping": evidence.get("mapping"),
                            "token_hits": sum(min(n, found[k]) for k, n in expected.items()) if cells else None,
                            "missing_tokens": sorted(f"{k}:{v}" for (k, v) in (expected - found)) if cells else None,
                            "unassigned_segments": evidence["unassigned_segments"],
                            "unassigned_text_sample": evidence["unassigned_text"][:120],
                            "details": {k: v for k, v in evidence.items()
                                        if k in ("row_counts_expected", "row_counts_detected", "grid_conflicts",
                                                 "degenerate_boxes", "uncovered_slots", "grid_shape", "unmatched_td",
                                                 "unmatched_detections", "scale_check", "removed_detections")},
                            "grid_signature": sorted((c["row"], c["col"], c["rowspan"], c["colspan"]) for c in cells)
                            if cells is not None and mode.startswith("grid") else None}
                        if mode in ("rows", "grid", "grid_norm_larger", "grid_norm_smaller"):
                            verdict, reasons, features = quality_gate(record, cells, evidence, native, page_size,
                                                                      scale, page["tables"])
                            quality[mode] = {"verdict": verdict, "reasons": reasons}
                        if cells is not None:
                            per_variant[(mode, sha)].append(make_table(page["page"], box_pt, cells,
                                                                       source={"quality": quality.get(mode)}))
                    failed = quality.get("grid", {}).get("verdict") == "TABLE_QUALITY_FAILED"
                    rows.append({
                        "failed_table_evidence": failed_table_evidence(document[page["page"] - 1], record, segments, scale)
                        if failed else None,
                        "sha256": sha, "group": corpus[sha]["group"], "page": page["page"], "table": index,
                        "bbox_pt": [round(v, 2) for v in box_pt], "classification": record.get("classification"),
                        "td_count": record["td_count"], "detected_raw": record.get("detected_raw"),
                        "detected_final": len(record["cell_box_list"]), "mismatch": mismatch,
                        "mismatch_reasons": dict(classify_mismatch(record, parsed)) if mismatch else {},
                        "mismatch_cause": mismatch_cause(record, segments) if mismatch else None,
                        "row_alignment_hidden": (not mismatch) and not adapters["rows"]["proven"],
                        "native_critical_tokens": sum(expected.values()),
                        "html_shape": [max((c["row"] + c["rowspan"] for c in parsed), default=0),
                                       max((c["col"] + c["colspan"] for c in parsed), default=0)],
                        "fallback_token_hits": sum(min(n, fallback[k]) for k, n in expected.items()),
                        "adapters": adapters, "quality": quality,
                        "layout_score": layout_scores[index] if index < len(layout_scores) else None,
                        "frame_features": features})
        finally:
            document.close()
    diagnosed = {path.stem for path in (run_dir / diag_dir).glob("*.json")}
    for variant in MODES:
        for sha in corpus:
            if sha not in diagnosed:
                continue
            # 평가 metric은 seconds를 합산하므로 진단 실행의 문서 시간 대신 0을 넣고 steady-state 시간은 timing.json에만 둔다.
            write_json(run_dir / f"engines/pp_tablemagic-{variant}{suffix}" / f"{sha}.json",
                       {"sha256": sha, "engine": "pp_tablemagic", "variant": variant + suffix, "seconds": 0, "peak_rss_mb": 0,
                        "error": None, "extra": {"adapter": f"{variant} mapping from pp_diagnostics"},
                        "tables": per_variant.get((variant, sha), [])})
    write_json(run_dir / f"pp_tables{suffix}.json", rows)
    return rows


def candidate_items(rows):
    """container(다른 PP 표 2개 이상을 90% 이상 포함)와 duplicate(IoU 0.8 초과) 후보. 번호는 review ID로 쓰므로 순서를 바꾸지 않는다."""
    by_page = defaultdict(list)
    for row in rows:
        by_page[(row["sha256"], row["page"])].append(row)
    items = []
    for row in rows:
        if row["frame_features"]["contains_other_tables"] >= 2:
            inside = [o for o in by_page[(row["sha256"], row["page"])] if o is not row and area(
                [max(row["bbox_pt"][0], o["bbox_pt"][0]), max(row["bbox_pt"][1], o["bbox_pt"][1]),
                 min(row["bbox_pt"][2], o["bbox_pt"][2]), min(row["bbox_pt"][3], o["bbox_pt"][3])]) >= 0.9 * area(o["bbox_pt"])]
            items.append(("container", row, inside))
    for (sha, page), group in by_page.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if iou(a["bbox_pt"], b["bbox_pt"]) > 0.8:
                    items.append(("duplicate", a, [b]))
    return items


def candidates_bundle(run_id):
    """container·duplicate 후보를 사람이 판정하도록 쪽 렌더링과 box를 한 HTML에 모은다. 규칙을 적용하지 않는다."""
    import pypdfium2
    from PIL import ImageDraw
    run_dir = OUTPUT_ROOT / run_id
    corpus = {d["sha256"]: d for d in read_json(ROOT / "evals/table_engine/corpus.json")["documents"]}
    items = candidate_items(read_json(run_dir / "pp_tables.json"))
    out = run_dir / "pp_candidates"
    out.mkdir(parents=True, exist_ok=True)
    sections = []
    for number, (kind, row, others) in enumerate(items):
        pdf = pypdfium2.PdfDocument(str(ROOT / corpus[row["sha256"]]["storage_path"]))
        try:
            image = pdf[row["page"] - 1].render(scale=1.2).to_pil().convert("RGB")
        finally:
            pdf.close()
        draw = ImageDraw.Draw(image)
        draw.rectangle([v * 1.2 for v in row["bbox_pt"]], outline="red", width=5)
        for other in others:
            draw.rectangle([v * 1.2 for v in other["bbox_pt"]], outline="blue", width=3)
        name = f"{number:02d}-{kind}-{row['sha256'][:12]}-p{row['page']}"
        image.save(out / f"{name}.png")
        describe = lambda r: (f"table {r['table']} · {r['classification']} · html {r['html_shape']} · "
                              f"gate {r['quality']['grid']['verdict']} {r['quality']['grid']['reasons']}")
        question = ("빨간 box가 실제 표인가, 아니면 파란 표들을 감싼 frame/container인가?" if kind == "container"
                    else "빨간 box와 파란 box가 같은 표의 중복 검출인가?")
        sections.append(f'<section><h2>{number}. {kind} · {row["sha256"]} · page {row["page"]}</h2>'
                        f'<p>red: {html.escape(describe(row))}</p>'
                        + "".join(f"<p>blue: {html.escape(describe(o))}</p>" for o in others)
                        + f'<p class="q">review: {question} → human_verification: <b>pending</b></p>'
                        f'<img src="{name}.png"></section>')
    style = "body{font-family:sans-serif;margin:16px}img{max-width:70%;border:1px solid #ccc}.q{color:#b00}"
    (out / "index.html").write_text(f"<title>PP candidates {run_id}</title><style>{style}</style>"
                                     f"<h1>PP container / duplicate 후보 ({len(items)})</h1>"
                                     "<p>규칙은 production에 적용되지 않은 후보다. 사람이 각 항목을 판정한다.</p>"
                                     + "".join(sections), encoding="utf-8")
    return Counter(kind for kind, _, _ in items)


def main(argv=None):
    parser = argparse.ArgumentParser(description="3-B.2 PP-TableMagic 적합성 분석")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--diag", choices=["pp_diag", "pp_diag_words"], default="pp_diag")
    parser.add_argument("--candidates-bundle", action="store_true")
    args = parser.parse_args(argv)
    if args.candidates_bundle:
        print(candidates_bundle(args.run_id))
        return
    rows = analyze(args.run_id, args.diag)
    proven = {mode: sum(r["adapters"][mode]["proven"] for r in rows) for mode in MODES}
    print(f"tables={len(rows)} mismatch={sum(r['mismatch'] for r in rows)} proven={proven}")


if __name__ == "__main__":
    main()
