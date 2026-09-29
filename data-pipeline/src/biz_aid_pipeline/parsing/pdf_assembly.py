"""Docling backbone과 PP 표 결과를 같은 DoclingDocument로 조립한다. 별도 canonical model을 만들지 않는다.

TABLE_VALID만 TableItem이 되고, 증명되지 않은 표·겹친 PP 영역·PP가 소유하지 않은 Docling 표는 구조 없이
native PDF text로 보존한다. item 단위 provenance는 BaseMeta의 `bizaid__table_quality` 필드에 둔다.
"""
import json
from collections import Counter

from docling_core.types.doc import (BoundingBox, ContentLayer, CoordOrigin, DocItemLabel, ProvenanceItem, TableCell,
                                    TableData)
from docling_core.types.doc.common.meta import BaseMeta

from biz_aid_pipeline.parsing.models import installed_version
from biz_aid_pipeline.parsing.pdf_tables import (TABLE_QUALITY_FAILED, TABLE_VALID, PdfTable, center_in,
                                                 native_words, reading_order_text, word_center)

CONTAIN_TOLERANCE_PT = 2.0
ALL_LAYERS = set(ContentLayer)
PICTURE_OVERLAP_IOU = 0.3


def parser_identity(contract):
    engine = contract["routes"]["PDF"]["table_engine"]
    return (f"paddlex {installed_version('paddlex')} {engine['pipeline']} + paddlepaddle {installed_version('paddlepaddle')} "
            f"+ {engine['adapter']} v{engine['adapter_version']} + pdfium native text")


def docling_identity():
    return f"docling-slim {installed_version('docling-slim')} layout (table structure disabled)"


def iou(a, b):
    inter = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def contained(outer, inner, tolerance=CONTAIN_TOLERANCE_PT):
    return (inner[0] >= outer[0] - tolerance and inner[1] >= outer[1] - tolerance
            and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance)


def top_left(prov, document):
    box = prov.bbox.to_top_left_origin(page_height=document.pages[prov.page_no].size.height)
    return [box.l, box.t, box.r, box.b]


def bizaid_meta(name, value):
    # WHY: 저장 artifact는 key를 정렬하므로 처음부터 정렬해 두어야 재적재 전후 Markdown·JSON 표현이 같다.
    meta = BaseMeta()
    meta.set_custom_field("bizaid", name, json.loads(json.dumps(value, sort_keys=True)))
    return meta


def provenance(page_no, bbox, text):
    return ProvenanceItem(page_no=page_no, charspan=(0, len(text)),
                          bbox=BoundingBox(l=bbox[0], t=bbox[1], r=bbox[2], b=bbox[3], coord_origin=CoordOrigin.TOPLEFT))


def table_data(cells):
    rows = max((c["row"] + c["rowspan"] for c in cells), default=0)
    cols = max((c["col"] + c["colspan"] for c in cells), default=0)
    return TableData(num_rows=rows, num_cols=cols, table_cells=[
        TableCell(text=c["text"], row_span=c["rowspan"], col_span=c["colspan"], start_row_offset_idx=c["row"],
                  end_row_offset_idx=c["row"] + c["rowspan"], start_col_offset_idx=c["col"],
                  end_col_offset_idx=c["col"] + c["colspan"]) for c in cells])


