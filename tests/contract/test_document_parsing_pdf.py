import copy
import hashlib
import io
import json
import subprocess
import tempfile
import sys
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import DoclingDocument

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing import parse_document
from biz_aid_pipeline.parsing import pdf as pdf_route
from biz_aid_pipeline.parsing.models import (ParseRequest, artifact_files, artifacts_manifest_sha256, docling_artifacts_path,
                                             parse_key, parsing_contract, pipeline_config)
from biz_aid_pipeline.parsing.quality import artifact_bytes


def build_pdf(contents, image=False):
    # 실제 corpus를 Git에 넣지 않도록 Type1 기본 글꼴과 선택적 회색 image만 쓰는 결정론적 PDF를 만든다.
    objects = []

    def add(value):
        objects.append(value)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    picture = None
    if image:
        data = zlib.compress(bytes((x * 7 + y * 13) % 256 for y in range(64) for x in range(64)))
        picture = add(b"<< /Type /XObject /Subtype /Image /Width 64 /Height 64 /ColorSpace /DeviceGray "
                      b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
    pages_id = len(objects) + 1 + 2 * len(contents)
    kids = []
    for content in contents:
        stream = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        resources = b"/Font << /F1 %d 0 R >>" % font + (b" /XObject << /Im1 %d 0 R >>" % picture if picture else b"")
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources << %s >> /Contents %d 0 R >>"
                        % (pages_id, resources, stream)))
    add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % kid for kid in kids), len(kids)))
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, value in enumerate(objects, 1):
        offsets.append(len(output))
        output += b"%d 0 obj\n" % number + value + b"\nendobj\n"
    xref = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    output += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    output += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(output)


def text_page():
    lines = [b"BT /F1 22 Tf 72 720 Td (1. Support Program Overview) Tj ET"]
    for index, sentence in enumerate((b"This program supports small businesses with export consulting costs.",
                                      b"Applicants must be registered small and medium enterprises in the region.",
                                      b"The application period runs from October 1 to October 31.")):
        lines.append(b"BT /F1 11 Tf 72 %d Td (%s) Tj ET" % (690 - 16 * index, sentence))
    lines.append(b"BT /F1 16 Tf 72 600 Td (2. Funding Table) Tj ET")
    rows = ((b"Item", b"Government", b"Company"), (b"Consulting", b"80 percent", b"20 percent"),
            (b"Training", b"70 percent", b"30 percent"))
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            x, y = 72 + col_index * 150, 570 - row_index * 24
            lines.append(b"%d %d 150 24 re S" % (x, y - 24))
            lines.append(b"BT /F1 11 Tf %d %d Td (%s) Tj ET" % (x + 6, y - 16, value))
    return b"\n".join(lines)


TEXT_PDF = build_pdf([text_page()])
IMAGE_PDF = build_pdf([b"q 400 0 0 400 100 200 cm /Im1 Do Q"], image=True)
MIXED_PDF = build_pdf([text_page(), b"q 400 0 0 400 100 200 cm /Im1 Do Q\nBT /F1 10 Tf 72 100 Td (Scan Page) Tj ET"],
                      image=True)
MALFORMED_PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> garbage"


def parse(raw, detected_format="PDF", contract=None):
    return parse_document(ParseRequest(hashlib.sha256(raw).hexdigest(), detected_format, len(raw)), raw, contract)


class DoclingPdfRouteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = parsing_contract()
        cls.text = parse(TEXT_PDF)

    def test_text_pdf_becomes_reloadable_docling_document(self):
        result = self.text
        self.assertEqual((result.route, result.status, result.failure_code), ("DOCLING_PDF", "PARSED", None))
        self.assertIsInstance(result.document, DoclingDocument)
        self.assertEqual(result.unit_count, 1)
        text = result.document.export_to_markdown()
        for expected in ("Support Program Overview", "export consulting costs", "Funding Table", "Consulting", "80 percent"):
            self.assertIn(expected, text)
        reloaded = DoclingDocument.model_validate_json(artifact_bytes(result.document))
        self.assertEqual(reloaded.export_to_markdown(), text)
        self.assertGreater(result.text_chars, 200)

    def test_image_only_pdf_runs_ocr_and_stays_ocr_required_without_text(self):
        result = parse(IMAGE_PDF)
        # 합성 회색 image에는 글자가 없으므로 OCR 후에도 OCR_REQUIRED이며 OCR 결과 부족이 드러난다.
        self.assertEqual((result.status, result.failure_code, result.text_chars), ("OCR_REQUIRED", None, 0))
        self.assertEqual((result.warnings["PDF_OCR_APPLIED"], result.warnings["OCR_TEXT_INSUFFICIENT"]), (1, 1))
        self.assertEqual(result.ocr["pages"], [1])
        self.assertIn("korean_PP-OCRv5_mobile_rec", result.ocr["engine"])
        self.assertIsInstance(result.document, DoclingDocument)

    def test_ocr_text_becomes_parsed_document_with_provenance(self):
        from biz_aid_pipeline.parsing import pdf_ocr
        lines = {1: [pdf_ocr.OcrLine(1, [100, 120, 400, 140], "지원 대상 중소기업 신청 기간 안내 문서입니다", 0.98),
                     pdf_ocr.OcrLine(1, [60, 80, 300, 100], "2026년 수출 바우처 지원사업 공고", 0.99),
                     pdf_ocr.OcrLine(1, [100, 160, 420, 180], "문의 전화 및 제출 서류는 붙임을 참고하십시오", 0.91)]}
        with mock.patch.object(pdf_ocr, "ocr_pages", return_value=lines):
            result = parse(IMAGE_PDF)
        self.assertEqual((result.status, result.warnings["PDF_OCR_APPLIED"]), ("PARSED", 1))
        texts = [item for item in result.document.texts if item.meta and item.meta.get_custom_part().get("bizaid__ocr")]
        # 읽기 순서(위→아래)로 들어가고 OCR provenance를 모두 가진다.
        self.assertEqual([item.text for item in texts][0], "2026년 수출 바우처 지원사업 공고")
        ocr = texts[0].meta.get_custom_part()["bizaid__ocr"]
        self.assertEqual((ocr["source_sha256"], ocr["page"], ocr["bbox_pt"], ocr["confidence"]),
                         (hashlib.sha256(IMAGE_PDF).hexdigest(), 1, [60, 80, 300, 100], 0.99))
        self.assertIn("PP-OCRv5_mobile_det", ocr["engine"])
        reloaded = DoclingDocument.model_validate_json(artifact_bytes(result.document))
        self.assertEqual(reloaded.export_to_markdown(), result.document.export_to_markdown())

    def test_mixed_pdf_ocrs_only_low_text_page_and_keeps_native_page(self):
        from biz_aid_pipeline.parsing import pdf_ocr, pdf_tables
        ocr_text = ("Scan Page 스캔 페이지의 지원 대상 신청 기간 제출 서류 안내를 OCR로 복원한 충분한 길이의 본문입니다. "
                    "이 페이지의 접수 조건과 문의 방법도 함께 보존합니다")
        lines = {2: [pdf_ocr.OcrLine(2, [72, 80, 500, 105], ocr_text, 0.97)]}
        with (mock.patch.object(pdf_ocr, "ocr_pages", return_value=lines) as ocr,
              mock.patch.object(pdf_tables, "page_tables", wraps=pdf_tables.page_tables) as page_tables):
            result = parse(MIXED_PDF)
        self.assertEqual((result.status, result.ocr["pages"], result.ocr["insufficient_pages"]), ("PARSED", [2], []))
        self.assertEqual(ocr.call_args.args[1], [2])
        # page 1은 native layer(None), page 2만 OCR layer를 기존 PP 경로에 전달한다.
        self.assertIsNone(page_tables.call_args_list[0].args[4])
        self.assertIsNotNone(page_tables.call_args_list[1].args[4])
        markdown = result.document.export_to_markdown()
        self.assertEqual(markdown.count("Support Program Overview"), 1)
        self.assertEqual(markdown.count(ocr_text), 1)
        self.assertEqual(markdown.count("Scan Page"), 1)
        self.assertTrue(any(table.prov[0].page_no == 1 for table in result.document.tables))
        ocr_items = [item for item in result.document.texts
                     if item.meta and item.meta.get_custom_part().get("bizaid__ocr")]
        self.assertEqual(len(ocr_items), 1)
        self.assertEqual(ocr_items[0].meta.get_custom_part()["bizaid__ocr"]["page"], 2)
        reloaded = DoclingDocument.model_validate_json(artifact_bytes(result.document))
        self.assertEqual(reloaded.export_to_markdown(), markdown)

    def test_mixed_pdf_keeps_insufficient_ocr_page_visible_without_discarding_the_document(self):
        from biz_aid_pipeline.parsing import pdf_ocr
        lines = {2: [pdf_ocr.OcrLine(2, [72, 80, 300, 105], "짧은 OCR", 0.9)]}
        with mock.patch.object(pdf_ocr, "ocr_pages", return_value=lines):
            result = parse(MIXED_PDF)
        # OCR 부족 page는 warning·insufficient_pages로 드러나고, 문서 status는 문서 text Gate가 정한다.
        # 빈 쪽 하나로 문서 전체를 OCR_REQUIRED로 두면 PARSED artifact가 저장되지 않아 본문이 사라진다.
        self.assertEqual((result.status, result.ocr["insufficient_pages"]), ("PARSED", [2]))
        self.assertEqual(result.warnings["OCR_TEXT_INSUFFICIENT"], 1)
        self.assertIn("짧은 OCR", result.document.export_to_markdown())

    def test_table_region_owns_its_words_and_native_items_keep_only_outside_words(self):
        from docling_core.types.doc import BoundingBox, ContentLayer, CoordOrigin, DocItemLabel, ProvenanceItem, Size
        from biz_aid_pipeline.parsing import pdf_assembly
        from biz_aid_pipeline.parsing.models import ParseResult

        def prov(l, t, r, b):
            return ProvenanceItem(page_no=1, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT), charspan=(0, 1))
        document = DoclingDocument(name="t")
        document.add_page(page_no=1, size=Size(width=600, height=800))
        crossing = document.add_text(label=DocItemLabel.FOOTNOTE, text="각주 표안글자", prov=prov(20, 100, 300, 120))
        inside = document.add_text(label=DocItemLabel.TEXT, text="표안", prov=prov(150, 150, 190, 160))
        footer = document.add_text(label=DocItemLabel.PAGE_FOOTER, text="3", prov=prov(290, 770, 300, 780),
                                   content_layer=ContentLayer.FURNITURE)
        words = [([20, 100, 60, 120], "각주"), ([140, 100, 200, 120], "표안글자"), ([150, 150, 190, 160], "표안")]
        region = [100, 90, 400, 200]
        assembler = pdf_assembly._Assembler(document, None, "a" * 64, self.contract, ParseResult("a" * 64, "PDF", "DOCLING_PDF", "k", "X"),
                                            {1: ([], words)})
        assembler.trim_overlapping_native(1, region, [region])
        # 영역에 걸친 item은 영역 밖 단어만 남기고, 영역 밖 단어가 없는 item은 지운다. 영역 안 단어는 표 결과가 가진다.
        self.assertEqual(crossing.text, "각주")
        self.assertNotIn(inside, [item for item, _ in document.iterate_items()])
        # OCR page의 native 제거는 furniture layer의 쪽 번호도 포함해 OCR과 중복되지 않게 한다.
        pdf_assembly.remove_native_content_on_ocr_pages(document, [1])
        self.assertEqual([item for item, _ in document.iterate_items(included_content_layers=set(ContentLayer))
                          if item is footer], [])

    def test_low_text_page_with_only_native_text_keeps_native_instead_of_ocr(self):
        from biz_aid_pipeline.parsing.pdf_ocr import select_ocr_pages
        native = {1: 0, 2: 26, 3: 26, 4: 400}
        images = {1: 0, 2: 0, 3: 1, 4: 2}
        # native 글자만 있는 low-text page(2)는 OCR하지 않는다. 글자 없는 page(1)와 image가 있는 page(3)는 OCR한다.
        self.assertEqual(select_ocr_pages(native, images, 50), [1, 3])

    def test_anchor_places_after_the_last_item_of_the_same_row(self):
        from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel, ProvenanceItem, Size
        from biz_aid_pipeline.parsing import pdf_assembly

        def prov(l, t, r, b):
            return ProvenanceItem(page_no=1, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT), charspan=(0, 1))
        document = DoclingDocument(name="t")
        document.add_page(page_no=1, size=Size(width=600, height=800))
        document.add_text(label=DocItemLabel.TEXT, text="참고", prov=prov(20, 76, 60, 96))
        second = document.add_text(label=DocItemLabel.TEXT, text="견적서 예시", prov=prov(80, 76, 300, 94))
        # 같은 행(top 동일)의 두 item 사이가 아니라 문서 순서상 마지막 item 뒤에 넣는다.
        self.assertEqual(pdf_assembly.anchor(document, 1, 117, []), (second, True))

    def test_ocr_runs_only_for_ocr_required_documents_and_fails_loudly(self):
        from biz_aid_pipeline.parsing import pdf_ocr
        with mock.patch.object(pdf_ocr, "ocr_pages") as ocr:
            self.assertEqual(parse(TEXT_PDF).status, "PARSED")
            ocr.assert_not_called()
        with mock.patch.object(pdf_ocr, "pipeline", side_effect=RuntimeError("boom")):
            result = parse(IMAGE_PDF)
        self.assertEqual((result.status, result.failure_code, result.document), ("PARSE_FAILED", "ocr_engine_error:RuntimeError", None))
        self.assertIn("ocr_engine_error:<ExceptionClass>", self.contract["failure_codes"]["PARSE_FAILED"])
        words = pdf_ocr.line_words(pdf_ocr.OcrLine(1, [0, 0, 110, 10], "지원 금액 100만원", 0.9))
        self.assertEqual([text for _, text in words], ["지원", "금액", "100만원"])
        self.assertEqual((words[0][0][0], words[-1][0][2]), (0, 110))

    def test_malformed_pdf_is_parse_failed_with_registered_code(self):
        result = parse(MALFORMED_PDF)
        self.assertEqual(result.status, "PARSE_FAILED")
        self.assertIn(result.failure_code, self.contract["failure_codes"]["PARSE_FAILED"])
        self.assertIsNone(result.document)

    def test_partial_or_missing_conversion_never_becomes_success(self):
        for status_name, code in (("PARTIAL_SUCCESS", "docling_partial_conversion"), ("FAILURE", "docling_conversion_failed")):
            outcome = mock.Mock(status=getattr(pdf_route.ConversionStatus, status_name), document=None)
            with self.subTest(status=status_name), mock.patch.object(pdf_route, "converter") as factory:
                factory.return_value.convert.return_value = outcome
                result = parse(TEXT_PDF)
                self.assertEqual((result.status, result.failure_code), ("PARSE_FAILED", code))
                self.assertIn(code, self.contract["failure_codes"]["PARSE_FAILED"])

    def test_pdf_handler_runs_only_for_detected_pdf(self):
        hwpx = io.BytesIO()
        with zipfile.ZipFile(hwpx, "w") as archive:
            archive.writestr("Contents/section0.xml", "<sec/>")
        with mock.patch.object(pdf_route, "convert_pdf", wraps=pdf_route.convert_pdf) as handler:
            for detected in ("HWPX", "HWP", "ZIP", "XLSX", "OTHER", "UNKNOWN", "DOCX"):
                parse(TEXT_PDF, detected)
            parse(hwpx.getvalue(), "HWPX")
            handler.assert_not_called()
            # BOUNDARY: byte가 PDF가 아니어도 detected_format이 PDF이면 PDF route만 판정한다.
            result = parse(hwpx.getvalue(), "PDF")
            handler.assert_called_once()
        self.assertEqual((result.route, result.status), ("DOCLING_PDF", "PARSE_FAILED"))

    def test_input_integrity_error_precedes_docling(self):
        with mock.patch.object(pdf_route, "convert_pdf") as handler:
            with self.assertRaisesRegex(PipelineError, "parse_input_integrity_mismatch"):
                parse_document(ParseRequest("0" * 64, "PDF", len(TEXT_PDF)), TEXT_PDF)
            handler.assert_not_called()

    def test_ocr_is_disabled_in_contract_and_converter(self):
        self.assertIs(pipeline_config(self.contract)["do_ocr"], False)
        options = pdf_route.converter(self.contract).format_to_options[InputFormat.PDF].pipeline_options
        self.assertIs(options.do_ocr, False)
        self.assertIs(options.enable_remote_services, False)
        enabled = copy.deepcopy(self.contract)
        enabled["routes"]["PDF"]["docling_options"]["do_ocr"] = True
        with self.assertRaisesRegex(ValueError, "pdf_ocr_must_be_disabled"):
            pipeline_config(enabled)

    def test_layout_model_is_pinned_to_a_commit(self):
        revision = self.contract["routes"]["PDF"]["layout_model_revision"]
        spec = pdf_route.converter(self.contract).format_to_options[InputFormat.PDF].pipeline_options.layout_options.model_spec
        self.assertEqual(spec.revision, revision)
        floating = copy.deepcopy(self.contract)
        floating["routes"]["PDF"]["layout_model_revision"] = "main"
        with self.assertRaisesRegex(ValueError, "layout_model_revision_must_be_commit"):
            parse_key("c" * 64, "DOCLING_PDF", floating)
        moved = copy.deepcopy(self.contract)
        moved["routes"]["PDF"]["layout_model_revision"] = "0" * 40
        self.assertNotEqual(parse_key("c" * 64, "DOCLING_PDF", self.contract), parse_key("c" * 64, "DOCLING_PDF", moved))

    def test_pp_table_becomes_structured_table_with_provenance(self):
        tables = self.text.document.tables
        self.assertEqual(len(tables), 1)
        quality = tables[0].meta.get_custom_part()["bizaid__table_quality"]
        self.assertEqual((quality["verdict"], quality["reasons"], quality["page"]), ("TABLE_VALID", [], 1))
        self.assertEqual(quality["source_sha256"], self.text.source_sha256)
        self.assertIn("table_recognition_v2", quality["parser_identity"])
        self.assertEqual((tables[0].data.num_rows, tables[0].data.num_cols), (3, 3))
        # cell text는 PDF native text layer에서 온다.
        self.assertEqual([cell.text for cell in tables[0].data.table_cells][3:6], ["Consulting", "80 percent", "20 percent"])

    def test_failed_table_keeps_native_text_without_structure(self):
        from biz_aid_pipeline.parsing import pdf_tables

        def failing(cell_boxes, td_count, words, engine):
            return pdf_tables.TABLE_QUALITY_FAILED, ["grid_unproven"], None
        with mock.patch.object(pdf_tables, "assess_table", side_effect=failing):
            result = parse(TEXT_PDF)
        # BOUNDARY: 증명되지 않은 표는 행·열 구조 없이 bbox native text와 provenance로만 남는다.
        self.assertEqual((result.status, result.document.tables), ("PARSED", []))
        self.assertEqual(result.warnings["PDF_TABLE_QUALITY_FAILED"], 1)
        failed = [item for item in result.document.texts if item.meta
                  and item.meta.get_custom_part().get("bizaid__table_quality", {}).get("verdict") == "TABLE_QUALITY_FAILED"]
        self.assertEqual(len(failed), 1)
        for value in ("Item", "Government", "Consulting", "80 percent", "Training", "30 percent"):
            self.assertIn(value, failed[0].text)
        self.assertEqual(failed[0].meta.get_custom_part()["bizaid__table_quality"]["reasons"], ["grid_unproven"])

    def test_table_engine_failure_is_parse_failed_without_fallback(self):
        from biz_aid_pipeline.parsing import pdf_tables
        with mock.patch.object(pdf_tables, "pipeline", side_effect=RuntimeError("boom")):
            result = parse(TEXT_PDF)
        self.assertEqual((result.status, result.failure_code, result.document), ("PARSE_FAILED", "pp_table_engine_error:RuntimeError", None))
        self.assertIn("pp_table_engine_error:<ExceptionClass>", self.contract["failure_codes"]["PARSE_FAILED"])
        for code in ("PDF_TABLE_QUALITY_FAILED", "PDF_TABLE_OVERLAP_PRESERVED_AS_TEXT", "PDF_DOCLING_TABLE_PRESERVED_AS_TEXT",
                     "PDF_TABLE_PICTURE_OVERLAP"):
            self.assertIn(code, self.contract["warning_codes"])

    def test_pp_cpu_path_is_the_same_on_every_platform(self):
        from paddlex.utils import flags
        from biz_aid_pipeline.parsing import pdf_tables
        pdf_tables.pipeline(self.contract)
        # RISK: Linux x86 wheel의 oneDNN 경로는 Paddle 3.3.1 PIR에서 NotImplementedError를 낸다. 모든 플랫폼에서 끈다.
        self.assertEqual(self.contract["routes"]["PDF"]["table_engine"]["runtime_environment"]["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"], "False")
        self.assertIs(flags.ENABLE_MKLDNN_BYDEFAULT, False)

    def test_docling_table_structure_is_off_and_pp_engine_is_ocr_free(self):
        options = pdf_route.converter(self.contract).format_to_options[InputFormat.PDF].pipeline_options
        self.assertIs(options.do_table_structure, False)
        engine = self.contract["routes"]["PDF"]["table_engine"]
        self.assertEqual((engine["engine"], engine["use_ocr_model"], engine["adapter"]), ("pp_tablemagic", False, "detection_edge_grid"))
        self.assertEqual(self.contract["table_engine"]["primary"], "pp_tablemagic")
        with_ocr = copy.deepcopy(self.contract)
        with_ocr["routes"]["PDF"]["table_engine"]["use_ocr_model"] = True
        with self.assertRaisesRegex(ValueError, "pdf_table_engine_ocr_must_be_disabled"):
            parse_key("c" * 64, "DOCLING_PDF", with_ocr)

    def fake_docker(self, output=TEXT_PDF, label=None, returncode=0, seen=None):
        from biz_aid_pipeline.parsing import hwp_pdf
        spec = self.contract["routes"]["HWP"]["converter"]

        def run(*args, timeout):
            if seen is not None:
                seen.append(args)
            if args[:2] == ("image", "inspect"):
                labels = {spec["image_label"]: label or spec["dockerfile_sha256"]}
                return mock.Mock(returncode=0, stdout=json.dumps(labels).encode())
            if "--entrypoint" in args:
                return mock.Mock(returncode=0, stdout=b"LibreOffice 25.2.3.2\nv0.7.14 abc\n")
            work = Path(args[args.index("-v") + 1].split(":")[0])
            if output is not None:
                (work / "out/source.pdf").write_bytes(output)
            return mock.Mock(returncode=returncode, stdout=b"")
        hwp_pdf._identity.cache_clear()
        self.addCleanup(hwp_pdf._identity.cache_clear)
        return mock.patch.multiple(hwp_pdf, _docker=run, shutil=mock.Mock(which=mock.Mock(return_value="/usr/bin/docker")))

    def test_hwp_converts_to_pdf_and_reuses_the_pdf_parser(self):
        from biz_aid_pipeline.parsing import hwp_pdf
        raw, seen = b"HWP Document File synthetic", []
        with self.fake_docker(seen=seen), mock.patch.object(pdf_route, "parse_pdf", wraps=pdf_route.parse_pdf) as reused:
            result = parse(raw, "HWP")
        sha = hashlib.sha256(raw).hexdigest()
        self.assertEqual((result.route, result.status), ("HWP_PDF_DOCLING", "PARSED"))
        reused.assert_called_once()
        # provenance는 원본 HWP SHA이고 변환 PDF는 derivation에만 남는다.
        quality = result.document.tables[0].meta.get_custom_part()["bizaid__table_quality"]
        self.assertEqual(quality["source_sha256"], sha)
        self.assertEqual(result.derivation["intermediate_sha256"], hashlib.sha256(TEXT_PDF).hexdigest())
        self.assertIs(result.derivation["persisted"], False)
        version = result.derivation["converter_version"]
        self.assertEqual(result.parse_key, parse_key(sha, "HWP_PDF_DOCLING", self.contract, version))
        convert = next(args for args in seen if args[0] == "run" and "--entrypoint" not in args)
        self.assertEqual(convert[convert.index("--network") + 1], "none")
        self.assertEqual(convert[convert.index("-v") + 1].split(":")[1], "/work")
        # BOUNDARY: 임시 작업 디렉터리는 변환이 끝나면 남지 않는다.
        self.assertFalse(Path(convert[convert.index("-v") + 1].split(":")[0]).exists())
        self.assertEqual(hwp_pdf.image_ref(self.contract).split(":")[1], self.contract["routes"]["HWP"]["converter"]["dockerfile_sha256"][:12])

    def test_hwp_conversion_failures_are_conversion_failed_without_fallback(self):
        cases = ((dict(output=None), "hwp_conversion_no_output"), (dict(output=b"not a pdf"), "hwp_conversion_no_output"),
                 (dict(returncode=1), "hwp_conversion_failed"), (dict(label="0" * 64), "hwp_converter_identity_mismatch"))
        for kwargs, code in cases:
            with self.subTest(code=code), self.fake_docker(**kwargs), mock.patch.object(pdf_route, "parse_pdf") as reused:
                result = parse(b"HWP Document File synthetic", "HWP")
                self.assertEqual((result.status, result.failure_code, result.document), ("CONVERSION_FAILED", code, None))
                reused.assert_not_called()
                self.assertIn(code, self.contract["failure_codes"]["CONVERSION_FAILED"])

    def test_hwp_conversion_timeout_removes_the_container(self):
        from biz_aid_pipeline.parsing import hwp_pdf
        seen = []

        def run(*args, timeout):
            seen.append(args)
            if args[:2] == ("image", "inspect"):
                spec = self.contract["routes"]["HWP"]["converter"]
                return mock.Mock(returncode=0, stdout=json.dumps({spec["image_label"]: spec["dockerfile_sha256"]}).encode())
            if "--entrypoint" in args or args[0] == "rm":
                return mock.Mock(returncode=0, stdout=b"LibreOffice 25.2.3.2\nv0.7.14 abc\n")
            raise subprocess.TimeoutExpired("docker", timeout)
        hwp_pdf._identity.cache_clear()
        self.addCleanup(hwp_pdf._identity.cache_clear)
        with mock.patch.multiple(hwp_pdf, _docker=run, shutil=mock.Mock(which=mock.Mock(return_value="/usr/bin/docker"))):
            result = parse(b"HWP Document File synthetic", "HWP")
        self.assertEqual((result.status, result.failure_code), ("CONVERSION_FAILED", "hwp_conversion_timeout"))
        name = next(args for args in seen if args[0] == "run" and "--name" in args)
        self.assertIn(("rm", "-f", name[name.index("--name") + 1]), seen)

    def test_converter_image_is_pinned_by_contract(self):
        spec = self.contract["routes"]["HWP"]["converter"]
        dockerfile = (ROOT / spec["dockerfile"]).read_bytes()
        self.assertEqual(hashlib.sha256(dockerfile).hexdigest(), spec["dockerfile_sha256"])
        text = dockerfile.decode()
        self.assertIn(f"FROM {spec['base_image']}", text)
        self.assertIn(f"H2ORESTART_VERSION={spec['h2orestart']['version']}", text)
        self.assertIn(f"H2ORESTART_SHA256={spec['h2orestart']['sha256']}", text)
        self.assertIn("sha256sum -c", text)
        self.assertEqual(spec["run"]["network"], "none")

    def test_model_artifacts_are_explicit_offline_and_identity_bearing(self):
        spec = self.contract["dependencies"]["docling"]["model_artifacts"]
        self.assertEqual(self.contract["test_runtime"]["network_download"], "forbidden")
        with self.assertRaisesRegex(PipelineError, "docling_artifacts_path_required"):
            docling_artifacts_path(self.contract, {})
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(PipelineError, "docling_artifacts_missing"):
                docling_artifacts_path(self.contract, {spec["artifacts_path_env"]: empty})
            files = artifact_files(self.contract)
            for folder, name in files:
                (Path(empty) / folder / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(empty) / folder / name).write_bytes(b"a")
            first = artifacts_manifest_sha256(empty, files)
            # 목록 밖 파일(README·다운로드 metadata)은 identity에 영향을 주지 않는다.
            (Path(empty) / files[0][0] / "README.md").write_bytes(b"ignored")
            artifacts_manifest_sha256.cache_clear()
            self.assertEqual(first, artifacts_manifest_sha256(empty, files))
            (Path(empty) / files[-1][0] / files[-1][1]).write_bytes(b"b")
            artifacts_manifest_sha256.cache_clear()
            self.assertNotEqual(first, artifacts_manifest_sha256(empty, files))
        artifacts_manifest_sha256.cache_clear()
        for model in spec["models"]:
            self.assertTrue(model["requested_revision"] and model["resolved_snapshot"])

    def test_parse_key_tracks_docling_distribution_and_pipeline_config(self):
        sha = "c" * 64
        key = parse_key(sha, "DOCLING_PDF", self.contract)
        self.assertEqual(key, parse_key(sha, "DOCLING_PDF", self.contract))
        self.assertEqual(self.text.parse_key, parse_key(self.text.source_sha256, "DOCLING_PDF", self.contract))
        changed = copy.deepcopy(self.contract)
        changed["routes"]["PDF"]["table_engine"]["edge_tolerance_px"] = 9
        self.assertNotEqual(key, parse_key(sha, "DOCLING_PDF", changed))
        with mock.patch("biz_aid_pipeline.parsing.models.installed_version", return_value="0.0.0"):
            self.assertNotEqual(key, parse_key(sha, "DOCLING_PDF", self.contract))
        self.assertNotEqual(key, parse_key(sha, "HWPX_DOCLING_ADAPTER", self.contract))
        for name in ("docling_version", "docling_parse_version", "docling_ibm_models_version", "pipeline_config_sha256",
                     "paddlepaddle_version", "paddlex_version"):
            self.assertIn(name, self.contract["versioning"]["parse_key_inputs"])


if __name__ == "__main__":
    unittest.main()
