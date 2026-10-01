import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from fastapi.testclient import TestClient

from biz_aid_pipeline.api.app import create_app
from biz_aid_pipeline.config.settings import PipelineError


class FakeRuntime:
    """실제 BGE-M3·Qwen 없이 HTTP 경계만 확인한다. 결과 dict는 서비스가 만든 그대로 돌려준다."""

    def __init__(self):
        self.calls, self.closed = [], False
        self.query_result = {"request_mode": "SEARCH_LIST", "status": "LISTED", "candidate_count": 2,
                             "programs": [{"rank": 1, "pblanc_id": "PBLN_000000000000001"}], "natural_filter": {"applied": {}}}

    def answer_query(self, query, as_of=None):
        self.calls.append(("query", query, as_of))
        return self.query_result

    def evaluate_eligibility(self, pblanc_id, company_profile, as_of=None):
        self.calls.append(("eligibility", pblanc_id, company_profile.credit_score, as_of))
        if pblanc_id == "PBLN_000000000000404":
            raise PipelineError("eligibility_program_not_found_or_inactive")
        # 서비스가 계산한 status를 그대로 둔다(criteria가 전부 MET이어도 HTTP 계층은 바꾸지 않는다).
        return {"pblanc_id": pblanc_id, "status": "NEEDS_MORE_INFO", "criteria": [{"result": "MET"}], "missing_information": []}

    def personalized_search(self, query, company_profile, as_of=None):
        self.calls.append(("personalized", query, company_profile.company_size, as_of))
        return {"status": "LISTED", "candidate_count": 4, "programs": [{"rank": 1, "pblanc_id": "PBLN_000000000000001"}]}

    def personalized_eligibility(self, query, company_profile, as_of=None):
        self.calls.append(("personalized_eligibility", query, company_profile.credit_score, company_profile.company_size))
        return {"search": {"status": "LISTED", "programs": []}, "evaluations": []}

    def close(self):
        self.closed = True


