import argparse
import json

from biz_aid_pipeline.config.settings import PipelineError


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only grounded answer: hybrid retrieval top5 → LLM → citations (JSON)")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--query", required=True)
    args = parser.parse_args(argv)
    from qdrant_client import QdrantClient
    from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
    from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
    from biz_aid_pipeline.rag.llm import provider_from_settings
    from biz_aid_pipeline.rag.service import RagService
    from biz_aid_pipeline.retrieval.retriever import Retriever
    try:
        provider = provider_from_settings(args.profile)
        contract = indexing_contract()
        retriever = Retriever(BgeM3Embedder(contract), QdrantClient(url=qdrant_url(args.profile)), contract)
        result = RagService(retriever, provider).answer(args.query)
    except PipelineError as error:
        print(json.dumps({"status": "FAILED", "failure_code": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0
