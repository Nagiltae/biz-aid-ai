import copy
import hashlib
import io
import logging
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
from docling_core.types.doc import DoclingDocument, Size

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
        result = parse(IMAGE_PDF)
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

    def test_table_cell_drop_is_exposed_without_changing_logging(self):
        logger = logging.getLogger(pdf_route.TABLE_DROP_LOGGER)
        before = (list(logger.handlers), list(logger.filters), logger.level, logger.propagate)
        document = DoclingDocument(name="drop")
        document.add_page(page_no=1, size=Size(width=612, height=792))
        document.add_text(label="text", text="지원금액과 자부담 비율은 아래 표를 따른다. " * 5)

        def convert(*args, **kwargs):
            logger.warning("3 of 40 pdf cells matched neither a row nor a column band of the 5x4 grid "
                           "and were dropped from the table")
            logger.warning("2 of 12 pdf cells matched neither a row nor a column band of the 3x2 grid "
                           "and were dropped from the table")
            return mock.Mock(status=pdf_route.ConversionStatus.SUCCESS, document=document)

        with mock.patch.object(pdf_route, "converter") as factory:
            factory.return_value.convert.side_effect = convert
            result = parse(TEXT_PDF)
        # BOUNDARY: 표 cell 탈락은 새 status가 아니라 PARSED 결과의 warning evidence다.
        self.assertEqual(result.status, "PARSED")
        self.assertEqual((result.warnings["TABLE_CELL_DROP_DETECTED"], result.warnings["TABLE_CELLS_DROPPED"]), (2, 5))
        self.assertEqual((list(logger.handlers), list(logger.filters), logger.level, logger.propagate), before)
        for code in ("TABLE_CELL_DROP_DETECTED", "TABLE_CELLS_DROPPED", "TABLE_CELL_DROP_COUNT_UNPARSED"):
            self.assertIn(code, self.contract["warning_codes"])
        self.assertIn("does not guarantee", self.contract["parse_status_semantics"]["PARSED"])

    def test_upstream_drop_message_still_matches_capture(self):
        # 설치된 docling-ibm-models가 문구를 바꾸면 탈락이 조용히 누락되므로 pin 변경 때 이 테스트가 먼저 실패해야 한다.
        from docling_ibm_models.tableformer.data_management import matching_post_processor
        source = Path(matching_post_processor.__file__).read_text(encoding="utf-8")
        self.assertIn('"{} of {} pdf cells matched neither a row nor a column band of "', source)
        self.assertIn("MatchingPostProcessor", source)
        self.assertRegex("7 of 90 pdf cells matched neither a row nor a column band of the 9x3 grid", pdf_route.TABLE_DROP_MESSAGE)

    def test_table_baseline_is_explicit_accurate_with_cell_matching(self):
        options = pdf_route.converter(self.contract).format_to_options[InputFormat.PDF].pipeline_options
        self.assertEqual((options.table_structure_options.mode.value, options.table_structure_options.do_cell_matching),
                         ("accurate", True))
        self.assertEqual(self.contract["routes"]["PDF"]["table_structure_options"], {"mode": "accurate", "do_cell_matching": True})

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
        changed["routes"]["PDF"]["docling_options"]["do_table_structure"] = False
        self.assertNotEqual(key, parse_key(sha, "DOCLING_PDF", changed))
        with mock.patch("biz_aid_pipeline.parsing.models.installed_version", return_value="0.0.0"):
            self.assertNotEqual(key, parse_key(sha, "DOCLING_PDF", self.contract))
        self.assertNotEqual(key, parse_key(sha, "HWPX_DOCLING_ADAPTER", self.contract))
        for name in ("docling_version", "docling_parse_version", "docling_ibm_models_version", "pipeline_config_sha256"):
            self.assertIn(name, self.contract["versioning"]["parse_key_inputs"])


if __name__ == "__main__":
    unittest.main()
