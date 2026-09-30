"""동결된 Gold로 dense·sparse·hybrid Retriever를 같은 top_k로 실행해 Source Hit@1·@5와 Evidence Hit@5를 낸다.

Retriever·embedding·collection 설정은 production 경로 그대로 쓴다. Gold hash가 동결 값과 다르면 실행하지 않는다.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
MODES = ("dense", "sparse", "hybrid")


def load_frozen_gold(directory):
    directory = Path(directory)
    raw = (directory / "gold.json").read_bytes()
    frozen = json.loads((directory / "gold.frozen.json").read_text(encoding="utf-8"))
    # BOUNDARY: 결과를 본 뒤 Gold를 고치면 평가가 자기 확인이 된다. 동결 hash와 다르면 멈춘다.
    if hashlib.sha256(raw).hexdigest() != frozen["sha256"]:
        raise SystemExit("gold_hash_mismatch: gold.json changed after freeze")
    return json.loads(raw), frozen


EVIDENCE_MATCH = "source_sha256+chunk_index"


def judge(item, results):
    """한 질문의 결과 목록(SearchResult dict)에서 세 지표를 판정한다.

    WHY(IMP-013): chunk_id는 chunk identity(chunker_version·embedding 입력 등)가 바뀌면 경계가 같아도 전부 바뀐다.
    근거는 (정답 문서 SHA, 문서 안 조각 순번)으로 판정해 Gold를 고치지 않고 다음 평가에도 쓴다.
    RISK: 조각 경계 자체가 바뀌면(조각 규칙 변경) 같은 순번이 다른 내용이 되므로 새 Gold 버전이 필요하다.
    """
    evidence = {(item["expected_source_sha256"], entry["chunk_index"]) for entry in item["expected_evidence"]}
    sources = [result["source_sha256"] for result in results]

    def hit(result):
        return (result["source_sha256"], result["chunk_index"]) in evidence

    return {"source_hit_at_1": bool(sources) and sources[0] == item["expected_source_sha256"],
            "source_hit_at_5": item["expected_source_sha256"] in sources[:5],
            "evidence_hit_at_5": any(hit(result) for result in results[:5]),
            "evidence_rank": next((rank for rank, result in enumerate(results[:5], 1) if hit(result)), None)}


def summarize(rows):
    summary = {}
    for mode in MODES:
        judged = [row[mode]["judgement"] for row in rows]
        summary[mode] = {name: sum(1 for j in judged if j[name]) for name in ("source_hit_at_1", "source_hit_at_5", "evidence_hit_at_5")}
        summary[mode]["questions"] = len(judged)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only retrieval evaluation over a frozen Gold set")
    parser.add_argument("--gold-dir", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    gold, frozen = load_frozen_gold(args.gold_dir)
    from qdrant_client import QdrantClient
    from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
    from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
    from biz_aid_pipeline.retrieval.retriever import Retriever
    contract = indexing_contract()
    embedder = BgeM3Embedder(contract)
    retriever = Retriever(embedder, QdrantClient(url=qdrant_url("dev")), contract)
    rows = []
    for item in gold["items"]:
        row = {"id": item["id"], "question": item["question"]}
        for mode in MODES:
            results = [result.to_dict() for result in retriever.search(item["question"], mode, args.top_k)]
            row[mode] = {"judgement": judge(item, results),
                         "top": [{key: result[key] for key in ("rank", "chunk_id", "source_sha256", "chunk_index", "pblanc_id", "pages",
                                                               "score", "dense_rank", "sparse_rank")} for result in results]}
        rows.append(row)
    report = {"gold_version": gold["gold_version"], "gold_sha256": frozen["sha256"], "evidence_match": EVIDENCE_MATCH,
              "collection": retriever.collection,
              "embedding_key": embedder.identity["embedding_key"], "top_k": args.top_k,
              "run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "summary": summarize(rows), "questions": rows}
    output = Path(args.gold_dir) / f"results-top{args.top_k}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"results: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