def resolve_overlaps(tables):
    """같은 page에서 한 PP 영역의 중심이 다른 영역 안에 있으면 한 그룹이다. 그룹은 고르지 않고 합친 영역 하나로 바꾼다."""
    # WHY: 그룹마다 표 하나를 고르면 구조가 틀리거나(container) 같은 text가 두 번 들어간다(duplicate). 둘 다 silent corruption이다.
    parent = list(range(len(tables)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(tables):
        for j, b in enumerate(tables):
            if i != j and a.page == b.page and center_in(b.bbox, (a.bbox[0] + a.bbox[2]) / 2, (a.bbox[1] + a.bbox[3]) / 2):
                parent[find(i)] = find(j)
    groups = {}
    for i, table in enumerate(tables):
        groups.setdefault(find(i), []).append(table)
    resolved = []
    for group in groups.values():
        if len(group) == 1:
            resolved.append((group[0], None))
            continue
        union = [min(t.bbox[0] for t in group), min(t.bbox[1] for t in group),
                 max(t.bbox[2] for t in group), max(t.bbox[3] for t in group)]
        members = [{"bbox_pt": t.bbox, "verdict": t.verdict, "reasons": t.reasons} for t in group]
        resolved.append((PdfTable(group[0].page, union, TABLE_QUALITY_FAILED, ["unresolved_overlapping_pp_regions"]), members))
    return resolved


def has_bizaid(item):
    return bool(item.meta and any(key.startswith("bizaid__") for key in item.meta.get_custom_part()))


def region_items(document, page_no, bbox):
    """PP 영역이 소유해 지울 Docling item과, 중심만 영역 안이라 남길 부분 겹침 text item을 나눈다."""
    # BOUNDARY: 이미 조립한 결과(bizaid 필드)는 다른 PP 영역이 지우지 못한다.
    # WHY: Docling은 그림 안 text를 picture 자식으로 두고 iterate_items 기본값은 그 안을 순회하지 않는다.
    # PP가 같은 영역을 표로 읽으면 text가 두 번 들어가므로 picture 자식도 영역 소유 판정에 넣는다.
    owned = [item for item, _ in document.iterate_items(traverse_pictures=True)
             if getattr(item, "prov", None) and item.prov[0].page_no == page_no and item.label != DocItemLabel.PICTURE
             and not has_bizaid(item)
             and center_in(bbox, *(lambda b: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))(top_left(item.prov[0], document)))]
    # WHY: 중심만 영역 안이고 일부가 밖에 걸친 text item을 지우면 밖 부분이 사라진다. 이런 item은 남긴다.
    # 남긴 item은 조립 끝에 trim_overlapping_native가 영역 밖 단어로만 text를 다시 만들어 중복을 없앤다.
    partial = [item for item in owned if item.label != DocItemLabel.TABLE and not contained(bbox, top_left(item.prov[0], document))]
    return [item for item in owned if not any(item is other for other in partial)], partial


def within(item, removing, document):
    while item is not None:
        if any(item is other for other in removing):
            return True
        item = item.parent.resolve(document) if getattr(item, "parent", None) else None
    return False


def anchor(document, page_no, top, removing):
    """삽입 위치: 같은 쪽에서 top이 표 top 이하인 마지막 item. 없으면 쪽 첫 item 앞이다."""
    # WHY: 삭제될 item이나 그 자식 옆에 넣으면 새 item이 함께 지워진다.
    candidates = [(item, top_left(item.prov[0], document)) for item, _ in document.iterate_items()
                  if getattr(item, "prov", None) and item.prov[0].page_no == page_no and not within(item, removing, document)]
    before = [(index, pair) for index, pair in enumerate(candidates) if pair[1][1] <= top]
    if before:
        # WHY: 같은 행 item은 top이 같다. 동점이면 문서 순서상 마지막 item 뒤에 넣어야 행 중간에 끼지 않는다(3-B.13 HWP p13).
        return max(before, key=lambda entry: (entry[1][1][1], entry[0]))[1][0], True
    return (candidates[0][0], False) if candidates else (None, True)


def insert_text(document, sibling, after, page_no, bbox, text):
    prov = provenance(page_no, bbox, text)
    if sibling is None:
        return document.add_text(label=DocItemLabel.TEXT, text=text, prov=prov)
    return document.insert_text(sibling=sibling, label=DocItemLabel.TEXT, text=text, prov=prov, after=after)


def rescue_children(document, parents, removing, after_item):
    """삭제할 item의 자식 중 삭제 대상이 아닌 text를 같은 label·provenance의 새 item으로 옮긴다."""
    # WHY: Docling은 표 caption·footnote를 표의 자식으로 두므로 부모를 지우면 영역 밖 text도 함께 사라진다.
    last, moved_count = after_item, 0
    for parent in parents:
        for ref in list(getattr(parent, "children", None) or []):
            child = ref.resolve(document)
            if any(child is other for other in removing):
                continue
            if not hasattr(child, "text"):
                # WHY: table structure를 끈 Docling은 표 안 text를 표 아래 group의 자식으로 둔다. group 안까지 내려가 보존한다.
                last, nested = rescue_children(document, [child], removing, last)
                moved_count += nested
                continue
            label = child.label if child.label in (DocItemLabel.CAPTION, DocItemLabel.FOOTNOTE) else DocItemLabel.TEXT
            moved = document.insert_text(sibling=last, label=label, text=child.text,
                                         prov=child.prov[0] if child.prov else None, after=True)
            moved.meta = bizaid_meta("rescued", {"original_label": str(child.label)})
            moved_count += 1
            last, nested = rescue_children(document, [child], removing, moved)
            moved_count += nested
    return last, moved_count


def outside_cell_words(region_words, cells):
    """VALID 표 영역 안 native 단어 중 어떤 cell text에도 쓰이지 않은 단어. 글자 multiset으로 소비해 비교한다."""
    pool = Counter(ch for cell in cells for ch in cell["text"] if not ch.isspace())
    leftover = []
    for box, text in region_words:
        need = Counter(ch for ch in text if not ch.isspace())
        if all(pool[ch] >= count for ch, count in need.items()):
            pool.subtract(need)
        else:
            leftover.append((box, text))
    return leftover


def spill_words(page_words, table_box, page_regions, surviving_boxes):
    """지우는 Docling 표 bbox 안이지만 어느 PP 영역에도, 남는 item에도 속하지 않는 native 단어."""
    # BOUNDARY: 같은 쪽 다른 PP 영역이나 남는 item(caption·footnote 포함)의 단어는 다시 넣지 않는다.
    return [w for w in page_words if center_in(table_box, *word_center(w))
            and not any(center_in(region, *word_center(w)) for region in page_regions)
            and not any(center_in(kept, *word_center(w)) for kept in surviving_boxes)]


class _Assembler:
    def __init__(self, document, pdf, source_sha256, contract, result, layers):
        self.document, self.pdf, self.sha, self.result = document, pdf, source_sha256, result
        # OCR한 page는 OCR 단어가 그 page의 text layer다. 나머지 page는 PDF native 단어를 쓴다.
        self.pp_identity, self.words = parser_identity(contract), {page: words for page, (_, words) in (layers or {}).items()}

    def page_words(self, page_no):
        if page_no not in self.words:
            page = self.pdf[page_no - 1]
            self.words[page_no] = native_words(page, 1.0, page.get_size()[1])
        return self.words[page_no]

    def quality(self, page_no, bbox, verdict, reasons, identity, **extra):
        return bizaid_meta("table_quality", dict({"source_sha256": self.sha, "page": page_no, "bbox_pt": bbox,
                                                  "parser_identity": identity, "verdict": verdict, "reasons": reasons}, **extra))

    def surviving_boxes(self, page_no, removing):
        return [top_left(i.prov[0], self.document) for i, _ in self.document.iterate_items(traverse_pictures=True)
                if getattr(i, "prov", None) and i.prov[0].page_no == page_no and i.label != DocItemLabel.PICTURE
                and not any(i is other for other in removing)]

    def place(self, table, members, page_regions):
        document, bbox, page_no = self.document, table.bbox, table.page
        removing, _ = region_items(document, page_no, bbox)
        region_words = [w for w in self.page_words(page_no) if center_in(bbox, *word_center(w))]
        if any(p.prov and p.prov[0].page_no == page_no and iou(top_left(p.prov[0], document), bbox) > PICTURE_OVERLAP_IOU
               for p in document.pictures):
            # BOUNDARY: picture와 PP 표가 같은 영역이면 어느 해석이 맞는지 정하지 않고 경고로만 드러낸다.
            self.result.warn("PDF_TABLE_PICTURE_OVERLAP")
        sibling, after = anchor(document, page_no, bbox[1], removing)
        extra = {"overlap_members": members} if members else {}
        if table.verdict == TABLE_VALID:
            data, prov = table_data(table.cells), provenance(page_no, bbox, "")
            item = (document.insert_table(sibling=sibling, data=data, prov=prov, after=after)
                    if sibling is not None else document.add_table(data=data, prov=prov))
        else:
            item = insert_text(document, sibling, after, page_no, bbox, reading_order_text(region_words))
            self.result.warn("PDF_TABLE_OVERLAP_PRESERVED_AS_TEXT" if members else "PDF_TABLE_QUALITY_FAILED")
        item.meta = self.quality(page_no, bbox, table.verdict, table.reasons, self.pp_identity, **extra)
        last = item
        if table.verdict == TABLE_VALID:
            # WHY: grid adapter는 cell box 밖 단어를 버린다. 표 밖 text로 보존한다.
            leftover = outside_cell_words(region_words, table.cells)
            if leftover:
                last = insert_text(document, item, True, page_no, bbox, reading_order_text(leftover))
                last.meta = self.quality(page_no, bbox, TABLE_VALID, ["valid_table_text_outside_cells"], self.pp_identity)
        surviving = self.surviving_boxes(page_no, removing)
        for docling_table in [i for i in removing if i.label == DocItemLabel.TABLE
                              and not contained(bbox, top_left(i.prov[0], document))]:
            # WHY: Docling 표가 PP 영역보다 크면 영역 밖 행(제목·단위 표기)이 표와 함께 사라지므로 따로 보존한다.
            box = top_left(docling_table.prov[0], document)
            spill = spill_words(self.page_words(page_no), box, page_regions, surviving)
            if spill:
                last = insert_text(document, last, True, page_no, box, reading_order_text(spill))
                last.meta = self.quality(page_no, box, TABLE_QUALITY_FAILED, ["docling_table_outside_pp_region"],
                                         docling_identity())
        if removing:
            rescue_children(document, removing, removing, last)
            document.delete_items(node_items=removing)
        self.trim_overlapping_native(page_no, bbox, page_regions)

    def trim_overlapping_native(self, page_no, bbox, page_regions):
        """PP 영역과 겹치는 native text item은 영역 밖 native 단어로만 text를 다시 만든다. 영역 안 단어는 PP 결과가 가진다."""
        # WHY: native 단어 하나는 한 곳에만 속해야 한다. 영역에 걸친 제목·각주·옮긴 자식을 통째로 두면 영역 안 글자가 표 결과와
        # 이중으로 들어간다(3-B.13 HWP 변환 PDF p2 각주·p10 금액). 영역 밖 단어가 없으면 item을 지운다. 단어는 원문 text layer다.
        document = self.document
        engine_output = ("bizaid__table_quality", "bizaid__ocr")
        overlapping = [item for item, _ in document.iterate_items(traverse_pictures=True, included_content_layers=ALL_LAYERS)
                       if getattr(item, "prov", None) and item.prov[0].page_no == page_no and hasattr(item, "text")
                       and item.label not in (DocItemLabel.PICTURE, DocItemLabel.TABLE)
                       and not (item.meta and any(key in item.meta.get_custom_part() for key in engine_output))
                       and overlaps(top_left(item.prov[0], document), bbox)]
        emptied = []
        for item in overlapping:
            box = top_left(item.prov[0], document)
            text = reading_order_text([w for w in self.page_words(page_no) if center_in(box, *word_center(w))
                                       and not any(center_in(region, *word_center(w)) for region in page_regions)])
            if text.strip():
                item.text = item.orig = text
                item.meta = bizaid_meta("trimmed_by_table_region", {"source_sha256": self.sha, "page": page_no,
                                                                   "table_bbox_pt": bbox, "original_label": str(item.label)})
            elif not getattr(item, "children", None):
                emptied.append(item)
        if emptied:
            document.delete_items(node_items=emptied)

    def keep_docling_tables(self, regions_by_page):
        """PP가 소유하지 않은 Docling 표는 구조 없이 bbox 안 native text로 남긴다(TableFormer는 실행하지 않는다)."""
        document = self.document
        for table in [t for t in document.tables if not has_bizaid(t)]:
            page_no, box = table.prov[0].page_no, top_left(table.prov[0], document)
            # 표 bbox 안 자손 text는 같은 native text에서 온 것이므로 하나의 비구조 text item으로 합친다. bbox 밖 자손은 옮겨 보존한다.
            inside = [item for item, _ in document.iterate_items(root=table, traverse_pictures=True)
                      if item is not table and getattr(item, "prov", None)
                      and center_in(box, *(lambda b: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))(top_left(item.prov[0], document)))]
            removing = [table] + inside
            surviving = self.surviving_boxes(page_no, removing)
            text = reading_order_text(spill_words(self.page_words(page_no), box, regions_by_page.get(page_no, []), surviving))
            replacement = insert_text(document, table, True, page_no, box, text)
            replacement.meta = self.quality(page_no, box, TABLE_QUALITY_FAILED, ["docling_only_table"], docling_identity())
            rescue_children(document, [table], removing, replacement)
            document.delete_items(node_items=[table])
            self.result.warn("PDF_DOCLING_TABLE_PRESERVED_AS_TEXT")


