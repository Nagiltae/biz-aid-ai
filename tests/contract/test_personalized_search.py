import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.candidates.natural import NaturalFilterResult
from biz_aid_pipeline.candidates.personalized import (CompanySearchProfile, PersonalizedSearchService, combine,
                                                       company_conditions)
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


if __name__ == "__main__":
    unittest.main()
