import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.candidates.natural import NaturalFilterResult
from biz_aid_pipeline.candidates.personalized import (CompanySearchProfile, PersonalizedSearchService, blend_rankings, combine,
                                                       company_conditions, company_query)
from biz_aid_pipeline.observability import tracing
from biz_aid_pipeline.rag.service import rag_contract
from biz_aid_pipeline.candidates.service import ProgramCandidateFilter, ProgramCandidateRepository, ProgramCandidateService
from biz_aid_pipeline.config.settings import PipelineError
from test_program_candidates import engine_with, row

AS_OF = date(2026, 10, 1)


def extraction(categories=(), targets=(), open_on=None, unapplied=(), jurisdictions=()):
    return NaturalFilterResult("SEARCH_LIST", ProgramCandidateFilter(categories=tuple(categories), targets=tuple(targets),
                                                                     jurisdictions=tuple(jurisdictions), not_closed_on=open_on),
                               {}, {}, list(unapplied), [], None)


class FakeNaturalFilter:
    def __init__(self, result):
        self.result, self.calls = result, []

    def extract(self, query, as_of=None):
        self.calls.append(query)
        return self.result


class FakeDiscovery:
    def __init__(self):
        self.calls = []

    def discover(self, query, candidates, limit=None):
        self.calls.append((query, tuple(candidates), limit))
        return [{"rank": rank, "pblanc_id": pblanc} for rank, pblanc in enumerate(candidates[:limit], 1)]


