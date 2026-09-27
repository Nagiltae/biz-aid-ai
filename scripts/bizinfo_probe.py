#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

import phase0

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "contracts/external-api/bizinfo.contract.json"


class ProbeError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    # 인증키가 query에 있으므로 redirect로 다른 출처에 전달하지 않는다.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SafeArgumentParser(argparse.ArgumentParser):
    # 잘못 입력한 명령 인수에 인증키가 있어도 argparse 오류가 그 값을 출력하지 않게 한다.
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "invalid probe arguments\n")


def contract():
    return phase0.read_json(SPEC_PATH)


def load_config(root, profile, environ):
    if profile not in ("dev", "prod"):
        raise ProbeError("unsupported_profile")
    values = {}
    # Profile은 CLI의 명시적 선택이며 Branch·APP_PROFILE·다른 파일로 대체하면 환경 경계가 섞인다.
    path = root / f".env.{profile}"
    # 사용자 Secret 파일은 설정으로만 읽고 셸 실행·source·수정 없이 선택된 파일 하나만 사용한다.
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.strip().removeprefix("export ").partition("=")
            name = name.strip()
            if not separator or name not in {"BIZINFO_API_BASE_URL", "BIZINFO_SERVICE_KEY", "BIZINFO_DATA_TYPE"}:
                continue
            value = value.strip()
            if value.startswith(("'", '"')):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ProbeError("invalid_env_format")
                value = value[1:-1]
            values[name] = value
    values.update({name: environ[name] for name in
                   ("BIZINFO_API_BASE_URL", "BIZINFO_SERVICE_KEY", "BIZINFO_DATA_TYPE") if name in environ})
    spec = contract()
    endpoint = values.get("BIZINFO_API_BASE_URL", spec["request"]["endpoint"])
    data_type = values.get("BIZINFO_DATA_TYPE", spec["probe"]["dataType"])
    if endpoint != spec["request"]["endpoint"] or data_type != "json":
        raise ProbeError("unsupported_endpoint_or_data_type")
    key = unquote(values.get("BIZINFO_SERVICE_KEY", "").strip())
    if any(ord(char) < 32 for char in key):
        raise ProbeError("invalid_credential_format")
    return {"profile": profile, "endpoint": endpoint, "dataType": data_type, "key": key}


