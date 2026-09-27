import copy
import io
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import phase0
import phase0_api_quality as quality
import phase0_document_download as documents

KEY = "synthetic-document-key+/="
URL = "https://www.bizinfo.go.kr/cmm/fms/getImageFile.do?atchFileId=SYNTHETIC&fileSn=0"
PDF = b"%PDF-1.7\nsynthetic-format-fixture\n%%EOF\n"


class Response(io.BytesIO):
    def __init__(self, raw=PDF, status=200, headers=None):
        super().__init__(raw)
        self.code = status
        self.headers = {"Content-Type": "application/pdf", **(headers or {})}


def zip_fixture(kind):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        if kind == "HWPX":
            archive.writestr("mimetype", "application/hwp+zip")
            archive.writestr("Contents/header.xml", "synthetic-header-not-parsed")
            archive.writestr("Contents/section0.xml", "synthetic-content-not-parsed")
        elif kind == "XLSX":
            archive.writestr("[Content_Types].xml", "synthetic-types-not-parsed")
            archive.writestr("xl/workbook.xml", "synthetic-workbook-not-parsed")
            archive.writestr("xl/worksheets/sheet1.xml", "synthetic-sheet-not-parsed")
        else:
            archive.writestr("test.bin", b"synthetic")
    return stream.getvalue()


def hwp_fixture():
    header = bytearray(512)
    header[:8] = bytes.fromhex("d0cf11e0a1b11ae1")
    header[28:30] = b"\xfe\xff"
    struct.pack_into("<HH", header, 30, 9, 6)
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into("<I", header, 48, 1)
    struct.pack_into("<I", header, 56, 4096)
    struct.pack_into("<II", header, 60, 2, 1)
    struct.pack_into("<II", header, 68, 0xfffffffe, 0)
    struct.pack_into("<109I", header, 76, 0, *([0xffffffff] * 108))
    fat = struct.pack("<128I", 0xfffffffd, 0xfffffffe, 0xfffffffe, 0xfffffffe, *([0xffffffff] * 124))
    directory = bytearray(512)
    for offset, name, kind, start, size in [(0, "Root Entry", 5, 3, 64), (128, "FileHeader", 2, 0, 32)]:
        encoded = (name + "\0").encode("utf-16le")
        directory[offset:offset + len(encoded)] = encoded
        struct.pack_into("<H", directory, offset + 64, len(encoded))
        directory[offset + 66] = kind
        struct.pack_into("<I", directory, offset + 116, start)
        struct.pack_into("<Q", directory, offset + 120, size)
    mini = struct.pack("<128I", 0xfffffffe, *([0xffffffff] * 127))
    data = b"HWP Document File".ljust(512, b"\0")
    return bytes(header) + fat + directory + mini + data


def prepare_source(root, transform=None):
    sample = phase0.read_json(ROOT / "tests/fixtures/external-api/bizinfo-user-sample.json")["response"]["body"]["items"]["item"][0]
    def fetch(url):
        number = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        items = []
        for offset in range(20):
            item = copy.deepcopy(sample)
            index = (number - 1) * 20 + offset
            item.update(pblancId=f"SYNTHETIC_{index:03}", printFileNm="synthetic.pdf", printFlpthNm=URL + str(index),
                        flpthNm="URL1@URL2", fileNm="A.pdf@B.hwpx")
            if transform:
                transform(item, index)
            items.append(item)
        payload = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                                "body": {"items": {"item": items}, "pageNo": number, "numOfRows": 20, "totalCount": 1200}}}
        return 200, json.dumps(payload, ensure_ascii=False).encode()
    return quality.collect(root, "dev", documents.contract()["source_run_id"], {"BIZINFO_SERVICE_KEY": KEY}, fetch)


class DocumentDownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.calls = []

    def fake(self, request, timeout):
        self.calls.append(request)
        self.assertEqual(timeout, 15)
        self.assertNotIn(KEY, request.full_url)
        self.assertNotIn("servicekey", request.full_url.lower())
        self.assertFalse(any(k.lower() in ("authorization", "cookie", "referer") for k in request.headers))
        return Response()

    def run_download(self, resume=False, stop_after=None, fetch=None):
        with redirect_stdout(io.StringIO()):
            return documents.download(self.root, "dev", "document-test", {"BIZINFO_SERVICE_KEY": KEY},
                                      resume, fetch or self.fake, stop_after, lambda _: None)

    def transfer(self, raw=PDF, status=200, headers=None, spec=None):
        return documents.transfer(URL, KEY, lambda req, timeout: Response(raw, status, headers), spec)

    def test_contract_local_boundaries_and_pending_gate(self):
        spec = documents.contract()
        self.assertEqual(spec["target_documents"], 100)
        self.assertEqual(spec["source_run_id"], "api-quality-dev-20260928-01")
        self.assertEqual(spec["profile"], "dev")
        self.assertEqual(spec["automatic_retries"], 0)
        self.assertEqual(spec["max_redirects"], 3)
        self.assertEqual(spec["max_file_bytes"], 25 * 1024 * 1024)
        self.assertEqual(spec["gate_decisions"], ["pending"])

    def test_exact_existing_sample_plan_with_checksum_references(self):
        prepare_source(self.root)
        plan = documents.plan(self.root)
        self.assertEqual(len(plan["candidates"]), 100)
        self.assertEqual(len({c["pblancId"] for c in plan["candidates"]}), 100)
        self.assertEqual([c["source_reference"]["page"] for c in plan["candidates"]], sum(([p] * 20 for p in range(1, 6)), []))
        self.assertEqual(len(plan["source_artifact_sha256"]), 64)
        self.assertTrue(all(len(c["source_reference"]["sha256"]) == 64 for c in plan["candidates"]))

    def test_source_sample_changed_checksum_fails_before_http(self):
        prepare_source(self.root)
        path = self.root / "data/raw/api-quality-dev-20260928-01-page1/response.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.run_download()
        self.assertEqual(self.calls, [])

    def test_success_hundred_sequential_requests_and_denominator(self):
        prepare_source(self.root)
        result = self.run_download()
        self.assertEqual(len(self.calls), 100)
        self.assertEqual(result["metrics"]["successful_downloads"], 100)
        self.assertEqual(result["metrics"]["download_success_rate"], 1)
        self.assertEqual(result["metrics"]["actual_formats"], {"PDF": 100})
        self.assertEqual(result["metrics"]["duplicate_sha256_extra_count"], 99)
        self.assertEqual(result["metrics"]["supplementary_pairing"]["PAIR_COUNT_MATCH"], 100)
        self.assertEqual(result["run"]["status"], "COMPLETED")
        with patch.object(documents, "open_document", side_effect=AssertionError("no HTTP")):
            reconstructed, rows = documents.analyze(self.root, "document-test")
        self.assertEqual(reconstructed, result)
        self.assertEqual(len(rows), 100)

    def test_http_404_and_500_are_failures(self):
        for status in (404, 500):
            with self.subTest(status=status):
                result, raw = self.transfer(b"synthetic-http-error", status)
                self.assertEqual(result["outcome"], "HTTP_ERROR")
                self.assertEqual(result["http_status"], status)
                self.assertEqual(raw, b"synthetic-http-error")

    def test_transport_failure_redacts_exception(self):
        result, raw = documents.transfer(URL, KEY, lambda *a: (_ for _ in ()).throw(URLError(KEY)))
        self.assertEqual(result["outcome"], "TRANSPORT_ERROR")
        self.assertIsNone(raw)
        self.assertNotIn(KEY, json.dumps(result))

    def test_redirect_records_hop_and_final_host_without_authentication(self):
        def fetch(req, timeout):
            self.calls.append(req)
            return Response(status=302, headers={"Location": URL + "1"}) if len(self.calls) == 1 else Response()
        result, raw = documents.transfer(URL, KEY, fetch)
        self.assertEqual(result["outcome"], "SUCCESS")
        self.assertEqual(result["redirect_count"], 1)
        self.assertEqual(result["http_requests"], 2)
        self.assertEqual(result["final_host"], "www.bizinfo.go.kr")
        self.assertEqual(raw, PDF)

    def test_redirect_limit_and_loop_fail(self):
        def fetch(req, timeout):
            self.calls.append(req)
            return Response(status=302, headers={"Location": URL + str(len(self.calls))})
        result, _ = documents.transfer(URL, KEY, fetch)
        self.assertEqual(result["outcome"], "REDIRECT_ERROR")
        self.assertEqual(result["redirect_count"], 3)
        self.assertEqual(len(self.calls), 4)
        loop, _ = self.transfer(status=302, headers={"Location": URL})
        self.assertEqual(loop["outcome"], "REDIRECT_ERROR")

    def test_cross_host_and_auth_query_redirect_never_requested(self):
        for location in ("https://evil.invalid/file.pdf", URL + "&serviceKey=" + KEY, "http://www.bizinfo.go.kr/file.pdf"):
            result, _ = self.transfer(status=302, headers={"Location": location})
            self.assertEqual(result["outcome"], "REDIRECT_ERROR")
            self.assertEqual(result["http_requests"], 1)
            self.assertNotIn(KEY, json.dumps(result))

    def test_empty_file(self):
        result, raw = self.transfer(b"")
        self.assertEqual(result["outcome"], "EMPTY_FILE")
        self.assertEqual(result["actual_byte_size"], 0)
        self.assertEqual(raw, b"")

    def test_stream_size_limit_ignores_false_content_length(self):
        spec = {**documents.contract(), "max_file_bytes": 20}
        result, raw = self.transfer(b"x" * 200, headers={"Content-Length": "1"}, spec=spec)
        self.assertEqual(result["outcome"], "SIZE_LIMIT_EXCEEDED")
        self.assertEqual(result["actual_byte_size"], 21)
        self.assertFalse(result["complete_body"])
        self.assertEqual(len(raw), 20)
        self.assertIn("size_is_lower_bound_not_full_file_size", result["observations"])

    def test_pdf_signature(self):
        self.assertEqual(documents.actual_format(PDF), "PDF")

    def test_hwp_fileheader_signature_not_generic_ole(self):
        raw = hwp_fixture()
        self.assertEqual(documents.actual_format(raw), "HWP")
        self.assertEqual(documents.actual_format(raw.replace(b"HWP Document File", b"NOT a HWP Header!")), "UNKNOWN")
        self.assertEqual(documents.actual_format(bytes.fromhex("d0cf11e0a1b11ae1")), "UNKNOWN")

    def test_hwpx_and_xlsx_container_identification(self):
        for kind in ("HWPX", "XLSX", "ZIP"):
            self.assertEqual(documents.actual_format(zip_fixture(kind)), kind)
        self.assertEqual(documents.actual_format(b"PKbroken"), "UNKNOWN")

    def test_unsafe_zip_and_ambiguous_container_are_unknown(self):
        for extra in ({"../escape": "x"}, {"xl/workbook.xml": "x", "[Content_Types].xml": "x", "xl/worksheets/sheet1.xml": "x"}):
            stream = io.BytesIO(zip_fixture("HWPX"))
            with zipfile.ZipFile(stream, "a") as archive:
                for name, value in extra.items():
                    archive.writestr(name, value)
            self.assertEqual(documents.actual_format(stream.getvalue()), "UNKNOWN")

    def test_unknown_format(self):
        result, _ = self.transfer(b"unrecognized-synthetic-bytes")
        self.assertEqual(result["outcome"], "UNKNOWN_FORMAT")
        self.assertEqual(result["actual_format"], "UNKNOWN")

    def test_filename_actual_mismatch_and_content_type_observation(self):
        result, _ = self.transfer(headers={"Content-Type": "application/octet-stream"})
        documents.check_content(result, "HWP")
        self.assertEqual(result["outcome"], "FORMAT_MISMATCH")
        self.assertFalse(result["filename_actual_match"])
        self.assertIn("content_type_differs_from_identified_format", result["observations"])
        correct, _ = self.transfer(headers={"Content-Type": "application/octet-stream"})
        documents.check_content(correct, "PDF")
        self.assertEqual(correct["outcome"], "SUCCESS")

    def test_duplicate_source_url_and_supplementary_count_mismatch(self):
        prepare_source(self.root, lambda item, i: item.update(printFlpthNm=URL, fileNm="only.pdf") if i < 2 else None)
        frozen = documents.plan(self.root)
        measured = documents.metrics(frozen, [])
        self.assertEqual(measured["url_quality"]["duplicate_url_extra_count"], 1)
        self.assertEqual(measured["supplementary_pairing"]["PAIR_COUNT_MISMATCH"], 2)
        self.assertEqual(measured["supplementary_pairing"]["semantic_pairing"], "UNCONFIRMED")
        self.assertEqual(measured["actual_formats"], "UNMEASURED")

    def test_partial_run_resume_skips_success_and_failed_items(self):
        prepare_source(self.root)
        def first(req, timeout):
            self.calls.append(req)
            return Response(status=404) if len(self.calls) == 1 else Response()
        partial = self.run_download(stop_after=3, fetch=first)
        self.assertEqual(partial["run"]["status"], "PARTIAL")
        self.assertEqual(partial["metrics"]["download_success_rate"], 0.02)
        resumed = self.run_download(resume=True)
        self.assertEqual(len(self.calls), 100)
        self.assertEqual(resumed["metrics"]["successful_downloads"], 99)
        self.assertEqual(resumed["metrics"]["outcome_counts"]["HTTP_ERROR"], 1)
        self.assertEqual(resumed["metrics"]["processed_candidates"], 100)
        self.assertEqual(resumed["metrics"]["primary_notice_hypothesis"], "WEAKENED_BY_DOWNLOAD_EVIDENCE")

    def test_overwrite_and_checksum_mismatch_fail_without_http(self):
        prepare_source(self.root)
        self.run_download(stop_after=1)
        with self.assertRaises(ValueError):
            self.run_download()
        path = self.root / "data/downloaded/document-test/SYNTHETIC_000/document.bin"
        path.write_bytes(PDF + b"tampered")
        with self.assertRaises(ValueError):
            self.run_download(resume=True)
        self.assertEqual(len(self.calls), 1)

    def test_orphan_file_never_success_or_overwritten(self):
        prepare_source(self.root)
        self.run_download(stop_after=0)
        folder = self.root / "data/downloaded/document-test/SYNTHETIC_000"
        folder.mkdir()
        (folder / "document.bin").write_bytes(b"orphan")
        with self.assertRaises(ValueError):
            self.run_download(resume=True)
        self.assertEqual(self.calls, [])
        self.assertEqual((folder / "document.bin").read_bytes(), b"orphan")

    def test_checkpoint_format_counts_resume_and_success_proof(self):
        prepare_source(self.root)
        result = self.run_download(stop_after=2)
        text = (self.root / result["run"]["checkpoint"]).read_text()
        state = json.loads(text.split("```json\n")[1].split("\n```", 1)[0])
        for name in ("run_id", "task", "started_at", "updated_at", "total_target", "completed_count", "failed_count", "failed_items", "current_stage", "last_processed_item", "next_action", "resume_command", "notes", "remaining_count", "success_count", "last_processed_pblancId"):
            self.assertIn(name, state)
        self.assertEqual(state["remaining_count"], 98)
        self.assertEqual(state["completed_count"], 2)
        self.assertIn("--resume", state["resume_command"])
        metadata = self.root / "data/downloaded/document-test/SYNTHETIC_000/metadata.json"
        record = phase0.read_json(metadata)
        self.assertEqual(record["sha256"], documents.digest(PDF))
        record["stored_path"] = None
        metadata.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            self.run_download(resume=True)

    def test_secret_response_header_body_and_url_are_rejected_without_storage(self):
        for raw in (KEY.encode(), quote(KEY, safe="").encode()):
            result, payload = self.transfer(raw)
            self.assertEqual(result["outcome"], "SECURITY_REJECTED")
            self.assertIsNone(payload)
            self.assertNotIn(KEY, json.dumps(result))
        result, raw = self.transfer(headers={"Content-Type": KEY})
        self.assertIsNone(raw)
        self.assertEqual(result["outcome"], "SECURITY_REJECTED")
        result, raw = documents.transfer(URL + "&serviceKey=" + KEY, KEY, self.fake)
        self.assertEqual(result["outcome"], "URL_POLICY_ERROR")
        self.assertEqual(self.calls, [])

    def test_secret_stdout_stderr_report_log_and_request_absent(self):
        prepare_source(self.root)
        capture = io.StringIO()
        with redirect_stdout(capture), redirect_stderr(capture):
            result = self.run_download(stop_after=2)
        manifest = phase0.read_json(self.root / "data/downloaded/document-test/manifest.json")
        rows = documents.records(self.root, manifest)
        self.assertNotIn(KEY, capture.getvalue() + documents.render(result, rows))
        for path in (self.root / "data/downloaded").rglob("*"):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes())
        self.assertTrue(all(KEY not in r.full_url and KEY not in str(r.headers) for r in self.calls))

    def test_prod_rejected_before_secret_or_source_read(self):
        with patch.object(documents.probe, "load_config", side_effect=AssertionError("not read")), patch.object(documents, "plan", side_effect=AssertionError("not read")):
            with self.assertRaises(ValueError):
                documents.download(self.root, "prod", "test", {})

    def test_raw_preserved_and_prod_file_not_read(self):
        prepare_source(self.root)
        before = {str(p): documents.digest(p.read_bytes()) for p in (self.root / "data/raw").rglob("*") if p.is_file()}
        (self.root / ".env.dev").write_text("BIZINFO_SERVICE_KEY=" + KEY)
        (self.root / ".env.prod").write_text("BIZINFO_SERVICE_KEY=synthetic-prod-never-read")
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            if path.name == ".env.prod":
                raise AssertionError("prod file read")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", guarded):
            self.run_download(stop_after=2)
        after = {str(p): documents.digest(p.read_bytes()) for p in (self.root / "data/raw").rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
