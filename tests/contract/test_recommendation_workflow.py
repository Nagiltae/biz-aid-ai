import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.workflow.recommendation import advance, build_final_result, build_graph, start

COMPANY = {"company_name": "흐름상사", "company_size": "소상공인", "business_status": "영업중", "business_entity_type": "개인사업자"}


def program(rank, pblanc_id):
    return {"rank": rank, "pblanc_id": pblanc_id, "name": f"공고 {pblanc_id}", "target": "소상공인", "rrf_score": 0.03}


def eligibility(pblanc_id, status, missing=()):
    return {"pblanc_id": pblanc_id, "program_name": f"공고 {pblanc_id}", "status": status, "missing_information": list(missing),
            "criteria": [{"criterion": "요건", "result": "UNKNOWN" if missing else "MET", "reason": "r", "profile_fields": [],
                          "missing_profile_fields": list(missing), "citations": [
                              {"evidence_id": "E1", "pblanc_id": pblanc_id, "title": "t", "pages": [3], "location": "p.3",
                               "heading_path": [], "provenance": [{"bbox_pt": [1, 2, 3, 4]}], "source_sha256": "x" * 64}]}],
            "retrieved": [{"chunk_id": "c"}], "explanation": ["..."], "llm_seconds": 30.0}


class Fakes:
    def __init__(self, search_result, outcomes):
        self.search_result, self.outcomes, self.searches, self.evaluations = search_result, outcomes, [], []

    def search(self, query, profile, as_of):
        self.searches.append((query, profile.company_size, as_of))
        return self.search_result

    def evaluate(self, pblanc_id, company, as_of):
        self.evaluations.append((pblanc_id, company.credit_score, company.tax_delinquent))
        outcome = self.outcomes[pblanc_id]
        result = outcome(company) if callable(outcome) else outcome
        if isinstance(result, Exception):
            raise result
        return result


def roundtrip(state):
    # Spring은 State를 MySQL JSON column에 저장했다가 다음 요청에서 그대로 돌려준다.
    return json.loads(json.dumps(state, ensure_ascii=False))


