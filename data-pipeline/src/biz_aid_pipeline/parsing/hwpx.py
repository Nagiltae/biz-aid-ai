import io
import re
import zipfile
from pathlib import PurePosixPath

from defusedxml import DefusedXmlException
from defusedxml import ElementTree
from docling_core.types.doc import (ContentLayer, DocItemLabel, DoclingDocument, GroupLabel, RichTableCell, TableCell,
                                    TableData)
from docling_core.types.doc.common.meta import BaseMeta
from docling_core.types.doc.document import DocumentOrigin

SECTION = re.compile(r"Contents/section(\d+)\.xml")
INLINE = {"tab": "\t", "lineBreak": "\n", "fwSpace": " ", "nbSpace": " ", "hyphen": "-"}
# BOUNDARY: 이미지·수식·OLE 등은 OCR/별도 해석 없이는 text가 없으므로 개수만 경고로 남긴다.
EMBEDDED = {"pic", "ole", "equation", "chart", "video", "container"}
# 한글 내장 개요 스타일 이름. 사용자 정의 스타일 이름(예: "제목")은 의미를 추측해야 하므로 heading 근거로 쓰지 않는다.
OUTLINE_STYLE = re.compile(r"(?:개요|Outline) ([1-9]|10)")
# 머리말·꼬리말·각주·미주는 HWPX control 이름으로 명시된다. 본문 읽기 순서와 분리한다.
CONTAINERS = {"header": DocItemLabel.PAGE_HEADER, "footer": DocItemLabel.PAGE_FOOTER,
              "footNote": DocItemLabel.FOOTNOTE, "endNote": DocItemLabel.FOOTNOTE}
FURNITURE = {"header", "footer"}


class HwpxError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def children(element, name):
    return [child for child in element if local(child.tag) == name]


def sublists(element):
    # 중첩 subList를 한 번만 방문해야 글상자·각주 text가 중복되지 않는다.
    for child, _, _ in located_sublists(element, "", None):
        yield child


def located_sublists(element, path, container):
    """subList와 XML 경로, 가장 가까운 머리말·꼬리말·각주 control 이름을 함께 돌려준다."""
    counts = {}
    for child in element:
        name = local(child.tag)
        index = counts[name] = counts.get(name, -1) + 1
        where = f"{path}/{name}[{index}]"
        if name == "subList":
            yield child, where, container
        elif name != "tbl":
            yield from located_sublists(child, where, name if name in CONTAINERS else container)


class HwpxStyles:
    """header.xml의 스타일·문단 모양·번호·글머리표 선언. 문단 구조는 이 명시 정보로만 정한다."""

    def __init__(self, root):
        self.styles, self.headings, self.bullets, self.numberings = {}, {}, {}, {}
        if root is None:
            return
        for element in root.iter():
            name = local(element.tag)
            if name == "style":
                self.styles[element.get("id")] = (element.get("name") or "", element.get("engName") or "")
            elif name == "paraPr":
                heading = next((node for node in element.iter() if local(node.tag) == "heading"), None)
                if heading is not None and heading.get("type", "NONE") != "NONE":
                    self.headings[element.get("id")] = (heading.get("type"), heading.get("idRef"), heading.get("level", "0"))
            elif name == "bullet":
                self.bullets[element.get("id")] = element.get("char")
            elif name == "numbering":
                self.numberings[element.get("id")] = {head.get("level"): (head.get("numFormat"), head.text or "")
                                                      for head in element if local(head.tag) == "paraHead"}

    def classify(self, paragraph):
        """(kind, level, marker, evidence). kind는 heading / list / text다."""
        style_name, style_eng = self.styles.get(paragraph.get("styleIDRef"), ("", ""))
        heading = self.headings.get(paragraph.get("paraPrIDRef"))
        evidence = {"style": style_name or None, "para_pr": paragraph.get("paraPrIDRef")}
        if heading and heading[0] == "OUTLINE":
            return "heading", int(heading[2]) + 1, None, dict(evidence, structure="paraPr.heading=OUTLINE")
        outline = OUTLINE_STYLE.fullmatch(style_name) or OUTLINE_STYLE.fullmatch(style_eng)
        if outline:
            return "heading", int(outline[1]), None, dict(evidence, structure="style=outline")
        if heading and heading[0] in ("NUMBER", "BULLET"):
            level = int(heading[2]) + 1
            if heading[0] == "BULLET":
                return "list", level, self.bullets.get(heading[1]), dict(evidence, structure="paraPr.heading=BULLET",
                                                                         list_id=f"bullet:{heading[1]}")
            numbering = self.numberings.get(heading[1], {}).get(str(level), (None, None))
            # BOUNDARY: 실제 번호 값은 앞 문단 누적 계산이 필요해 만들지 않는다. 번호 형식 선언만 provenance로 남긴다.
            return "list", level, None, dict(evidence, structure="paraPr.heading=NUMBER", list_id=f"numbering:{heading[1]}",
                                              numbering_format=numbering[0], numbering_template=numbering[1])
        return "text", None, None, dict(evidence, structure="none")


