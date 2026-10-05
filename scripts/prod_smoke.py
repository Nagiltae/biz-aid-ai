"""배포 후 최소 연결 점검. 실패 위치와 비밀값을 가린 응답 앞부분만 출력한다."""
import json
import re
import sys
import time

from urllib.request import Request, urlopen
from urllib.parse import urlparse
from urllib.error import HTTPError


def body_preview(raw, token=None):
    # BOUNDARY: 성공 응답의 토큰도 오류 응답에 반사될 수 있어 자르기 전에 전체 문자열에서 가린다.
    if token:
        raw = raw.replace(token, "[REDACTED]")
    raw = re.sub(r"(?im)^(authorization|cookie|set-cookie)\s*:[^\r\n]*", r"\1: [REDACTED]", raw)
    raw = re.sub(r"(?i)Bearer\s+[^\s\"',}]+", "Bearer [REDACTED]", raw)
    sensitive = r"(?:[\w-]*(?:token|password|secret|api[_-]?key|credential)[\w-]*|authorization|cookie|set-cookie)"
    raw = re.sub(r'(?i)(["\']?' + sensitive + r'["\']?\s*[:=]\s*)(?:"[^"\n]*(?:"|$)|\'[^\'\n]*(?:\'|$)|[^\s,}\n]+)',
                 r'\1"[REDACTED]"', raw)
    raw = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", raw)
    raw = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[REDACTED]", raw)
    return raw[:300]


class SmokeFailure(RuntimeError):
    def __init__(self, stage, url, status, raw, reason, token=None):
        self.details = {"status": "FAIL", "stage": stage, "url": url, "http_status": status,
                        "body_preview": body_preview(raw, token), "reason": reason}
        super().__init__(reason)


def smoke(base):
    base = base.rstrip("/")
    parsed = urlparse(base)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("http_service_url_required")
    token = None
    def request(stage, method, path, *, body=None, text=False, valid=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else (b"" if method == "POST" else None)
        url, raw, status = base + path, "", None
        try:
            with urlopen(Request(url, data=payload, headers=headers, method=method), timeout=110) as response:
                status = response.status
                raw = response.read().decode("utf-8", errors="replace")
            output = raw if text else json.loads(raw)
            if valid and not valid(output):
                raise SmokeFailure(stage, url, status, raw, "unexpected_response", token)
            return output, raw, status
        except HTTPError as error:
            # BOUNDARY: HTTPError 본문만 처리하며 요청 헤더·쿠키·연결 예외의 원문은 출력하지 않는다.
            try:
                raw = error.read().decode("utf-8", errors="replace")
            except OSError:
                raw = ""
            finally:
                error.close()
            raise SmokeFailure(stage, url, error.code, raw, "HTTPError", token) from None
        except SmokeFailure:
            raise
        except Exception as error:
            raise SmokeFailure(stage, url, status, raw, type(error).__name__, token) from None
    request("health", "GET", "/api/health", valid=lambda value: value == {"status": "ok"})
    request("landing", "GET", "/", text=True, valid=lambda value: '<div id="root">' in value)
    trial, _, _ = request("trial", "POST", "/api/auth/trial", valid=lambda value:
                          isinstance(value, dict) and isinstance(value.get("accessToken"), str) and bool(value["accessToken"]))
    token = trial["accessToken"]
    usage_valid = lambda value: isinstance(value, dict) and type(value.get("remaining")) is int
    before = request("usage", "GET", "/api/ai/usage", valid=usage_valid)[0]["remaining"]
    started = time.monotonic()
    output, _, _ = request("ai_query", "POST", "/api/ai/query", body={"query": "소상공인 금융 지원사업 찾아줘"},
                           valid=lambda value: isinstance(value, dict) and isinstance(value.get("result", value), dict))
    elapsed = round(time.monotonic() - started, 2)
    usage, raw, status = request("usage", "GET", "/api/ai/usage", valid=usage_valid)
    after = usage["remaining"]
    if before - after != 1:
        raise SmokeFailure("usage", base + "/api/ai/usage", status, raw, "smoke_usage_mismatch", token)
    result = output.get("result", output)
    return {"health": "PASS", "landing": "PASS", "trial": "PASS", "ai_query": "PASS", "usage": "PASS",
            "request_mode": result.get("requestMode"), "remaining": after, "seconds": elapsed}


if __name__ == "__main__":
    try:
        print(json.dumps(smoke(sys.argv[1]), ensure_ascii=False))
    except SmokeFailure as error:
        print(json.dumps(error.details, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # BOUNDARY: 요청 객체·Bearer 값·상세 연결 오류를 출력하지 않는다.
        print("smoke_failed:" + type(error).__name__, file=sys.stderr)
        sys.exit(1)
