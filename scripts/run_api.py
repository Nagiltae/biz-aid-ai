#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-pipeline/src"))
# BOUNDARY: 모델은 고정 artifact에서만 읽는다. 내부 API라 loopback에만 연다.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("biz_aid_pipeline.api.app:app", host="127.0.0.1", port=int(os.environ.get("BIZAID_API_PORT", "8000")), workers=1)
