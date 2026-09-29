#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-pipeline/src"))
# BOUNDARY: corpus 실행 중 모델 네트워크 다운로드를 막는다. 모델은 고정 artifact 경로에서만 읽는다.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
from biz_aid_pipeline.parsing.corpus import main

if __name__ == "__main__":
    sys.exit(main())
