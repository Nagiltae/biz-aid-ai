#!/usr/bin/env python3
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import bizinfo_probe as probe
import phase0

ROOT = Path(__file__).resolve().parents[1]


def contract():
    return phase0.read_json(ROOT / "contracts/schemas/phase0-api-quality.contract.json")


def field_state(item, name):
    if name not in item:
        return "MISSING"
    value = item[name]
    if value is None:
        return "NULL"
    if isinstance(value, str) and not value.strip():
        return "BLANK"
    observed = probe.contract()["response"]["item_fields"][name]["type"]
    valid = isinstance(value, str) if observed == "string" else type(value) is int
    return "VALID" if valid else "INVALID"


def period_category(item):
    state = field_state(item, "reqstBeginEndDe")
    if state in ("MISSING", "NULL", "BLANK"):
        return "MISSING"
    if state == "INVALID":
        return "INVALID"
    value = item["reqstBeginEndDe"].strip()
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", value)
    if not match:
        return "FREE_TEXT"
    # 품질 분류에만 달력 유효성을 확인하며 서비스 날짜나 Raw field를 변경하지 않는다.
    try:
        start, end = (date.fromisoformat(part) for part in match.groups())
        return "DATE_RANGE" if start <= end else "INVALID"
    except ValueError:
        return "INVALID"


def extension(filename):
    suffix = Path(filename.strip()).suffix.lstrip(".").upper()
    if not suffix:
        return "UNKNOWN"
    return suffix if suffix in ("PDF", "HWP", "HWPX", "ZIP") else "OTHER"


def distribution(counter, labels, denominator):
    # 분모가 없을 때 0%를 만들면 미수집을 품질 측정으로 오인하므로 null과 UNMEASURED를 쓴다.
    return {"status": "MEASURED" if denominator else "UNMEASURED", "denominator": denominator,
            "counts": {label: counter[label] if denominator else None for label in labels},
            "ratios": {label: counter[label] / denominator if denominator else None for label in labels}}


def raw_items(root, identifier, page):
    reference = f"data/raw/{identifier}-page{page['requested']['pageNo']}/metadata.json"
    if page["raw_snapshot"] != reference:
        raise probe.ProbeError("unexpected_raw_reference")
    path = root / reference
    if path.is_symlink() or path.resolve() != path:
        raise probe.ProbeError("unsafe_raw_reference")
    metadata = phase0.verify_snapshot(path)
    if metadata["sha256"] != page["sha256"] or metadata["run_id"] != f"{identifier}-page{page['requested']['pageNo']}":
        raise probe.ProbeError("run_raw_checksum_mismatch")
    payload = phase0.read_json(path.parent / metadata["raw_path"])
    probe.validate_envelope(payload)
    body = payload["response"]["body"]
    if (body["pageNo"] != page["requested"]["pageNo"] or body["numOfRows"] != 20
            or len(body["items"]["item"]) != page["item_count"] or body["totalCount"] != page["totalCount"]):
        raise probe.ProbeError("run_raw_pagination_mismatch")
    return body["items"]["item"]


