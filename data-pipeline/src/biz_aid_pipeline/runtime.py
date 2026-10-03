"""CLI와 내부 HTTP API가 함께 쓰는 서비스 실행 환경. 요청 흐름 조립만 하고 판단 로직은 기존 서비스에 있다.

WHY: BGE-M3 모델·MySQL engine(connection pool)·Qdrant client·LLM 설정을 요청마다 만들면 느리고 자원을 낭비한다.
provider·repository·Qdrant client는 생성 시 한 번, BGE-M3 Retriever는 처음 필요할 때 한 번 만들어 재사용한다.
"""
import threading

from biz_aid_pipeline.config.settings import ROOT, DbConfig

FROM_SETTINGS = object()


class ServiceRuntime:
    def __init__(self, profile, root=ROOT, collection_namespace=FROM_SETTINGS, tracer=FROM_SETTINGS):
        from qdrant_client import QdrantClient
        from biz_aid_pipeline.candidates.service import ProgramCandidateRepository
        from biz_aid_pipeline.indexing.qdrant_store import collection_namespace as configured_namespace, qdrant_url
        from biz_aid_pipeline.rag.llm import provider_from_settings
        self.profile = profile
        # 검색 collection은 설정(QDRANT_COLLECTION_NAMESPACE)으로 전환한다. V1 baseline 평가는 None(V1 collection)을 명시해 고정한다.
        self.collection_namespace = (configured_namespace(profile, root) if collection_namespace is FROM_SETTINGS
                                     else collection_namespace)
        self.provider = provider_from_settings(profile)
        self.repository = ProgramCandidateRepository.from_config(DbConfig.load(root, profile))
        self.qdrant = QdrantClient(url=qdrant_url(profile))
        self._retriever, self._lock = None, threading.Lock()
        # V2-6 실행 추적: 설정(BIZAID_TRACING_ENABLED)이 꺼져 있으면 None이고 흐름은 그대로다.
        from biz_aid_pipeline.observability.tracing import TraceSettings, build_tracer
        self.tracer = build_tracer(TraceSettings.load(root, profile)) if tracer is FROM_SETTINGS else tracer

    def retriever(self):
        """BGE-M3 Retriever. 후보가 없는 요청은 모델을 적재하지 않도록 처음 필요할 때 한 번만 만든다."""
        with self._lock:
            if self._retriever is None:
                from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
                from biz_aid_pipeline.retrieval.retriever import Retriever
                contract = indexing_contract()
                # 질문 서버는 BGE-M3 범위 모델만 검증한다(IMP-005). 파싱 모델이 없는 컨테이너에서도 같은 embedding_key를 쓴다.
                self._retriever = Retriever(BgeM3Embedder(contract, scope_only=True), self.qdrant, contract,
                                            namespace=self.collection_namespace)
            return self._retriever

    def answer_query(self, query, as_of=None, manual_filter=None, selected_pblanc_id=None, company_region=None):
        """자연어(또는 수동 정형 필터) 질문 → MySQL 후보 → request_mode 분기(SEARCH_LIST·DOCUMENT_QA) 결과 dict."""
        from biz_aid_pipeline.candidates.discovery import ProgramDiscoveryService
        from biz_aid_pipeline.candidates.natural import NaturalLanguageFilterService, filter_domain
        from biz_aid_pipeline.candidates.service import ProgramCandidateService
        from biz_aid_pipeline.rag.router import handle_request
        from biz_aid_pipeline.rag.service import RagService
        from biz_aid_pipeline.candidates.question import deterministic_mode, choose_program
        from biz_aid_pipeline.candidates.natural import service_today
        from biz_aid_pipeline.candidates.service import ProgramCandidateFilter
        from biz_aid_pipeline.candidates.region import standard_regions, region_allowed
        from dataclasses import replace
        from biz_aid_pipeline.candidates.question import name_matches
        as_of = as_of or service_today()
        extraction, request_mode = None, "DOCUMENT_QA"
        active = self.repository.find(ProgramCandidateFilter()).pblanc_ids
        metadata = self.repository.program_metadata(active)
        mode = "DOCUMENT_QA" if selected_pblanc_id else deterministic_mode(query, metadata)
        if selected_pblanc_id:
            candidate_filter = ProgramCandidateFilter()
        elif manual_filter is None:
            extraction = NaturalLanguageFilterService(self.provider, filter_domain(self.repository)).extract(query, as_of, request_mode=mode)
            candidate_filter, request_mode = extraction.candidate_filter, mode or extraction.request_mode
        else:
            candidate_filter = manual_filter
        # BOUNDARY: 정형 조건(활성 공고 포함)은 항상 MySQL에서 먼저 적용한다. 후보가 없으면 BGE-M3·Qdrant를 쓰지 않는다.
        region = company_region if company_region in standard_regions() else None
        named = request_mode == "DOCUMENT_QA" and bool(selected_pblanc_id or name_matches(query, metadata))
        # EXCEPTION: 특정 공고를 직접 묻는 사용자의 의도는 지역 필터로 숨기지 않는다. 지역 차이는 응답에 별도 기록한다.
        candidate_filter = replace(candidate_filter, company_region=None if named else region)
        candidates = ProgramCandidateService(self.repository).find_candidates(candidate_filter)
        scope = candidates.pblanc_ids
        if request_mode == "DOCUMENT_QA":
            # BOUNDARY: 사용자 선택은 현재 활성 공고만 허용하고 그 공고 하나로 근거를 격리한다.
            selection_metadata = metadata if selected_pblanc_id else {key: metadata[key] for key in scope if key in metadata}
            scope, choices = choose_program(query, selection_metadata, as_of, selected_pblanc_id)
            if choices:
                return {"request_mode": request_mode, "status": "SELECTION_REQUIRED", "query": query,
                        "selection_candidates": choices, "candidate_count": len(choices),
                        "answer": None, "citations": [], "programs": [],
                        "applied_region": region, "region_filter_basis": candidates.region_basis,
                        "region_filter_applied": bool(region and not named), "region_warning": None}
        retriever = self.retriever() if scope else None
        rag_service = RagService(retriever, self.provider)
        discovery = ProgramDiscoveryService(self.repository, retriever, rag_service.contract)
        output = handle_request(query, request_mode, scope, rag_service, discovery)
        output["applied_region"] = region
        output["region_filter_basis"] = candidates.region_basis
        output["region_filter_applied"] = bool(region and not named)
        output["region_warning"] = "기업 지역과 다른 지역 공고입니다" if (region and named and scope and any(
            not region_allowed(region, metadata[pid].get("name"), metadata[pid].get("jurisdiction_name")) for pid in scope)) else None
        output["query"] = query
        output["selected_pblanc_id"] = scope[0] if request_mode == "DOCUMENT_QA" and len(scope) == 1 else None
        output["mode_basis"] = "rule" if mode else "llm"
        output["candidate_period_unknown"] = candidates.period_unknown
        if extraction is not None:
            output["natural_filter"] = extraction.to_dict()
        return output

    def personalized_search(self, query, company_profile, as_of=None):
        """V2 개인화 검색: Spring이 보낸 기업정보 snapshot + 질문 → 후보 → 공고 단위 Top 3. V1 answer_query와 별개 경로다."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from biz_aid_pipeline.candidates.discovery import ProgramDiscoveryService
        from biz_aid_pipeline.candidates.natural import NaturalLanguageFilterService, filter_domain
        from biz_aid_pipeline.candidates.personalized import PersonalizedSearchService
        from biz_aid_pipeline.candidates.service import ProgramCandidateService
        from biz_aid_pipeline.rag.service import rag_contract
        as_of = as_of or datetime.now(ZoneInfo("Asia/Seoul")).date()
        service = PersonalizedSearchService(
            NaturalLanguageFilterService(self.provider, filter_domain(self.repository)), ProgramCandidateService(self.repository),
            # 후보가 있을 때만 BGE-M3 Retriever를 적재한다.
            lambda: ProgramDiscoveryService(self.repository, self.retriever(), rag_contract()))
        return service.search(query, company_profile, as_of)

    def recommendation_graph(self):
        """V2-3 LangGraph 흐름. 검색·판정은 기존 서비스를 노드에서 그대로 호출한다. 그래프는 한 번 만들어 재사용한다."""
        with self._lock:
            graph = getattr(self, "_recommendation_graph", None)
        if graph is not None:
            return graph
        from biz_aid_pipeline.candidates.discovery import ProgramDiscoveryService
        from biz_aid_pipeline.candidates.natural import NaturalLanguageFilterService, filter_domain
        from biz_aid_pipeline.candidates.personalized import PersonalizedSearchService
        from biz_aid_pipeline.candidates.service import ProgramCandidateService
        from biz_aid_pipeline.eligibility.service import EligibilityService
        from biz_aid_pipeline.rag.service import rag_contract
        from biz_aid_pipeline.observability import tracing
        from biz_aid_pipeline.workflow.recommendation import build_graph
        # 기존 서비스를 고치지 않고 주요 단계만 실행 추적으로 감싼다(추적 중이 아니면 그대로 호출만 한다).
        natural = NaturalLanguageFilterService(self.provider, filter_domain(self.repository))
        natural.extract = tracing.traced("natural_filter", natural.extract, tracing.natural_summary)
        candidates = ProgramCandidateService(self.repository)
        candidates.find_candidates = tracing.traced("mysql_candidates", candidates.find_candidates, tracing.candidates_summary)

        def discovery():
            service = ProgramDiscoveryService(self.repository, self.retriever(), rag_contract())
            service.discover = tracing.traced("qdrant_search", service.discover, tracing.discovery_summary,
                                              lambda query, scope, **_: {"scope_size": len(scope)})
            return service
        search = PersonalizedSearchService(natural, candidates, discovery)
        graph = build_graph(
            tracing.traced("personalized_search", search.search, tracing.search_summary),
            tracing.traced("eligibility", lambda pblanc_id, company, day: EligibilityService(
                self.repository, self.retriever(), self.provider).evaluate(pblanc_id, company, day), tracing.eligibility_summary,
                lambda pblanc_id, *_: {"pblanc_id": pblanc_id}))
        with self._lock:
            self._recommendation_graph = graph
        return graph

    def workflow_start(self, query, company_profile, as_of=None):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from uuid import uuid4
        from biz_aid_pipeline.observability.tracing import state_summary, workflow_trace
        from biz_aid_pipeline.workflow.recommendation import start
        graph, trace_key = self.recommendation_graph(), uuid4().hex
        # 질문·기업정보는 추적 입력에 넣지 않는다(명령과 묶음 키만).
        with workflow_trace(self.tracer, "workflow.start", trace_key, command="start") as span:
            state = start(graph, query, company_profile, as_of or datetime.now(ZoneInfo("Asia/Seoul")).date(), trace_key)
            span.record(**state_summary(state))
            return state

    def workflow_advance(self, state, command, answers=None):
        from biz_aid_pipeline.observability.tracing import state_summary, workflow_trace
        from biz_aid_pipeline.workflow.recommendation import advance
        graph = self.recommendation_graph()
        before = state_summary(state) if isinstance(state, dict) else {}
        trace_key = state.get("trace_key") if isinstance(state, dict) else None
        with workflow_trace(self.tracer, f"workflow.{command}", trace_key, command=command, status_before=before.get("status"),
                            round=before.get("round"), pending_count=before.get("pending_count")) as span:
            result = advance(graph, state, command, answers)
            span.record(**state_summary(result))
            return result

    def personalized_eligibility(self, query, company_profile, as_of=None):
        """V2-2: 개인화 검색 Top 3 → 공고별 기존 자격 판정. company_profile은 판정용 CompanyProfileSnapshot이다."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from biz_aid_pipeline.candidates.discovery import ProgramDiscoveryService
        from biz_aid_pipeline.candidates.natural import NaturalLanguageFilterService, filter_domain
        from biz_aid_pipeline.candidates.personalized import PersonalizedSearchService
        from biz_aid_pipeline.candidates.service import ProgramCandidateService
        from biz_aid_pipeline.eligibility.service import EligibilityService
        from biz_aid_pipeline.eligibility.top_programs import PersonalizedEligibilityService
        from biz_aid_pipeline.rag.service import rag_contract
        as_of = as_of or datetime.now(ZoneInfo("Asia/Seoul")).date()
        search = PersonalizedSearchService(
            NaturalLanguageFilterService(self.provider, filter_domain(self.repository)), ProgramCandidateService(self.repository),
            lambda: ProgramDiscoveryService(self.repository, self.retriever(), rag_contract()))
        return PersonalizedEligibilityService(
            search, lambda pblanc_id, company, day: EligibilityService(self.repository, self.retriever(), self.provider).evaluate(
                pblanc_id, company, day)).run(query, company_profile, as_of)

    def evaluate_eligibility(self, pblanc_id, company_profile, as_of=None):
        from biz_aid_pipeline.eligibility.service import EligibilityService
        return EligibilityService(self.repository, self.retriever(), self.provider).evaluate(pblanc_id, company_profile, as_of)

    def close(self):
        if getattr(self, "tracer", None) is not None:
            # 종료 전에 남은 실행 기록을 보낸다(실패해도 무시).
            self.tracer.flush()
        self.repository.close()
        self.qdrant.close()
