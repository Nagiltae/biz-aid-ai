import copy
import hashlib
import io
import sys
import unittest
from unittest import mock
import warnings
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from docling_core.types.doc import DocItemLabel, DoclingDocument, RichTableCell

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing import parse_document, route_for
from biz_aid_pipeline.parsing.models import ParseRequest, ParseResult, parse_identity, parse_key, parsing_contract
from biz_aid_pipeline.parsing.quality import apply_gate, artifact_bytes, normalize_document

NS = ('xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
      'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"')


def paragraph(body):
    return f"<hp:p><hp:run>{body}</hp:run></hp:p>"


def cell(row, col, text, row_span=1, col_span=1):
    return (f'<hp:tc><hp:subList>{paragraph(f"<hp:t>{text}</hp:t>")}</hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
            f'<hp:cellSpan colSpan="{col_span}" rowSpan="{row_span}"/></hp:tc>')


def section(*paragraphs):
    return f'<?xml version="1.0" encoding="UTF-8"?><hs:sec {NS}>{"".join(paragraphs)}</hs:sec>'


HEADER = ('<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"><hh:refList>'
          '<hh:paraProperties>'
          '<hh:paraPr id="1"><hh:heading type="OUTLINE" idRef="0" level="1"/></hh:paraPr>'
          '<hh:paraPr id="2"><hh:heading type="NUMBER" idRef="1" level="0"/></hh:paraPr>'
          '<hh:paraPr id="3"><hh:heading type="BULLET" idRef="1" level="0"/></hh:paraPr>'
          '<hh:paraPr id="4"><hh:heading type="NONE" idRef="0" level="0"/></hh:paraPr></hh:paraProperties>'
          '<hh:numberings><hh:numbering id="1" start="0"><hh:paraHead level="1" numFormat="DIGIT">^1.</hh:paraHead>'
          '</hh:numbering></hh:numberings><hh:bullets><hh:bullet id="1" char="-"/></hh:bullets>'
          '<hh:styles><hh:style id="0" type="PARA" name="바탕글" engName="Normal" paraPrIDRef="4"/>'
          '<hh:style id="2" type="PARA" name="개요 1" engName="Outline 1" paraPrIDRef="4"/>'
          '<hh:style id="9" type="PARA" name="제목" engName="" paraPrIDRef="4"/></hh:styles></hh:refList></hh:head>')


def styled(body, para_pr="4", style="0", pid="0"):
    return f'<hp:p id="{pid}" paraPrIDRef="{para_pr}" styleIDRef="{style}"><hp:run>{body}</hp:run></hp:p>'


