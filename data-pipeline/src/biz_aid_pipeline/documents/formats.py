import io
import re
import struct
import zipfile
from pathlib import PurePosixPath


def _cfb(raw):
    """OLE(CFB) 디렉터리 항목과 stream 읽기 함수. 구조가 제한 범위를 벗어나면 None.

    OLE magic은 HWP·DOC·XLS·PPT가 공유하므로 형식은 stream 이름으로 가린다. 모든 chain·크기를 제한해 손상 파일을 읽지 않는다.
    """
    if len(raw) < 512 or raw[:8] != bytes.fromhex("d0cf11e0a1b11ae1") or raw[28:30] != b"\xfe\xff":
        return None
    sector_shift, mini_shift = struct.unpack_from("<HH", raw, 30)
    if sector_shift not in (9, 12) or mini_shift != 6:
        return None
    size = 1 << sector_shift
    count = len(raw) // size - 1

    def sector(index):
        if not 0 <= index < count:
            raise ValueError("invalid_sector")
        return raw[(index + 1) * size:(index + 2) * size]

    def integers(value):
        return list(struct.unpack("<" + "I" * (len(value) // 4), value))

    def chain(index, table, reader, limit):
        seen, result = set(), bytearray()
        while index != 0xfffffffe:
            if index in seen or not 0 <= index < len(table) or len(result) >= limit:
                raise ValueError("invalid_chain")
            seen.add(index)
            result.extend(reader(index))
            index = table[index]
        return bytes(result)

    try:
        fat_count = struct.unpack_from("<I", raw, 44)[0]
        if not 1 <= fat_count <= count:
            return None
        difat = [number for number in integers(raw[76:512]) if number != 0xffffffff]
        next_sector, difat_count = struct.unpack_from("<II", raw, 68)
        seen = set()
        if difat_count > count:
            return None
        for _ in range(difat_count):
            if next_sector in seen:
                return None
            seen.add(next_sector)
            entries = integers(sector(next_sector))
            difat.extend(number for number in entries[:-1] if number != 0xffffffff)
            next_sector = entries[-1]
        if len(difat) != fat_count or len(set(difat)) != fat_count:
            return None
        fat = [number for index in difat for number in integers(sector(index))]
        directory = chain(struct.unpack_from("<I", raw, 48)[0], fat, sector, 524288)
        entries = []
        for offset in range(0, len(directory), 128):
            entry = directory[offset:offset + 128]
            name_size = struct.unpack_from("<H", entry, 64)[0]
            if entry[66] not in (2, 5) or not 2 <= name_size <= 64 or name_size % 2:
                continue
            name = entry[:name_size - 2].decode("utf-16le")
            entries.append((name, entry[66], struct.unpack_from("<I", entry, 116)[0],
                            struct.unpack_from("<Q", entry, 120)[0]))
    except (ValueError, UnicodeError, struct.error, IndexError):
        return None

    def read_stream(entry, limit):
        """작은 stream(4096 byte 미만)은 mini stream에서, 나머지는 일반 sector chain에서 읽는다."""
        _, _, start, length = entry
        if length >= 4096:
            return chain(start, fat, sector, limit)[:length]
        roots = [item for item in entries if item[1] == 5]
        if len(roots) != 1 or roots[0][3] > len(raw):
            raise ValueError("invalid_root")
        miniature = chain(roots[0][2], fat, sector, len(raw))[:roots[0][3]]
        mini_start, mini_count = struct.unpack_from("<II", raw, 60)
        if not 1 <= mini_count <= count:
            raise ValueError("invalid_mini_count")
        mini_fat = integers(chain(mini_start, fat, sector, mini_count * size + size))

        def mini_sector(index):
            if (index + 1) * 64 > len(miniature):
                raise ValueError("invalid_mini_sector")
            return miniature[index * 64:(index + 1) * 64]

        return chain(start, mini_fat, mini_sector, limit)[:length]

    return entries, read_stream


def hwp_header(raw):
    # OLE magic은 여러 Office 형식이 공유하므로 제한된 CFB chain에서 HWP FileHeader를 확인한다.
    cfb = _cfb(raw)
    if cfb is None:
        return False
    entries, read_stream = cfb
    try:
        headers = [entry for entry in entries if entry[0] == "FileHeader" and entry[1] == 2]
        if len(headers) != 1 or not 32 <= headers[0][3] <= 4096:
            return False
        value = read_stream(headers[0], 8192)
        return value[:32].rstrip(b"\x00") == b"HWP Document File"
    except (ValueError, UnicodeError, struct.error, IndexError):
        return False


# 옛 Microsoft Office(OLE)는 대표 stream 이름으로 가린다. 암호화된 새 Office(EncryptedPackage)는 형식을 확정하지 않는다.
OLE_OFFICE_STREAMS = (("WordDocument", "DOC"), ("PowerPoint Document", "PPT"), ("Workbook", "XLS"), ("Book", "XLS"))


def ole_office_format(raw):
    """HWP가 아닌 OLE 파일의 옛 Office 형식(DOC·XLS·PPT). 판별할 수 없거나 둘 이상이면 None."""
    cfb = _cfb(raw)
    if cfb is None:
        return None
    names = {entry[0] for entry in cfb[0] if entry[1] == 2}
    if "EncryptedPackage" in names:
        return None
    found = {kind for stream, kind in OLE_OFFICE_STREAMS if stream in names}
    return found.pop() if len(found) == 1 else None


def zip_document_format(archive, names):
    """압축 container 안의 문서 형식. HWPX·XLSX·DOCX·PPTX·ODT 중 정확히 하나면 그 값, 없으면 ZIP, 둘 이상이면 UNKNOWN."""
    found = []
    mimetype = b""
    if "mimetype" in names and archive.getinfo("mimetype").file_size <= 128:
        mimetype = archive.read("mimetype").strip()
    if (mimetype == b"application/hwp+zip" and "Contents/header.xml" in names
            and any(re.fullmatch(r"Contents/section\d+\.xml", name) for name in names)):
        found.append("HWPX")
    office = "[Content_Types].xml" in names
    if office and "xl/workbook.xml" in names and any(re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name) for name in names):
        found.append("XLSX")
    if office and "word/document.xml" in names:
        found.append("DOCX")
    if office and "ppt/presentation.xml" in names:
        found.append("PPTX")
    if mimetype == b"application/vnd.oasis.opendocument.text" and "content.xml" in names:
        found.append("ODT")
    return found[0] if len(found) == 1 else "UNKNOWN" if found else "ZIP"


def hwpml(raw):
    """XML 기반 한글 문서(HWPML, .hml). 판별만 하고 처리 경로는 보류한다."""
    head = raw[:4096].lstrip(b"\xef\xbb\xbf").lstrip()
    return head.startswith(b"<?xml") and b"<HWPML" in head


def actual_format(raw):
    if raw.startswith(b"%PDF-"):
        return "PDF"
    if raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        if hwp_header(raw):
            return "HWP"
        return ole_office_format(raw) or "UNKNOWN"
    if raw.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                # Container를 풀지 않고 directory와 작은 mimetype만 읽어 경로 탈출·압축 폭탄을 제한한다.
                if (len(entries) > 4096 or len(set(names)) != len(names)
                        or any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names)
                        or sum(entry.file_size for entry in entries) > 104857600):
                    return "UNKNOWN"
                return zip_document_format(archive, names)
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
            return "UNKNOWN"
    if raw.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return "OTHER"
    if raw.startswith(b"\x89PNG\r\n"):
        return "PNG"
    if raw.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if hwpml(raw):
        return "HWPML"
    return "UNKNOWN"


def html_response(raw):
    return raw.lstrip().lower().startswith((b"<!doctype html", b"<html"))
