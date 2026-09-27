#!/usr/bin/env python3
import hashlib
import io
import json
import os
import re
import statistics
import struct
import sys
import time
import zipfile
from collections import Counter
from datetime import datetime
from http.client import HTTPException
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import bizinfo_probe as probe
import phase0
import phase0_api_quality as quality

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "contracts/schemas/phase0-document-download.contract.json"


def contract():
    return phase0.read_json(SPEC_PATH)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_path(root, relative):
    path = root / relative
    if path.resolve() != path or path.is_symlink():
        raise ValueError("unsafe_evidence_path")
    return path


def url_syntax(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value)
        return (value == value.strip() and not any(c.isspace() or ord(c) < 32 for c in value)
                and parsed.scheme in ("http", "https") and bool(parsed.hostname) and bool(parsed.path)
                and parsed.port in (None, 80, 443))
    except ValueError:
        return False


def public_url(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value)
        # 공개 공고문만 요청하므로 인증 query·사용자 정보·다른 host로의 이동을 허용하지 않는다.
        return (value == value.strip() and not any(c.isspace() or ord(c) < 32 for c in value)
                and parsed.scheme == "https" and parsed.hostname in contract()["allowed_hosts"]
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and not parsed.fragment and bool(parsed.path)
                and all(k.lower() in ("atchfileid", "filesn") for k, _ in parse_qsl(parsed.query)))
    except ValueError:
        return False


def extension(filename):
    if not isinstance(filename, str) or not filename.strip():
        return "UNKNOWN"
    suffix = PurePosixPath(filename).suffix.removeprefix(".").upper()
    return suffix if suffix in contract()["formats"][:-2] else "OTHER" if suffix else "UNKNOWN"


def hwp_header(raw):
    # OLE magic만으로 HWP라고 판단하면 다른 Office 문서를 오인하므로 FileHeader 식별자까지만 확인한다.
    # 본문 stream·업무 XML은 읽지 않는다. 모든 sector chain은 파일 크기·방문 집합으로 제한한다.
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
    def ints(value):
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
        difat = [n for n in ints(raw[76:512]) if n != 0xffffffff]
        next_sector, difat_count = struct.unpack_from("<II", raw, 68)
        seen = set()
        if difat_count > count:
            return False
        for _ in range(difat_count):
            if next_sector in seen:
                return False
            seen.add(next_sector)
            entries = ints(sector(next_sector))
            difat.extend(n for n in entries[:-1] if n != 0xffffffff)
            next_sector = entries[-1]
        if len(difat) != fat_count or len(set(difat)) != fat_count:
            return False
        fat = [n for index in difat for n in ints(sector(index))]
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
        headers = [e for e in entries if e[0] == "FileHeader" and e[1] == 2]
        if len(headers) != 1 or not 32 <= headers[0][3] <= 4096:
            return False
        _, _, start, length = headers[0]
        if length >= 4096:
            value = chain(start, fat, sector, 8192)[:length]
        else:
            roots = [e for e in entries if e[1] == 5]
            if len(roots) != 1 or roots[0][3] > len(raw):
                return False
            miniature = chain(roots[0][2], fat, sector, len(raw))[:roots[0][3]]
            mini_start, mini_count = struct.unpack_from("<II", raw, 60)
            if not 1 <= mini_count <= count:
                return False
            mini_fat = ints(chain(mini_start, fat, sector, mini_count * size + size))
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
                names = [e.filename for e in entries]
                # ZIP을 추출하지 않고 directory와 작은 mimetype만 확인해 경로 탈출·압축 폭탄을 피한다.
                if (len(entries) > 4096 or len(set(names)) != len(names)
                        or any(PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names)
                        or sum(e.file_size for e in entries) > 104857600):
                    return "UNKNOWN"
                hwpx = False
                if "mimetype" in names and archive.getinfo("mimetype").file_size <= 128:
                    hwpx = (archive.read("mimetype").strip() == b"application/hwp+zip"
                            and "Contents/header.xml" in names
                            and any(re.fullmatch(r"Contents/section\d+\.xml", n) for n in names))
                xlsx = ("[Content_Types].xml" in names and "xl/workbook.xml" in names
                        and any(re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n) for n in names))
                return "UNKNOWN" if hwpx and xlsx else "HWPX" if hwpx else "XLSX" if xlsx else "ZIP"
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
            return "UNKNOWN"
    if raw.lstrip().lower().startswith((b"<!doctype html", b"<html")) or raw.startswith((b"\x89PNG\r\n", b"\xff\xd8\xff")):
        return "OTHER"
    return "UNKNOWN"