def analyze(run, root):
    spec = contract()
    phase0.run_id(run["run_id"])
    if (run["profile"] != "dev" or run["requested_pages"] != spec["pages"]
            or run["requested_rows_per_page"] != spec["rows_per_page"]):
        raise probe.ProbeError("unsupported_quality_run")
    rows = []
    by_page = {}
    for page in run["pages"]:
        number = page["requested"]["pageNo"]
        if number not in spec["pages"] or number in by_page:
            raise probe.ProbeError("unexpected_quality_page")
        by_page[number] = []
        if page["outcome"] == "SUCCESS":
            items = raw_items(root, run["run_id"], page)
            by_page[number] = items
            rows += [(number, index, item) for index, item in enumerate(items)]
    size = len(rows)
    fields = {}
    exceptions = []
    for name in dict.fromkeys(spec["major_fields"] + spec["attachment_fields"]):
        counts = Counter(field_state(item, name) for _, _, item in rows)
        fields[name] = distribution(counts, spec["field_states"], size)
        for number, index, item in rows:
            state = field_state(item, name)
            if state != "VALID":
                exceptions.append({"page": number, "item_index": index, "field": name, "state": state})
    positions = defaultdict(list)
    for number, index, item in rows:
        if field_state(item, "pblancId") == "VALID":
            positions[item["pblancId"]].append({"page": number, "item_index": index})
    duplicates = [{"pblancId": name, "count": len(locations), "locations": locations}
                  for name, locations in sorted(positions.items()) if len(locations) > 1]
    periods = Counter(period_category(item) for _, _, item in rows)
    period_missing = Counter(field_state(item, "reqstBeginEndDe") for _, _, item in rows
                             if field_state(item, "reqstBeginEndDe") in ("MISSING", "NULL", "BLANK"))
    extensions = {}
    for name in ("printFileNm", "fileNm"):
        # @는 파일명 통계에만 사용하며 URL과의 positional pairing이나 첨부 역할을 확정하지 않는다.
        tokens = [token for _, _, item in rows if field_state(item, name) == "VALID" for token in item[name].split("@")]
        extensions[name] = distribution(Counter(extension(token) for token in tokens), spec["extension_categories"], len(tokens))
    boundaries = []
    for left, right in zip(spec["pages"], spec["pages"][1:]):
        first, second = by_page.get(left), by_page.get(right)
        order = probe.ordering([first[-1].get("creatPnttm"), second[0].get("creatPnttm")]) if first and second else "UNMEASURED"
        boundaries.append({"left_page": left, "right_page": right, "ordering": order})
    success = [p for p in run["pages"] if p["outcome"] == "SUCCESS"]
    totals = [p["totalCount"] for p in success]
    keyword_counts = {word: sum(field_state(item, "printFileNm") == "VALID" and word in item["printFileNm"]
                               for _, _, item in rows) if size else None for word in ("공고", "공고문", "안내문")}
    both = sum(all(field_state(item, name) == "VALID" for name in spec["attachment_fields"]) for _, _, item in rows)
    ids = fields["pblancId"]
    return {
        "sample_definition": spec["sample_definition"], "sample_target": spec["sample_target"], "actual_items": size,
        "page_request_success": distribution(Counter(SUCCESS=len(success), FAILURE=len(run["failed_pages"])),
                                               ["SUCCESS", "FAILURE"], len(run["pages"])),
        "pblancId": {"status": "MEASURED" if size else "UNMEASURED", "unique_count": len(positions) if size else None,
                     "duplicate_extra_count": sum(d["count"] - 1 for d in duplicates) if size else None,
                     "duplicated_id_count": len(duplicates) if size else None, "duplicates": duplicates,
                     "key_presence_rate": (size - ids["counts"]["MISSING"]) / size if size else None,
                     "usable_id_rate": ids["ratios"]["VALID"], "states": ids},
        "fields": fields, "application_period": distribution(periods, spec["period_categories"], size),
        "period_unavailable_reasons": {s: period_missing[s] if size else None for s in ("MISSING", "NULL", "BLANK")},
        "attachment_metadata": {name: fields[name] for name in spec["attachment_fields"]},
        "filename_extensions": extensions,
        "pagination": {"observed_total_counts": totals, "totalCount_changed": len(set(totals)) > 1 if totals else None,
                       "missing_pages": [n for n in spec["pages"] if n not in run["successful_pages"]],
                       "item_count_mismatches": [{"page": p["requested"]["pageNo"], "received": p["item_count"]}
                                                 for p in success if p["item_count"] != spec["rows_per_page"]]},
        "ordering": {"per_page": [{"page": n, "ordering": probe.ordering([i.get("creatPnttm") for i in items])
                                   if items else "UNMEASURED"} for n, items in sorted(by_page.items())],
                     "boundaries": boundaries, "all_received": probe.ordering([i.get("creatPnttm") for _, _, i in rows])
                     if size else "UNMEASURED", "guarantee": "UNCONFIRMED", "complete_sample": size == spec["sample_target"]},
        "primary_notice_hypothesis": {"status": "CANDIDATE_UNCONFIRMED", "denominator": size,
                                      "print_url_and_name_valid": sum(all(field_state(i, f) == "VALID"
                                      for f in ("printFlpthNm", "printFileNm")) for _, _, i in rows) if size else None,
                                      "print_and_supplement_both_valid": both if size else None,
                                      "overlapping_filename_keyword_counts": keyword_counts},
        "exceptions": exceptions + [{"type": "DUPLICATE_ID", **d} for d in duplicates]
                      + [{"type": "PAGE_FAILURE", "page": p} for p in run["failed_pages"]]
                      + [{"type": "PERIOD_INVALID", "page": n, "item_index": index}
                         for n, index, item in rows if period_category(item) == "INVALID"],
        "unmeasured": ["document_download", "parser", "URL_reachability", "field_semantic_validity", "RAG_value"],
        "gate_decision": "pending",
    }


