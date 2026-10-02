import io
import struct
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.documents.formats import actual_format, hwp_header, ole_office_format
from test_phase0_document_download import PDF, hwp_fixture, zip_fixture


def ole_fixture(streams):
    """합성 OLE(CFB) 파일: Root Entry 아래 이름만 다른 32 byte stream들. 내용은 형식 판별에 쓰지 않는다."""
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
    entries = [("Root Entry", 5, 3, 64)] + [(name, 2, 0, 32) for name in streams]
    for index, (name, kind, start, size) in enumerate(entries):
        offset = index * 128
        encoded = (name + "\0").encode("utf-16le")
        directory[offset:offset + len(encoded)] = encoded
        struct.pack_into("<H", directory, offset + 64, len(encoded))
        directory[offset + 66] = kind
        struct.pack_into("<I", directory, offset + 116, start)
        struct.pack_into("<Q", directory, offset + 120, size)
    mini = struct.pack("<128I", 0xfffffffe, *([0xffffffff] * 127))
    return bytes(header) + fat + directory + mini + b"synthetic".ljust(512, b"\0")


def container(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return stream.getvalue()


OOXML = {"[Content_Types].xml": "synthetic"}


class DocumentFormatTests(unittest.TestCase):
    def test_existing_pdf_hwp_hwpx_xlsx_results_do_not_change(self):
        # BOUNDARY: 공통 기반 세분화가 이미 처리 중인 형식의 판별을 바꾸면 적재된 문서의 형식이 흔들린다.
        self.assertEqual(actual_format(PDF), "PDF")
        self.assertEqual(actual_format(hwp_fixture()), "HWP")
        self.assertTrue(hwp_header(hwp_fixture()))
        self.assertEqual(actual_format(zip_fixture("HWPX")), "HWPX")
        self.assertEqual(actual_format(zip_fixture("XLSX")), "XLSX")
        self.assertEqual(actual_format(zip_fixture("ZIP")), "ZIP")
        # HWP FileHeader 문자열이 틀리면 HWP가 아니고, 다른 Office stream도 없으면 UNKNOWN이다.
        self.assertEqual(actual_format(hwp_fixture().replace(b"HWP Document File", b"NOT a HWP Header!")), "UNKNOWN")

    def test_office_containers_are_split_out_of_generic_zip(self):
        self.assertEqual(actual_format(container(dict(OOXML, **{"word/document.xml": "x"}))), "DOCX")
        self.assertEqual(actual_format(container(dict(OOXML, **{"ppt/presentation.xml": "x"}))), "PPTX")
        self.assertEqual(actual_format(container({"mimetype": "application/vnd.oasis.opendocument.text", "content.xml": "x"})), "ODT")
        # ODT 외 OpenDocument(스프레드시트)와 Office 표식이 없는 압축은 일반 ZIP으로 남는다.
        self.assertEqual(actual_format(container({"mimetype": "application/vnd.oasis.opendocument.spreadsheet", "content.xml": "x"})), "ZIP")
        self.assertEqual(actual_format(container({"공고문.hwp": "x", "양식.xlsx": "y"})), "ZIP")
        # 두 형식의 표식이 함께 있으면 어느 하나로 단정하지 않는다.
        both = dict(OOXML, **{"word/document.xml": "x", "xl/workbook.xml": "y", "xl/worksheets/sheet1.xml": "z"})
        self.assertEqual(actual_format(container(both)), "UNKNOWN")
        self.assertEqual(actual_format(container(dict(OOXML, **{"word/document.xml": "x", "../escape.txt": "y"}))), "UNKNOWN")

    def test_legacy_office_ole_files_are_identified_by_stream_names(self):
        self.assertEqual(actual_format(ole_fixture(["WordDocument"])), "DOC")
        self.assertEqual(actual_format(ole_fixture(["Workbook"])), "XLS")
        self.assertEqual(actual_format(ole_fixture(["Book"])), "XLS")
        self.assertEqual(actual_format(ole_fixture(["PowerPoint Document", "Current User"])), "PPT")
        # 암호화된 새 Office, 알 수 없는 stream, 모호한 조합, 손상된 OLE는 형식을 정하지 않는다.
        for streams in (["EncryptedPackage", "EncryptionInfo"], ["Thumbs"], ["WordDocument", "Workbook"]):
            with self.subTest(streams=streams):
                self.assertIsNone(ole_office_format(ole_fixture(streams)))
                self.assertEqual(actual_format(ole_fixture(streams)), "UNKNOWN")
        self.assertEqual(actual_format(bytes.fromhex("d0cf11e0a1b11ae1")), "UNKNOWN")

    def test_images_html_and_hwpml(self):
        self.assertEqual(actual_format(b"\x89PNG\r\n\x1a\n" + b"\0" * 16), "PNG")
        self.assertEqual(actual_format(b"\xff\xd8\xff\xe0" + b"\0" * 16), "JPEG")
        # HTML(다운로드 오류 페이지 등)은 이미지와 섞이지 않게 OTHER로 남는다.
        self.assertEqual(actual_format(b"  <!DOCTYPE html><html></html>"), "OTHER")
        hml = '﻿<?xml version="1.0" encoding="UTF-8"?><HWPML Version="2.8"><HEAD/></HWPML>'.encode()
        self.assertEqual(actual_format(hml), "HWPML")
        self.assertEqual(actual_format(b'<?xml version="1.0"?><svg/>'), "UNKNOWN")
        self.assertEqual(actual_format(b"unknown-safe-binary"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