def plan(root):
    source_id = contract()["source_run_id"]
    source_path = safe_path(root, f"harness/workspace/artifacts/bizinfo-quality-{source_id}.json")
    source = phase0.read_json(source_path)["run"]
    if (source["run_id"] != source_id or source["profile"] != "dev" or source["collection_status"] != "COMPLETED"
            or source["requested_pages"] != [1, 2, 3, 4, 5] or source["requested_rows_per_page"] != 20
            or source["successful_pages"] != [1, 2, 3, 4, 5] or source["failed_pages"]
            or [p["requested"]["pageNo"] for p in source["pages"]] != [1, 2, 3, 4, 5]):
        raise ValueError("source_sample_incomplete")
    candidates = []
    for page in source["pages"]:
        if page["outcome"] != "SUCCESS":
            raise ValueError("source_page_failed")
        rows = quality.raw_items(root, source_id, page)
        if len(rows) != 20:
            raise ValueError("source_page_count")
        for index, item in enumerate(rows):
            identifier = item.get("pblancId")
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
                raise ValueError("unsafe_identifier")
            url = item.get("printFlpthNm")
            candidates.append({"pblancId": identifier, "source_url": url if public_url(url) else None,
                               "url_state": quality.field_state(item, "printFlpthNm"),
                               "url_allowed": public_url(url), "url_syntax_valid": url_syntax(url), "printFileNm": item.get("printFileNm"),
                               "source_reference": {"raw_metadata": page["raw_snapshot"], "sha256": page["sha256"],
                                                    "page": page["requested"]["pageNo"], "item_index": index,
                                                    "field": "printFlpthNm"},
                               "supplementary": {"url_tokens": len(item["flpthNm"].split("@")) if quality.field_state(item, "flpthNm") == "VALID" else None,
                                                  "filename_tokens": len(item["fileNm"].split("@")) if quality.field_state(item, "fileNm") == "VALID" else None}})
    if len(candidates) != 100 or len({c["pblancId"] for c in candidates}) != 100:
        raise ValueError("source_target_mismatch")
    return {"source_run_id": source_id, "source_artifact_sha256": digest(source_path.read_bytes()), "candidates": candidates}


def open_document(request, timeout):
    # 공개 파일 전용 opener에는 Proxy·Cookie·인증 handler를 추가하지 않는다.
    opener = build_opener(ProxyHandler({}), probe.NoRedirect())
    try:
        return opener.open(request, timeout=timeout)
    except HTTPError as error:
        return error