def hwpx(sections, spine=None, extra=None, header="<head/>"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", header)
        for name, xml in sections.items():
            archive.writestr(name, xml)
        if spine is not None:
            items = "".join(f'<opf:item id="s{index}" href="{name}"/>' for index, name in enumerate(spine))
            refs = "".join(f'<opf:itemref idref="s{index}"/>' for index in range(len(spine)))
            archive.writestr("Contents/content.hpf", '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
                             f"<opf:manifest>{items}</opf:manifest><opf:spine>{refs}</opf:spine></opf:package>")
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return buffer.getvalue()


def parse(raw, detected_format="HWPX", contract=None):
    request = ParseRequest(hashlib.sha256(raw).hexdigest(), detected_format, len(raw))
    return parse_document(request, raw, contract)


class DocumentParsingContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = parsing_contract()

    def test_contract_keeps_docling_document_as_the_only_representation(self):
        representation = self.contract["representation"]
        self.assertEqual(representation["document_model"], "DoclingDocument")
        self.assertIs(representation["own_canonical_document_tree"], False)
        self.assertEqual(self.contract["input"]["trusted_format_hints"], [])
        self.assertEqual(self.contract["input"]["format_source"], "document_sources.detected_format")
        for excluded in ("Chunking", "Embedding", "Qdrant"):
            self.assertIn(excluded, self.contract["out_of_scope"])
        # OCR은 low-text page에만 허용되고 Docling 자체 OCR은 계속 꺼져 있다.
        self.assertEqual(self.contract["routes"]["PDF"]["ocr"]["selection_scope"], "page")
        self.assertIn("document-average", self.contract["routes"]["PDF"]["ocr"]["trigger"])
        self.assertIs(self.contract["routes"]["PDF"]["docling_options"]["do_ocr"], False)
        # 2026-10-02 공통 기반: 새 판별 형식마다 route가 있어야 한다(없으면 UNSUPPORTED로 떨어진다).
        formats = {"PDF", "HWP", "HWPX", "XLSX", "DOCX", "PPTX", "ODT", "DOC", "XLS", "PPT", "PNG", "JPEG", "HWPML",
                   "ZIP", "OTHER", "UNKNOWN"}
        self.assertEqual(set(self.contract["routes"]), formats)
        self.assertEqual(self.contract["routes"]["PDF"]["route"], "DOCLING_PDF")
        self.assertEqual(self.contract["routes"]["HWP"]["route"], "HWP_PDF_DOCLING")

    def test_count_basis_keeps_unique_binaries_and_relations_separate(self):
        basis = self.contract["count_basis"]
        self.assertEqual(basis["parse_unit"], "unique_content_sha")
        baseline = basis["phase2_5_baseline"]
        by_format = baseline["by_detected_format"]
        # Phase 2.5 기준 집계는 당시 판별 기준(ZIP·OTHER·UNKNOWN 묶음)의 과거 기록이다. 그 형식은 모두 현재 route에 있어야 한다.
        self.assertEqual(set(by_format), {"PDF", "HWP", "HWPX", "ZIP", "XLSX", "OTHER", "UNKNOWN"})
        self.assertLessEqual(set(by_format), set(self.contract["routes"]))
        for name in ("unique_content_sha", "source_relation"):
            self.assertEqual(sum(item[name] for item in by_format.values()), baseline["totals"][name])
        for detected, counts in by_format.items():
            with self.subTest(detected=detected):
                self.assertEqual(set(counts), {"unique_content_sha", "source_relation"})
                self.assertLessEqual(counts["unique_content_sha"], counts["source_relation"])
        self.assertEqual(baseline["totals"], {"unique_content_sha": 3231, "source_relation": 3288})

    def test_pending_policies_stay_disabled_until_decided(self):
        routes = self.contract["routes"]
        # HWP는 전용 Docker 변환기로 PDF를 만든 뒤 PDF route를 재사용하고, HWPX는 native adapter를 유지한다.
        self.assertTrue(routes["HWP"]["enabled"])
        self.assertIn("Docker", routes["HWP"]["converter"]["decision"])
        self.assertEqual(routes["HWPX"]["route"], "HWPX_DOCLING_ADAPTER")
        zip_route = routes["ZIP"]
        self.assertEqual((zip_route["route"], zip_route["enabled"], zip_route["extraction_enabled"]),
                         ("POLICY_PENDING", False, False))
        # DOCX·PPTX·ODT container는 2026-10-02부터 따로 판별하고, ZIP은 일반 압축만 뜻한다.
        self.assertEqual(zip_route["container_subtypes_detected_separately"], ["DOCX", "PPTX", "ODT"])
        self.assertEqual(set(zip_route["generic_zip_member_provenance_required"]), {
            "archive_source_sha256", "member_path", "member_sha256", "member_detected_format",
            "archive_depth", "parent_member_provenance"})
        # 공통 기반 단계에서는 새 형식 route를 정의만 하고 하나도 켜지 않는다.
        for detected in ("XLSX", "DOCX", "PPTX", "ODT", "DOC", "XLS", "PPT", "PNG", "JPEG", "HWPML", "OTHER", "UNKNOWN"):
            self.assertFalse(routes[detected]["enabled"])
        xlsx = routes["XLSX"]
        self.assertEqual(xlsx["limits"], {"max_visible_nonempty_cells": 5000, "max_file_bytes": 10485760, "max_sheets": 20})
        self.assertIn("visible sheets only", xlsx["sheet_policy"])
        self.assertIn("never recalculated", xlsx["formula_policy"])
        self.assertIn("xlsx_limit_exceeded:<visible_nonempty_cells|file_bytes|sheets>", self.contract["failure_codes"]["PARSE_FAILED"])
        self.assertEqual((routes["HWPML"]["route"], routes["PNG"]["route"], routes["DOC"]["route"]),
                         ("POLICY_PENDING", "IMAGE_OCR", "LIBREOFFICE_TO_DOCX"))
        quality = routes["HWPX"]["quality_status"]
        self.assertEqual(quality["validated"], ["Paragraph", "List", "Table", "Reading Order", "Source Location", "Footnote/Header"])
        # 실제 문서에서 명시적 heading을 아직 관찰하지 못했으므로 Heading은 제한 사항으로 남긴다.
        self.assertIn("Heading", quality["limited"])
        self.assertIn("never used", routes["HWPX"]["structure_rules"]["heading"])
        storage = self.contract["artifact_storage"]
        self.assertEqual(storage["persistent_parsed_artifact"], "S3")
        self.assertNotIn("persistent", storage["local_filesystem"])
        self.assertEqual(storage["migration"], "V5__document_parse_results.sql")
        self.assertIn("{parse_key}.json", storage["parsed_key"])
        self.assertIn("S3", storage["commit_order"])
        self.assertIn("MySQL", storage["commit_order"])
        docling = self.contract["dependencies"]["docling"]
        # 3-B는 PDF 전용 extras만 허용하며 OCR engine을 끌어오는 standard/ocr extras를 pin하지 않는다.
        self.assertEqual(docling["pin"], "docling-slim[convert-core,format-pdf,models-local]==2.130.0")
        self.assertNotIn("ocr", docling["pin"])
        self.assertNotIn("standard", docling["pin"])

    def test_router_uses_detected_format_only_and_reports_disabled_routes(self):
        raw = b"%PDF-1.7 synthetic"
        self.assertEqual(route_for("PDF", self.contract), ("DOCLING_PDF", True))
        # HWPX byte라도 detected_format이 HWP이면 HWP 변환 경계로만 보낸다.
        from biz_aid_pipeline.parsing import hwp_pdf
        hwp_pdf._identity.cache_clear()
        with mock.patch.object(hwp_pdf.shutil, "which", return_value=None):
            hwp = parse(hwpx({"Contents/section0.xml": section(paragraph("<hp:t>본문</hp:t>"))}), "HWP")
        hwp_pdf._identity.cache_clear()
        self.assertEqual((hwp.route, hwp.status, hwp.failure_code), ("HWP_PDF_DOCLING", "CONVERSION_FAILED", "hwp_converter_unavailable"))
        for detected in ("ZIP", "HWPML", "OTHER", "UNKNOWN"):
            result = parse(raw, detected)
            self.assertEqual((result.route, result.status, result.failure_code),
                             ("POLICY_PENDING", "ROUTE_NOT_ENABLED", "policy_pending"))
            self.assertIsNone(result.document)
        # 정의만 하고 켜지 않은 새 route는 parser를 부르지 않고 route_not_enabled로 끝난다.
        for detected, route in (("XLSX", "DOCLING_XLSX"), ("DOCX", "DOCLING_DOCX"), ("PPTX", "DOCLING_PPTX"),
                                ("ODT", "LIBREOFFICE_TO_DOCX"), ("XLS", "LIBREOFFICE_TO_XLSX"), ("PNG", "IMAGE_OCR")):
            result = parse(raw, detected)
            self.assertEqual((result.route, result.status, result.failure_code), (route, "ROUTE_NOT_ENABLED", "route_not_enabled"))
            self.assertIsNone(result.document)
        unknown = parse(raw, "RTF")
        self.assertEqual((unknown.status, unknown.failure_code), ("UNSUPPORTED_FORMAT", "unknown_detected_format"))
        self.assertEqual(route_for("HWPX", self.contract), ("HWPX_DOCLING_ADAPTER", True))

    def test_input_bytes_must_match_database_metadata(self):
        raw = b"%PDF-1.7 synthetic"
        with self.assertRaisesRegex(PipelineError, "parse_input_integrity_mismatch"):
            parse_document(ParseRequest("0" * 64, "PDF", len(raw)), raw)
        with self.assertRaisesRegex(PipelineError, "parse_input_integrity_mismatch"):
            parse_document(ParseRequest(hashlib.sha256(raw).hexdigest(), "PDF", len(raw) + 1), raw)
        with self.assertRaisesRegex(PipelineError, "invalid_source_sha256"):
            ParseRequest("ABC", "PDF", 1)

    def test_hwpx_becomes_reloadable_docling_document_with_tables_and_normalization(self):
        table = ('<hp:tbl rowCnt="2" colCnt="2"><hp:tr>' + cell(0, 0, "지원금액", col_span=2) + "</hp:tr><hp:tr>"
                 + cell(1, 0, "5천만원") + cell(1, 1, "80%") + "</hp:tr></hp:tbl>")
        raw = hwpx({"Contents/section0.xml": section(
            paragraph("<hp:t>사업목적<hp:tab/>안내<hp:lineBreak/>둘째 줄   </hp:t>"),
            paragraph(table),
            paragraph("<hp:t>é</hp:t>"))}, spine=["Contents/section0.xml"])
        result = parse(raw)
        self.assertEqual((result.status, result.route, result.unit_count), ("PARSED", "HWPX_DOCLING_ADAPTER", 1))
        self.assertEqual(result.warnings, {})
        document = result.document
        self.assertIsInstance(document, DoclingDocument)
        self.assertEqual(document.texts[0].text, "사업목적\t안내\n둘째 줄")
        self.assertEqual(document.texts[0].orig, "사업목적\t안내\n둘째 줄   ")
        self.assertEqual(document.texts[1].text, "é")
        grid = [[item.text for item in row] for row in document.tables[0].data.grid]
        self.assertEqual(grid, [["지원금액", "지원금액"], ["5천만원", "80%"]])
        reloaded = DoclingDocument.model_validate_json(artifact_bytes(document))
        self.assertEqual(reloaded.export_to_markdown(), document.export_to_markdown())
        self.assertEqual(result.text_chars, len("사업목적안내둘째줄지원금액5천만원80%é"))

    def test_normalization_applies_to_any_docling_document_and_keeps_orig(self):
        document = DoclingDocument(name="pdf-like")
        document.add_text(label="text", text="지원\u0007대상\r\n다음 줄  ")
        result = ParseResult("0" * 64, "PDF", "DOCLING_PDF", "0" * 64, "ROUTE_NOT_ENABLED")
        normalize_document(document, result)
        self.assertEqual(document.texts[0].text, "지원대상\n다음 줄")
        self.assertEqual(document.texts[0].orig, "지원\u0007대상\r\n다음 줄  ")
        self.assertEqual(result.warnings, {"CONTROL_CHARACTERS_REMOVED": 1})
        # 재정규화는 orig에서 다시 계산하므로 text가 누적 변형되지 않는다.
        normalize_document(document, ParseResult("0" * 64, "PDF", "DOCLING_PDF", "0" * 64, "ROUTE_NOT_ENABLED"))
        self.assertEqual(document.texts[0].text, "지원대상\n다음 줄")

    def test_section_order_follows_spine_and_falls_back_with_warning(self):
        sections = {"Contents/section0.xml": section(paragraph("<hp:t>둘째</hp:t>")),
                    "Contents/section1.xml": section(paragraph("<hp:t>첫째</hp:t>"))}
        ordered = parse(hwpx(sections, spine=["Contents/section1.xml", "Contents/section0.xml"]))
        self.assertEqual([item.text for item in ordered.document.texts], ["첫째", "둘째"])
        self.assertNotIn("SECTION_ORDER_FROM_FILENAME", ordered.warnings)
        fallback = parse(hwpx(sections))
        self.assertEqual([item.text for item in fallback.document.texts], ["둘째", "첫째"])
        self.assertEqual(fallback.warnings["SECTION_ORDER_FROM_FILENAME"], 1)

    def test_textbox_nested_table_and_embedded_object_are_explicit(self):
        nested = '<hp:tbl rowCnt="1" colCnt="1"><hp:tr>' + cell(0, 0, "내부") + "</hp:tr></hp:tbl>"
        outer_cell = (f'<hp:tc><hp:subList>{paragraph("<hp:t>외부</hp:t>")}{paragraph(nested)}</hp:subList>'
                      '<hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/></hp:tc>')
        textbox = f'<hp:rect><hp:drawText><hp:subList>{paragraph("<hp:t>글상자</hp:t>")}</hp:subList></hp:drawText></hp:rect>'
        raw = hwpx({"Contents/section0.xml": section(
            paragraph(f'<hp:tbl rowCnt="1" colCnt="1"><hp:tr>{outer_cell}</hp:tr></hp:tbl>'),
            paragraph(textbox), paragraph("<hp:pic/>"))})
        result = parse(raw)
        self.assertEqual(result.status, "PARSED")
        document = result.document
        outer = document.tables[0].data.table_cells[0]
        # 중첩 표는 평탄화하지 않고 표를 부모로 둔 group에 두며 RichTableCell이 참조한다. 평탄화 text도 cell.text에 남는다.
        self.assertIsInstance(outer, RichTableCell)
        self.assertEqual(outer.text, "외부\n내부")
        group = outer.ref.resolve(document)
        self.assertEqual(group.parent.cref, document.tables[0].self_ref)
        self.assertEqual([child.resolve(document).label for child in group.children], [DocItemLabel.PARAGRAPH, DocItemLabel.TABLE])
        self.assertEqual(document.tables[1].data.table_cells[0].text, "내부")
        self.assertNotIn("NESTED_TABLE_FLATTENED", result.warnings)
        self.assertEqual([item.text for item, _ in document.iterate_items(root=document.body) if item.label == DocItemLabel.PARAGRAPH
                          and item.parent.cref == "#/body"], ["글상자"])
        self.assertEqual(result.warnings["EMBEDDED_OBJECT_SKIPPED"], 1)
        # 중첩 표도 원문 text 손실 없이 한 번만 센다.
        self.assertEqual(result.text_chars, len("외부내부글상자"))

    def test_explicit_hwpx_structure_becomes_heading_list_and_notes(self):
        footnote = f'<hp:ctrl><hp:footNote><hp:subList>{styled("<hp:t>각주 내용</hp:t>")}</hp:subList></hp:footNote></hp:ctrl>'
        header = f'<hp:ctrl><hp:header><hp:subList>{styled("<hp:t>머리말</hp:t>")}</hp:subList></hp:header></hp:ctrl>'
        table = ('<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList>'
                 f'{styled("<hp:t>셀 제목</hp:t>", style="2")}{styled("<hp:t>셀 목록</hp:t>", para_pr="3")}</hp:subList>'
                 '<hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/></hp:tc></hp:tr></hp:tbl>')
        raw = hwpx({"Contents/section0.xml": section(
            styled(header), styled("<hp:t>사업 개요</hp:t>", para_pr="1", pid="10"), styled("<hp:t>개요 스타일 제목</hp:t>", style="2"),
            styled("<hp:t>사용자 제목 스타일</hp:t>", style="9"), styled("<hp:t>첫째 번호</hp:t>", para_pr="2"),
            styled("<hp:t>둘째 번호</hp:t>", para_pr="2"), styled("<hp:t>글머리</hp:t>", para_pr="3"),
            styled("<hp:t>본문 문단</hp:t>" + footnote), styled(table))}, header=HEADER)
        result = parse(raw)
        document = result.document
        items = [(item.label, item.text) for item, _ in document.iterate_items(included_content_layers=None) if hasattr(item, "text")]
        # HWPX가 명시한 개요(OUTLINE)·내장 개요 스타일만 heading이다. 사용자 정의 "제목" 스타일은 문단으로 둔다.
        self.assertIn((DocItemLabel.SECTION_HEADER, "사업 개요"), items)
        self.assertIn((DocItemLabel.SECTION_HEADER, "개요 스타일 제목"), items)
        self.assertIn((DocItemLabel.PARAGRAPH, "사용자 제목 스타일"), items)
        heading = next(item for item in document.texts if item.text == "사업 개요")
        self.assertEqual(heading.level, 2)
        lists = [item for item in document.texts if item.label == DocItemLabel.LIST_ITEM and item.parent.cref.startswith("#/groups")
                 and item.parent.resolve(document).parent.cref == "#/body"]
        self.assertEqual([(item.text, item.enumerated, item.marker) for item in lists],
                         [("첫째 번호", True, ""), ("둘째 번호", True, ""), ("글머리", False, "-")])
        # 번호 목록과 글머리 목록은 다른 선언이므로 다른 list group이다.
        self.assertEqual(lists[0].parent.cref, lists[1].parent.cref)
        self.assertNotEqual(lists[1].parent.cref, lists[2].parent.cref)
        self.assertIn((DocItemLabel.FOOTNOTE, "각주 내용"), items)
        page_header = next(item for item in document.texts if item.text == "머리말")
        self.assertEqual((page_header.label, page_header.content_layer.value), (DocItemLabel.PAGE_HEADER, "furniture"))
        # 표 cell 안 개요 스타일은 heading이 되지 않고, cell 안 목록은 RichTableCell group에 남는다.
        cell_heading = next(item for item in document.texts if item.text == "셀 제목")
        self.assertEqual(cell_heading.label, DocItemLabel.PARAGRAPH)
        self.assertIsInstance(document.tables[0].data.table_cells[0], RichTableCell)
        provenance = heading.meta.get_custom_part()["bizaid__hwpx"]
        self.assertEqual((provenance["source_sha256"], provenance["section"], provenance["path"], provenance["paragraph_id"],
                          provenance["structure"]), (hashlib.sha256(raw).hexdigest(), "Contents/section0.xml", "p[1]", "10",
                                                     "paraPr.heading=OUTLINE"))
        # HWPX에는 page·좌표가 없으므로 가짜 provenance를 만들지 않는다.
        self.assertTrue(all(not item.prov for item in document.texts))
        self.assertTrue(all(item.meta and item.meta.get_custom_part().get("bizaid__hwpx")
                            for item, _ in document.iterate_items(included_content_layers=None)))
        reloaded = DoclingDocument.model_validate_json(artifact_bytes(document))
        self.assertEqual(reloaded.export_to_markdown(), document.export_to_markdown())

    def test_parser_completion_without_text_is_not_success(self):
        result = parse(hwpx({"Contents/section0.xml": section(paragraph("<hp:t>   </hp:t>"))}))
        self.assertEqual((result.status, result.text_chars), ("EMPTY_TEXT", 0))
        document = DoclingDocument(name="scan")
        document.add_text(label="text", text="쪽번호 1")
        gated = apply_gate(ParseResult("0" * 64, "PDF", "DOCLING_PDF", "0" * 64, "ROUTE_NOT_ENABLED"),
                           document, self.contract, page_count=3)
        self.assertEqual(gated.status, "OCR_REQUIRED")

    def test_hwpx_container_safety_limits(self):
        good = {"Contents/section0.xml": section(paragraph("<hp:t>본문</hp:t>"))}
        cases = {
            "container_path_rejected": hwpx(good, extra={"../evil.xml": "x"}),
            "compression_ratio_exceeded": hwpx(good, extra={"BinData/bomb.bin": b"a" * 2097152}),
            "missing_section_xml": hwpx({}),
            "invalid_zip_container": b"PK\x03\x04 broken",
        }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cases["container_entries_rejected"] = hwpx(good, extra={"Contents/section0.xml": "<dup/>"})
        dtd = section(paragraph("<hp:t>&x;</hp:t>")).replace("?>", '?><!DOCTYPE hs:sec [<!ENTITY x "a">]>', 1)
        cases["xml_declaration_rejected"] = hwpx({"Contents/section0.xml": dtd})
        cases["malformed_xml"] = hwpx({"Contents/section0.xml": "<hs:sec"})
        statuses = {"container_path_rejected": "REJECTED_UNSAFE", "compression_ratio_exceeded": "REJECTED_UNSAFE",
                    "container_entries_rejected": "REJECTED_UNSAFE", "xml_declaration_rejected": "REJECTED_UNSAFE",
                    "missing_section_xml": "PARSE_FAILED", "malformed_xml": "PARSE_FAILED",
                    "invalid_zip_container": "PARSE_FAILED"}
        for code, raw in cases.items():
            with self.subTest(code=code):
                result = parse(raw)
                self.assertEqual((result.status, result.failure_code), (statuses[code], code))
                self.assertIsNone(result.document)
        limited = copy.deepcopy(self.contract)
        limited["hwpx_container_limits"]["max_total_uncompressed_bytes"] = 10
        self.assertEqual(parse(hwpx(good), contract=limited).failure_code, "uncompressed_size_exceeded")

    def test_encrypted_entry_is_classified_not_read(self):
        raw = bytearray(hwpx({"Contents/section0.xml": section(paragraph("<hp:t>본문</hp:t>"))}))
        # 중앙 directory의 general purpose flag에 암호화 bit를 세워 실제 암호 해독 없이 분류 경계를 검증한다.
        offset = raw.find(b"PK\x01\x02")
        raw[offset + 8] |= 0x1
        result = parse(bytes(raw))
        self.assertEqual((result.status, result.failure_code), ("ENCRYPTED", "encrypted_entry"))

    def test_parse_key_is_stable_and_versioned_per_route(self):
        sha = "a" * 64
        key = parse_key(sha, "HWPX_DOCLING_ADAPTER", self.contract)
        self.assertEqual(key, parse_key(sha, "HWPX_DOCLING_ADAPTER", self.contract))
        self.assertNotEqual(key, parse_key(sha, "DOCLING_PDF", self.contract))
        self.assertNotEqual(key, parse_key("b" * 64, "HWPX_DOCLING_ADAPTER", self.contract))
        self.assertNotEqual(parse_key(sha, "HWP_PDF_DOCLING", self.contract, "converter-1"),
                            parse_key(sha, "HWP_PDF_DOCLING", self.contract, "converter-2"))

    def test_parse_key_changes_only_on_routes_that_depend_on_the_component(self):
        sha = "a" * 64

        def keys(contract):
            return {"HWPX": parse_key(sha, "HWPX_DOCLING_ADAPTER", contract), "PDF": parse_key(sha, "DOCLING_PDF", contract),
                    "HWP": parse_key(sha, "HWP_PDF_DOCLING", contract, "converter-1")}

        def changed(mutate):
            contract = copy.deepcopy(self.contract)
            mutate(contract)
            after = keys(contract)
            return {route for route, key in base.items() if after[route] != key}
        base = keys(self.contract)
        # HWPX adapter 변경은 HWPX만, PDF parser 설정 변경은 PDF와 이를 재사용하는 HWP만, 공통 normalizer 변경은 모두를 바꾼다.
        self.assertEqual(changed(lambda c: c["versioning"].update(hwpx_adapter_version=c["versioning"]["hwpx_adapter_version"] + 1)),
                         {"HWPX"})
        self.assertEqual(changed(lambda c: c["routes"]["PDF"]["table_engine"].update(edge_tolerance_px=9)), {"PDF", "HWP"})
        self.assertEqual(changed(lambda c: c["versioning"].update(normalizer_version=c["versioning"]["normalizer_version"] + 1)),
                         {"HWPX", "PDF", "HWP"})
        self.assertNotEqual(base["HWP"], parse_key(sha, "HWP_PDF_DOCLING", self.contract, "converter-2"))
        self.assertIsNone(parse_identity(sha, "DOCLING_PDF", self.contract)["hwpx_adapter_version"])
        self.assertIsNone(parse_identity(sha, "DOCLING_PDF", self.contract)["converter_version"])
        self.assertIsNone(parse_identity(sha, "HWPX_DOCLING_ADAPTER", self.contract)["pipeline_config_sha256"])
        drift = copy.deepcopy(self.contract)
        drift["versioning"]["parse_key_inputs"].append("unregistered")
        with self.assertRaisesRegex(PipelineError, "parse_key_contract_drift"):
            parse_key(sha, "HWPX_DOCLING_ADAPTER", drift)


if __name__ == "__main__":
    unittest.main()