class RecommendationWorkflowTests(unittest.TestCase):
    def setUp(self):
        def after_answer(company):
            # 신용점수를 받으면 판정이 끝나는 공고
            return eligibility("PBLN_A", "ELIGIBLE") if company.credit_score else eligibility(
                "PBLN_A", "NEEDS_MORE_INFO", ["credit_score", "business_age_months"])
        self.fakes = Fakes({"status": "LISTED", "candidate_count": 9, "natural_filter": {"raw": "large"},
                            "programs": [program(1, "PBLN_A"), program(2, "PBLN_B"), program(3, "PBLN_C")]},
                           {"PBLN_A": after_answer,
                            "PBLN_B": eligibility("PBLN_B", "NEEDS_MORE_INFO", ["credit_score", "tax_delinquent"]),
                            "PBLN_C": PipelineError("eligibility_unknown_profile_field:x")})
        self.graph = build_graph(self.fakes.search, self.fakes.evaluate)

    def test_each_request_runs_at_most_one_eligibility_and_the_state_decides_the_next_step(self):
        state = roundtrip(start(self.graph, "금융 지원사업", COMPANY, date(2026, 10, 1)))
        # 시작 요청은 검색·Top 3 확정까지만(판정 0건). 큰 진단 값(natural_filter)은 State에 두지 않는다.
        self.assertEqual((state["status"], state["current_step"], state["next_action"], len(self.fakes.evaluations)),
                         ("IN_PROGRESS", "EVALUATE_PROGRAM", "CONTINUE", 0))
        self.assertEqual((state["pending"], "natural_filter" in state["search"], "command" in state), (["PBLN_A", "PBLN_B", "PBLN_C"], False, False))
        for expected_count in (1, 2):
            state = roundtrip(advance(self.graph, state, "continue"))
            self.assertEqual((len(self.fakes.evaluations), state["status"]), (expected_count, "IN_PROGRESS"))
        state = roundtrip(advance(self.graph, state, "continue"))
        # 세 번째 판정 뒤에는 같은 요청 안에서 부족 정보를 합쳐 사용자 답변 대기로 간다.
        self.assertEqual((len(self.fakes.evaluations), state["status"], state["next_action"]), (3, "WAITING_FOR_USER", "ANSWER"))
        self.assertEqual([e["evaluation_status"] for e in state["evaluations"]], ["COMPLETED", "COMPLETED", "FAILED"])
        self.assertEqual(state["evaluations"][2]["error_code"], "eligibility_unknown_profile_field:x")
        # State에는 근거 위치 원본(provenance)·검색 진단을 저장하지 않는다.
        citation = state["evaluations"][0]["eligibility"]["criteria"][0]["citations"][0]
        self.assertNotIn("provenance", citation)
        self.assertNotIn("retrieved", state["evaluations"][0]["eligibility"])
        with self.assertRaisesRegex(PipelineError, "workflow_invalid_transition"):
            advance(self.graph, state, "continue")

    def test_missing_information_is_merged_answers_are_restricted_and_only_affected_programs_are_reevaluated(self):
        state = roundtrip(start(self.graph, "q", COMPANY, date(2026, 10, 1)))
        for _ in range(3):
            state = roundtrip(advance(self.graph, state, "continue"))
        # field ID 기준 중복 제거: credit_score는 A·B 두 공고, 업력(business_age_months)은 개업일로 묻는다.
        missing = {item["field_id"]: item["programs"] for item in state["missing_information"]}
        self.assertEqual(missing, {"credit_score": ["PBLN_A", "PBLN_B"], "business_start_date": ["PBLN_A"],
                                   "tax_delinquent": ["PBLN_B"]})
        for bad in ({"ceo_age": 40}, {"annual_revenue_krw": 1}, {}):
            with self.subTest(answers=bad), self.assertRaisesRegex(PipelineError, "workflow_answer_field_not_requested"):
                advance(self.graph, state, "answer", bad)
        with self.assertRaisesRegex(PipelineError, "company_profile_invalid:credit_score"):
            advance(self.graph, state, "answer", {"credit_score": "높음"})
        before = len(self.fakes.evaluations)
        state = roundtrip(advance(self.graph, state, "answer", {"credit_score": 720}))
        # 답변 요청은 판정을 하지 않는다. 임시 정보만 State에 두고, 답한 field 때문에 부족했던 A·B만 재판정 대상이다(실패 C 제외).
        self.assertEqual((len(self.fakes.evaluations), state["temporary_company_facts"], state["pending"], state["round"]),
                         (before, {"credit_score": 720}, ["PBLN_A", "PBLN_B"], 1))
        self.assertEqual(state["company_profile"], COMPANY)
        state = roundtrip(advance(self.graph, state, "continue"))
        self.assertEqual(self.fakes.evaluations[-1], ("PBLN_A", 720, None))
        state = roundtrip(advance(self.graph, state, "continue"))
        # A는 지원 가능, B는 체납 정보가 아직 없어 다시 묻는다. 이미 답한 credit_score는 다시 묻지 않는다.
        self.assertEqual(state["evaluations"][0]["eligibility"]["status"], "ELIGIBLE")
        self.assertEqual([item["field_id"] for item in state["missing_information"]], ["tax_delinquent"])
        self.assertEqual(state["status"], "WAITING_FOR_USER")

    def test_search_without_programs_completes_and_search_failure_fails_the_workflow(self):
        empty = build_graph(Fakes({"status": "COMPANY_CLOSED", "programs": []}, {}).search, None)
        state = start(empty, "q", COMPANY, date(2026, 10, 1))
        self.assertEqual((state["status"], state["current_step"], state["evaluations"]), ("COMPLETED", "DONE", []))

        def broken(*_):
            raise PipelineError("llm_unavailable")
        failed = start(build_graph(broken, None), "q", COMPANY, date(2026, 10, 1))
        # 검색 실패는 빈 결과로 바꾸지 않고 흐름 실패로 남긴다.
        self.assertEqual((failed["status"], failed["failure_code"], failed["next_action"]), ("FAILED", "llm_unavailable", "NONE"))
        with self.assertRaisesRegex(PipelineError, "workflow_state_version_unsupported"):
            advance(empty, {"status": "IN_PROGRESS"}, "continue")