def validate_header(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
        raise ProbeError("invalid_response_envelope")
    header = payload["response"].get("header")
    if not isinstance(header, dict):
        raise ProbeError("invalid_header")
    if any(not isinstance(header.get(name), str) or not header[name].strip()
           for name in ("resultCode", "resultMsg")):
        raise ProbeError("invalid_header_fields")
    return header


def validate_envelope(payload):
    header = validate_header(payload)
    spec = contract()["response"]
    if header["resultCode"] != spec["success_code"]:
        raise ProbeError("api_error")
    body = payload["response"].get("body")
    if not isinstance(body, dict) or not isinstance(body.get("items"), dict):
        raise ProbeError("invalid_body_or_items")
    items = body["items"].get("item")
    if not isinstance(items, list):
        raise ProbeError("invalid_item_array")
    for name in spec["pagination_fields"]:
        if type(body.get(name)) is not int or body[name] < (0 if name == "totalCount" else 1):
            raise ProbeError("invalid_pagination_field")
    for item in items:
        if not isinstance(item, dict):
            raise ProbeError("invalid_item_object")
    return payload


def validate_response(payload):
    validate_envelope(payload)
    spec = contract()["response"]
    for item in payload["response"]["body"]["items"]["item"]:
        for name, field in spec["item_fields"].items():
            if name not in item:
                if field["required_for_probe"]:
                    raise ProbeError("missing_identifier")
                continue
            value = item[name]
            if value is None and field["observed_nullable"]:
                continue
            if field["type"] == "string" and not isinstance(value, str):
                raise ProbeError("invalid_observed_item_type")
            if field["type"] == "integer" and type(value) is not int:
                raise ProbeError("invalid_observed_item_type")
            if field["required_for_probe"] and not value.strip():
                raise ProbeError("blank_identifier")
    # 비정형 기간·HTML·첨부 연결값·미지 field를 그대로 반환해 Raw에서 정보가 사라지지 않게 한다.
    return payload


def ordering(values):
    if len(values) < 2:
        return "insufficient_observations"
    try:
        parsed = [datetime.strptime(value, "%Y-%m-%d %H:%M:%S") for value in values]
    except (TypeError, ValueError):
        return "unconfirmed_timestamp_format"
    if len(set(parsed)) == 1:
        return "observed_equal"
    if all(left >= right for left, right in zip(parsed, parsed[1:])):
        return "observed_descending"
    if all(left <= right for left, right in zip(parsed, parsed[1:])):
        return "observed_ascending"
    return "observed_mixed"


def credential_echo(raw, key):
    if not key:
        return False
    text = raw.decode("utf-8", errors="replace")
    candidates = [text, unquote(text)]
    try:
        candidates.append(json.dumps(json.loads(raw), ensure_ascii=False))
    except (ValueError, UnicodeError, RecursionError):
        pass
    return any(key in value or quote(key, safe="") in value for value in candidates)


def http_get(url):
    spec = contract()["probe"]
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    opener = build_opener(NoRedirect())
    try:
        response = opener.open(request, timeout=spec["timeout_seconds"])
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(spec["max_response_bytes"] + 1)
        if len(raw) > spec["max_response_bytes"]:
            raise ProbeError("response_too_large")
        return response.code, raw


def request_snapshot(config, name, params, identifier, root, fetch):
    query = urlencode({**params, "serviceKey": config["key"]}, quote_via=quote)
    url = config["endpoint"] + "?" + query
    result = {
        "name": name, "requested": params, "requested_at": phase0.now(),
        "http_status": None, "status": "failed", "resultCode": None, "resultMsg": None,
        "outcome": "TRANSPORT_ERROR", "expected_outcome": "SUCCESS",
        "item_count": None, "pageNo": None, "numOfRows": None, "totalCount": None,
        "pblancIds": [], "creatPnttm": [], "ordering": "unconfirmed",
        "pagination_echo_matches": None, "raw_snapshot": None, "error": None,
    }
    try:
        result["http_status"], raw = fetch(url)
    except (URLError, TimeoutError, OSError, HTTPException):
        # HTTP 예외 문자열에는 인증 URL이 들어갈 수 있으므로 고정된 오류 분류만 기록한다.
        result["error"] = "network_error"
        return result, None
    except ProbeError as error:
        result["error"] = "response_too_large" if str(error) == "response_too_large" else "transport_error"
        return result, None
    if not raw:
        result["error"] = "empty_response"
        result["outcome"] = "CONTRACT_ERROR"
        return result, None
    # 인증키가 반사된 응답은 원문을 변조하지 않고 저장을 거부해 비밀과 Raw 무결성을 함께 지킨다.
    if credential_echo(raw, config["key"]):
        result["error"] = "credential_echo_response_not_preserved"
        result["outcome"] = "CONTRACT_ERROR"
        return result, None
    media_type = "application/xml" if raw.lstrip().startswith(b"<") else "application/json"
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "response"
        source.write_bytes(raw)
        metadata = phase0.snapshot(source, root / "data/raw", identifier, media_type, phase0.now())
    result["raw_snapshot"] = str(metadata.relative_to(root))
    if not 200 <= result["http_status"] < 300:
        result["error"] = "http_error"
        return result, None
    result["outcome"] = "CONTRACT_ERROR"
    try:
        payload = json.loads(raw, object_pairs_hook=phase0.unique_object, parse_constant=phase0.reject_constant)
        header = validate_header(payload)
        result.update({key: header[key] for key in ("resultCode", "resultMsg")})
        return result, payload
    except ProbeError as error:
        result["error"] = str(error)
    except (ValueError, UnicodeError, RecursionError):
        result["error"] = "invalid_json"
    return result, None


def expected_no_data(payload, params):
    body = payload["response"].get("body")
    return (isinstance(body, dict) and body.get("items") == {}
            and type(body.get("pageNo")) is int and body["pageNo"] == params["pageNo"]
            and type(body.get("numOfRows")) is int and body["numOfRows"] == 0
            and type(body.get("totalCount")) is int and body["totalCount"] == 0)


def probe_one(config, name, params, identifier, root, fetch, negative=False):
    result, payload = request_snapshot(config, name, params, identifier, root, fetch)
    result["expected_outcome"] = "EXPECTED_NO_DATA" if negative else "SUCCESS"
    if payload is None:
        return result
    code = result["resultCode"]
    if code != contract()["response"]["success_code"]:
        # 같은 no-data라도 정상 페이지와 known ID에서는 실패이며 명시적 음성 계획에서만 기대 결과다.
        explicit_negative = (negative and name == "presumed_missing_id"
                             and params.get("pblancId") == contract()["probe"]["presumed_missing_id"])
        if explicit_negative and result["http_status"] == 200 and code == "03" and result["resultMsg"] == "NODATA_ERROR":
            if not expected_no_data(payload, params):
                result["error"] = "invalid_expected_no_data_envelope"
                return result
            body = payload["response"]["body"]
            result.update({key: body[key] for key in ("pageNo", "numOfRows", "totalCount")})
            result.update(outcome="EXPECTED_NO_DATA", status="expected_no_data", item_count=0,
                          pagination_echo_matches=None, error=None)
            return result
        result.update(outcome="API_ERROR", error="api_error")
        return result
    try:
        validate_response(payload)
        body = payload["response"]["body"]
        items = body["items"]["item"]
        result.update({key: body[key] for key in ("pageNo", "numOfRows", "totalCount")})
        result["item_count"] = len(items)
        result["pblancIds"] = [item["pblancId"] for item in items]
        result["creatPnttm"] = [item.get("creatPnttm") for item in items]
        result["ordering"] = ordering(result["creatPnttm"])
        result["pagination_echo_matches"] = all(body[key] == params[key] for key in ("pageNo", "numOfRows"))
        result["status"] = "observed" if 200 <= result["http_status"] < 300 else "failed"
        result["outcome"] = "SUCCESS"
        if not result["pagination_echo_matches"]:
            result["status"], result["error"] = "failed", "pagination_echo_mismatch"
            result["outcome"] = "CONTRACT_ERROR"
    except ProbeError as error:
        result["error"] = str(error)
        result["outcome"] = "CONTRACT_ERROR"
    except (ValueError, UnicodeError, RecursionError):
        result["error"] = "invalid_json"
    return result


def comparisons(observations):
    pages = [item for item in observations if item["name"] in ("page1", "page2")]
    ready = len(pages) == 2 and all(item["status"] == "observed" for item in pages)
    page_summary = {"status": "observed" if ready else "unconfirmed"}
    if ready:
        first, second = pages
        page_summary.update({
            "item_counts": [item["item_count"] for item in pages],
            "within_page_duplicate_ids": [
                sorted({value for value in item["pblancIds"] if item["pblancIds"].count(value) > 1})
                for item in pages
            ],
            "cross_page_duplicate_ids": sorted(set(first["pblancIds"]) & set(second["pblancIds"])),
            "totalCount_consistent": first["totalCount"] == second["totalCount"],
            "combined_creatPnttm_ordering": ordering(first["creatPnttm"] + second["creatPnttm"]),
            "ordering_guarantee": "unconfirmed",
        })
    identifier_summary = []
    for item in observations:
        if item["name"] in ("known_id", "presumed_missing_id"):
            identifier_summary.append({
                "name": item["name"], "status": item["status"], "outcome": item["outcome"],
                "requested_pblancId": item["requested"]["pblancId"], "item_count": item["item_count"],
                "returned_ids": item["pblancIds"],
                "all_returned_ids_match": (
                    all(value == item["requested"]["pblancId"] for value in item["pblancIds"])
                    if item["status"] == "observed" and item["pblancIds"] else None
                ),
                "empty_observed": (item["item_count"] == 0
                                   if item["outcome"] in ("SUCCESS", "EXPECTED_NO_DATA") else None),
                "single_exact_match": (
                    item["pblancIds"] == [item["requested"]["pblancId"]]
                    if item["status"] == "observed" else None
                ),
            })
    return {"pagination": page_summary, "identifiers": identifier_summary, "recent_100_rule": "unconfirmed"}


def run_probe(root, profile, identifier, mode, environ, fetch=None):
    root = Path(root).resolve()
    phase0.run_id(identifier)
    spec = contract()["probe"]
    plan = []
    if mode in ("all", "pages"):
        plan += [(f"page{page}", {"dataType": "json", "pageNo": page, "numOfRows": spec["numOfRows"]})
                 for page in spec["page_numbers"]]
    if mode in ("all", "identifier"):
        plan += [(name, {"dataType": "json", "pageNo": 1, "numOfRows": spec["numOfRows"], "pblancId": value})
                 for name, value in (("known_id", spec["known_id"]), ("presumed_missing_id", spec["presumed_missing_id"]))]
    if not plan or len(plan) > spec["request_limit"]:
        raise ProbeError("unsupported_probe_plan")
    output = root / f"harness/workspace/artifacts/bizinfo-probe-{identifier}.json"
    if output.exists() or output.is_symlink():
        raise ProbeError("output_exists")
    if output.parent.resolve() != output.parent:
        raise ProbeError("unsafe_output_directory")
    # 일부 실행 후 재호출에서 원문이 충돌하지 않도록 모든 저장 경로를 요청 전에 확인한다.
    for name, _ in plan:
        phase0.run_id(f"{identifier}-{name}")
        path = root / f"data/raw/{identifier}-{name}"
        if path.exists() or path.is_symlink() or (root / "data/raw").resolve() != root / "data/raw":
            raise ProbeError("raw_output_exists_or_unsafe")
    config = load_config(root, profile, environ)
    report = {
        "run_id": identifier, "created_at": phase0.now(), "mode": mode, "profile": profile,
        "endpoint": config["endpoint"], "execution": "not_run", "reason": "credential_missing",
        "observations": [], "analysis": comparisons([]),
    }
    if config["key"]:
        report["observations"] = [
            probe_one(config, name, params, f"{identifier}-{name}", root, fetch or http_get,
                      negative=name == "presumed_missing_id") for name, params in plan
        ]
        report["execution"] = "completed"
        report["reason"] = None
        report["analysis"] = comparisons(report["observations"])
    phase0.write_json(output, report)
    return report


def main(argv=None, root=ROOT, environ=None):
    parser = SafeArgumentParser(description="Local-only Bizinfo contract probe; never invoked by CI.")
    parser.add_argument("--profile", choices=("dev", "prod"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=("all", "pages", "identifier"), default="all")
    args = parser.parse_args(argv)
    try:
        report = run_probe(root, args.profile, args.run_id, args.mode, os.environ if environ is None else environ)
    except (ProbeError, ValueError, OSError, UnicodeError):
        print("FAIL: probe configuration or output; no credential details emitted", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["execution"] == "not_run":
        return 3
    return 0 if all(item["outcome"] == item["expected_outcome"] for item in report["observations"]) else 1


if __name__ == "__main__":
    sys.exit(main())
