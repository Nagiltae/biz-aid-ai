import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.config.settings import PipelineError, api_contract, credential_echo


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BizinfoClient:
    def __init__(self, config, root, transport=None):
        if config.profile != "dev":
            raise PipelineError("prod_api_access_forbidden")
        self.config = config
        self.spec = api_contract(root)
        if config.endpoint != self.spec["request"]["endpoint"]:
            raise PipelineError("unsupported_api_endpoint")
        self.transport = transport or self._get

    def _get(self, url):
        try:
            response = build_opener(NoRedirect()).open(Request(url, headers={"Accept": "application/json"}), timeout=self.spec["probe"]["timeout_seconds"])
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(self.spec["probe"]["max_response_bytes"] + 1)
            return response.code, raw

    def fetch_page(self, number, rows=20, identifier=None, explicit_negative=False):
        if type(number) is not int or type(rows) is not int or number < 1 or not 1 <= rows <= 100:
            raise PipelineError("invalid_pagination_request")
        if explicit_negative and not identifier:
            raise PipelineError("negative_probe_requires_identifier")
        params = {"dataType": "json", "pageNo": number, "numOfRows": rows, "serviceKey": self.config.key}
        if identifier is not None:
            params["pblancId"] = identifier
        url = self.config.endpoint + "?" + urlencode(params, quote_via=quote)
        def failed(outcome, status=None, code=None, message=None):
            return SourcePage(number, rows, (), None, outcome, status, code, message, False)
        if not self.config.key:
            return failed("TRANSPORT_ERROR")
        try:
            status, raw = self.transport(url)
        except (URLError, TimeoutError, OSError, HTTPException):
            # 네트워크 예외에 인증 URL이 포함될 수 있어 원문 예외를 결과에 넣지 않는다.
            return failed("TRANSPORT_ERROR")
        if (credential_echo(raw, self.config.key) or len(raw) > self.spec["probe"]["max_response_bytes"]):
            return failed("CONTRACT_ERROR", status)
        if status != 200:
            return failed("TRANSPORT_ERROR", status)
        try:
            def unique(pairs):
                result = {}
                for k, v in pairs:
                    if k in result:
                        raise ValueError("duplicate_key")
                    result[k] = v
                return result
            payload = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("invalid_constant")))
            header, body = payload["response"]["header"], payload["response"]["body"]
            code, message = header["resultCode"], header["resultMsg"]
            if not isinstance(code, str) or not isinstance(message, str) or not code.strip() or not message.strip():
                return failed("CONTRACT_ERROR", status)
            if code != self.spec["response"]["success_code"]:
                expected = self.spec["probe"]["negative_expectation"]
                if (explicit_negative and code == expected["resultCode"] and message == expected["resultMsg"]
                        and body["items"] == {} and type(body["numOfRows"]) is int and body["numOfRows"] == 0
                        and type(body["totalCount"]) is int and body["totalCount"] == 0 and type(body["pageNo"]) is int and body["pageNo"] == number):
                    return SourcePage(number, rows, (), 0, "EXPECTED_NO_DATA", status, code, message)
                return failed("API_ERROR", status, code, message)
            items = body["items"]["item"]
            if (not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
                    or any(type(body[n]) is not int for n in self.spec["response"]["pagination_fields"])
                    or body["totalCount"] < 0 or body["pageNo"] != number or body["numOfRows"] != rows or len(items) > rows):
                return failed("CONTRACT_ERROR", status, code, message)
            return SourcePage(number, rows, tuple(items), body["totalCount"], "SUCCESS", status, code, message)
        except (ValueError, KeyError, TypeError, UnicodeError):
            return failed("CONTRACT_ERROR", status)

    def scan_full(self, rows=20, max_pages=1000):
        if type(max_pages) is not int or not 1 <= max_pages <= 1000:
            raise PipelineError("invalid_full_scan_limit")
        pages, observed, terminated = [], 0, False
        for number in range(1, max_pages + 1):
            page = self.fetch_page(number, rows)
            pages.append(page)
            if page.outcome != "SUCCESS":
                break
            observed += len(page.items)
            if len(page.items) < rows or observed >= page.total_count:
                terminated = True
                break
        return SourceBatch(SyncScope.FULL, tuple(pages), "explicit full API pagination", terminated,
                           {"kind": "API_PAGINATION", "official_ordering": "UNCONFIRMED"})
