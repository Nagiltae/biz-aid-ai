import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.candidates.natural import OUTPUT_SCHEMA, NaturalLanguageFilterService, filter_domain
from biz_aid_pipeline.candidates.service import ProgramCandidateRepository
from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.rag.llm import LlmResponse
from test_program_candidates import engine_with, row


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, text):
        self.text, self.requests = text, []

    def generate(self, request):
        self.requests.append(request)
        return LlmResponse(self.text, self.name, self.model, 0.1)


def output(categories=(), targets=(), currently_open=False, unapplied=(), mode="SEARCH_LIST"):
    return json.dumps({"request_mode": mode, "categories": list(categories), "targets": list(targets), "currently_open_requested": currently_open,
                       "unapplied_constraints": list(unapplied)}, ensure_ascii=False)


DOMAIN = {"categories": ("경영", "금융", "기술"), "targets": ("소상공인", "중소기업")}


class NaturalLanguageFilterTests(unittest.TestCase):
    def test_extracted_values_are_limited_to_the_active_db_domain(self):
        repository = ProgramCandidateRepository(engine_with([row("P1"), row("P2", category="기술", target="중소기업"),
                                                             row("P3", category="수출", active=False)]))
        # 허용 값은 활성 공고에 실제로 있는 값이다. 비활성 공고에만 있는 "수출"은 허용 값이 아니다.
        self.assertEqual(filter_domain(repository), {"categories": ("금융", "기술"), "targets": ("소상공인", "중소기업")})
        provider = FakeProvider(output(["금융", "금융지원", "finance", "기술"], ["소상공인"]))
        result = NaturalLanguageFilterService(provider, DOMAIN).extract("소상공인 금융 지원사업 찾아줘")
        self.assertEqual(result.request_mode, "SEARCH_LIST")
        self.assertEqual((result.candidate_filter.categories, result.candidate_filter.targets), (("금융",), ("소상공인",)))
        # 질문에 있는 표현("금융지원")은 허용 값이 아니라 unapplied, 질문에 없는 값("finance", "기술")은 hard filter가 되지 않고 진단으로만 남는다.
        self.assertEqual(result.unapplied_constraints, ["categories:금융지원(허용 값 아님)"])
        self.assertEqual([(d["field"], d["value"]) for d in result.discarded], [("categories", "finance"), ("categories", "기술")])
        self.assertIn("금융, 기술", provider.requests[0].system.replace("경영, ", ""))

    def test_currently_open_uses_application_date_not_llm_date(self):
        # BOUNDARY: 출력 schema에는 날짜 field가 없다. "지금"은 application의 as_of 날짜로만 바뀐다.
        self.assertFalse(any("date" in name or "day" in name for name in OUTPUT_SCHEMA["properties"]))
        result = NaturalLanguageFilterService(FakeProvider(output(["금융"], [], True)), DOMAIN).extract("지금 신청 가능한 금융", date(2026, 9, 30))
        self.assertEqual((result.candidate_filter.not_closed_on, result.as_of), (date(2026, 9, 30), "2026-09-30"))
        closed = NaturalLanguageFilterService(FakeProvider(output(["금융"])), DOMAIN).extract("금융 지원", date(2026, 9, 30))
        self.assertIsNone(closed.candidate_filter.not_closed_on)
        # BOUNDARY: 질문에 "지금·모집 중" 같은 표현이 없으면 모델이 true를 내도 날짜 hard filter를 걸지 않는다(IMP-012 smoke B).
        guarded = NaturalLanguageFilterService(FakeProvider(output(["금융"], ["소상공인"], True, ["서울 지역"])), DOMAIN).extract(
            "서울 지역 소상공인 금융 지원사업 찾아줘", date(2026, 9, 30))
        self.assertIsNone(guarded.candidate_filter.not_closed_on)
        self.assertIn({"field": "currently_open_requested", "value": True, "reason": "no_open_phrase_in_query"}, guarded.discarded)

    def test_region_is_never_mapped_to_jurisdiction_or_other_fields(self):
        # 모델이 지역을 target에 잘못 넣어도 허용 값이 아니라 적용되지 않고, jurisdiction 필터는 자연어로 만들지 않는다.
        provider = FakeProvider(output(["금융"], ["소상공인", "서울특별시"], False, ["서울 지역", "부산 지역"]))
        result = NaturalLanguageFilterService(provider, DOMAIN).extract("서울 지역 소상공인 금융 지원사업")
        self.assertEqual((result.candidate_filter.jurisdictions, result.candidate_filter.targets), ((), ("소상공인",)))
        # 질문에 있는 지역은 unapplied로 드러내고, 질문에 없는 "부산 지역"·"서울특별시"는 진단으로만 남는다.
        self.assertEqual(result.unapplied_constraints, ["서울 지역"])
        self.assertEqual({d["value"] for d in result.discarded}, {"부산 지역", "서울특별시"})
        self.assertNotIn("jurisdictions", OUTPUT_SCHEMA["properties"])

    def test_extraction_failure_raises_instead_of_falling_back_to_all_candidates(self):
        for text in ("not json", json.dumps({"categories": "금융"}), output(mode="RECOMMEND"), json.dumps({"categories": [], "targets": [],
                                                                               "currently_open_requested": "yes", "unapplied_constraints": []})):
            with self.assertRaises(PipelineError):
                NaturalLanguageFilterService(FakeProvider(text), DOMAIN).extract("금융 지원")

    def test_search_list_returns_program_results_with_mysql_metadata_in_scope(self):
        from biz_aid_pipeline.candidates.discovery import ProgramDiscoveryService
        from test_rag_answer import result as chunk
        repository = ProgramCandidateRepository(engine_with([row("P1"), row("P2"), row("P3", active=False)]))

        class Retriever:
            calls = []

            def __init__(self, ranked):
                self.ranked = ranked

            def search_programs(self, query, limit, pblanc_ids, group_limit):
                self.calls.append((limit, tuple(pblanc_ids), group_limit))
                return self.ranked
        contract = {"discovery": {"max_programs": 5, "group_limit_per_mode": 50}}
        retriever = Retriever([chunk(1, "c1", "P2", "a"), chunk(2, "c3", "P1", "c")])
        programs = ProgramDiscoveryService(repository, retriever, contract).discover("금융 찾아줘", ("P1", "P2"))
        # 목록 정보는 MySQL 값이고, 순위 근거는 공고 순위·대표 조각이다.
        self.assertEqual([(p["rank"], p["pblanc_id"], p["evidence_chunk_id"]) for p in programs], [(1, "P2", "c1"), (2, "P1", "c3")])
        self.assertEqual((programs[0]["category"], programs[0]["target"], Retriever.calls), ("금융", "소상공인", [(5, ("P1", "P2"), 50)]))
        self.assertEqual(ProgramDiscoveryService(repository, retriever, contract).discover("q", ()), [])
        self.assertEqual(len(Retriever.calls), 1)
        for ranked, code in (([chunk(1, "c1", "P9", "x")], "retrieval_scope_violation"),
                             ([chunk(1, "c1", "P1", "x"), chunk(2, "c2", "P1", "y")], "discovery_duplicate_program")):
            with self.assertRaisesRegex(PipelineError, code):
                ProgramDiscoveryService(repository, Retriever(ranked), contract).discover("q", ("P1", "P2"))

    def test_router_uses_list_without_answer_llm_and_qa_through_existing_rag(self):
        from biz_aid_pipeline.rag.router import handle_request
        calls = []

        class Rag:
            def answer(self, query, candidate_pblanc_ids=None):
                calls.append(("rag", tuple(candidate_pblanc_ids)))

                class Answer:
                    def to_dict(self):
                        return {"status": "ANSWERED"}
                return Answer()

        class Discovery:
            def discover(self, query, candidate_pblanc_ids):
                calls.append(("list", tuple(candidate_pblanc_ids)))
                return [{"pblanc_id": "P1"}]
        listed = handle_request("금융 찾아줘", "SEARCH_LIST", ("P1",), Rag(), Discovery())
        self.assertEqual((listed["status"], calls), ("LISTED", [("list", ("P1",))]))
        qa = handle_request("비즈플러스카드 요건", "DOCUMENT_QA", ("P1",), Rag(), Discovery())
        self.assertEqual((qa["request_mode"], calls[-1]), ("DOCUMENT_QA", ("rag", ("P1",))))
        self.assertEqual(handle_request("q", "SEARCH_LIST", (), Rag(), Discovery())["status"], "NO_CANDIDATES")


if __name__ == "__main__":
    unittest.main()
