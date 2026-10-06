"""AI 개선 0단계(3): Gold-v1 12문항의 정답 근거 chunk 순위(Evidence Hit@1·3·5, 문항별 순위).

기존 evals/retrieval/evaluate.py의 Gold 동결 확인·근거 판정 규칙(정답 문서 SHA + 조각 순번)을 그대로 가져다 쓴다.
BOUNDARY: 기존 평가기는 결과를 Gold 폴더에 쓰므로 실행하지 않는다. 이 스크립트는 지정한 새 경로에만 쓴다. LLM 호출 없음.
V1 collection(기준선 재현)과 서비스가 읽는 V2 collection을 읽기만 한다.
V2_scoped는 서비스 문서 질문처럼 정답 공고 1개 범위 + 신청서식(FORM) 제외로 찾아, 같은 공고 안에서 근거 조각의 순위를 본다(IMP-004).
"""
import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
GOLD_DIR = ROOT / "data/parsed/retrieval-eval/gold-v1"
MODES = ("dense", "sparse", "hybrid")
spec = importlib.util.spec_from_file_location("retrieval_eval", ROOT / "evals/retrieval/evaluate.py")
retrieval_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retrieval_eval)


def rank_of(item, results):
    evidence = {(item["expected_source_sha256"], entry["chunk_index"]) for entry in item["expected_evidence"]}
    return next((rank for rank, result in enumerate(results, 1) if (result["source_sha256"], result["chunk_index"]) in evidence), None)


def main():
    parser = argparse.ArgumentParser(description="Evidence rank over frozen Gold-v1; read-only, no LLM, no overwrite")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output_exists")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    gold, frozen = retrieval_eval.load_frozen_gold(GOLD_DIR)
    from qdrant_client import QdrantClient
    from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
    from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
    from biz_aid_pipeline.retrieval.retriever import Retriever
    contract = indexing_contract()
    embedder = BgeM3Embedder(contract)
    client = QdrantClient(url=qdrant_url("dev"))
    report = {"gold_version": gold["gold_version"], "gold_sha256": frozen["sha256"], "top_k": args.top_k,
              "embedding_key": embedder.identity["embedding_key"], "run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "collections": {}}
    for label, namespace, scoped in (("V1", None, False), ("V2", "v2", False), ("V2_scoped", "v2", True)):
        retriever = Retriever(embedder, client, contract, namespace=namespace)
        rows = []
        for item in gold["items"]:
            row = {"id": item["id"], "question_type": item.get("question_type"), "table_question": item.get("table_question")}
            for mode in MODES:
                begin = time.monotonic()
                options = {"pblanc_ids": item["expected_pblanc_ids"], "exclude_roles": ("FORM",)} if scoped else {}
                results = [result.to_dict() for result in retriever.search(item["question"], mode, args.top_k, **options)]
                row[mode] = {"evidence_rank": rank_of(item, results),
                             "source_rank": next((rank for rank, result in enumerate(results, 1)
                                                  if result["source_sha256"] == item["expected_source_sha256"]), None),
                             "seconds": round(time.monotonic() - begin, 3)}
            rows.append(row)
        summary = {}
        for mode in MODES:
            ranks = [row[mode]["evidence_rank"] for row in rows]
            summary[mode] = {f"evidence_hit_at_{k}": sum(1 for rank in ranks if rank is not None and rank <= k) for k in (1, 3, 5, args.top_k)}
            summary[mode]["questions"] = len(rows)
        report["collections"][label] = {"collection": retriever.collection, "summary": summary, "questions": rows}
        print(label, json.dumps(summary, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