def ocr_reading_order(lines):
    """중심 y가 줄 높이 절반 안이면 같은 행으로 묶고 행 안은 x 순서다. native 단어의 reading_order_text와 같은 규칙이다."""
    rows = []
    for line in sorted(lines, key=lambda item: ((item.bbox[1] + item.bbox[3]) / 2, item.bbox[0])):
        center, height = (line.bbox[1] + line.bbox[3]) / 2, line.bbox[3] - line.bbox[1]
        if rows and abs(rows[-1][0] - center) <= 0.5 * max(height, 1):
            rows[-1][1].append(line)
        else:
            rows.append([center, [line]])
    return [line for _, row in rows for line in sorted(row, key=lambda item: item.bbox[0])]


def add_ocr_lines(document, ocr_lines, regions_by_page, source_sha256, identity):
    """PP 표 영역 밖 OCR 줄을 읽기 순서로 text item에 넣는다. 표 영역 안 줄은 표 조립이 OCR 단어로 채운다."""
    for page_no, lines in sorted(ocr_lines.items()):
        regions = regions_by_page.get(page_no, [])
        previous = None
        for line in ocr_reading_order(lines):
            center = ((line.bbox[0] + line.bbox[2]) / 2, (line.bbox[1] + line.bbox[3]) / 2)
            if any(center_in(region, *center) for region in regions):
                continue
            # WHY: 줄마다 top으로 위치를 찾으면 같은 행의 줄이 먼저 넣은 줄 바로 뒤로 들어가 순서가 뒤집힌다(04596fcf p1).
            # 첫 줄만 page 안 위치를 찾고 이후 줄은 직전 줄 뒤에 둔다.
            sibling, after = (previous, True) if previous is not None else anchor(document, page_no, line.bbox[1], [])
            item = insert_text(document, sibling, after, page_no, line.bbox, line.text)
            previous = item
            # OCR text는 모델 파생 text다. 원본 SHA·page·bbox·confidence·engine identity를 item에 남긴다.
            item.meta = bizaid_meta("ocr", {"source_sha256": source_sha256, "page": page_no, "bbox_pt": line.bbox,
                                            "confidence": round(line.confidence, 4), "engine": identity})


