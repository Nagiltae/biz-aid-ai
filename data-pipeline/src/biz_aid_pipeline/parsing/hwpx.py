import io
import re
import zipfile
from pathlib import PurePosixPath

from defusedxml import DefusedXmlException
from defusedxml import ElementTree
from docling_core.types.doc import DocItemLabel, DoclingDocument, TableCell, TableData
from docling_core.types.doc.document import DocumentOrigin

SECTION = re.compile(r"Contents/section(\d+)\.xml")
INLINE = {"tab": "\t", "lineBreak": "\n", "fwSpace": " ", "nbSpace": " ", "hyphen": "-"}
# BOUNDARY: 이미지·수식·OLE 등은 OCR/별도 해석 없이는 text가 없으므로 개수만 경고로 남긴다.
EMBEDDED = {"pic", "ole", "equation", "chart", "video", "container"}


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
    for child in element:
        if local(child.tag) == "subList":
            yield child
        elif local(child.tag) != "tbl":
            yield from sublists(child)


class HwpxDoclingAdapter:
    """HWPX native XML을 DoclingDocument로 옮긴다. 별도 문서 tree를 만들지 않는다."""

    def __init__(self, contract):
        self.limits = contract["hwpx_container_limits"]
        self.version = contract["versioning"]["adapter_version"]

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
            for name in sections:
                root = self.xml(archive, name)
                for paragraph in children(root, "p"):
                    self.paragraph(document, paragraph, result)
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

    def paragraph(self, document, paragraph, result):
        buffer = []

        def flush():
            value = "".join(buffer)
            buffer.clear()
            if value.strip():
                document.add_text(label=DocItemLabel.PARAGRAPH, text=value)

        for run in children(paragraph, "run"):
            for child in run:
                name = local(child.tag)
                if name == "t":
                    buffer.append(self.text(child))
                elif name == "tbl":
                    flush()
                    self.table(document, child, result)
                else:
                    nested = list(sublists(child))
                    if nested:
                        flush()
                        for sublist in nested:
                            for inner in children(sublist, "p"):
                                self.paragraph(document, inner, result)
                    elif name in EMBEDDED:
                        result.warn("EMBEDDED_OBJECT_SKIPPED")
        flush()

    def cell_text(self, cell, result):
        lines = []
        for sublist in sublists(cell):
            if any(local(node.tag) == "tbl" for node in sublist.iter()):
                # BOUNDARY: DoclingDocument cell은 문자열이므로 중첩 표 구조는 text로만 보존하고 경고한다.
                result.warn("NESTED_TABLE_FLATTENED")
            for paragraph in sublist.iter():
                if local(paragraph.tag) == "p":
                    value = "".join(self.text(node) for run in children(paragraph, "run")
                                    for node in children(run, "t"))
                    if value.strip():
                        lines.append(value)
        return "\n".join(lines)

    def table(self, document, table, result):
        cells = []
        for row in children(table, "tr"):
            for cell in children(row, "tc"):
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
                cells.append((row_index, col_index, row_span, col_span, self.cell_text(cell, result)))
        if not cells:
            return
        try:
            rows = int(table.get("rowCnt"))
            cols = int(table.get("colCnt"))
        except (TypeError, ValueError):
            rows = cols = 0
        # EXCEPTION: 선언된 행/열 수보다 병합 범위가 넓으면 cell을 버리지 않고 표 크기를 넓혀 text 손실을 막는다.
        needed_rows = max(item[0] + item[2] for item in cells)
        needed_cols = max(item[1] + item[3] for item in cells)
        if needed_rows > rows or needed_cols > cols:
            result.warn("TABLE_CELL_OUT_OF_RANGE")
        rows, cols = max(rows, needed_rows), max(cols, needed_cols)
        data = TableData(num_rows=rows, num_cols=cols, table_cells=[
            TableCell(text=text, row_span=row_span, col_span=col_span,
                      start_row_offset_idx=row_index, end_row_offset_idx=row_index + row_span,
                      start_col_offset_idx=col_index, end_col_offset_idx=col_index + col_span)
            for row_index, col_index, row_span, col_span, text in cells])
        document.add_table(data=data)
