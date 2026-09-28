import io
import re
import struct
import zipfile
from pathlib import PurePosixPath


def hwp_header(raw):
    # OLE magic은 여러 Office 형식이 공유하므로 제한된 CFB chain에서 HWP FileHeader를 확인한다.
    if len(raw) < 512 or raw[:8] != bytes.fromhex("d0cf11e0a1b11ae1") or raw[28:30] != b"\xfe\xff":
        return False
    sector_shift, mini_shift = struct.unpack_from("<HH", raw, 30)
    if sector_shift not in (9, 12) or mini_shift != 6:
        return False
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
            return False
        difat = [number for number in integers(raw[76:512]) if number != 0xffffffff]
        next_sector, difat_count = struct.unpack_from("<II", raw, 68)
        seen = set()
        if difat_count > count:
            return False
        for _ in range(difat_count):
            if next_sector in seen:
                return False
            seen.add(next_sector)
            entries = integers(sector(next_sector))
            difat.extend(number for number in entries[:-1] if number != 0xffffffff)
            next_sector = entries[-1]
        if len(difat) != fat_count or len(set(difat)) != fat_count:
            return False
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
        headers = [entry for entry in entries if entry[0] == "FileHeader" and entry[1] == 2]
        if len(headers) != 1 or not 32 <= headers[0][3] <= 4096:
            return False
        _, _, start, length = headers[0]
        if length >= 4096:
            value = chain(start, fat, sector, 8192)[:length]
        else:
            roots = [entry for entry in entries if entry[1] == 5]
            if len(roots) != 1 or roots[0][3] > len(raw):
                return False
            miniature = chain(roots[0][2], fat, sector, len(raw))[:roots[0][3]]
            mini_start, mini_count = struct.unpack_from("<II", raw, 60)
            if not 1 <= mini_count <= count:
                return False
            mini_fat = integers(chain(mini_start, fat, sector, mini_count * size + size))

            def mini_sector(index):
                if (index + 1) * 64 > len(miniature):
                    raise ValueError("invalid_mini_sector")
                return miniature[index * 64:(index + 1) * 64]

            value = chain(start, mini_fat, mini_sector, 8192)[:length]
        return value[:32].rstrip(b"\x00") == b"HWP Document File"
    except (ValueError, UnicodeError, struct.error, IndexError):
        return False


def actual_format(raw):
    if raw.startswith(b"%PDF-"):
        return "PDF"
    if raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        return "HWP" if hwp_header(raw) else "UNKNOWN"
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
                hwpx = False
                if "mimetype" in names and archive.getinfo("mimetype").file_size <= 128:
                    hwpx = (archive.read("mimetype").strip() == b"application/hwp+zip"
                            and "Contents/header.xml" in names
                            and any(re.fullmatch(r"Contents/section\d+\.xml", name) for name in names))
                xlsx = ("[Content_Types].xml" in names and "xl/workbook.xml" in names
                        and any(re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name) for name in names))
                return "UNKNOWN" if hwpx and xlsx else "HWPX" if hwpx else "XLSX" if xlsx else "ZIP"
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
            return "UNKNOWN"
    if raw.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return "OTHER"
    if raw.startswith((b"\x89PNG\r\n", b"\xff\xd8\xff")):
        return "OTHER"
    return "UNKNOWN"


def html_response(raw):
    return raw.lstrip().lower().startswith((b"<!doctype html", b"<html"))
