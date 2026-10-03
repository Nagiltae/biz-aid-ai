import copy
import hashlib
import io
import re
import sys
import unittest
import warnings
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.documents.archive import (member_basename, member_key, member_row, plan_archive,
                                                processable_formats)
from biz_aid_pipeline.indexing.document_role import document_role
from biz_aid_pipeline.parsing.models import parsing_contract
from biz_aid_pipeline.parsing.router import route_for
from test_phase0_document_download import PDF, hwp_fixture, zip_fixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
HWPML = '<?xml version="1.0" encoding="UTF-8"?><HWPML Version="2.8"><HEAD/></HWPML>'.encode()
MIGRATION = ROOT / "migrations/V10__document_archive_members.sql"


class RawNameInfo(zipfile.ZipInfo):
    """UTF-8 플래그 없이 원래 byte 이름을 그대로 쓰는 항목(한국 Windows 압축 프로그램이 만드는 CP949 이름 재현)."""

    def __init__(self, raw_name, flag_bits=0):
        super().__init__(raw_name.decode("cp437"))
        self.raw_name, self.extra_flags = raw_name, flag_bits

    def _encodeFilenameFlags(self):
        return self.raw_name, (self.flag_bits | self.extra_flags) & ~0x800


def archive(entries, compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(stream, "w", compression) as output:
            for name, value in entries:
                if isinstance(name, zipfile.ZipInfo):
                    name.compress_type = compression
                output.writestr(name, value)
    return stream.getvalue()


def plan(raw, attachments=(), contract=None):
    return plan_archive(raw, hashlib.sha256(raw).hexdigest(), contract or parsing_contract(), set(attachments).__contains__)


def by_name(result):
    return {member.basename: member for member in result.members}


class GenericZipTests(unittest.TestCase):
    def test_member_names_utf8_flag_cp949_and_raw_bytes(self):
        raw = archive([("공고문.pdf", PDF), (RawNameInfo("붙임1_신청서.hwp".encode("cp949")), hwp_fixture()),
                       (RawNameInfo(b"\xff\xfe-broken.pdf"), PDF + b"x")])
        members = sorted(plan(raw).members, key=lambda member: member.member_index)
        self.assertEqual([(m.path, m.encoding) for m in members],
                         [("공고문.pdf", "UTF8_FLAG"), ("붙임1_신청서.hwp", "CP949"), (None, "RAW_BYTES")])
        # 원래 이름 byte는 해석 결과와 상관없이 항상 남고, 관계 키는 원래 byte 기준이라 다시 실행해도 같다.
        self.assertEqual(members[1].path_raw, "붙임1_신청서.hwp".encode("cp949"))
        self.assertEqual(members[2].path_raw, b"\xff\xfe-broken.pdf")
        self.assertEqual(members[2].member_key, member_key(hashlib.sha256(raw).hexdigest(), b"\xff\xfe-broken.pdf"))
        self.assertEqual(plan(raw).members, plan(raw).members)

    def test_member_rules_exclusions_duplicates_and_depth_one(self):
        attachment = PDF + b"already-a-standalone-attachment"
        raw = archive([("서식/", b""), ("서식/Thumbs.db", b"\0" * 64), ("서식/빈파일.txt", b""),
                       ("서식/사업자등록증 사본(스캔하여 pdf로 제출 요망).txt", "사업자등록증 사본(스캔하여 pdf로 제출 요망)".encode("cp949")),
                       ("서식/HTML.txt", ("<p>안내</p>\n" * 30).encode()), ("서식/첨부.zip", zip_fixture("ZIP")),
                       ("서식/본문.hwp", HWPML), ("서식/명단.xlsx", zip_fixture("XLSX")), ("서식/빈.pdf", b""),
                       ("서식/로고.ai", PDF + b"illustrator"), ("서식/포스터.png", PNG), ("서식/공고문.pdf", attachment),
                       ("서식/신청서.hwp", hwp_fixture()), ("서식/모름.bin", b"unknown-binary")])
        result = plan(raw, attachments={hashlib.sha256(attachment).hexdigest()})
        members = by_name(result)
        self.assertIsNone(result.failure_code)
        # 디렉터리 항목은 내부 파일이 아니므로 기록하지 않는다.
        self.assertEqual((result.directories, len(result.members)), (1, 13))
        expected = {"Thumbs.db": ("EXCLUDED", "os_metadata_file"), "빈파일.txt": ("EXCLUDED", "empty_or_placeholder_text"),
                    "사업자등록증 사본(스캔하여 pdf로 제출 요망).txt": ("EXCLUDED", "empty_or_placeholder_text"),
                    "HTML.txt": ("EXCLUDED", "unsupported_format"), "첨부.zip": ("EXCLUDED", "nested_archive"),
                    "본문.hwp": ("EXCLUDED", "hwpml_on_hold"), "명단.xlsx": ("EXCLUDED", "intentionally_excluded_format"),
                    "빈.pdf": ("EXCLUDED", "empty_member"), "로고.ai": ("STORED", None), "포스터.png": ("STORED", None),
                    "공고문.pdf": ("DUPLICATE_SOURCE", "same_sha_as_attachment"), "신청서.hwp": ("STORED", None),
                    "모름.bin": ("EXCLUDED", "unsupported_format")}
        self.assertEqual({name: (member.status, member.reason) for name, member in members.items()}, expected)
        # .ai는 실제 byte가 PDF라 PDF route로 간다. 저장용 byte는 STORED 항목만 들고 있다.
        self.assertEqual(members["로고.ai"].detected_format, "PDF")
        self.assertEqual(route_for("PDF", parsing_contract())[0], "DOCLING_PDF")
        self.assertTrue(all((member.raw is not None) == (member.status == "STORED") for member in result.members))
        # 압축 안 압축은 열지 않는다: 그 안의 파일은 기록되지 않는다.
        self.assertNotIn("test.bin", members)

    def test_unsafe_archives_write_no_members(self):
        cases = [("archive_unsafe:path", archive([("../escape.pdf", PDF)])),
                 # Windows 압축의 역슬래시 경로 탈출도 같은 검사를 받는다.
                 ("archive_unsafe:path", archive([(RawNameInfo(b"..\\escape.pdf"), PDF)])),
                 ("archive_unsafe:path", archive([("/etc/escape.pdf", PDF)])),
                 ("archive_unsafe:duplicate_name", archive([("a.pdf", PDF), ("a.pdf", PDF + b"2")])),
                 ("archive_encrypted", archive([(RawNameInfo(b"locked.pdf", flag_bits=0x1), PDF)])),
                 ("archive_unsafe:compression_ratio", archive([("zeros.pdf", PDF + b"\0" * 3_000_000)], zipfile.ZIP_DEFLATED)),
                 ("archive_unreadable", b"PK\x03\x04 broken")]
        for code, raw in cases:
            with self.subTest(code=code, raw=raw[:40]):
                result = plan(raw)
                self.assertEqual((result.failure_code, result.members), (code, ()))
        limited = copy.deepcopy(parsing_contract())
        limited["hwpx_container_limits"]["max_entries"] = 1
        self.assertEqual(plan(archive([("a.pdf", PDF), ("b.pdf", PDF + b"b")]), contract=limited).failure_code,
                         "archive_unsafe:entry_limit")

    def test_member_read_failure_is_recorded_without_sha(self):
        raw = bytearray(archive([("ok.pdf", PDF), ("broken.pdf", PDF + b"payload")]))
        # 저장(무압축) 항목의 본문 byte를 바꿔 CRC가 맞지 않게 만든다.
        offset = bytes(raw).rindex(b"payload")
        raw[offset] ^= 0xFF
        members = by_name(plan(bytes(raw)))
        self.assertEqual((members["ok.pdf"].status, members["broken.pdf"].status), ("STORED", "FAILED"))
        self.assertEqual(members["broken.pdf"].reason, "member_read_failed:BadZipFile")
        self.assertIsNone(members["broken.pdf"].sha256)

    def test_contract_route_and_role_boundaries(self):
        contract = parsing_contract()
        spec = contract["generic_zip"]
        # 압축 자체는 파싱하지 않고 내부 파일만 기존 route로 간다. 새 parser 없음.
        self.assertEqual(route_for("ZIP", contract)[0], "POLICY_PENDING")
        self.assertTrue(contract["routes"]["ZIP"]["extraction_enabled"])
        self.assertEqual(processable_formats(contract), {"PDF", "HWP", "HWPX", "PNG", "JPEG", "DOCX", "PPTX"})
        self.assertEqual(spec["intentionally_excluded_formats"], ["XLSX", "DOC", "XLS", "PPT"])
        # 출처 종류는 압축 이름이 아니라 내부 파일명으로 정한다.
        self.assertEqual(document_role("HWP", [member_basename("공고문_모음/붙임2. 사업계획서 양식.hwp")]), "FORM")
        self.assertEqual(document_role("PDF", [member_basename("양식/2026 모집공고.pdf")]), "BODY")

    def test_member_rows_match_migration(self):
        contract = parsing_contract()
        sql = MIGRATION.read_text(encoding="utf-8")
        columns = re.findall(r"^    ([a-z0-9_]+) [A-Z]", sql, re.MULTILINE)
        raw = archive([("공고.pdf", PDF)])
        member = plan(raw).members[0]
        row = member_row(member, hashlib.sha256(raw).hexdigest(), "test-run", ("ap-northeast-2", "bucket", "key", None))
        self.assertEqual(sorted(row), sorted(columns))
        # 계약의 계보 필드·상태가 migration에 모두 있다.
        for name in contract["routes"]["ZIP"]["generic_zip_member_provenance_required"]:
            self.assertIn(name, columns)
        for status in contract["generic_zip"]["statuses"]:
            self.assertIn(f"'{status}'", sql)
        self.assertEqual(len(re.findall(r" COMMENT '", sql)), len(columns))
        # 승인(2026-10-02) 뒤 공통 Flyway 계보로 옮겼다. 두 번째 migration 보관 위치가 남지 않는다.
        self.assertIn("migrations/", contract["generic_zip"]["database"])
        self.assertFalse((ROOT / "data-pipeline/pending-migrations/V10__document_archive_members.sql").exists())


if __name__ == "__main__":
    unittest.main()
