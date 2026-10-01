import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
from biz_aid_pipeline.eligibility.service import EligibilityService, eligibility_contract
from biz_aid_pipeline.rag.llm import LlmResponse
from test_rag_answer import result

TARGET = "PBLN_1"
AS_OF = date(2026, 9, 30)
PROFILE = CompanyProfileSnapshot.from_dict({"business_entity_type": "개인사업자", "business_start_date": "2025-01-10",
                                            "credit_score": 700, "tax_delinquent": False})


class Repository:
    def program_metadata(self, ids):
        return {TARGET: {"name": "지원사업 공고"}} if TARGET in ids else {}


class Retriever:
    def __init__(self, results):
        self.results, self.calls = results, []

    def search(self, query, mode, top_k, pblanc_ids=None):
        self.calls.append((query, mode, top_k, tuple(pblanc_ids)))
        return self.results


class Provider:
    name, model = "fake", "fake-1"

    def __init__(self, criteria):
        self.text, self.requests = json.dumps({"criteria": criteria}, ensure_ascii=False), []

    def generate(self, request):
        self.requests.append(request)
        return LlmResponse(self.text, self.name, self.model, 0.1)


def criterion(name, verdict, fields, evidence=("E1",)):
    return {"criterion": name, "result": verdict, "reason": "근거와 비교", "evidence_ids": list(evidence), "profile_fields": list(fields)}


EVIDENCE = [result(1, "chunk-1", TARGET, "개인사업자, NCB 595~964점, 업력 6개월 이상, 체납 시 제외"),
            result(2, "chunk-2", TARGET, "매출 요건")]


def evaluate(criteria, profile=PROFILE, evidence=EVIDENCE):
    retriever = Retriever(evidence)
    return EligibilityService(Repository(), retriever, Provider(criteria)).evaluate(TARGET, profile, AS_OF), retriever


