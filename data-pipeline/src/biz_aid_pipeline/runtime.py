"""CLI와 내부 HTTP API가 함께 쓰는 서비스 실행 환경. 요청 흐름 조립만 하고 판단 로직은 기존 서비스에 있다.

WHY: BGE-M3 모델·MySQL engine(connection pool)·Qdrant client·LLM 설정을 요청마다 만들면 느리고 자원을 낭비한다.
provider·repository·Qdrant client는 생성 시 한 번, BGE-M3 Retriever는 처음 필요할 때 한 번 만들어 재사용한다.
"""
import threading

from biz_aid_pipeline.config.settings import ROOT, DbConfig


class ServiceRuntime:
    def __init__(self, profile, root=ROOT):
        from qdrant_client import QdrantClient
        from biz_aid_pipeline.candidates.service import ProgramCandidateRepository
        from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
        from biz_aid_pipeline.rag.llm import provider_from_settings
        self.profile = profile
        self.provider = provider_from_settings(profile)
        self.repository = ProgramCandidateRepository.from_config(DbConfig.load(root, profile))
        self.qdrant = QdrantClient(url=qdrant_url(profile))
        self._retriever, self._lock = None, threading.Lock()

    def retriever(self):
        """BGE-M3 Retriever. 후보가 없는 요청은 모델을 적재하지 않도록 처음 필요할 때 한 번만 만든다."""
        with self._lock:
            if self._retriever is None:
                from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
                from biz_aid_pipeline.retrieval.retriever import Retriever
                contract = indexing_contract()
                self._retriever = Retriever(BgeM3Embedder(contract), self.qdrant, contract)
            return self._retriever

    def answer_query(self, query, as_of=None, manual_filter=None):
        """자연어(또는 수동 정형 필터) 질문 → MySQL 후보 → request_mode 분기(SEARCH_LIST·DOCUMENT_QA) 결과 dict."""
        from biz_aid_pipeline.candidates.discovery import ProgramDiscoveryService
        from biz_aid_pipeline.candidates.natural import NaturalLanguageFilterService, filter_domain
        from biz_aid_pipeline.candidates.service import ProgramCandidateService
        from biz_aid_pipeline.rag.router import handle_request
        from biz_aid_pipeline.rag.service import RagService
        extraction, request_mode = None, "DOCUMENT_QA"
        if manual_filter is None:
            extraction = NaturalLanguageFilterService(self.provider, filter_domain(self.repository)).extract(query, as_of)
            candidate_filter, request_mode = extraction.candidate_filter, extraction.request_mode
        else:
            candidate_filter = manual_filter
        # BOUNDARY: 정형 조건(활성 공고 포함)은 항상 MySQL에서 먼저 적용한다. 후보가 없으면 BGE-M3·Qdrant를 쓰지 않는다.
        candidates = ProgramCandidateService(self.repository).find_candidates(candidate_filter)
        retriever = self.retriever() if candidates.pblanc_ids else None
        rag_service = RagService(retriever, self.provider)
        discovery = ProgramDiscoveryService(self.repository, retriever, rag_service.contract)
        output = handle_request(query, request_mode, candidates.pblanc_ids, rag_service, discovery)
        output["candidate_period_unknown"] = candidates.period_unknown
        if extraction is not None:
            output["natural_filter"] = extraction.to_dict()
        return output

    def evaluate_eligibility(self, pblanc_id, company_profile, as_of=None):
        from biz_aid_pipeline.eligibility.service import EligibilityService
        return EligibilityService(self.repository, self.retriever(), self.provider).evaluate(pblanc_id, company_profile, as_of)

    def close(self):
        self.repository.close()
        self.qdrant.close()