def transfer(url, secret, fetch=None, spec=None):
    spec = contract() if spec is None else spec
    result = {"http_status": None, "http_requests": 0, "redirect_count": 0, "redirect_statuses": [],
              "final_host": None, "content_type": None, "content_length": None,
              "actual_byte_size": None, "complete_body": False, "actual_format": "UNMEASURED",
              "outcome": "URL_POLICY_ERROR", "observations": [], "error": None}
    seen = set()
    current = url
    while True:
        if not public_url(current) or probe.credential_echo(str(current).encode(), secret):
            result["outcome"] = "REDIRECT_ERROR" if seen else "URL_POLICY_ERROR"
            result["error"] = "unsafe_or_credential_bearing_url"
            return result, None
        result["final_host"] = urlsplit(current).hostname
        seen.add(current)
        request = Request(current, headers={"Accept": "*/*", "Accept-Encoding": "identity"}, method="GET")
        try:
            result["http_requests"] += 1
            with (fetch or open_document)(request, spec["timeout_seconds"]) as response:
                status = response.code
                result["http_status"] = status
                if status in (301, 302, 303, 307, 308):
                    result["redirect_statuses"].append(status)
                    location = response.headers.get("Location")
                    if not location or result["redirect_count"] >= spec["max_redirects"]:
                        result.update(outcome="REDIRECT_ERROR", error="redirect_missing_location_or_limit")
                        return result, None
                    following = urljoin(current, location)
                    if following in seen:
                        result.update(outcome="REDIRECT_ERROR", error="redirect_loop")
                        return result, None
                    current = following
                    result["redirect_count"] += 1
                    continue
                content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower() or None
                if probe.credential_echo(str(content_type).encode(), secret):
                    result.update(outcome="SECURITY_REJECTED", error="credential_echo_header")
                    return result, None
                result["content_type"] = content_type
                length = response.headers.get("Content-Length", "")
                result["content_length"] = int(length) if length.isdigit() else None
                chunks, received = [], 0
                # Content-Length는 참고값이다. 실제 read를 최대값+1에서 멈춰 무한 응답과 과소 표기 모두 제한한다.
                while received <= spec["max_file_bytes"]:
                    chunk = response.read(min(65536, spec["max_file_bytes"] + 1 - received))
                    if not chunk:
                        result["complete_body"] = True
                        break
                    chunks.append(chunk)
                    received += len(chunk)
                raw = b"".join(chunks)
                result["actual_byte_size"] = len(raw)
                # 인증정보가 반사된 원문은 redaction 대신 저장 거부한다. 예외 문자열·Location도 출력하지 않는다.
                if probe.credential_echo(raw, secret):
                    result.update(outcome="SECURITY_REJECTED", error="credential_echo_body", actual_byte_size=None)
                    return result, None
                if not 200 <= status < 300:
                    result["outcome"] = "HTTP_ERROR"
                elif not result["complete_body"]:
                    result["outcome"] = "SIZE_LIMIT_EXCEEDED"
                elif not raw:
                    result["outcome"] = "EMPTY_FILE"
                else:
                    result["actual_format"] = actual_format(raw)
                    result["outcome"] = "UNKNOWN_FORMAT" if result["actual_format"] == "UNKNOWN" else "SUCCESS"
                if not result["complete_body"]:
                    result["observations"].append("size_is_lower_bound_not_full_file_size")
                    raw = raw[:spec["max_file_bytes"]]
                return result, raw
        except KeyboardInterrupt:
            result.update(outcome="TRANSPORT_ERROR", error="interrupted_request")
            result["observations"].append("interrupted_request_not_retried")
            return result, None
        except (URLError, TimeoutError, OSError, HTTPException):
            result.update(outcome="TRANSPORT_ERROR", error="network_or_stream_error")
            return result, None


def check_content(result, declared):
    actual = result["actual_format"]
    match = declared == actual and actual not in ("UNKNOWN", "OTHER") if actual != "UNMEASURED" else None
    if result["outcome"] == "SUCCESS" and not match:
        result["outcome"] = "FORMAT_MISMATCH"
    result["filename_actual_match"] = match
    expected = {"PDF": {"application/pdf"}, "HWP": {"application/x-hwp", "application/haansofthwp"},
                "HWPX": {"application/hwp+zip", "application/haansofthwpx"}, "ZIP": {"application/zip"},
                "XLSX": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}}
    if actual in expected and result["content_type"] not in expected[actual]:
        result["observations"].append("content_type_differs_from_identified_format")
    return result


def records(root, manifest):
    output = []
    for candidate in manifest["candidates"]:
        folder = safe_path(root, f"data/downloaded/{manifest['run_id']}/{candidate['pblancId']}")
        if not folder.exists():
            continue
        path = safe_path(root, str(folder.relative_to(root) / "metadata.json"))
        # 중단 직전의 미확정 파일을 성공으로 세면 복원 시 증거가 사라지므로 고립 파일이 있으면 멈춘다.
        if not path.is_file():
            raise ValueError("incomplete_document_evidence_requires_review")
        record = phase0.read_json(path)
        if (record["run_id"] != manifest["run_id"] or record["candidate"] != candidate
                or record["outcome"] not in contract()["outcomes"]):
            raise ValueError("document_metadata_mismatch")
        if record["stored_path"]:
            raw_path = safe_path(root, record["stored_path"])
            if raw_path != folder / "document.bin" or not raw_path.is_file():
                raise ValueError("unexpected_document_path")
            raw = raw_path.read_bytes()
            if len(raw) != record["stored_byte_size"] or digest(raw) != record["sha256"]:
                raise ValueError("document_checksum_mismatch")
            if record["complete_body"] and record["actual_byte_size"] != len(raw):
                raise ValueError("document_size_mismatch")
            if record["actual_format"] != "UNMEASURED" and actual_format(raw) != record["actual_format"]:
                raise ValueError("document_format_evidence_mismatch")
        if record["outcome"] == "SUCCESS" and (not record["stored_path"] or not record["complete_body"]
                or not record["stored_byte_size"] or not record["filename_actual_match"]
                or not 200 <= record["http_status"] < 300 or record["actual_format"] in ("UNKNOWN", "UNMEASURED")):
            raise ValueError("unverified_success")
        if check_content(dict(record, observations=list(record["observations"])), record["declared_extension"])["outcome"] != record["outcome"]:
            raise ValueError("document_outcome_inconsistent")
        if record["declared_extension"] != extension(candidate["printFileNm"]) or record["filename_actual_match"] != (record["actual_format"] == record["declared_extension"] and record["actual_format"] not in ("UNKNOWN", "OTHER") if record["actual_format"] != "UNMEASURED" else None):
            raise ValueError("document_extension_evidence_mismatch")
        output.append(record)
    return output