def collect(root, profile, identifier, environ, fetch=None):
    root = Path(root).resolve()
    if profile != "dev":
        raise probe.ProbeError("quality_profile_must_be_dev")
    phase0.run_id(identifier)
    spec = contract()
    output = root / f"harness/workspace/artifacts/codex/phase0-api-quality/bizinfo-quality-{identifier}.json"
    if output.exists() or output.is_symlink() or output.parent.resolve() != output.parent:
        raise probe.ProbeError("quality_output_exists_or_unsafe")
    for number in spec["pages"]:
        suffix = f"{identifier}-page{number}"
        phase0.run_id(suffix)
        path = root / "data/raw" / suffix
        if path.exists() or path.is_symlink() or (root / "data/raw").resolve() != root / "data/raw":
            raise probe.ProbeError("quality_raw_exists_or_unsafe")
    config = probe.load_config(root, "dev", environ)
    run = {"run_id": identifier, "profile": "dev", "started_at": phase0.now(), "completed_at": None,
           "requested_pages": spec["pages"], "requested_rows_per_page": spec["rows_per_page"],
           "successful_pages": [], "failed_pages": [], "total_items_received": 0,
           "unique_pblanc_ids": None, "duplicate_pblanc_ids": None, "observed_total_counts": [],
           "collection_status": "NOT_RUN", "http_requests_attempted": 0, "pages": [],
           "next_action": "provide_dev_credential_then_use_new_run_id"}
    if config["key"]:
        for number in spec["pages"]:
            params = {"dataType": "json", "pageNo": number, "numOfRows": spec["rows_per_page"]}
            page, payload = probe.request_snapshot(config, f"page{number}", params, f"{identifier}-page{number}", root, fetch or probe.http_get)
            run["http_requests_attempted"] += 1
            if payload is not None:
                try:
                    # 품질 이상 행을 탈락시키면 null·누락 비율이 왜곡되므로 Envelope만 검사하고 field는 별도 측정한다.
                    probe.validate_envelope(payload)
                    body = payload["response"]["body"]
                    page.update({name: body[name] for name in ("pageNo", "numOfRows", "totalCount")})
                    page["item_count"] = len(body["items"]["item"])
                    page["pagination_echo_matches"] = all(body[name] == params[name] for name in ("pageNo", "numOfRows"))
                    if not page["pagination_echo_matches"] or page["item_count"] > spec["rows_per_page"]:
                        raise probe.ProbeError("quality_pagination_or_size_mismatch")
                    page.update(outcome="SUCCESS", status="observed", error=None)
                except probe.ProbeError as error:
                    page.update(outcome="API_ERROR" if str(error) == "api_error" else "CONTRACT_ERROR", error=str(error))
            page["sha256"] = None
            page["collected_at"] = None
            if page["raw_snapshot"]:
                metadata = phase0.verify_snapshot(root / page["raw_snapshot"])
                page.update(sha256=metadata["sha256"], collected_at=metadata["collected_at"])
            run["pages"].append(page)
            run["successful_pages" if page["outcome"] == "SUCCESS" else "failed_pages"].append(number)
    run["completed_at"] = phase0.now()
    metrics = analyze(run, root)
    run.update(total_items_received=metrics["actual_items"], unique_pblanc_ids=metrics["pblancId"]["unique_count"],
               duplicate_pblanc_ids=metrics["pblancId"]["duplicates"], observed_total_counts=metrics["pagination"]["observed_total_counts"])
    if config["key"]:
        run["collection_status"] = ("PARTIAL_FAILED" if run["failed_pages"] and run["successful_pages"] else
                                    "FAILED" if run["failed_pages"] else "COMPLETED" if metrics["actual_items"] == spec["sample_target"] else "INCOMPLETE")
        run["next_action"] = "review_quality_evidence" if run["collection_status"] == "COMPLETED" else "review_pages_and_preserve_raw_before_authorizing_new_run"
    result = {"run": run, "metrics": metrics}
    phase0.write_json(output, result)
    return result


