import argparse
import json

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
from biz_aid_pipeline.retrieval.retriever import MODES, Retriever

PREVIEW_CHARS = 200


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only query → BGE-M3 dense·sparse → Qdrant 검색(JSONL 출력)")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", choices=MODES, default="hybrid")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--pblanc-id")
    parser.add_argument("--source-sha256")
    parser.add_argument("--full-text", action="store_true", help="text를 자르지 않고 출력")
    args = parser.parse_args(argv)
    from qdrant_client import QdrantClient
    contract = indexing_contract()
    try:
        embedder = BgeM3Embedder(contract)
        retriever = Retriever(embedder, QdrantClient(url=qdrant_url(args.profile)), contract)
        results = retriever.search(args.query, args.mode, args.top_k, args.pblanc_id, args.source_sha256)
    except PipelineError as error:
        print(json.dumps({"status": "FAILED", "failure_code": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"query": args.query, "mode": args.mode, "collection": retriever.collection,
                      "embedding_key": embedder.identity["embedding_key"], "results": len(results)}, ensure_ascii=False))
    for result in results:
        row = result.to_dict()
        if not args.full_text:
            row["text"] = row["text"][:PREVIEW_CHARS]
            row["provenance"] = row["provenance"][:3]
        print(json.dumps(row, ensure_ascii=False))
    return 0