class PersonalizedSearchTests(unittest.TestCase):
    def test_company_facts_become_filters_only_through_the_approved_code_mapping(self):
        small = company_conditions(CompanySearchProfile.from_dict({"company_size": "소상공인", "region": "경기도 광명시",
                                                                    "business_start_date": "2024-03-01", "business_status": "휴업"}))
        # 소상공인은 중소기업에 포함되므로 두 대상을 모두 남긴다(사용자 승인 표).
        self.assertEqual((small.targets, small.closed_company), (("소상공인", "중소기업"), False))
        # BOUNDARY: 업력·휴업은 Hard Filter로 추측하지 않는다. 지역은 표준명(광역)일 때만 쓰고, 예전 자유 입력 값은 추측하지 않는다.
        self.assertEqual({item["field"]: item["reason"] for item in small.unapplied},
                         {"region": "region_not_standard", "business_start_date": "age_rule_differs_by_program",
                          "business_status": "rule_differs_by_program"})
        self.assertEqual((small.region, small.excluded_jurisdictions), (None, ()))
        self.assertEqual(company_conditions(CompanySearchProfile.from_dict({"company_size": "중소기업"})).targets, ("중소기업",))
        unknown = company_conditions(CompanySearchProfile.from_dict({"company_size": "중견기업"}))
        self.assertEqual((unknown.targets, unknown.unapplied[0]["reason"]), (None, "no_approved_target_mapping"))
        self.assertTrue(company_conditions(CompanySearchProfile.from_dict({"business_status": "폐업"})).closed_company)
        with self.assertRaisesRegex(PipelineError, "company_search_profile_unknown_field:credit_score"):
            CompanySearchProfile.from_dict({"credit_score": 700})

    def test_company_and_query_conditions_are_combined_and_conflicts_are_not_relaxed(self):
        company = company_conditions(CompanySearchProfile.from_dict({"company_size": "소상공인"}))
        merged, conflict = combine(company, extraction(["금융"], ["소상공인"], AS_OF), AS_OF)
        self.assertIsNone(conflict)
        self.assertEqual((merged.categories, merged.targets, merged.not_closed_on, merged.exclude_closed_on),
                         (("금융",), ("소상공인",), AS_OF, AS_OF))
        # 질문에 대상이 없으면 기업규모가 정한 대상을 쓴다.
        self.assertEqual(combine(company, extraction(["금융"]), AS_OF)[0].targets, ("소상공인", "중소기업"))
        # 질문 대상(사회적기업)과 기업정보가 겹치지 않으면 몰래 완화하지 않고 충돌로 돌려준다.
        merged, conflict = combine(company, extraction(targets=["사회적기업"]), AS_OF)
        self.assertEqual((merged, conflict["query_targets"]), (None, ["사회적기업"]))

    def test_company_region_excludes_only_other_metropolitan_jurisdictions(self):
        # 2026-10-03 사용자 결정(IMP-019 A안): 다른 광역 지자체 소관 공고만 뺀다. 매핑은 계약(company-region)에만 있다.
        rows = [row("SEOUL", jurisdiction="서울특별시"), row("BUSAN", jurisdiction="부산광역시"), row("GYEONGGI", jurisdiction="경기도"),
                row("MSS", jurisdiction="중소벤처기업부"), row("NEWBODY", jurisdiction="새로운공공기관"),
                row("JEONNAM", jurisdiction="전남광주통합특별시")]
        repository = ProgramCandidateRepository(engine_with(rows))
        natural, discovery = FakeNaturalFilter(extraction(["금융"])), FakeDiscovery()
        service = PersonalizedSearchService(natural, ProgramCandidateService(repository), lambda: discovery)
        result = service.search("금융 지원사업", CompanySearchProfile.from_dict({"region": "경기도"}), AS_OF)
        # 서울·부산·전남광주 소관은 빠지고, 경기도·중앙부처(중소벤처기업부)·매핑에 없는 소관기관(fail-open)은 남는다.
        self.assertEqual(discovery.calls[0][1], ("GYEONGGI", "MSS", "NEWBODY"))
        company = result["applied_conditions"]["company"]
        self.assertEqual(company["region"], "경기도")
        self.assertIn("서울특별시", company["excluded_jurisdictions"])
        self.assertNotIn("경기도", company["excluded_jurisdictions"])
        self.assertNotIn("중소벤처기업부", company["excluded_jurisdictions"])
        self.assertFalse(any(item["field"] == "region" for item in result["unapplied_conditions"]))
        # 광주·전남은 데이터 기준 하나(전남광주통합특별시)다.
        jeonnam = service.search("금융 지원사업", CompanySearchProfile.from_dict({"region": "전남광주통합특별시"}), AS_OF)
        self.assertEqual(discovery.calls[-1][1], ("JEONNAM", "MSS", "NEWBODY"))
        self.assertEqual(jeonnam["status"], "LISTED")

    def test_query_region_conflict_is_returned_not_relaxed(self):
        company = company_conditions(CompanySearchProfile.from_dict({"region": "경기도"}))
        # 질문 지역이 기업 지역과 다르면 결과 없이 충돌로 돌려준다(지원대상 충돌과 같은 원칙).
        merged, conflict = combine(company, extraction(jurisdictions=["서울특별시"]), AS_OF)
        self.assertEqual((merged, conflict), (None, {"kind": "region", "company_region": "경기도", "query_jurisdictions": ["서울특별시"]}))
        # 일부가 겹치면 겹치는 것만 남긴다. 중앙부처를 말한 질문은 충돌이 아니다.
        merged, conflict = combine(company, extraction(jurisdictions=["서울특별시", "경기도"]), AS_OF)
        self.assertEqual((merged.jurisdictions, conflict), (("경기도",), None))
        merged, conflict = combine(company, extraction(jurisdictions=["중소벤처기업부"]), AS_OF)
        self.assertEqual((merged.jurisdictions, conflict), (("중소벤처기업부",), None))
        self.assertIn("부산광역시", merged.exclude_jurisdictions)
        # 지역이 없는 기업은 질문 지역을 그대로 쓴다(기존 동작).
        nowhere = company_conditions(CompanySearchProfile.from_dict({}))
        self.assertEqual(combine(nowhere, extraction(jurisdictions=["서울특별시"]), AS_OF)[0].jurisdictions, ("서울특별시",))
        # 지원대상 충돌도 같은 구조(kind)로 구분된다.
        size = company_conditions(CompanySearchProfile.from_dict({"company_size": "소상공인"}))
        self.assertEqual(combine(size, extraction(targets=["사회적기업"]), AS_OF)[1]["kind"], "target")

    def test_closed_programs_are_excluded_and_top3_comes_from_scoped_candidates(self):
        rows = [row("P1", start=date(2026, 9, 1), end=date(2026, 10, 31)), row("P2", start=date(2026, 8, 1), end=date(2026, 9, 30)),
                row("P3"), row("P4", start=date(2026, 11, 1), end=date(2026, 11, 30)), row("P5", target="사회적기업"),
                row("P6", target="중소기업"), row("P7", target="중소기업", active=False)]
        repository = ProgramCandidateRepository(engine_with(rows))
        natural, discovery = FakeNaturalFilter(extraction(["금융"])), FakeDiscovery()
        service = PersonalizedSearchService(natural, ProgramCandidateService(repository), lambda: discovery)
        result = service.search("우리 회사가 신청할 수 있는 금융 지원사업", CompanySearchProfile.from_dict({"company_size": "소상공인"}), AS_OF)
        # CLOSED(P2)·인증 대상(P5)·비활성(P7)은 후보가 아니다. OPEN(P1)·UNKNOWN(P3)·UPCOMING(P4)·중소기업(P6)은 남는다.
        self.assertEqual(discovery.calls, [("우리 회사가 신청할 수 있는 금융 지원사업", ("P1", "P3", "P4", "P6"), 10)])
        self.assertEqual((result["status"], result["candidate_count"], len(result["programs"])), ("LISTED", 4, 3))
        self.assertEqual(result["applied_conditions"]["company"]["targets"], ["소상공인", "중소기업"])
        closed = PersonalizedSearchService(natural, ProgramCandidateService(repository), lambda: discovery).search(
            "금융", CompanySearchProfile.from_dict({"business_status": "폐업"}), AS_OF)
        # 폐업 기업은 LLM·검색 없이 명확한 상태로 끝난다.
        self.assertEqual((closed["status"], len(natural.calls), len(discovery.calls)), ("COMPANY_CLOSED", 1, 1))