def judged(pblanc_id, status, criteria, missing=()):
    """조건별 결과를 직접 정한 판정 결과. citations의 pblanc_id는 기본으로 같은 공고다."""
    return {"pblanc_id": pblanc_id, "program_name": f"공고 {pblanc_id}", "status": status, "missing_information": list(missing),
            "disclaimer": "참고용", "criteria": [
                {"criterion": name, "result": result, "reason": f"{name} 이유", "profile_fields": [], "missing_profile_fields": [],
                 "citations": [{"evidence_id": evidence, "pblanc_id": owner or pblanc_id, "title": "t", "pages": [1],
                                "location": "p.1", "heading_path": [], "provenance": [{"bbox_pt": [1, 2, 3, 4]}]}]}
                for name, result, evidence, owner in criteria]}


def run_to_end(outcomes, ranks=("PBLN_A", "PBLN_B", "PBLN_C")):
    fakes = Fakes({"status": "LISTED", "programs": [program(index + 1, pid) for index, pid in enumerate(ranks)]}, outcomes)
    graph = build_graph(fakes.search, fakes.evaluate)
    state = roundtrip(start(graph, "q", COMPANY, date(2026, 10, 1)))
    while state["next_action"] == "CONTINUE":
        state = roundtrip(advance(graph, state, "continue"))
    return state, fakes


