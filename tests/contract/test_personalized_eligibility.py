import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
from biz_aid_pipeline.eligibility.top_programs import PersonalizedEligibilityService

AS_OF = date(2026, 10, 1)
COMPANY = CompanyProfileSnapshot.from_dict({"company_size": "소상공인", "business_status": "영업중", "region": "경기도",
                                            "business_entity_type": "개인사업자"})


def program(rank, pblanc_id):
    return {"rank": rank, "pblanc_id": pblanc_id, "name": f"공고 {pblanc_id}", "category": "금융", "target": "소상공인",
            "jurisdiction_name": "중소벤처기업부", "rrf_score": 0.03}


class FakeSearch:
    def __init__(self, result):
        self.result, self.calls = result, []

    def search(self, query, profile, as_of):
        self.calls.append((query, profile, as_of))
        return self.result


class Evaluator:
    """공고별로 정해 둔 판정 결과나 예외를 돌려주는 가짜 단일 공고 판정."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, []

    def __call__(self, pblanc_id, company, as_of):
        self.calls.append(pblanc_id)
        outcome = self.outcomes[pblanc_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def eligibility(pblanc_id, status, missing=()):
    return {"pblanc_id": pblanc_id, "status": status, "criteria": [], "missing_information": list(missing),
            "disclaimer": "사전 판단"}


class PersonalizedEligibilityTests(unittest.TestCase):
    def test_top3_order_is_kept_and_each_program_gets_its_own_existing_eligibility_result(self):
        search = FakeSearch({"status": "LISTED", "candidate_count": 9,
                             "programs": [program(1, "PBLN_C"), program(2, "PBLN_A"), program(3, "PBLN_B")]})
        evaluator = Evaluator({"PBLN_C": eligibility("PBLN_C", "ELIGIBLE"),
                               "PBLN_A": eligibility("PBLN_A", "NEEDS_MORE_INFO", ["credit_score", "tax_delinquent"]),
                               "PBLN_B": eligibility("PBLN_B", "INELIGIBLE")})
        result = PersonalizedEligibilityService(search, evaluator).run("금융 지원사업", COMPANY, AS_OF)
        # 검색에는 판정용 snapshot에서 코드로 꺼낸 4개 값만 간다.
        profile = search.calls[0][1]
        self.assertEqual((profile.company_size, profile.business_status, profile.region), ("소상공인", "영업중", "경기도"))
        # 검색 순위를 다시 계산하지 않고 Top 3 순서대로 판정한다.
        self.assertEqual(evaluator.calls, ["PBLN_C", "PBLN_A", "PBLN_B"])
        self.assertEqual([(e["rank"], e["pblanc_id"], e["eligibility"]["status"]) for e in result["evaluations"]],
                         [(1, "PBLN_C", "ELIGIBLE"), (2, "PBLN_A", "NEEDS_MORE_INFO"), (3, "PBLN_B", "INELIGIBLE")])
        # 부족한 기업정보는 실패가 아니라 다음 추가 질문 단계의 입력으로 그대로 전달된다.
        self.assertEqual(result["evaluations"][1]["eligibility"]["missing_information"], ["credit_score", "tax_delinquent"])
        self.assertEqual(result["evaluations"][0]["program"]["name"], "공고 PBLN_C")
        self.assertEqual(result["search"]["candidate_count"], 9)

    def test_one_program_failure_is_isolated_and_never_turned_into_a_result(self):
        search = FakeSearch({"status": "LISTED", "programs": [program(1, "PBLN_1"), program(2, "PBLN_2"), program(3, "PBLN_3")]})
        evaluator = Evaluator({"PBLN_1": eligibility("PBLN_1", "ELIGIBLE"),
                               "PBLN_2": PipelineError("eligibility_unknown_profile_field:x"),
                               "PBLN_3": RuntimeError("connection to 10.0.0.1 refused")})
        evaluations = PersonalizedEligibilityService(search, evaluator).run("q", COMPANY, AS_OF)["evaluations"]
        self.assertEqual([(e["evaluation_status"], e["error_code"]) for e in evaluations],
                         [("COMPLETED", None), ("FAILED", "eligibility_unknown_profile_field:x"),
                          ("FAILED", "eligibility_unexpected_error")])
        # 실패한 공고는 판정 결과가 없다(UNKNOWN·성공으로 바꾸지 않는다). 내부 오류 원문은 싣지 않는다.
        self.assertIsNone(evaluations[1]["eligibility"])
        self.assertNotIn("10.0.0.1", str(evaluations))

    def test_no_listed_programs_means_no_eligibility_calls(self):
        for status in ("NO_CANDIDATES", "COMPANY_CLOSED", "CONDITION_CONFLICT"):
            evaluator = Evaluator({})
            result = PersonalizedEligibilityService(FakeSearch({"status": status, "programs": []}), evaluator).run("q", COMPANY, AS_OF)
            self.assertEqual((result["search"]["status"], result["evaluations"], evaluator.calls), (status, [], []))


if __name__ == "__main__":
    unittest.main()