def remove_native_content_on_ocr_pages(document, page_numbers):
    """OCR이 page text layer를 대체하므로 그 page의 기존 native content item을 제거한다. picture layout은 유지한다."""
    pages = set(page_numbers)
    # WHY: iterate_items 기본값은 본문 layer만 순회해 furniture의 쪽 번호가 남고 OCR이 같은 글자를 다시 넣었다(3-B.13 HWP p13).
    removing = [item for item, _ in document.iterate_items(traverse_pictures=True, included_content_layers=ALL_LAYERS)
                if getattr(item, "prov", None) and item.prov[0].page_no in pages
                and item.label != DocItemLabel.PICTURE and not has_bizaid(item)]
    if removing:
        # WHY: low-text page의 남은 native 글자를 그대로 두면 full-page OCR이 같은 글자를 다시 넣어 중복된다.
        document.delete_items(node_items=removing)


def assemble(document, pdf, tables, source_sha256, contract, result, layers=None, ocr_lines=None, ocr_engine=None):
    """Docling 문서에 PP 표(와 OCR page의 text 줄)를 넣는다. pdf는 같은 byte로 연 pypdfium2 문서이며 호출자가 닫는다."""
    assembler = _Assembler(document, pdf, source_sha256, contract, result, layers)
    regions_by_page = {}
    for table in tables:
        regions_by_page.setdefault(table.page, []).append(table.bbox)
    if ocr_lines:
        remove_native_content_on_ocr_pages(document, ocr_lines)
        add_ocr_lines(document, ocr_lines, regions_by_page, source_sha256, ocr_engine)
    for table, members in resolve_overlaps(tables):
        assembler.place(table, members, regions_by_page[table.page])
    assembler.keep_docling_tables(regions_by_page)
    return document
