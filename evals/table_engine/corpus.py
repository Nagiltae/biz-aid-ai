"""3-B evidence에서 평가 corpus를 결정적 규칙으로 고르고 SHA·provenance를 고정한다. 제품 venv와 dev DB 읽기만 사용한다."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import sha256_file, write_json

NORMAL_LIMIT = 18
NORMAL_MAX_PAGES = 40
CORPUS_PATH = ROOT / "evals/table_engine/corpus.json"


def select(evidence):
    # 3-B 표본에서 표 cell 탈락 문서는 모두 넣고 정상 표 문서는 쪽수 상한과 SHA 순서로만 골라 선택 편향을 규칙으로 드러낸다.
    dropped = [row for row in evidence if row["warnings"].get("TABLE_CELL_DROP_DETECTED")]
    normal = [row for row in evidence if row["status"] == "PARSED" and row.get("tables", 0) >= 1
              and not row["warnings"].get("TABLE_CELL_DROP_DETECTED") and row["pages"] <= NORMAL_MAX_PAGES]
    return dropped, normal


def build(evidence_path, connection):
    from sqlalchemy import text
    evidence = [json.loads(line) for line in Path(evidence_path).read_text(encoding="utf-8").splitlines() if line]
    dropped, normal = select(evidence)
    documents = []
    for group, rows in (("docling_cell_drop", dropped), ("normal_table", normal)):
        resolved = []
        for row in rows:
            found = connection.execute(text(
                "select distinct content_sha256 from document_sources where content_sha256 like :prefix "
                "and detected_format = 'PDF' and download_status = 'ACQUIRED'"), {"prefix": row["sha"] + "%"}).fetchall()
            if len(found) != 1:
                raise ValueError(f"ambiguous_or_missing_sha_prefix:{row['sha']}")
            resolved.append((found[0][0], row))
        resolved.sort()
        if group == "normal_table":
            resolved = resolved[:NORMAL_LIMIT]
        for sha, row in resolved:
            relations = connection.execute(text(
                "select pblanc_id, source_role, source_token_index, byte_size, storage_path, s3_object_key "
                "from document_sources where content_sha256 = :sha order by pblanc_id, source_role, source_token_index"),
                {"sha": sha}).fetchall()
            local = ROOT / relations[0].storage_path
            if sha256_file(local) != sha:
                raise ValueError(f"local_blob_sha_mismatch:{sha}")
            documents.append({
                "sha256": sha, "group": group, "byte_size": relations[0].byte_size,
                "storage_path": relations[0].storage_path, "s3_object_key": relations[0].s3_object_key,
                "relations": [{"pblanc_id": r.pblanc_id, "source_role": r.source_role, "token_index": r.source_token_index}
                              for r in relations],
                "baseline_3b": {"pages": row["pages"], "tables": row.get("tables"),
                                "drop_events": row["warnings"].get("TABLE_CELL_DROP_DETECTED", 0),
                                "dropped_cells": row["warnings"].get("TABLE_CELLS_DROPPED", 0)}})
    return {"version": 1, "task": "3-B.1 PDF Table Engine Evaluation",
            "selection": {"evidence": "3-B local PDF sample: SHA-ascending head 80 unique PDF, Docling baseline run",
                          "docling_cell_drop": "every document with TABLE_CELL_DROP_DETECTED",
                          "normal_table": f"PARSED, tables>=1, no drop, pages<={NORMAL_MAX_PAGES}, first {NORMAL_LIMIT} by SHA",
                          "bias": "the 80-document pool is not a random corpus sample; prevalence is not inferred"},
            "documents": documents}


def main(argv=None):
    parser = argparse.ArgumentParser(description="3-B.1 표 engine 평가 corpus 고정")
    parser.add_argument("--evidence", required=True, help="3-B 표본 실행 JSONL(문서별 status/tables/warnings)")
    parser.add_argument("--out", default=str(CORPUS_PATH))
    args = parser.parse_args(argv)
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from biz_aid_pipeline.config.settings import DbConfig
    config = DbConfig.load(ROOT, "dev")
    engine = create_engine(URL.create("mysql+pymysql", username=config.user, password=config.password,
                                      host=config.host, port=config.port, database=config.database))
    with engine.connect() as connection:
        corpus = build(args.evidence, connection)
    write_json(args.out, corpus)
    print(f"corpus documents={len(corpus['documents'])} pages={sum(d['baseline_3b']['pages'] for d in corpus['documents'])}")


if __name__ == "__main__":
    main()