class RankedDiscovery:
    """질문·기업정보 문장마다 정해진 공고 순위를 돌려주는 가짜 discovery(호출 문장은 기록하되 결과에는 넣지 않는다)."""

    def __init__(self, orders):
        self.orders, self.calls = orders, []

    def discover(self, query, candidates, limit=None):
        self.calls.append((query, limit))
        order = next(value for key, value in self.orders.items() if key in query)
        return [{"rank": rank, "pblanc_id": pblanc, "rrf_score": 1.0 / (60 + rank)} for rank, pblanc in enumerate(order[:limit], 1)]


RESTAURANT = {"company_size": "소상공인", "industry": "음식점업", "business_entity_type": "개인사업자", "business_start_date": "2024-03-01",
              "employee_count": 3, "annual_revenue_krw": 150000000, "exporter": False, "venture_certified": True}


class CompanyRankingTests(unittest.TestCase):
    def test_company_sentence_uses_buckets_not_raw_values_and_only_listed_fields(self):
        text, used = company_query(CompanySearchProfile.from_dict(RESTAURANT), AS_OF)
        self.assertEqual(text, "음식점업 개인사업자 창업 3년 이내 창업기업 상시근로자 5인 미만 연매출 10억 미만 벤처기업")
        self.assertEqual(used, ["industry", "business_entity_type", "business_start_date", "employee_count", "annual_revenue_krw",
                                "venture_certified"])
        # 원래 값(직원 3명·매출 1.5억·개업일)은 문장에 없다. 아니오(False)는 검색어가 되지 않는다.
        for raw in ("3명", "150000000", "2024-03-01", "수출"):
            self.assertNotIn(raw, text)
        # 후보 조건용 4개 값만 있으면 문장이 없고 기존 경로 그대로다.
        self.assertEqual(company_query(CompanySearchProfile.from_dict({"company_size": "소상공인", "region": "경기도"}), AS_OF), (None, []))
        with self.assertRaisesRegex(PipelineError, "company_search_profile_invalid:employee_count"):
            CompanySearchProfile.from_dict({"employee_count": "3"})
        with self.assertRaisesRegex(PipelineError, "company_search_profile_invalid:exporter"):
            CompanySearchProfile.from_dict({"exporter": "yes"})

    def test_weighted_rrf_keeps_question_weight_larger(self):
        question = [{"rank": rank, "pblanc_id": pblanc, "rrf_score": 0.1} for rank, pblanc in enumerate(["Q1", "Q2", "Q3"], 1)]
        company = [{"rank": rank, "pblanc_id": pblanc, "rrf_score": 0.2} for rank, pblanc in enumerate(["Q3", "C1"], 1)]
        blended = blend_rankings(question, company, 0.5, 60, 10)
        # 두 검색 모두에 있는 Q3가 1위, 질문 1위 Q1이 기업정보 검색에만 있는 C1보다 앞선다.
        self.assertEqual([item["pblanc_id"] for item in blended], ["Q3", "Q1", "Q2", "C1"])
        self.assertEqual({key: blended[0][key] for key in ("rank", "question_rank", "company_rank", "company_weight")},
                         {"rank": 1, "question_rank": 3, "company_rank": 1, "company_weight": 0.5})
        self.assertAlmostEqual(blended[0]["blended_score"], 1 / 63 + 0.5 / 61)
        # 기업정보 검색에서만 온 공고는 질문 검색 점수(rrf_score)가 없다.
        self.assertIsNone(blended[-1]["rrf_score"])
        # 같은 순위면 질문 가중치(1)가 기업정보 가중치(<1)보다 크다.
        self.assertEqual(blend_rankings([{"rank": 1, "pblanc_id": "A"}], [{"rank": 1, "pblanc_id": "B"}], 0.5, 60, 2)[0]["pblanc_id"], "A")

    def test_company_sentence_reranks_inside_candidates_without_leaking_the_sentence(self):
        rows = [row(f"P{index}") for index in range(1, 6)]
        repository = ProgramCandidateRepository(engine_with(rows))
        orders = {"금융": ["P1", "P2", "P3", "P4", "P5"], "음식점업": ["P4", "P5", "P3"]}
        spec = rag_contract()["personalized_ranking"]["company_query"]
        for categories, weight in ((["금융"], spec["company_weight"]), ([], spec["generic_question_weight"])):
            with self.subTest(generic=not categories):
                discovery = RankedDiscovery(orders)
                service = PersonalizedSearchService(FakeNaturalFilter(extraction(categories)), ProgramCandidateService(repository),
                                                    lambda: discovery)
                result = service.search("금융 지원사업", CompanySearchProfile.from_dict(RESTAURANT), AS_OF)
                # 같은 후보 scope로 질문·기업정보 문장 두 번 검색한다(depth까지).
                self.assertEqual([limit for _, limit in discovery.calls], [spec["depth"], spec["depth"]])
                self.assertIn("음식점업", discovery.calls[1][0])
                applied = result["applied_conditions"]["company"]["company_query"]
                self.assertEqual((applied["applied"], applied["weight"], applied["generic_question"]), (True, weight, not categories))
                self.assertIn("industry", applied["fields"])
                # RISK: 문장 원문은 응답·추적 요약 어디에도 없다.
                self.assertNotIn("음식점업", json.dumps(result, ensure_ascii=False))
                self.assertNotIn("음식점업", json.dumps(tracing.search_summary(result), ensure_ascii=False))
                self.assertTrue(tracing.search_summary(result)["company_query_applied"])
                top = result["programs"]
                self.assertEqual(len(top), 3)
                # 기존 기록 필드는 유지되고 새 점수 필드가 붙는다.
                for key in ("original_rank", "original_score", "region_bonus", "final_score", "question_rank", "company_rank",
                            "company_weight", "blended_score"):
                    self.assertIn(key, top[0])
        # 순위용 항목이 없으면 기존처럼 질문으로 한 번만 검색한다.
        discovery = RankedDiscovery(orders)
        plain = PersonalizedSearchService(FakeNaturalFilter(extraction(["금융"])), ProgramCandidateService(repository),
                                          lambda: discovery).search("금융 지원사업", CompanySearchProfile.from_dict({"company_size": "소상공인"}), AS_OF)
        self.assertEqual(discovery.calls, [("금융 지원사업", 10)])
        self.assertEqual([item["pblanc_id"] for item in plain["programs"]], ["P1", "P2", "P3"])
        self.assertFalse(plain["applied_conditions"]["company"]["company_query"]["applied"])


if __name__ == "__main__":
    unittest.main()
