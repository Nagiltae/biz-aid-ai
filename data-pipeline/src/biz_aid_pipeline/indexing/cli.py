import argparse
import json

from biz_aid_pipeline.config.settings import ROOT, PipelineError
from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
from biz_aid_pipeline.indexing.pipeline import index_source
from biz_aid_pipeline.indexing.qdrant_store import qdrant_url


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only FinalChunk → BGE-M3 dense·sparse → Qdrant indexing")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--source-sha256", action="append", required=True)
    args = parser.parse_args(argv)
    from qdrant_client import QdrantClient
    contract = indexing_contract()
    client = QdrantClient(url=qdrant_url(args.profile))
    embedder = BgeM3Embedder(contract)
    status = 0
    for source_sha256 in args.source_sha256:
        try:
            result = index_source(source_sha256, embedder, client, contract, args.profile, ROOT)
        except PipelineError as error:
            result = {"source_sha256": source_sha256, "status": "FAILED", "failure_code": str(error)}
            status = 1
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return status