def checkpoint(root, manifest, rows, final=False):
    success = sum(r["outcome"] == "SUCCESS" for r in rows)
    remaining = 100 - len(rows)
    completed = final and not remaining
    prefix = f"{manifest['run_id']}-"
    parent = safe_path(root, "harness/workspace/checkpoints")
    parent.mkdir(parents=True, exist_ok=True)
    sequence = len(list(parent.glob(prefix + "*.md")))
    result = {"run_id": manifest["run_id"], "task": "Phase 0 Document Download Gate", "started_at": manifest["started_at"],
              "updated_at": phase0.now(), "total_target": 100, "completed_count": success, "success_count": success,
              "processed_count": len(rows), "failed_count": len(rows) - success, "remaining_count": remaining,
              "failed_items": [{"item_id": r["candidate"]["pblancId"], "stage": "document-download", "reason": r["outcome"],
                                "attempts": r["http_requests"], "evidence": r["metadata_path"], "sha256": r["sha256"]}
                               for r in rows if r["outcome"] != "SUCCESS"],
              "current_stage": "document-download", "last_processed_item": rows[-1]["candidate"]["pblancId"] if rows else None,
              "last_processed_pblancId": rows[-1]["candidate"]["pblancId"] if rows else None,
              "next_action": None if completed else "verify_evidence_then_resume_unprocessed_candidates",
              "resume_command": None if completed else f"python3 -B scripts/phase0_document_download.py download --profile dev --run-id {manifest['run_id']} --resume",
              "notes": ["1 item = 1 primary candidate; completed_count = SUCCESS; processed_count = success + failure",
                        "Finalized failures are not retried; all payload checksums verified before resume",
                        f"source_run_id={manifest['source_run_id']}; source_artifact_sha256={manifest['source_artifact_sha256']}",
                        "Checkpoint completed means run evidence finalized, not Gate GO or Human approval"],
              "status": "completed" if completed else "running"}
    path = parent / f"{prefix}{sequence:04}.md"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# Document Download Checkpoint\n\n```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```\n")
    return str(path.relative_to(root))


