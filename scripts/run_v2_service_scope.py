#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-pipeline/src"))

from biz_aid_pipeline.indexing.service_scope import main

if __name__ == "__main__":
    sys.exit(main())
