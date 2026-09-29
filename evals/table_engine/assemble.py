"""3-B.3 DoclingDocument 조립 pilot. Docling backbone에 PP 표·실패 표 native text·PaddleOCR-VL visual 결과를 합친다.

평가 전용이며 production route를 바꾸지 않는다. 결과는 DoclingDocument 하나이고 별도 canonical model을 만들지 않는다.
item 단위 provenance는 docling-core BaseMeta의 `bizaid__*` 사용자 정의 필드에 둔다(Contract 변경 전 pilot 제안).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from evals.table_engine.common import OUTPUT_ROOT, iou, read_json, sha256_file, write_json
from evals.table_engine.pp_analysis import center_in, reading_order_text
from evals.table_engine.run_engine import native_words

PP_IDENTITY = ("paddleocr 3.7.0 / paddlex 3.7.2 table_recognition_v2 (models: bench manifest) + grid adapter "
               "(evals/table_engine/pp_analysis.py) + pdfium native_words")
DOCLING_IDENTITY = "docling-slim 2.130.0 / docling-core 2.99.0 / docling-ibm-models 4.0.3 TableFormer accurate"
SCALE = 2.0


def top_left(prov, document):
    height = document.pages[prov.page_no].size.height
    box = prov.bbox.to_top_left_origin(page_height=height)
    return [box.l, box.t, box.r, box.b]


def bizaid_meta(field, value):
    from docling_core.types.doc.common.meta import BaseMeta
    meta = BaseMeta()
    meta.set_custom_field("bizaid", field, value)
    return meta


def table_data(cells):
    from docling_core.types.doc import TableCell, TableData
    rows = max((c["row"] + c["rowspan"] for c in cells), default=0)
    cols = max((c["col"] + c["colspan"] for c in cells), default=0)
    return TableData(num_rows=rows, num_cols=cols, table_cells=[
        TableCell(text=c["text"], row_span=c["rowspan"], col_span=c["colspan"], start_row_offset_idx=c["row"],
                  end_row_offset_idx=c["row"] + c["rowspan"], start_col_offset_idx=c["col"],
                  end_col_offset_idx=c["col"] + c["colspan"]) for c in cells])


def provenance(page_no, bbox, text):
    from docling_core.types.doc import BoundingBox, CoordOrigin, ProvenanceItem
    return ProvenanceItem(page_no=page_no, charspan=(0, len(text)),
                          bbox=BoundingBox(l=bbox[0], t=bbox[1], r=bbox[2], b=bbox[3], coord_origin=CoordOrigin.TOPLEFT))


def page_chars(pdf):
    """쪽별 native 글자 multiset. 조립 결과의 누락·중복을 재는 기준이다."""
    pages = {}
    for index in range(len(pdf)):
        text_page = pdf[index].get_textpage()
        try:
            pages[index + 1] = Counter(ch for ch in text_page.get_text_range(0, text_page.count_chars()) if ch.strip())
        finally:
            text_page.close()
    return pages


def document_chars(document):
    """쪽별 조립 글자 multiset. provenance가 없는 item은 쪽 0에 모아 누락으로 숨지 않게 한다."""
    pages = {}
    for item in document.texts:
        pages.setdefault(item.prov[0].page_no if item.prov else 0, Counter()).update(ch for ch in item.text if ch.strip())
    for table in document.tables:
        pages.setdefault(table.prov[0].page_no if table.prov else 0, Counter()).update(
            ch for cell in table.data.table_cells for ch in cell.text if ch.strip())
    return pages


def total(pages):
    counts = Counter()
    for value in pages.values():
        counts.update(value)
    return counts


def loss_pages(native, base, assembled, regions):
    """baseline이 가진 글자를 조립 결과가 잃은 쪽. 쪽 단위로 봐야 다른 쪽의 중복이 손실을 가리지 않는다."""
    # WHY: 문서 합계 missing은 한 쪽의 손실과 다른 쪽의 개선이 상쇄될 수 있다. silent loss는 쪽별 baseline 대비로 판정한다.
    rows = []
    for page, counts in native.items():
        base_missing = counts - base.get(page, Counter())
        lost = (counts - assembled.get(page, Counter())) - base_missing
        if lost:
            rows.append({"page": page, "lost_vs_baseline": sum(lost.values()),
                         "lost_chars": "".join(sorted(lost.elements()))[:80],
                         "pp_regions_on_page": regions.get(page, 0)})
    return rows


def within(item, doomed, document):
    """item 자신이나 조상이 삭제 대상이면 True. Docling은 표 caption·footnote를 표의 자식으로 둔다."""
    while item is not None:
        if any(item is other for other in doomed):
            return True
        item = item.parent.resolve(document) if getattr(item, "parent", None) else None
    return False


def anchor(document, page_no, top, doomed=()):
    """삽입 위치: 같은 쪽에서 top이 표 top 이하인 마지막 item. 없으면 쪽 첫 item 앞이다."""
    # WHY: 삭제될 item이나 그 자식 옆에 넣으면 새 표가 함께 지워진다(3-B.3 pilot 0e8c217fbad8 p11에서 관찰).
    candidates = [(item, top_left(item.prov[0], document)) for item, _ in document.iterate_items()
                  if getattr(item, "prov", None) and item.prov[0].page_no == page_no
                  and not within(item, doomed, document)]
    before = [pair for pair in candidates if pair[1][1] <= top]
    if before:
        return max(before, key=lambda pair: pair[1][1])[0], True
    return (candidates[0][0], False) if candidates else (None, True)


def table_provenance(document):
    """조립기가 만든 table/text의 순서와 필수 provenance를 round-trip 전후 비교한다."""
    rows = []
    for position, (item, _) in enumerate(document.iterate_items()):
        custom = item.meta.get_custom_part() if getattr(item, "meta", None) else {}
        value = custom.get("bizaid__table_quality")
        if value:
            required = ("source_sha256", "page", "bbox_pt", "parser_identity", "verdict", "reasons")
            rows.append({"position": position, "page": value.get("page"), "bbox": value.get("bbox_pt"),
                         "verdict": value.get("verdict"), "complete": all(value.get(k) is not None for k in required)})
    return rows


def visual_provenance(document):
    rows = []
    required = ("source_sha256", "page", "bbox", "visual_type", "task", "model_identity", "extraction_method",
                "quality")
    for picture in document.pictures:
        custom = picture.meta.get_custom_part() if picture.meta else {}
        for value in custom.get("bizaid__visual_results", []):
            rows.append({"page": value.get("page"), "bbox": value.get("bbox"), "task": value.get("task"),
                         "complete": all(value.get(k) is not None for k in required)})
    return rows


def overlap_groups(rows):
    """같은 page에서 한 PP 영역의 중심이 다른 영역 안에 있으면 한 그룹으로 묶는다(연결 요소)."""
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(rows):
        for j, b in enumerate(rows):
            box = a["bbox_pt"]
            if i != j and a["page"] == b["page"] and center_in(b["bbox_pt"], (box[0] + box[2]) / 2, (box[1] + box[3]) / 2):
                parent[find(i)] = find(j)
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)
    return list(groups.values())


def resolve_overlaps(rows):
    """겹친 PP 영역은 container / duplicate 규칙이 검증되기 전이므로 어느 쪽도 고르지 않는다.

    그룹 전체를 합친 영역 하나로 바꿔 native text만 보존하고 TABLE_QUALITY_FAILED로 둔다.
    """
    # WHY: 그룹마다 표 하나를 고르면 구조가 틀리거나(container) 같은 text가 두 번 들어간다(duplicate). 둘 다 silent corruption이다.
    resolved = []
    for group in overlap_groups(rows):
        if len(group) == 1:
            resolved.append(group[0])
            continue
        boxes = [r["bbox_pt"] for r in group]
        union = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
        resolved.append({"sha256": group[0]["sha256"], "page": group[0]["page"], "bbox_pt": union,
                         "quality": {"grid": {"verdict": "TABLE_QUALITY_FAILED",
                                              "reasons": ["unresolved_overlapping_pp_regions"]}},
                         "members": [{"bbox_pt": r["bbox_pt"], "verdict": r["quality"]["grid"]["verdict"],
                                      "reasons": r["quality"]["grid"]["reasons"]} for r in group]})
    return resolved


CONTAIN_TOLERANCE_PT = 2.0


def contained(outer, inner, tolerance=CONTAIN_TOLERANCE_PT):
    return (inner[0] >= outer[0] - tolerance and inner[1] >= outer[1] - tolerance
            and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance)


def rescue_children(document, parents, removing, after_item, stats):
    """삭제할 item의 자식 중 삭제 대상이 아닌 text를 같은 label·provenance의 새 item으로 옮긴다.

    Docling은 표 caption·footnote를 표의 자식으로 두므로 부모를 지우면 영역 밖 text도 함께 사라진다.
    """
    # WHY: 3-B.4 corpus 조립에서 caption·footnote 손실이 여러 문서에서 관찰됐다(0054723c p20, 008f1c p35·p225 등).
    from docling_core.types.doc import DocItemLabel
    last = after_item
    for parent in parents:
        for ref in list(getattr(parent, "children", None) or []):
            child = ref.resolve(document)
            if any(child is other for other in removing) or not hasattr(child, "text"):
                continue
            label = child.label if child.label in (DocItemLabel.CAPTION, DocItemLabel.FOOTNOTE) else DocItemLabel.TEXT
            moved = document.insert_text(sibling=last, label=label, text=child.text,
                                         prov=child.prov[0] if child.prov else None, after=True)
            moved.meta = bizaid_meta("rescued", {"from_parent": parent.self_ref, "original_label": str(child.label),
                                                 "original_ref": child.self_ref})
            stats["children_rescued"] += 1
            last = rescue_children(document, [child], removing, moved, stats)
    return last


def outside_cell_words(region_words, cells):
    """VALID 표 영역 안 native 단어 중 어떤 cell text에도 쓰이지 않은 단어. 표 밖 text item으로 보존한다."""
    # WHY: cell text는 단어를 다시 이어 붙이므로 단어 단위 비교는 같은 글자를 못 찾는다(008f1c p211의 '->'). 글자 multiset으로 소비한다.
    pool = Counter(ch for cell in cells for ch in cell["text"] if not ch.isspace())
    leftover = []
    for box, text in region_words:
        need = Counter(ch for ch in text if not ch.isspace())
        if all(pool[ch] >= count for ch, count in need.items()):
            pool.subtract(need)
        else:
            leftover.append((box, text))
    return leftover


def word_center(word):
    return (word[0][0] + word[0][2]) / 2, (word[0][1] + word[0][3]) / 2


def region_items(document, page_no, bbox):
    """PP 영역이 소유해 지울 Docling item과, 중심만 영역 안이라 남길 부분 겹침 text item을 나눈다."""
    from docling_core.types.doc import DocItemLabel
    # PP 표 영역 안의 Docling 표·text는 PP가 소유하므로 지운다. 중복 text를 만들지 않기 위해서다.
    # BOUNDARY: 이미 조립한 PP 결과(bizaid 필드)는 다른 PP 영역이 지우지 못한다. 겹침은 resolve_overlaps에서 먼저 처리한다.
    # WHY: Docling은 그림 안 text를 picture 자식으로 두며 iterate_items 기본값은 그 안을 순회하지 않는다.
    # PP가 같은 영역을 표로 읽으면 text가 두 번 들어가므로 picture 자식도 영역 소유 판정에 넣는다(03df54 p2에서 관찰).
    owned = [item for item, _ in document.iterate_items(traverse_pictures=True)
             if getattr(item, "prov", None) and item.prov[0].page_no == page_no
             and item.label != DocItemLabel.PICTURE
             and not (item.meta and any(key.startswith("bizaid__") for key in item.meta.get_custom_part()))
             and center_in(bbox, *(lambda b: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))(top_left(item.prov[0], document)))]
    # WHY: 중심만 영역 안이고 일부가 밖에 걸친 text item을 지우면 밖 부분이 사라진다. 이런 item은 지우지 않고 남긴다.
    # RISK: 남긴 item의 영역 안 부분은 PP 결과와 중복될 수 있다. 중복은 extra로 집계되어 드러나며 손실보다 우선하지 않는다.
    partial = [item for item in owned if item.label != DocItemLabel.TABLE
               and not contained(bbox, top_left(item.prov[0], document))]
    return [item for item in owned if not any(item is other for other in partial)], partial


def spill_words(page_words, table_box, page_regions, surviving_boxes):
    """지우는 Docling 표 bbox 안이지만 어느 PP 영역에도, 남는 item에도 속하지 않는 native 단어."""
    # WHY: Docling 표가 PP 영역보다 크면 영역 밖 행(제목·단위 표기)이 표와 함께 사라진다(0438b7 p26·p119, 0b7a25 p19에서 관찰).
    # BOUNDARY: 같은 쪽 다른 PP 영역이나 남는 item(caption·footnote 포함)의 단어는 다시 넣지 않는다. 중복을 만들지 않기 위해서다.
    return [w for w in page_words if center_in(table_box, *word_center(w))
            and not any(center_in(region, *word_center(w)) for region in page_regions)
            and not any(center_in(kept, *word_center(w)) for kept in surviving_boxes)]


def assemble(run_id, sha, vl_results):
    import pypdfium2
    from docling_core.types.doc import DocItemLabel, DoclingDocument
    from biz_aid_pipeline.parsing.models import parsing_contract
    from biz_aid_pipeline.parsing.pdf import convert_pdf
    run_dir = OUTPUT_ROOT / run_id
    entry = next(d for d in read_json(ROOT / "evals/table_engine/corpus.json")["documents"] if d["sha256"] == sha)
    path = ROOT / entry["storage_path"]
    if sha256_file(path) != sha:
        raise SystemExit("local_blob_sha_mismatch")
    baseline, _ = convert_pdf(path.read_bytes(), sha, parsing_contract())
    document = DoclingDocument.model_validate_json(baseline.model_dump_json())
    raw_rows = [r for r in read_json(run_dir / "pp_tables.json") if r["sha256"] == sha]
    pp_rows = resolve_overlaps(raw_rows)
    grid_tables = read_json(run_dir / "engines/pp_tablemagic-grid" / f"{sha}.json")["tables"]
    pdf = pypdfium2.PdfDocument(str(path))
    stats, picture_conflicts = Counter(), []
    try:
        words = {}
        for row in pp_rows:
            page = pdf[row["page"] - 1]
            if row["page"] not in words:
                boxes, texts = native_words(page, 1.0, page.get_size()[1])
                words[row["page"]] = list(zip(boxes, texts))
            bbox = row["bbox_pt"]
            doomed, partial = region_items(document, row["page"], bbox)
            stats["partial_overlap_texts_kept"] += len(partial)
            region_words = [w for w in words[row["page"]] if center_in(bbox, (w[0][0] + w[0][2]) / 2, (w[0][1] + w[0][3]) / 2)]
            conflicts = [p for p in document.pictures if p.prov and p.prov[0].page_no == row["page"]
                         and iou(top_left(p.prov[0], document), bbox) > 0.3]
            if conflicts:
                # BOUNDARY: picture와 PP 표가 같은 영역이면 어느 해석이 맞는지 사람이 정한다. 여기서는 기록만 한다.
                picture_conflicts.append({"page": row["page"], "bbox_pt": bbox, "verdict": row["quality"]["grid"]["verdict"],
                                          "pictures": [p.self_ref for p in conflicts]})
            stats["docling_tables_replaced"] += sum(1 for item in doomed if item.label == DocItemLabel.TABLE)
            stats["docling_texts_absorbed"] += sum(1 for item in doomed if item.label != DocItemLabel.TABLE)
            sibling, after = anchor(document, row["page"], bbox[1], doomed)
            valid = row["quality"]["grid"]["verdict"] == "TABLE_VALID"
            common = {"source_sha256": sha, "page": row["page"], "bbox_pt": bbox, "parser_identity": PP_IDENTITY,
                      "verdict": row["quality"]["grid"]["verdict"], "reasons": row["quality"]["grid"]["reasons"]}
            if "members" in row:
                common["overlap_members"] = row["members"]
                stats["overlap_groups"] += 1
                stats["overlap_member_tables"] += len(row["members"])
                stats["overlap_member_valid_withheld"] += sum(m["verdict"] == "TABLE_VALID" for m in row["members"])
            if valid:
                cells = next(t["cells"] for t in grid_tables if t["page"] == row["page"] and iou(t["bbox"], bbox) > 0.99)
                data = table_data(cells)
                item = (document.insert_table(sibling=sibling, data=data, prov=provenance(row["page"], bbox, ""), after=after)
                        if sibling is not None else document.add_table(data=data, prov=provenance(row["page"], bbox, "")))
                stats["pp_tables_valid"] += 1
            else:
                text = reading_order_text(region_words)
                prov = provenance(row["page"], bbox, text)
                item = (document.insert_text(sibling=sibling, label=DocItemLabel.TEXT, text=text, prov=prov, after=after)
                        if sibling is not None else document.add_text(label=DocItemLabel.TEXT, text=text, prov=prov))
                stats["pp_tables_failed_as_text"] += 1
            item.meta = bizaid_meta("table_quality", common)
            last = item
            if valid:
                # WHY: grid adapter는 cell box 밖 단어를 버린다(00a9bc p2의 '‣', 008f1c p195의 ';}'). 표 밖 text로 보존한다.
                leftover = outside_cell_words(region_words, cells)
                if leftover:
                    text = reading_order_text(leftover)
                    last = document.insert_text(sibling=item, label=DocItemLabel.TEXT, text=text,
                                                prov=provenance(row["page"], bbox, text), after=True)
                    last.meta = bizaid_meta("table_outside_cells", dict(common, reasons=["valid_table_text_outside_cells"]))
                    stats["valid_table_outside_cell_texts"] += 1
            surviving = [top_left(i.prov[0], document) for i, _ in document.iterate_items(traverse_pictures=True)
                         if getattr(i, "prov", None) and i.prov[0].page_no == row["page"] and i.label != DocItemLabel.PICTURE
                         and not any(i is other for other in doomed)]
            page_regions = [r["bbox_pt"] for r in pp_rows if r["page"] == row["page"]]
            for table in [i for i in doomed if i.label == DocItemLabel.TABLE and not contained(bbox, top_left(i.prov[0], document))]:
                box = top_left(table.prov[0], document)
                spill = spill_words(words[row["page"]], box, page_regions, surviving)
                if spill:
                    text = reading_order_text(spill)
                    last = document.insert_text(sibling=last, label=DocItemLabel.TEXT, text=text,
                                                prov=provenance(row["page"], box, text), after=True)
                    last.meta = bizaid_meta("table_outside_region", {
                        "source_sha256": sha, "page": row["page"], "bbox_pt": box, "parser_identity": DOCLING_IDENTITY,
                        "reasons": ["docling_table_outside_pp_region"]})
                    stats["docling_table_spill_texts"] += 1
            if doomed:
                rescue_children(document, doomed, doomed, last, stats)
                document.delete_items(node_items=doomed)
        for table in [t for t in document.tables if not (t.meta and t.meta.get_custom_part().get("bizaid__table_quality"))]:
            # PP가 표로 보지 않은 Docling 표는 TableFormer 구조로 fallback하지 않고 text로만 남긴다.
            text = "\n".join(cell.text for cell in table.data.table_cells if cell.text.strip())
            prov = table.prov[0]
            replacement = document.insert_text(sibling=table, label=DocItemLabel.TEXT, text=text,
                                               prov=provenance(prov.page_no, top_left(prov, document), text), after=True)
            replacement.meta = bizaid_meta("table_quality", {
                "source_sha256": sha, "page": prov.page_no, "bbox_pt": top_left(prov, document),
                "parser_identity": DOCLING_IDENTITY, "verdict": "NOT_A_PP_TABLE",
                "reasons": ["docling_only_table"],
            })
            rescue_children(document, [table], [table], replacement, stats)
            document.delete_items(node_items=[table])
            stats["docling_only_tables_as_text"] += 1
        for picture in document.pictures:
            box = top_left(picture.prov[0], document)
            annotations = []
            for result in vl_results:
                if (result["sha256"] == sha and result["page"] == picture.prov[0].page_no and iou(result["bbox"], box) > 0.9):
                    annotations.append({
                        k: result.get(k) for k in ("visual_type", "task", "model_identity", "extraction_method", "output",
                                                   "quality")} | {"source_sha256": sha, "page": result["page"],
                                                              "bbox": result["bbox"], "derivation": "model_derived"})
                    stats["visual_annotations"] += 1
            if annotations:
                picture.meta = picture.meta or bizaid_meta("visual_results", annotations)
                if picture.meta.get_custom_part().get("bizaid__visual_results") is None:
                    picture.meta.set_custom_field("bizaid", "visual_results", annotations)
        native = page_chars(pdf)
    finally:
        pdf.close()
    before_table_provenance = table_provenance(document)
    before_visual_provenance = visual_provenance(document)
    serialized = document.model_dump_json()
    reloaded = DoclingDocument.model_validate_json(serialized)
    normalized = reloaded.model_dump_json()
    second_reload = DoclingDocument.model_validate_json(normalized)
    after_table_provenance = table_provenance(reloaded)
    after_visual_provenance = visual_provenance(reloaded)
    base_pages, asm_pages = document_chars(baseline), document_chars(reloaded)
    base_chars, chars, native_pages, native = total(base_pages), total(asm_pages), native, total(native)
    lost = loss_pages(native_pages, base_pages, asm_pages, Counter(r["page"] for r in raw_rows))
    report = dict(stats, sha256=sha, pp_regions=len(raw_rows),
                  first_reload_normalized=json.loads(normalized) != json.loads(serialized),
                  json_roundtrip=json.loads(second_reload.model_dump_json()) == json.loads(normalized),
                  markdown_roundtrip=second_reload.export_to_markdown() == reloaded.export_to_markdown(),
                  item_order_roundtrip=before_table_provenance == after_table_provenance,
                  table_provenance_items=len(after_table_provenance),
                  table_provenance_complete=sum(r["complete"] for r in after_table_provenance),
                  visual_provenance_items=len(after_visual_provenance),
                  visual_provenance_complete=sum(r["complete"] for r in after_visual_provenance),
                  visual_provenance_roundtrip=before_visual_provenance == after_visual_provenance,
                  native_chars=sum(native.values()),
                  baseline_missing_chars=sum((native - base_chars).values()), baseline_extra_chars=sum((base_chars - native).values()),
                  assembled_missing_chars=sum((native - chars).values()), assembled_extra_chars=sum((chars - native).values()),
                  loss_pages=lost, picture_conflicts=picture_conflicts, lost_vs_baseline_chars=sum(r["lost_vs_baseline"] for r in lost),
                  tables=len(reloaded.tables), pictures=len(reloaded.pictures))
    write_json(run_dir / "assembled" / f"{sha}.json", json.loads(reloaded.model_dump_json()))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="3-B.3·3-B.4 DoclingDocument 조립 평가")
    parser.add_argument("--run-id", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sha", nargs="+")
    target.add_argument("--all", action="store_true", help="evaluation corpus 전체")
    parser.add_argument("--summary", default="summary.json", help="assembled/ 아래 요약 파일 이름")
    args = parser.parse_args(argv)
    corpus = [d["sha256"] for d in read_json(ROOT / "evals/table_engine/corpus.json")["documents"]]
    vl_path = OUTPUT_ROOT / args.run_id / "visuals/vl_results.json"
    vl_results = read_json(vl_path)["results"] if vl_path.exists() else []
    targets = corpus if args.all else [next(s for s in corpus if s.startswith(prefix)) for prefix in args.sha]
    reports = []
    for sha in targets:
        reports.append(assemble(args.run_id, sha, vl_results))
        # 긴 corpus 실행이 중간에 멈춰도 끝난 문서 결과는 남긴다.
        write_json(OUTPUT_ROOT / args.run_id / "assembled" / args.summary, reports)
        print({k: v for k, v in reports[-1].items() if k not in ("sha256", "loss_pages")}, sha[:12], flush=True)


if __name__ == "__main__":
    main()