class InternalApiTests(unittest.TestCase):
    def setUp(self):
        self.runtime = FakeRuntime()
        self.app = create_app(lambda: self.runtime, api_key="test-internal-key")

    def test_query_serializes_search_list_and_document_qa_service_results(self):
        with TestClient(self.app, headers={"X-Internal-Api-Key": "test-internal-key"}) as client:
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            listed = client.post("/internal/v1/query", json={"query": "소상공인 금융 지원사업 찾아줘", "as_of": "2026-09-30"})
            self.assertEqual((listed.status_code, listed.json()), (200, self.runtime.query_result))
            self.runtime.query_result = {"request_mode": "DOCUMENT_QA", "status": "INSUFFICIENT_EVIDENCE", "answer": "확인 불가",
                                         "citations": []}
            qa = client.post("/internal/v1/query", json={"query": "비즈플러스카드 지원요건"})
            # BOUNDARY: 근거 부족·후보 없음 같은 판단 결과는 전송 실패가 아니므로 200이다.
            self.assertEqual((qa.status_code, qa.json()["status"]), (200, "INSUFFICIENT_EVIDENCE"))
        self.assertEqual(self.runtime.calls[:2], [("query", "소상공인 금융 지원사업 찾아줘", date(2026, 9, 30)),
                                                  ("query", "비즈플러스카드 지원요건", None)])
        self.assertTrue(self.runtime.closed)

    def test_eligibility_returns_service_status_unchanged(self):
        with TestClient(self.app, headers={"X-Internal-Api-Key": "test-internal-key"}) as client:
            response = client.post("/internal/v1/eligibility", json={
                "pblanc_id": "PBLN_000000000119801", "as_of": "2026-09-30", "company_profile": {"credit_score": 750}})
        self.assertEqual((response.status_code, response.json()["status"]), (200, "NEEDS_MORE_INFO"))
        self.assertEqual(self.runtime.calls, [("eligibility", "PBLN_000000000119801", 750, date(2026, 9, 30))])

    def test_invalid_requests_and_typed_errors_map_to_http_errors_without_internals(self):
        with TestClient(self.app, headers={"X-Internal-Api-Key": "test-internal-key"}) as client:
            self.assertEqual(client.post("/internal/v1/query", json={"query": ""}).status_code, 422)
            bad_profile = client.post("/internal/v1/eligibility", json={
                "pblanc_id": "PBLN_000000000119801", "company_profile": {"credit_score": "high"}})
            self.assertEqual((bad_profile.status_code, bad_profile.json()), (422, {"error": {"code": "company_profile_invalid:credit_score"}}))
            missing = client.post("/internal/v1/eligibility", json={"pblanc_id": "PBLN_000000000000404", "company_profile": {}})
            self.assertEqual((missing.status_code, missing.json()), (404, {"error": {"code": "eligibility_program_not_found_or_inactive"}}))

    def test_internal_endpoints_require_service_key_but_health_does_not(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            for headers in ({}, {"X-Internal-Api-Key": "wrong"}):
                response = client.post("/internal/v1/query", json={"query": "금융"}, headers=headers)
                self.assertEqual((response.status_code, response.json()), (401, {"error": {"code": "internal_auth_failed"}}))
        # 키가 설정되지 않은 서버는 열어 두지 않고 거부한다(fail closed).
        with TestClient(create_app(lambda: FakeRuntime(), api_key="")) as client:
            response = client.post("/internal/v1/query", json={"query": "금융"}, headers={"X-Internal-Api-Key": ""})
            self.assertEqual((response.status_code, response.json()), (503, {"error": {"code": "internal_auth_not_configured"}}))
        self.assertEqual(self.runtime.calls, [])

    def test_v2_personalized_search_is_a_separate_authenticated_contract(self):
        body = {"query": "우리 회사가 신청할 수 있는 지원사업", "company_profile": {"company_size": "소상공인", "business_status": "영업중"}}
        with TestClient(self.app, headers={"X-Internal-Api-Key": "test-internal-key"}) as client:
            ok = client.post("/internal/v2/personalized-search", json=body)
            self.assertEqual((ok.status_code, ok.json()["status"]), (200, "LISTED"))
            # 개인화 검색에 필요 없는 기업정보 field(신용점수 등)는 받지 않는다.
            bad = client.post("/internal/v2/personalized-search", json={"query": "q", "company_profile": {"credit_score": 700}})
            self.assertEqual((bad.status_code, bad.json()), (422, {"error": {"code": "company_search_profile_unknown_field:credit_score"}}))
            self.assertEqual(client.post("/internal/v2/personalized-search", json=body, headers={"X-Internal-Api-Key": "x"}).status_code, 401)
        self.assertEqual(self.runtime.calls, [("personalized", body["query"], "소상공인", None)])

    def test_v2_personalized_eligibility_accepts_the_eligibility_snapshot_contract(self):
        body = {"query": "금융 지원사업", "company_profile": {"company_size": "소상공인", "business_entity_type": "개인사업자"}}
        with TestClient(self.app, headers={"X-Internal-Api-Key": "test-internal-key"}) as client:
            ok = client.post("/internal/v2/personalized-eligibility", json=body)
            self.assertEqual((ok.status_code, ok.json()["search"]["status"]), (200, "LISTED"))
            bad = client.post("/internal/v2/personalized-eligibility", json={"query": "q", "company_profile": {"ceo_age": 40}})
            self.assertEqual((bad.status_code, bad.json()["error"]["code"]), (422, "company_profile_unknown_field:ceo_age"))
        # 저장되지 않은 신용점수는 기본값으로 만들지 않는다(None 그대로).
        self.assertEqual(self.runtime.calls, [("personalized_eligibility", "금융 지원사업", None, "소상공인")])


if __name__ == "__main__":
    unittest.main()