def metrics(manifest, rows):
    candidates = manifest["candidates"]
    successes = sum(r["outcome"] == "SUCCESS" for r in rows)
    outcomes = Counter(r["outcome"] for r in rows)
    urls = Counter(c["source_url"] for c in candidates if c["source_url"])
    hashes = Counter(r["sha256"] for r in rows if r["sha256"] and r["complete_body"] and r["stored_byte_size"] and r["http_status"] and 200 <= r["http_status"] < 300)
    complete = [r for r in rows if r["complete_body"] and r["stored_byte_size"] and r["http_status"] and 200 <= r["http_status"] < 300]
    sizes = [r["stored_byte_size"] for r in complete]
    identified = [r for r in rows if r["actual_format"] != "UNMEASURED"]
    pairing = [c["supplementary"] for c in candidates if all(v is not None for v in c["supplementary"].values())]
    mismatch = [c["pblancId"] for c in candidates if all(v is not None for v in c["supplementary"].values()) and c["supplementary"]["url_tokens"] != c["supplementary"]["filename_tokens"]]
    return {"target_documents": 100, "processed_candidates": len(rows), "attempted_downloads": sum(r["http_requests"] > 0 for r in rows),
            "http_requests": sum(r["http_requests"] for r in rows), "successful_downloads": successes,
            "download_success_rate": successes / 100, "outcome_denominator": 100,
            "outcome_counts": {o: outcomes[o] if rows else "UNMEASURED" for o in contract()["outcomes"]},
            "outcome_ratios": {o: outcomes[o] / 100 if rows else "UNMEASURED" for o in contract()["outcomes"]},
            "unprocessed_candidates": 100 - len(rows),
            "http_status_distribution": dict(Counter(str(r["http_status"]) for r in rows if r["http_status"] is not None)) if rows else "UNMEASURED",
            "redirected_document_count": sum(bool(r["redirect_statuses"]) for r in rows) if rows else "UNMEASURED",
            "redirect_count_distribution": dict(Counter(str(r["redirect_count"]) for r in rows)) if rows else "UNMEASURED",
            "url_quality": {"total": 100, "states": dict(Counter(c["url_state"] for c in candidates)),
                            "invalid_url_syntax": sum(c["url_state"] == "VALID" and not c["url_syntax_valid"] for c in candidates),
                            "local_url_policy_rejected": sum(c["url_syntax_valid"] and not c["url_allowed"] for c in candidates),
                            "unique_url": len(urls), "duplicate_url_extra_count": sum(n - 1 for n in urls.values()),
                            "duplicate_url_groups": [{"pblancIds": [c["pblancId"] for c in candidates if c["source_url"] == u], "count": n} for u, n in urls.items() if n > 1],
                            "host_distribution": dict(Counter(urlsplit(c["source_url"]).hostname for c in candidates if c["source_url"])),
                            "http_reachable_2xx": sum(r["http_status"] is not None and 200 <= r["http_status"] < 300 for r in rows) if rows else "UNMEASURED",
                            "http_unreachable_or_non_2xx": sum(r["http_requests"] > 0 and (r["http_status"] is None or not 200 <= r["http_status"] < 300) for r in rows) if rows else "UNMEASURED"},
            "file_size": {"denominator_complete_nonempty_2xx_bodies": len(sizes), "min": min(sizes) if sizes else "UNMEASURED",
                          "max": max(sizes) if sizes else "UNMEASURED", "average": statistics.mean(sizes) if sizes else "UNMEASURED",
                          "median": statistics.median(sizes) if sizes else "UNMEASURED"},
            "declared_extensions": dict(Counter(extension(c["printFileNm"]) for c in candidates)),
            "content_types": dict(Counter(r["content_type"] or "ABSENT" for r in rows if r["http_status"] is not None)) if rows else "UNMEASURED",
            "actual_formats": dict(Counter(r["actual_format"] for r in identified)) if identified else "UNMEASURED",
            "actual_format_measured_count": len(identified), "filename_actual_match_count": sum(r["filename_actual_match"] is True for r in rows),
            "filename_actual_match_rate_target": sum(r["filename_actual_match"] is True for r in rows) / 100 if rows else "UNMEASURED",
            "content_type_mismatch_count": sum("content_type_differs_from_identified_format" in r["observations"] for r in rows) if rows else "UNMEASURED",
            "final_host_distribution": dict(Counter(r["final_host"] for r in rows if r["final_host"])) if rows else "UNMEASURED",
            "duplicate_sha256_extra_count": sum(n - 1 for n in hashes.values()) if rows else "UNMEASURED",
            "duplicate_sha256_denominator": len(complete),
            "duplicate_sha256_groups": [{"sha256": h, "pblancIds": [r["candidate"]["pblancId"] for r in complete if r["sha256"] == h], "count": n} for h, n in hashes.items() if n > 1],
            "supplementary_pairing": {"denominator": len(pairing), "PAIR_COUNT_MATCH": len(pairing) - len(mismatch), "PAIR_COUNT_MISMATCH": len(mismatch), "mismatched_pblancIds": mismatch, "semantic_pairing": "UNCONFIRMED"},
            "primary_notice_hypothesis": "SUPPORTED_BY_DOWNLOAD_EVIDENCE" if successes == 100 else "WEAKENED_BY_DOWNLOAD_EVIDENCE" if len(rows) > successes else "UNCONFIRMED",
            "unmeasured": ["document_body_semantics", "PDF_HWP_HWPX_XLSX_text_parsing", "OCR", "complete_container_integrity", "long_term_URL_stability", "supplementary_download", "RAG_value"],
            "official_newest_first": "UNCONFIRMED", "gate_decision": "pending"}


