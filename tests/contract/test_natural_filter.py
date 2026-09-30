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


def output(categories=(), targets=(), currently_open=False, unapplied=()):
    return json.dumps({"categories": list(categories), "targets": list(targets), "currently_open_requested": currently_open,
                       "unapplied_constraints": list(unapplied)}, ensure_ascii=False)


DOMAIN = {"categories": ("경영", "금융", "기술"), "targets": ("소상공인", "중소기업")}


class NaturalLanguageFilterTests(unittest.TestCase):
    def test_extracted_values_are_limited_to_the_active_db_domain(self):
        repository = ProgramCandidateRepository(engine_with([row("P1"), row("P2", category="기술", target="중소기업"),
                                                             row("P3", category="수출", active=False)]))
        # 허용 값은 활성 공고에 실제로 있는 값이다. 비활성 공고에만 있는 "수출"은 허용 값이 아니다.
        self.assertEqual(filter_domain(repository), {"categories": ("금융", "기술"), "targets": ("소상공인", "중소기업")})
        provider = FakeProvider(output(["금융", "금융지원", "finance"], ["소상공인"]))
        result = NaturalLanguageFilterService(provider, DOMAIN).extract("소상공인 금융 지원사업")
        self.assertEqual((result.candidate_filter.categories, result.candidate_filter.targets), (("금융",), ("소상공인",)))
        self.assertEqual(result.unapplied_constraints, ["categories:금융지원(허용 값 아님)", "categories:finance(허용 값 아님)"])
        self.assertIn("금융, 기술", provider.requests[0].system.replace("경영, ", ""))

    def test_currently_open_uses_application_date_not_llm_date(self):
        # BOUNDARY: 출력 schema에는 날짜 field가 없다. "지금"은 application의 as_of 날짜로만 바뀐다.
        self.assertFalse(any("date" in name or "day" in name for name in OUTPUT_SCHEMA["properties"]))
        result = NaturalLanguageFilterService(FakeProvider(output(["금융"], [], True)), DOMAIN).extract("지금 신청 가능한 금융", date(2026, 9, 30))
        self.assertEqual((result.candidate_filter.not_closed_on, result.as_of), (date(2026, 9, 30), "2026-09-30"))
        closed = NaturalLanguageFilterService(FakeProvider(output(["금융"])), DOMAIN).extract("금융 지원", date(2026, 9, 30))
        self.assertIsNone(closed.candidate_filter.not_closed_on)

    def test_region_is_never_mapped_to_jurisdiction_or_other_fields(self):
        # 모델이 지역을 target에 잘못 넣어도 허용 값이 아니라 적용되지 않고, jurisdiction 필터는 자연어로 만들지 않는다.
        provider = FakeProvider(output(["금융"], ["소상공인", "서울특별시"], False, ["서울 지역"]))
        result = NaturalLanguageFilterService(provider, DOMAIN).extract("서울 지역 소상공인 금융 지원사업")
        self.assertEqual((result.candidate_filter.jurisdictions, result.candidate_filter.targets), ((), ("소상공인",)))
        self.assertEqual(result.unapplied_constraints, ["서울 지역", "targets:서울특별시(허용 값 아님)"])
        self.assertNotIn("jurisdictions", OUTPUT_SCHEMA["properties"])

    def test_extraction_failure_raises_instead_of_falling_back_to_all_candidates(self):
        for text in ("not json", json.dumps({"categories": "금융"}), json.dumps({"categories": [], "targets": [],
                                                                               "currently_open_requested": "yes", "unapplied_constraints": []})):
            with self.assertRaises(PipelineError):
                NaturalLanguageFilterService(FakeProvider(text), DOMAIN).extract("금융 지원")


if __name__ == "__main__":
    unittest.main()
