#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-pipeline/src"))
# BOUNDARY: 모델·tokenizer는 고정 artifact에서만 읽고 실행 중 Hub 다운로드를 하지 않는다.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from biz_aid_pipeline.indexing.corpus import main

if __name__ == "__main__":
    sys.exit(main())
