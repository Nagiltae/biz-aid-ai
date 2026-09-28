from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from biz_aid_pipeline.config.settings import credential_echo
from biz_aid_pipeline.documents.formats import actual_format, html_response


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def public_url(value, spec):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value)
        return (value == value.strip() and not any(character.isspace() or ord(character) < 32 for character in value)
                and parsed.scheme == spec["allowed_scheme"] and parsed.hostname in spec["allowed_hosts"]
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and not parsed.fragment and bool(parsed.path)
                and all(name.lower() in ("atchfileid", "filesn") for name, _ in parse_qsl(parsed.query)))
    except ValueError:
        return False


def open_document(request, timeout):
    # 공개 문서 요청에는 proxy·cookie·인증 handler를 추가하지 않는다.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        return opener.open(request, timeout=timeout)
    except HTTPError as error:
        return error


def transfer(url, secret, spec, fetch=None):
    result = {"http_status": None, "http_requests": 0, "redirect_count": 0, "final_host": None,
              "content_type": None, "detected_format": "UNKNOWN", "invalid_response": False,
              "failure_category": "URL_POLICY_ERROR", "complete_body": False}
    current, seen = url, set()
    while True:
        if not public_url(current, spec) or credential_echo(current.encode(), secret):
            result["failure_category"] = "REDIRECT_ERROR" if seen else "URL_POLICY_ERROR"
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
                    location = response.headers.get("Location")
                    if not location or result["redirect_count"] >= spec["max_redirects"]:
                        result["failure_category"] = "REDIRECT_ERROR"
                        return result, None
                    following = urljoin(current, location)
                    if following in seen:
                        result["failure_category"] = "REDIRECT_ERROR"
                        return result, None
                    current = following
                    result["redirect_count"] += 1
                    continue
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() or None
                if credential_echo(str(content_type).encode(), secret):
                    result["failure_category"] = "SECURITY_REJECTED"
                    return result, None
                result["content_type"] = content_type
                chunks, received = [], 0
                # Content-Length를 신뢰하지 않고 실제 stream을 최대 byte+1에서 중단한다.
                while received <= spec["max_file_bytes"]:
                    chunk = response.read(min(65536, spec["max_file_bytes"] + 1 - received))
                    if not chunk:
                        result["complete_body"] = True
                        break
                    chunks.append(chunk)
                    received += len(chunk)
                raw = b"".join(chunks)
                if credential_echo(raw, secret):
                    result["failure_category"] = "SECURITY_REJECTED"
                    return result, None
                if not 200 <= status < 300:
                    result["failure_category"] = "HTTP_ERROR"
                elif not result["complete_body"]:
                    result["failure_category"] = "SIZE_LIMIT_EXCEEDED"
                    raw = raw[:spec["max_file_bytes"]]
                elif not raw:
                    result["failure_category"] = "EMPTY_FILE"
                else:
                    result["detected_format"] = actual_format(raw)
                    result["invalid_response"] = html_response(raw)
                    result["failure_category"] = "INVALID_RESPONSE" if result["invalid_response"] else None
                return result, raw
        except KeyboardInterrupt:
            raise
        except (URLError, TimeoutError, OSError, HTTPException):
            result["failure_category"] = "TRANSPORT_ERROR"
            return result, None