class EligibilityContractTests(unittest.TestCase):
    def test_all_met_is_eligible_with_program_scoped_retrieval_and_resolved_citations(self):
        outcome, retriever = evaluate([criterion("개인사업자", "MET", ["business_entity_type"]),
                                       criterion("업력 6개월 이상", "MET", ["business_age_months"]),
                                       criterion("신용점수 595~964점", "MET", ["credit_score"], ("E1", "E2"))])
        self.assertEqual(outcome["status"], "ELIGIBLE")
        # 검색은 고정 질의로 대상 공고 하나만 본다(기업 정보를 질의에 넣지 않는다).
        spec = eligibility_contract()["retrieval"]
        self.assertEqual(retriever.calls, [(spec["query"], "hybrid", 5, (TARGET,))])
        self.assertEqual([c["chunk_id"] for c in outcome["criteria"][2]["citations"]], ["chunk-1", "chunk-2"])
        self.assertTrue(outcome["disclaimer"])

    def test_missing_company_fact_is_unknown_and_needs_more_info_even_if_model_guesses(self):
        profile = CompanyProfileSnapshot.from_dict({"business_entity_type": "개인사업자", "credit_score": 700})
        outcome, _ = evaluate([criterion("개인사업자", "MET", ["business_entity_type"]),
                               criterion("업력 6개월 이상", "UNKNOWN", ["business_age_months"]),
                               criterion("국세·지방세 체납 없음", "MET", ["tax_delinquent"])], profile)
        # BOUNDARY: 값이 없는 체납 여부로 낸 MET은 추측이므로 application이 UNKNOWN으로 되돌린다.
        self.assertEqual(outcome["status"], "NEEDS_MORE_INFO")
        self.assertEqual([c["result"] for c in outcome["criteria"]], ["MET", "UNKNOWN", "UNKNOWN"])
        self.assertEqual(outcome["criteria"][2]["adjusted"], "model_MET_without_profile_value")
        self.assertEqual(outcome["missing_information"], ["business_age_months", "tax_delinquent"])

    def test_any_not_met_is_ineligible_regardless_of_unknowns(self):
        outcome, _ = evaluate([criterion("신용점수 595~964점", "NOT_MET", ["credit_score"]),
                               criterion("매출 요건", "UNKNOWN", ["annual_revenue_krw"], ("E2",))])
        self.assertEqual(outcome["status"], "INELIGIBLE")
        self.assertEqual(evaluate([])[0]["status"], "INSUFFICIENT_EVIDENCE")

    def test_invalid_model_output_and_cross_program_evidence_are_rejected(self):
        cases = [([criterion("요건", "MET", ["credit_score"], ("E9",))], EVIDENCE, "eligibility_invalid_evidence_id"),
                 ([criterion("요건", "MET", ["credit_score"], ())], EVIDENCE, "eligibility_invalid_evidence_id"),
                 ([criterion("요건", "MET", ["ceo_age"])], EVIDENCE, "eligibility_unknown_profile_field"),
                 ([criterion("요건", "LIKELY", ["credit_score"])], EVIDENCE, "eligibility_output_schema_mismatch"),
                 ([criterion("요건", "MET", ["credit_score"])], [result(1, "chunk-x", "PBLN_OTHER", "다른 공고")], "retrieval_scope_violation")]
        for criteria, evidence, code in cases:
            with self.assertRaisesRegex(PipelineError, code):
                evaluate(criteria, evidence=evidence)
        with self.assertRaisesRegex(PipelineError, "eligibility_program_not_found_or_inactive"):
            EligibilityService(Repository(), Retriever(EVIDENCE), Provider([])).evaluate("PBLN_GONE", PROFILE, AS_OF)

    def test_profile_fields_are_stable_ids_limited_by_enum_and_mapped_back_to_original_names(self):
        profile = CompanyProfileSnapshot.from_dict({"credit_score": 700, "additional_facts": {"최근 2개월 매출(원)": 5000000}})
        provider = Provider([criterion("매출 요건", "MET", ["extra_1"], ("E2",))])
        outcome = EligibilityService(Repository(), Retriever(EVIDENCE), provider).evaluate(TARGET, profile, AS_OF)
        request = provider.requests[0]
        fields = request.output_schema["properties"]["criteria"]["items"]["properties"]
        # 생성 단계: 고를 수 있는 field ID와 evidence 번호를 이번 요청의 실제 값으로 제한한다(enum).
        self.assertIn("extra_1", fields["profile_fields"]["items"]["enum"])
        self.assertNotIn("additional_facts.최근 2개월 매출(원)", fields["profile_fields"]["items"]["enum"])
        self.assertEqual(fields["evidence_ids"]["items"]["enum"], ["E1", "E2"])
        self.assertIn("extra_1: 최근 2개월 매출(원)", request.user)
        # 결과 의미는 그대로: 원래 field 이름으로 되돌려 응답한다.
        self.assertEqual(outcome["criteria"][0]["profile_fields"], ["additional_facts.최근 2개월 매출(원)"])
        self.assertEqual(outcome["status"], "ELIGIBLE")

    def test_field_names_outside_the_allowed_ids_are_still_rejected_by_the_application(self):
        # V1 baseline E01·E03 실패 형태: 모델이 사람이 읽는 이름을 바꿔 쓴 경우. provider가 schema를 어겨도 application이 거부한다.
        profile = CompanyProfileSnapshot.from_dict({"credit_score": 700, "additional_facts": {"최근 2개월 매출(원)": 5000000}})
        for bad in ("additional_facts.최근 2 개월 매출", "additional_facts.최근 2개월 매출(원)", "extra_9"):
            with self.subTest(field=bad), self.assertRaisesRegex(PipelineError, "eligibility_unknown_profile_field"):
                evaluate([criterion("매출 요건", "MET", [bad])], profile)


if __name__ == "__main__":
    unittest.main()
