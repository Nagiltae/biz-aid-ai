import argparse
import json
from datetime import date

from biz_aid_pipeline.config.settings import PipelineError


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only grounded answer: MySQL candidates → scoped hybrid top5 → LLM → citations (JSON)")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--category", action="append", default=[], help="support_programs.category 정확 일치(반복 시 OR)")
    parser.add_argument("--target", action="append", default=[], help="support_programs.target 정확 일치(반복 시 OR)")
    parser.add_argument("--jurisdiction", action="append", default=[], help="support_programs.jurisdiction_name 정확 일치(반복 시 OR)")
    parser.add_argument("--not-closed-on", type=date.fromisoformat, help="YYYY-MM-DD. 파생 신청기간이 이 날짜를 포함하지 않는 공고 제외")
    parser.add_argument("--natural-filter", action="store_true", help="질문에서 LLM으로 정형 조건을 추출(수동 필터와 함께 쓸 수 없음)")
    parser.add_argument("--as-of", type=date.fromisoformat, help="YYYY-MM-DD. --natural-filter의 '지금' 기준일(기본: Asia/Seoul 오늘)")
    args = parser.parse_args(argv)
    manual = args.category or args.target or args.jurisdiction or args.not_closed_on
    # WHY: 수동 필터와 추출 필터를 합치는 규칙은 모호하다. 둘 중 하나만 허용한다.
    if args.natural_filter and manual:
        parser.error("--natural-filter cannot be combined with manual filters")
    if args.as_of and not args.natural_filter:
        parser.error("--as-of requires --natural-filter")
    from biz_aid_pipeline.candidates.service import ProgramCandidateFilter, ProgramCandidateRepository, ProgramCandidateService
    from biz_aid_pipeline.config.settings import ROOT, DbConfig
    from biz_aid_pipeline.rag.llm import provider_from_settings
    from biz_aid_pipeline.candidates.discovery import ProgramDiscoveryService
    from biz_aid_pipeline.rag.router import handle_request
    from biz_aid_pipeline.rag.service import RagService
    try:
        provider = provider_from_settings(args.profile)
        repository = ProgramCandidateRepository.from_config(DbConfig.load(ROOT, args.profile))
        extraction, request_mode = None, "DOCUMENT_QA"
        try:
            if args.natural_filter:
                from biz_aid_pipeline.candidates.natural import NaturalLanguageFilterService, filter_domain
                extraction = NaturalLanguageFilterService(provider, filter_domain(repository)).extract(args.query, args.as_of)
                candidate_filter, request_mode = extraction.candidate_filter, extraction.request_mode
            else:
                candidate_filter = ProgramCandidateFilter(tuple(args.category), tuple(args.target), tuple(args.jurisdiction),
                                                          args.not_closed_on)
            # BOUNDARY: 정형 조건(활성 공고 포함)은 항상 MySQL에서 먼저 적용한다. 필터 인자가 없어도 lifecycle 조건은 적용된다.
            candidates = ProgramCandidateService(repository).find_candidates(candidate_filter)
            retriever = None
            if candidates.pblanc_ids:
                from qdrant_client import QdrantClient
                from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
                from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
                from biz_aid_pipeline.retrieval.retriever import Retriever
                contract = indexing_contract()
                retriever = Retriever(BgeM3Embedder(contract), QdrantClient(url=qdrant_url(args.profile)), contract)
            rag_service = RagService(retriever, provider)
            discovery = ProgramDiscoveryService(repository, retriever, rag_service.contract)
            output = handle_request(args.query, request_mode, candidates.pblanc_ids, rag_service, discovery)
        finally:
            repository.close()
    except PipelineError as error:
        print(json.dumps({"status": "FAILED", "failure_code": str(error)}, ensure_ascii=False))
        return 1
    output["candidate_period_unknown"] = candidates.period_unknown
    if extraction is not None:
        output["natural_filter"] = extraction.to_dict()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0