class HwpxDoclingAdapter:
    """HWPX native XML을 DoclingDocument로 옮긴다. 별도 문서 tree를 만들지 않는다."""

    def __init__(self, contract):
        self.limits = contract["hwpx_container_limits"]
        self.version = contract["versioning"]["hwpx_adapter_version"]

    def convert(self, raw, source_sha256, result):
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except (zipfile.BadZipFile, ValueError, EOFError):
            raise HwpxError("PARSE_FAILED", "invalid_zip_container") from None
        with archive:
            sections = self.sections(archive, result)
            document = DoclingDocument(name=source_sha256, origin=DocumentOrigin(
                # EXCEPTION: docling-core가 HWPX MIME을 거부하므로 실제 format은 BizAid 결과 봉투의 detected_format이 소유한다.
                mimetype="application/octet-stream", binary_hash=int(source_sha256[:16], 16),
                filename=f"{source_sha256}.hwpx"))
            header = self.xml(archive, "Contents/header.xml") if "Contents/header.xml" in archive.namelist() else None
            if header is None:
                # EXCEPTION: 스타일 선언이 없으면 heading·list 근거가 없으므로 모든 문단을 문단으로 두고 드러낸다.
                result.warn("HWPX_STYLE_HEADER_MISSING")
            self.styles, self.sha, self.list_group = HwpxStyles(header), source_sha256, None
            for name in sections:
                root = self.xml(archive, name)
                for index, paragraph in enumerate(children(root, "p")):
                    self.paragraph(document, paragraph, result, name, f"p[{index}]", None)
        result.unit_count = len(sections)
        return document

    def sections(self, archive, result):
        entries = archive.infolist()
        limits = self.limits
        names = [entry.filename for entry in entries]
        if len(entries) > limits["max_entries"] or len(set(names)) != len(names):
            raise HwpxError("REJECTED_UNSAFE", "container_entries_rejected")
        total = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                    or re.match(r"[A-Za-z]:", entry.filename)):
                raise HwpxError("REJECTED_UNSAFE", "container_path_rejected")
            if entry.flag_bits & 0x1:
                raise HwpxError("ENCRYPTED", "encrypted_entry")
            total += entry.file_size
            if (entry.file_size >= limits["compression_ratio_min_entry_bytes"]
                    and entry.file_size > limits["max_compression_ratio"] * max(entry.compress_size, 1)):
                raise HwpxError("REJECTED_UNSAFE", "compression_ratio_exceeded")
        if total > limits["max_total_uncompressed_bytes"]:
            raise HwpxError("REJECTED_UNSAFE", "uncompressed_size_exceeded")
        available = {name for name in names if SECTION.fullmatch(name)}
        if not available:
            raise HwpxError("PARSE_FAILED", "missing_section_xml")
        if len(available) > limits["max_sections"]:
            raise HwpxError("REJECTED_UNSAFE", "section_count_exceeded")
        ordered = self.spine(archive, available)
        if ordered is None:
            # EXCEPTION: content.hpf spine이 없거나 불완전하면 파일명 번호 순서를 쓰고 추정임을 경고한다.
            result.warn("SECTION_ORDER_FROM_FILENAME")
            ordered = sorted(available, key=lambda name: int(SECTION.fullmatch(name)[1]))
        return ordered

    def spine(self, archive, available):
        if "Contents/content.hpf" not in archive.namelist():
            return None
        root = self.xml(archive, "Contents/content.hpf")
        hrefs = {item.get("id"): item.get("href") for item in root.iter() if local(item.tag) == "item"}
        ordered = [hrefs.get(ref.get("idref")) for ref in root.iter() if local(ref.tag) == "itemref"]
        ordered = [name for name in ordered if name in available]
        return ordered if set(ordered) == available and len(ordered) == len(available) else None

    def xml(self, archive, name):
        if archive.getinfo(name).file_size > self.limits["max_xml_entry_bytes"]:
            raise HwpxError("REJECTED_UNSAFE", "xml_entry_size_exceeded")
        try:
            return ElementTree.fromstring(archive.read(name), forbid_dtd=True)
        except DefusedXmlException:
            raise HwpxError("REJECTED_UNSAFE", "xml_declaration_rejected") from None
        except ElementTree.ParseError:
            raise HwpxError("PARSE_FAILED", "malformed_xml") from None
        except RuntimeError:
            raise HwpxError("ENCRYPTED", "encrypted_entry") from None

    @staticmethod
    def text(element):
        parts = [element.text or ""]
        for child in element:
            parts.append(INLINE.get(local(child.tag), ""))
            parts.append(child.tail or "")
        return "".join(parts)

    def provenance(self, section, path, **extra):
        # BOUNDARY: HWPX XML에는 page·좌표가 없으므로 ProvenanceItem(page/bbox)을 만들지 않고 section·XML 경로만 남긴다.
        meta = BaseMeta()
        meta.set_custom_field("bizaid", "hwpx", dict(sorted(dict(extra, source_sha256=self.sha, section=section, path=path).items())))
        return meta

    def emit(self, document, text, kind, level, marker, evidence, container, section, path, parent):
        layer = ContentLayer.FURNITURE if container in FURNITURE else None
        if kind == "heading" and container == "table_cell":
            # BOUNDARY: 표 cell 안 문단은 문서 제목이 아니다. 개요 스타일이 cell 글자에 걸린 문서가 있어 cell에서는 heading을 만들지 않는다.
            kind, evidence = "text", dict(evidence, structure=evidence["structure"] + " (ignored in table cell)")
        meta = self.provenance(section, path, container=container or "body",
                               level=level, **{k: v for k, v in evidence.items() if v is not None})
        if container in CONTAINERS:
            # 머리말·꼬리말·각주 안에서는 control 종류가 문단 역할이다. 본문 heading·list로 올리지 않는다.
            self.list_group = None
            item = document.add_text(label=CONTAINERS[container], text=text, content_layer=layer, parent=parent)
        elif kind == "heading":
            self.list_group = None
            item = document.add_heading(text=text, level=min(level, 100), parent=parent)
        elif kind == "list":
            key = (container, evidence["list_id"], parent.self_ref if parent is not None else None)
            if self.list_group is None or self.list_group[0] != key:
                # 같은 번호·글머리표 선언이 연속되는 동안 한 목록이다. 사이에 다른 item이 오면 목록을 닫는다.
                self.list_group = (key, document.add_list_group(parent=parent))
            item = document.add_list_item(text=text, enumerated=evidence["structure"].endswith("NUMBER"), marker=marker,
                                          parent=self.list_group[1])
        else:
            self.list_group = None
            item = document.add_text(label=DocItemLabel.PARAGRAPH, text=text, content_layer=layer, parent=parent)
        item.meta = meta

    def paragraph(self, document, paragraph, result, section, path, container, parent=None):
        buffer = []
        kind, level, marker, evidence = self.styles.classify(paragraph)
        evidence = dict(evidence, paragraph_id=paragraph.get("id"))

        def flush():
            value = "".join(buffer)
            buffer.clear()
            if value.strip():
                self.emit(document, value, kind, level, marker, evidence, container, section, path, parent)

        for run_index, run in enumerate(children(paragraph, "run")):
            run_path = f"{path}/run[{run_index}]"
            counts = {}
            for child in run:
                name = local(child.tag)
                index = counts[name] = counts.get(name, -1) + 1
                if name == "t":
                    buffer.append(self.text(child))
                elif name == "tbl":
                    flush()
                    self.list_group = None
                    self.table(document, child, result, section, f"{run_path}/tbl[{index}]", parent)
                else:
                    nested = list(located_sublists(child, f"{run_path}/{name}[{index}]",
                                                   name if name in CONTAINERS else container))
                    if nested:
                        flush()
                        for sublist, where, inner_container in nested:
                            for inner_index, inner in enumerate(children(sublist, "p")):
                                self.paragraph(document, inner, result, section, f"{where}/p[{inner_index}]", inner_container,
                                               parent)
                    elif name in EMBEDDED:
                        result.warn("EMBEDDED_OBJECT_SKIPPED")
        flush()

    def cell_text(self, cell):
        """cell 전체 text(중첩 subList·표 포함)를 줄 단위로 평탄화한다. 구조가 있는 cell은 RichTableCell이 구조를 따로 가진다."""
        lines = []
        for sublist in sublists(cell):
            for paragraph in sublist.iter():
                if local(paragraph.tag) == "p":
                    value = "".join(self.text(node) for run in children(paragraph, "run")
                                    for node in children(run, "t"))
                    if value.strip():
                        lines.append(value)
        return "\n".join(lines)

    def structured(self, cell):
        """cell 안에 번호·글머리표 목록이나 중첩 표가 있으면 문자열 cell로는 구조를 잃는다."""
        return any(local(node.tag) == "tbl" or (local(node.tag) == "p" and self.styles.classify(node)[0] == "list")
                   for node in cell.iter() if node is not cell)

    def table(self, document, table, result, section, path, parent=None):
        entries = []
        for row_position, row in enumerate(children(table, "tr")):
            for cell_position, cell in enumerate(children(row, "tc")):
                address = next(iter(children(cell, "cellAddr")), None)
                span = next(iter(children(cell, "cellSpan")), None)
                try:
                    row_index = int(address.get("rowAddr"))
                    col_index = int(address.get("colAddr"))
                    row_span = int(span.get("rowSpan", 1)) if span is not None else 1
                    col_span = int(span.get("colSpan", 1)) if span is not None else 1
                except (AttributeError, TypeError, ValueError):
                    result.warn("TABLE_CELL_OUT_OF_RANGE")
                    continue
                if row_index < 0 or col_index < 0 or row_span < 1 or col_span < 1:
                    result.warn("TABLE_CELL_OUT_OF_RANGE")
                    continue
                entries.append((row_index, col_index, row_span, col_span, cell, f"{path}/tr[{row_position}]/tc[{cell_position}]"))
        if not entries:
            return
        try:
            rows = int(table.get("rowCnt"))
            cols = int(table.get("colCnt"))
        except (TypeError, ValueError):
            rows = cols = 0
        # EXCEPTION: 선언된 행/열 수보다 병합 범위가 넓으면 cell을 버리지 않고 표 크기를 넓혀 text 손실을 막는다.
        needed_rows = max(item[0] + item[2] for item in entries)
        needed_cols = max(item[1] + item[3] for item in entries)
        if needed_rows > rows or needed_cols > cols:
            result.warn("TABLE_CELL_OUT_OF_RANGE")
        rows, cols = max(rows, needed_rows), max(cols, needed_cols)
        item = document.add_table(data=TableData(num_rows=rows, num_cols=cols, table_cells=[]), parent=parent)
        item.meta = self.provenance(section, path, container="body" if parent is None else "table_cell", table_id=table.get("id"))
        for row_index, col_index, row_span, col_span, cell, cell_path in entries:
            coordinates = dict(text=self.cell_text(cell), row_span=row_span, col_span=col_span,
                               start_row_offset_idx=row_index, end_row_offset_idx=row_index + row_span,
                               start_col_offset_idx=col_index, end_col_offset_idx=col_index + col_span)
            if not self.structured(cell):
                document.add_table_cell(item, TableCell(**coordinates))
                continue
            # WHY: cell 안 목록·중첩 표는 표를 부모로 둔 group에 문서 item으로 넣고 RichTableCell이 참조한다.
            # 평탄화된 text는 cell.text에도 남는다(docling 관례). 이전의 NESTED_TABLE_FLATTENED 손실 없이 구조를 보존한다.
            group = document.add_group(parent=item, label=GroupLabel.UNSPECIFIED)
            saved, self.list_group = self.list_group, None
            for sublist, where, _ in located_sublists(cell, cell_path, None):
                for inner_index, inner in enumerate(children(sublist, "p")):
                    self.paragraph(document, inner, result, section, f"{where}/p[{inner_index}]", "table_cell", group)
            self.list_group = saved
            document.add_table_cell(item, RichTableCell(ref=group.get_ref(), **coordinates))
