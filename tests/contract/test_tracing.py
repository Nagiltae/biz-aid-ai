import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from langsmith import utils as ls_utils

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.observability import tracing
from biz_aid_pipeline.runtime import ServiceRuntime
from biz_aid_pipeline.workflow.recommendation import build_graph
from test_recommendation_workflow import judged, program

# 민감 표식: 이 문자열·값이 LangSmith로 나가는 HTTP 본문에 하나라도 있으면 실패다.
QUESTION, COMPANY_NAME, REGION, CREDIT = "민감질문_ZQ 금융 지원", "비밀상사", "서울 비밀동", 7123
REASON, SECRET_MESSAGE, API_KEY = "근거원문_RQ 이유", "secret-msg-XYZ", "test-key-SECRET-123"
COMPANY = {"company_name": COMPANY_NAME, "company_size": "소상공인", "business_status": "영업중", "region": REGION}


class Capture(requests.Session):
    """LangSmith Client가 실제로 보내는 요청을 가로채 본문을 모은다(네트워크 없음)."""

    def __init__(self, fail=False):
        super().__init__()
        self.fail, self.bodies, self.lock = fail, [], threading.Lock()

    def request(self, method, url, *args, **kwargs):
        if self.fail:
            raise requests.ConnectionError("down")
        body = kwargs.get("data")
        with self.lock:
            self.bodies.append(body if isinstance(body, bytes) else str(body or "").encode())
        response = requests.Response()
        response.status_code, response._content, response.url = 200, b"{}", url
        return response


def runtime(tracer, observed):
    """DB 없이 ServiceRuntime의 workflow 진입점만 쓴다. 그래프는 가짜 검색·판정을 runtime과 같은 방식으로 감싼다."""
    def search(query, profile, as_of):
        # runtime이 감싸는 하위 단계(조건 분석·후보 조회·검색)를 같은 traced로 흉내 낸다.
        tracing.traced("mysql_candidates", lambda: type("R", (), {"pblanc_ids": ("PBLN_A", "PBLN_B", "PBLN_C")})(),
                       tracing.candidates_summary)()
        tracing.traced("qdrant_search", lambda q, scope: ["PBLN_A", "PBLN_B"], tracing.discovery_summary,
                       lambda q, scope: {"scope_size": len(scope)})(query, ("PBLN_A", "PBLN_B", "PBLN_C"))
        return {"status": "LISTED", "candidate_count": 3, "programs": [program(1, "PBLN_A"), program(2, "PBLN_B")]}

    def evaluate(pblanc_id, company, as_of):
        # BOUNDARY 확인: 추적 중이어도 LangChain/LangGraph 자동 추적은 꺼져 있어야 한다(환경변수가 켜져 있어도).
        observed.append(ls_utils.tracing_is_enabled())
        if pblanc_id == "PBLN_B" and company.credit_score is None:
            criteria = [("신용점수 기준", "UNKNOWN", "E1", None)]
            result = judged(pblanc_id, "NEEDS_MORE_INFO", criteria, ["credit_score"])
            result["criteria"][0]["missing_profile_fields"] = ["credit_score"]
            return result
        if pblanc_id == "PBLN_B":
            raise RuntimeError(SECRET_MESSAGE)
        result = judged(pblanc_id, "ELIGIBLE", [("소상공인", "MET", "E1", None)])
        result["criteria"][0]["reason"] = REASON
        return result

    service = ServiceRuntime.__new__(ServiceRuntime)
    service._lock, service.tracer = threading.Lock(), tracer
    service._recommendation_graph = build_graph(
        tracing.traced("personalized_search", search, tracing.search_summary),
        tracing.traced("eligibility", evaluate, tracing.eligibility_summary, lambda pblanc_id, *_: {"pblanc_id": pblanc_id}))
    return service


def run_flow(service):
    state = service.workflow_start(QUESTION, COMPANY, date(2026, 10, 1))
    state = json.loads(json.dumps(state, ensure_ascii=False))
    while state["next_action"] == "CONTINUE":
        state = json.loads(json.dumps(service.workflow_advance(state, "continue"), ensure_ascii=False))
    state = service.workflow_advance(state, "answer", {"credit_score": CREDIT})
    while state["next_action"] == "CONTINUE":
        state = service.workflow_advance(state, "continue")
    return state


def parts(bodies):
    """multipart 본문에서 JSON 조각만 꺼낸다."""
    found = []
    for body in bodies:
        for chunk in body.split(b"\r\n"):
            if chunk.startswith((b"{", b"[")):
                found.append(json.loads(chunk))
    return found