class FinalResultTests(unittest.TestCase):
    def test_final_result_classifies_by_existing_status_and_keeps_search_rank_and_reasons(self):
        state, fakes = run_to_end({
            "PBLN_A": judged("PBLN_A", "INELIGIBLE", [("소상공인", "MET", "E1", None), ("체납 없음", "NOT_MET", "E2", None)]),
            "PBLN_B": judged("PBLN_B", "ELIGIBLE", [("소상공인", "MET", "E1", None), ("영업중", "MET", "E1", None)]),
            "PBLN_C": judged("PBLN_C", "INSUFFICIENT_EVIDENCE", [])})
        final = state["final_result"]
        self.assertEqual((state["status"], state["schema_version"], len(fakes.evaluations)), ("COMPLETED", 2, 3))
        self.assertEqual([[item["pblanc_id"] for item in final[key]] for key in ("recommended", "excluded", "unresolved")],
                         [["PBLN_B"], ["PBLN_A"], ["PBLN_C"]])
        self.assertEqual((final["counts"], final["disclaimer"]), ({"recommended": 1, "excluded": 1, "unresolved": 1}, "참고용"))
        recommended, excluded, unresolved = final["recommended"][0], final["excluded"][0], final["unresolved"][0]
        # 추천 이유 = 충족 조건, 제외 이유 = 실제로 INELIGIBLE을 만든 NOT_MET 조건만. 문구는 기존 판정 결과 그대로다.
        self.assertEqual([(r["criterion"], r["reason"], r["evidence_ids"]) for r in recommended["reasons"]],
                         [("소상공인", "소상공인 이유", ["E1"]), ("영업중", "영업중 이유", ["E1"])])
        self.assertEqual([citation["evidence_id"] for citation in recommended["citations"]], ["E1"])  # 같은 근거는 한 번만
        self.assertEqual(([r["criterion"] for r in excluded["reasons"]], [c["evidence_id"] for c in excluded["citations"]]),
                         (["체납 없음"], ["E2"]))
        self.assertEqual((unresolved["reason_code"], unresolved["reasons"], unresolved["citations"]), ("insufficient_evidence", [], []))
        self.assertEqual((recommended["rank"], recommended["program"]["name"], recommended["eligibility_status"]), (2, "공고 PBLN_B", "ELIGIBLE"))
        self.assertNotIn("provenance", json.dumps(final))

        # 판정 순서·적합도와 무관하게 검색 순위(rank) 그대로 둔다. 판정 실패는 실패 코드와 함께 판단 불가다.
        evaluations = [{"rank": rank, "pblanc_id": pid, "program": program(rank, pid), "evaluation_status": "COMPLETED", "error_code": None,
                        "eligibility": judged(pid, "ELIGIBLE", [("요건", "MET", "E1", None)])} for rank, pid in ((3, "P3"), (1, "P1"))]
        evaluations.append({"rank": 2, "pblanc_id": "P2", "program": program(2, "P2"), "evaluation_status": "FAILED",
                            "error_code": "llm_timeout", "eligibility": None})
        final = build_final_result(evaluations)
        self.assertEqual([item["rank"] for item in final["recommended"]], [1, 3])
        self.assertEqual((final["unresolved"][0]["reason_code"], final["unresolved"][0]["error_code"]), ("evaluation_failed", "llm_timeout"))

    def test_answerable_missing_information_keeps_waiting_and_unanswerable_becomes_unresolved(self):
        state, _ = run_to_end({"PBLN_A": judged("PBLN_A", "ELIGIBLE", [("요건", "MET", "E1", None)]),
                               "PBLN_B": eligibility("PBLN_B", "NEEDS_MORE_INFO", ["credit_score"])}, ("PBLN_A", "PBLN_B"))
        # 사용자가 답할 수 있는 부족 정보가 남으면 최종 결과를 만들지 않는다.
        self.assertEqual((state["status"], state["next_action"], state["final_result"]), ("WAITING_FOR_USER", "ANSWER", None))
        # 물을 수 없는 정보(공고별 추가 사실)만 부족하면 흐름은 끝나지만 추천으로 바꾸지 않고 판단 불가로 둔다.
        state, _ = run_to_end({"PBLN_A": judged("PBLN_A", "NEEDS_MORE_INFO", [("특수 요건", "UNKNOWN", "E1", None)], ["extra_1"])},
                              ("PBLN_A",))
        unresolved = state["final_result"]["unresolved"][0]
        self.assertEqual((state["status"], state["final_result"]["recommended"]), ("COMPLETED", []))
        self.assertEqual((unresolved["reason_code"], unresolved["missing_information"], unresolved["reasons"][0]["result"]),
                         ("missing_information_unresolved", ["extra_1"], "UNKNOWN"))
        with self.assertRaisesRegex(PipelineError, "final_result_pending_evaluation"):
            build_final_result([{"rank": 1, "pblanc_id": "P", "evaluation_status": "PENDING"}])

    def test_citations_stay_per_program_and_zero_recommendations_is_a_normal_result(self):
        state, _ = run_to_end({pid: judged(pid, "INELIGIBLE", [("요건", "NOT_MET", f"E-{pid}", None)]) for pid in ("PBLN_A", "PBLN_B", "PBLN_C")})
        final = state["final_result"]
        # 추천할 공고가 없어도 COMPLETED이고 추천 목록은 비어 있다(가짜 추천 없음).
        self.assertEqual((state["status"], final["recommended"], final["counts"]["excluded"]), ("COMPLETED", [], 3))
        for item in final["excluded"]:
            self.assertEqual({(c["pblanc_id"], c["evidence_id"]) for c in item["citations"]}, {(item["pblanc_id"], f"E-{item['pblanc_id']}")})
        # 다른 공고의 근거가 섞여 있으면 걸러 내지 않고 조립을 실패시킨다.
        mixed = [{"rank": 1, "pblanc_id": "P1", "program": program(1, "P1"), "evaluation_status": "COMPLETED", "error_code": None,
                  "eligibility": judged("P1", "ELIGIBLE", [("요건", "MET", "E1", "P2")])}]
        with self.assertRaisesRegex(PipelineError, "final_result_cross_program_citation"):
            build_final_result(mixed)
        empty = start(build_graph(Fakes({"status": "COMPANY_CLOSED", "programs": []}, {}).search, None), "q", COMPANY, date(2026, 10, 1))
        self.assertEqual(empty["final_result"]["counts"], {"recommended": 0, "excluded": 0, "unresolved": 0})

    def test_schema_version_1_state_is_still_advanced(self):
        fakes = Fakes({"status": "LISTED", "programs": [program(1, "PBLN_A")]}, {"PBLN_A": judged("PBLN_A", "ELIGIBLE", [("요건", "MET", "E1", None)])})
        graph = build_graph(fakes.search, fakes.evaluate)
        old = roundtrip(start(graph, "q", COMPANY, date(2026, 10, 1)))
        old["schema_version"] = 1
        old.pop("final_result")
        # V2-3 때 저장된 State는 별도 migration 없이 다음 단계에서 final_result가 붙고 2로 올라간다.
        state = advance(graph, old, "continue")
        self.assertEqual((state["schema_version"], state["final_result"]["counts"]["recommended"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