def download(root, profile, identifier, environ, resume=False, fetch=None, stop_after=None, pause=time.sleep):
    root = Path(root).resolve()
    if profile != "dev":
        raise ValueError("document_profile_must_be_dev")
    phase0.run_id(identifier)
    frozen = plan(root)
    # 공개 문서는 인증이 필요 없다. dev key는 반사 검출에만 사용하고 요청·manifest에 전달하지 않는다.
    secret = probe.load_config(root, "dev", environ)["key"]
    if probe.credential_echo(json.dumps(frozen, ensure_ascii=False).encode(), secret):
        raise ValueError("credential_echo_source")
    folder = safe_path(root, f"data/downloaded/{identifier}")
    if resume:
        manifest = phase0.read_json(safe_path(root, f"data/downloaded/{identifier}/manifest.json"))
        if manifest["run_id"] != identifier or manifest["profile"] != "dev" or manifest["safety"] != contract() or any(manifest[k] != v for k, v in frozen.items()):
            raise ValueError("resume_source_mismatch")
    else:
        if folder.exists():
            raise ValueError("run_exists")
        folder.mkdir(parents=True)
        manifest = {"run_id": identifier, "profile": "dev", "started_at": phase0.now(), "safety": contract(), "evidence_kind": "SYNTHETIC_MOCK" if fetch else "LIVE_HTTP", **frozen}
        phase0.write_json(folder / "manifest.json", manifest)
    rows = records(root, manifest)
    done = {r["candidate"]["pblancId"] for r in rows}
    last_checkpoint = checkpoint(root, manifest, rows)
    interrupted = False
    try:
        for candidate in manifest["candidates"]:
            if candidate["pblancId"] in done:
                continue
            if stop_after is not None and len(rows) >= stop_after:
                break
            item_folder = safe_path(root, f"data/downloaded/{identifier}/{candidate['pblancId']}")
            item_folder.mkdir()
            started = phase0.now()
            result, raw = transfer(candidate["source_url"], secret, fetch, manifest["safety"])
            check_content(result, extension(candidate["printFileNm"]))
            result.update(run_id=identifier, candidate=candidate, declared_extension=extension(candidate["printFileNm"]),
                          started_at=started, completed_at=phase0.now(), stored_path=None, stored_byte_size=None, sha256=None,
                          metadata_path=str((item_folder / "metadata.json").relative_to(root)))
            if raw is not None:
                with (item_folder / "document.bin").open("xb") as stream:
                    stream.write(raw)
                result.update(stored_path=str((item_folder / "document.bin").relative_to(root)), stored_byte_size=len(raw), sha256=digest(raw))
            phase0.write_json(item_folder / "metadata.json", result)
            rows = records(root, manifest)
            if len(rows) % 10 == 0 or result["outcome"] != "SUCCESS":
                last_checkpoint = checkpoint(root, manifest, rows)
                print(f"PROGRESS: {len(rows)}/100; outcome={result['outcome']}", flush=True)
            if result["error"] == "interrupted_request":
                interrupted = True
                break
            if len(rows) < 100:
                pause(manifest["safety"]["pause_seconds"])
    except KeyboardInterrupt:
        interrupted = True
    rows = records(root, manifest)
    final = len(rows) == 100
    last_checkpoint = checkpoint(root, manifest, rows, final)
    ended = phase0.now()
    result = {"run": {"run_id": identifier, "profile": "dev", "source_run_id": manifest["source_run_id"], "evidence_kind": manifest["evidence_kind"],
                      "started_at": manifest["started_at"], "completed_at": ended if final else None, "updated_at": ended,
                      "elapsed_seconds": (datetime.fromisoformat(ended) - datetime.fromisoformat(manifest["started_at"])).total_seconds(),
                      "status": "COMPLETED" if final else "INTERRUPTED" if interrupted else "PARTIAL",
                      "checkpoint": last_checkpoint}, "metrics": metrics(manifest, rows)}
    sequence = len(list(folder.glob("summary-*.json")))
    phase0.write_json(folder / f"summary-{sequence:04}.json", result)
    return result


def analyze(root, identifier):
    phase0.run_id(identifier)
    manifest = phase0.read_json(safe_path(root, f"data/downloaded/{identifier}/manifest.json"))
    fresh = plan(root)
    if manifest["run_id"] != identifier or manifest["profile"] != "dev" or manifest["safety"] != contract() or any(manifest[k] != v for k, v in fresh.items()):
        raise ValueError("source_evidence_changed")
    rows = records(root, manifest)
    summaries = sorted(safe_path(root, f"data/downloaded/{identifier}").glob("summary-*.json"))
    if not summaries:
        raise ValueError("missing_run_summary")
    result = phase0.read_json(summaries[-1])
    if result["metrics"] != metrics(manifest, rows):
        raise ValueError("summary_metrics_changed")
    return result, rows


