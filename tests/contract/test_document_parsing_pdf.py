import copy
import hashlib
import io
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

    def test_image_only_pdf_is_ocr_required_not_failure(self):
        from biz_aid_pipeline.parsing import pdf_tables
        with mock.patch.object(pdf_tables, "detect_tables", wraps=pdf_tables.detect_tables) as tables:
            result = parse(IMAGE_PDF)
        # BOUNDARY: native text가 없는 문서는 표 cell text의 출처가 없으므로 PP를 실행하지 않고 OCR_REQUIRED로 남는다.
        tables.assert_not_called()
        self.assertEqual((result.status, result.failure_code, result.text_chars), ("OCR_REQUIRED", None, 0))
        self.assertIsInstance(result.document, DoclingDocument)

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
