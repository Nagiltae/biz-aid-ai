"""배포 후 최소 연결 점검. 토큰·질문·응답 전문은 출력하거나 파일에 저장하지 않는다."""
import json
import sys
import time

from urllib.request import Request, urlopen
from urllib.parse import urlparse


def smoke(base):
    base = base.rstrip("/")
    if urlparse(base).scheme not in ("http", "https") or not urlparse(base).hostname:
        raise ValueError("http_service_url_required")
    token = None
    def request(method, path, *, body=None, text=False):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else (b"" if method == "POST" else None)
        with urlopen(Request(base + path, data=payload, headers=headers, method=method), timeout=110) as response:
            raw = response.read().decode("utf-8")
            return raw if text else json.loads(raw)
    assert request("GET", "/api/health") == {"status": "ok"}
    assert '<div id="root">' in request("GET", "/", text=True)
    token = request("POST", "/api/auth/trial")["accessToken"]
    before = request("GET", "/api/ai/usage")["remaining"]
    started = time.monotonic()
    output = request("POST", "/api/ai/query", body={"query": "소상공인 금융 지원사업 찾아줘"})
    elapsed = round(time.monotonic() - started, 2)
    after = request("GET", "/api/ai/usage")["remaining"]
    if before - after != 1:
        raise RuntimeError("smoke_usage_mismatch")
    result = output.get("result", output)
    return {"health": "PASS", "landing": "PASS", "trial": "PASS", "ai_query": "PASS", "usage": "PASS",
            "request_mode": result.get("requestMode"), "remaining": after, "seconds": elapsed}


if __name__ == "__main__":
    try:
        print(json.dumps(smoke(sys.argv[1]), ensure_ascii=False))
    except Exception as error:
        # BOUNDARY: 요청 객체·Bearer 값·상세 연결 오류를 출력하지 않는다.
        print("smoke_failed:" + type(error).__name__, file=sys.stderr)
        sys.exit(1)