def render(result, rows):
    lines = ["# Phase 0 Document Download Gate Report", "", f"Evidence: {result['run']['evidence_kind']}; dev; source=api-quality-dev-20260928-01, 동일한 100 Item.",
             "", "비율의 기본 분모는 Target 100이다. 크기는 완전한 비어 있지 않은 HTTP 2xx body, 형식은 식별을 시도한 body를 별도 집계한다.",
             "", "Primary Notice Candidate의 본문 의미·Parsing·OCR·장기 URL 안정성은 UNMEASURED다. GO/DROP은 판단하지 않는다.",
             "", "## Run / Reproducible Metrics", "", "```json", json.dumps(result, ensure_ascii=False, indent=2), "```", "",
             "## Document Evidence", "", "| pblancId | HTTP | redirects | bytes stored | actual | outcome | SHA-256 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['candidate']['pblancId']} | {r['http_status']} | {r['redirect_count']} | {r['stored_byte_size']} | {r['actual_format']} | {r['outcome']} | {r['sha256']} |")
    lines += ["", "## URL / Supplementary Metadata Quality", "",
              "API VALID는 타입/nonblank였다. 이번 URL syntax / local host policy / 실제 HTTP 접속은 별도 측정이다.", "",
              "| URL field state | Count / target 100 |", "| --- | --- |"]
    for state in quality.contract()["field_states"]:
        lines.append(f"| {state} | {result['metrics']['url_quality']['states'].get(state, 0)} / 100 |")
    paired = [r["candidate"]["supplementary"] for r in rows if all(v is not None for v in r["candidate"]["supplementary"].values())]
    token_totals = {name: sum(p[name] for p in paired) if len(rows) == 100 else "UNMEASURED" for name in ("url_tokens", "filename_tokens")}
    lines += ["", "Supplementary token totals (전체 표본의 기록이 있을 때만 집계):", "", "```json",
              json.dumps(token_totals, ensure_ascii=False, indent=2), "```", "",
              "Count 일치는 의미상 positional pairing의 보장이 아니다. Supplementary HTTP 요청은 수행하지 않았다.", "",
              "Content-Type 차이는 Observation이다. application/octet-stream은 구체적 형식을 식별하지 못한다.", "",
              "각 행의 filename·Content-Type·final host·시각·source Raw/page/item reference는", f"`data/downloaded/{result['run']['run_id']}/<pblancId>/metadata.json`. 원본은 같은 디렉터리의 document.bin이다.", "",
              "## Recovery / Next Gate", "", "최신 Checkpoint와 manifest, 모든 metadata/hash를 검증하고 미처리 Candidate만 재개한다. 확정된 실패도 자동 재시도하지 않는다.",
              "고립 파일·변조 checksum을 발견하면 중단하고 사람이 Evidence를 확인한다. 기존 원본을 덮어쓰지 않는다.",
              "Parsing Gate는 별도 Task와 Human Review 후에 시작한다. 다운로드 가능 여부만으로 실제 본공고라는 의미를 보장하지 않는다.", ""]
    return "\n".join(lines)


def main(argv=None, root=ROOT, environ=None):
    parser = probe.SafeArgumentParser(description="Bounded dev document gate; no API collection or text parsing.")
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("download")
    live.add_argument("--profile", choices=("dev",), required=True)
    live.add_argument("--run-id", required=True)
    live.add_argument("--resume", action="store_true")
    offline = sub.add_parser("analyze")
    offline.add_argument("--run-id", required=True)
    offline.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    root = Path(root).resolve()
    try:
        if args.command == "download":
            result = download(root, args.profile, args.run_id, os.environ if environ is None else environ, args.resume)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["run"]["status"] == "COMPLETED" and result["metrics"]["successful_downloads"] == 100 else 1
        result, rows = analyze(root, args.run_id)
        output = root / args.output
        if output.parent != root / "harness/workspace/reports" or output.suffix != ".md" or output.parent.resolve() != output.parent:
            raise ValueError("report_output_boundary")
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render(result, rows))
        print("PASS: offline download evidence analysis; no HTTP")
        return 0
    except (ValueError, OSError, UnicodeError, KeyError, TypeError):
        print("FAIL: document configuration/evidence/output; no secret details emitted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