def render(result):
    run, m = result["run"], result["metrics"]
    lines = ["# Phase 0 API Data Quality Report", "", f"Run: {run['run_id']} / Profile: {run['profile']}", "",
             f"표본: {m['sample_definition']}. 공식 최신순 보장은 UNCONFIRMED.", "",
             f"Started: {run['started_at']} / Completed: {run['completed_at']}", "",
             f"Sample Target: {m['sample_target']} / Actual Items: {m['actual_items']} / Status: {run['collection_status']}", "",
             f"HTTP requests: {run['http_requests_attempted']} / Successful pages: {run['successful_pages']} / Failed pages: {run['failed_pages']}", "",
             f"pblancId unique: {m['pblancId']['unique_count']} / duplicate extra: {m['pblancId']['duplicate_extra_count']}", "",
             "모든 품질 비율의 분모는 수집된 성공 Envelope의 실제 Item 수다. 중복 행을 제거하지 않는다.", "",
             "VALID는 관찰 타입과 nonblank 검사이며 URL 접속·날짜 의미·기관 / 대상 의미 검증은 UNMEASURED다.", "",
             "## Page / Raw Evidence", "", "| Page | HTTP | Code / Message | Echo page / rows | Items | totalCount | Outcome |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for p in run["pages"]:
        lines.append(f"| {p['requested']['pageNo']} | {p['http_status']} | {p['resultCode']} / {p['resultMsg']} | {p['pageNo']} / {p['numOfRows']} | {p['item_count']} | {p['totalCount']} | {p['outcome']} |")
    lines += ["", "## Field Quality", "", "상태별 Count / Ratio를 기록한다. NULL / BLANK / MISSING을 분리한다.", "",
              "| Field | VALID | MISSING | NULL | BLANK | INVALID |", "| --- | --- | --- | --- | --- | --- |"]
    for name, field in m["fields"].items():
        cells = [f"{field['counts'][s]} / {field['ratios'][s]}" for s in contract()["field_states"]]
        lines.append("| " + name + " | " + " | ".join(cells) + " |")
    lines += ["", "## Reproducible Measurements", "", "아래 JSON은 Run / Raw checksum에서 재현한 요약이며 API 원문이나 Secret을 포함하지 않는다.", "", "```json",
              json.dumps(m, ensure_ascii=False, indent=2), "```", "", "## Raw Metadata / Recovery", ""]
    for p in run["pages"]:
        lines.append(f"- page {p['requested']['pageNo']}: {p['raw_snapshot']}; SHA-256={p['sha256']}; collected_at={p['collected_at']}")
    lines += ["", f"Next action: {run['next_action']}. 기존 run-id / Raw를 덮어쓰거나 자동 재시도하지 않는다.", "",
              "print* / flpth*는 역할 후보다. 파일명 키워드 count는 중복 가능하며 확장자 분모는 @로 분리한 파일명 token 수다.", "",
              "공고문 다운로드·Parser·DB·AI·RAG는 UNMEASURED이며 GO / DROP은 판단하지 않는다.", ""]
    return "\n".join(lines)


def main(argv=None, root=ROOT, environ=None):
    parser = probe.SafeArgumentParser(description="Bounded Phase 0 API quality batch; offline analysis; no downloads.")
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("collect")
    live.add_argument("--profile", choices=("dev",), required=True)
    live.add_argument("--run-id", required=True)
    offline = sub.add_parser("analyze")
    offline.add_argument("--run-id", required=True)
    offline.add_argument("--output", required=True)
    offline.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    root = Path(root).resolve()
    try:
        if args.command == "collect":
            result = collect(root, args.profile, args.run_id, os.environ if environ is None else environ)
            print(json.dumps({"run": result["run"], "quality_artifact": f"harness/workspace/artifacts/codex/phase0-api-quality/bizinfo-quality-{args.run_id}.json"}, ensure_ascii=False, indent=2))
            return 3 if result["run"]["collection_status"] == "NOT_RUN" else 0 if result["run"]["collection_status"] == "COMPLETED" else 1
        phase0.run_id(args.run_id)
        result = phase0.read_json(root / f"harness/workspace/artifacts/codex/phase0-api-quality/bizinfo-quality-{args.run_id}.json")
        if result["run"]["run_id"] != args.run_id:
            raise probe.ProbeError("run_id_mismatch")
        result["metrics"] = analyze(result["run"], root)
        output = root / args.output
        expected_parent = root / ("harness/workspace/reports/codex" if args.markdown else "harness/workspace/artifacts/codex/phase0-api-quality")
        if output.parent.resolve() != expected_parent or output.suffix != (".md" if args.markdown else ".json"):
            raise probe.ProbeError("quality_output_boundary")
        if args.markdown:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(render(result))
        else:
            phase0.write_json(output, result)
        print("PASS: offline quality analysis; no HTTP")
        return 0
    except (ValueError, OSError, UnicodeError, KeyError, TypeError):
        print("FAIL: quality configuration/evidence/output; no credential details emitted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