class TracingTests(unittest.TestCase):
    def tracer(self, session):
        return tracing.build_tracer(tracing.TraceSettings(True, "biz-aid", "http://langsmith.invalid", API_KEY), session=session)

    def test_disabled_by_default_and_the_flow_runs_without_a_client(self):
        with tempfile.TemporaryDirectory() as root:
            settings = tracing.TraceSettings.load(Path(root), "dev", environ={})
            self.assertEqual((settings.enabled, settings.project), (False, "biz-aid"))
            # 켜도 키가 없으면 끈다. 키는 repr에 나오지 않는다.
            keyless = tracing.TraceSettings.load(Path(root), "dev", environ={"BIZAID_TRACING_ENABLED": "true"})
            self.assertFalse(keyless.enabled)
            keyed = tracing.TraceSettings.load(Path(root), "dev", environ={"BIZAID_TRACING_ENABLED": "true", "LANGSMITH_API_KEY": API_KEY})
            self.assertTrue(keyed.enabled)
            self.assertNotIn(API_KEY, repr(keyed))
        self.assertIsNone(tracing.build_tracer(settings))
        observed = []
        state = run_flow(runtime(None, observed))
        self.assertEqual((state["status"], state["final_result"]["counts"]["recommended"]), ("COMPLETED", 1))
        self.assertEqual(set(observed), {False})

    def test_enabled_tracing_sends_only_step_names_counts_and_codes(self):
        session, observed = Capture(), []
        tracer = self.tracer(session)
        with mock.patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGCHAIN_TRACING_V2": "true"}):
            state = run_flow(runtime(tracer, observed))
        tracer.flush()
        self.assertEqual(state["status"], "COMPLETED")
        self.assertEqual(set(observed), {False})
        sent = b"".join(session.bodies)
        text = sent.decode("utf-8")
        # 원문·개인정보·비밀값·예외 메시지는 본문 어디에도 없다.
        for marker in (QUESTION, COMPANY_NAME, REGION, str(CREDIT), REASON, SECRET_MESSAGE, API_KEY, "공고 PBLN_A", "p.1"):
            self.assertNotIn(marker, text)
        runs = [item for item in parts(session.bodies) if isinstance(item, dict) and "name" in item]
        names = [run["name"] for run in runs]
        for name in ("workflow.start", "workflow.continue", "workflow.answer", "personalized_search", "mysql_candidates",
                     "qdrant_search", "eligibility", "apply_answers", "final_result"):
            self.assertIn(name, names)
        # 여러 HTTP 요청의 최상위 실행이 같은 무작위 묶음 키(thread_id)로 이어진다.
        threads = {item["metadata"]["thread_id"] for item in parts(session.bodies)
                   if isinstance(item, dict) and isinstance(item.get("metadata"), dict) and "thread_id" in item["metadata"]}
        self.assertEqual(threads, {state["trace_key"]})
        # 실패한 판정은 메시지 없이 코드만 남는다. 답변은 field ID만 남고 값은 없다.
        # SDK는 오류를 별도 multipart 조각(.error)으로 보낸다.
        self.assertIn('.error"', text)
        self.assertIn('"unexpected:RuntimeError"', text)
        self.assertIn("credit_score", text)
        self.assertIn('"status":"ELIGIBLE"', text.replace(" ", ""))
        # 런타임 정보·환경변수·git 정보 자동 첨부는 끈다.
        for marker in ("platform", "revision_id", "runtime_version", "LANGSMITH_TRACING"):
            self.assertNotIn(marker, text)

    def test_tracing_failure_never_breaks_the_flow(self):
        observed = []
        state = run_flow(runtime(self.tracer(Capture(fail=True)), observed))
        self.assertEqual(state["status"], "COMPLETED")

        class Broken:
            def __getattr__(self, name):
                raise RuntimeError("client broken")
        broken = tracing.Tracer(Broken(), "biz-aid")
        state = run_flow(runtime(broken, observed))
        self.assertEqual(state["final_result"]["counts"], {"recommended": 1, "excluded": 0, "unresolved": 1})
        # 기존 오류 코드는 그대로 위로 전달된다(추적이 삼키지 않는다).
        with self.assertRaisesRegex(PipelineError, "workflow_invalid_transition"):
            runtime(self.tracer(Capture()), observed).workflow_advance(state, "continue")

    def test_sanitize_drops_free_text_and_nested_values(self):
        self.assertEqual(tracing.sanitize({"status": "ELIGIBLE", "count": 3, "query": "금융 지원사업 찾아줘", "nested": {"a": 1},
                                           "ids": ["PBLN_A", "한글"], "질문": "x"}),
                         {"status": "ELIGIBLE", "count": 3, "query": "<redacted>", "nested": "<redacted>", "ids": ["PBLN_A", "<redacted>"]})
        self.assertEqual(tracing.error_code(PipelineError("eligibility_output_not_json")), "eligibility_output_not_json")
        self.assertEqual(tracing.error_code(ValueError("내부 메시지 원문")), "unexpected:ValueError")


if __name__ == "__main__":
    unittest.main()
