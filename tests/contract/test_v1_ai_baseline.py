import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from evals.v1_baseline.evaluate import fact_groups_hit, load_frozen_cases, summarize


class V1AiBaselineTest(unittest.TestCase):
    def test_fixed_v1_cases_cover_three_product_behaviors(self):
        cases, frozen = load_frozen_cases(ROOT / "evals/v1_baseline/cases-v1.json")
        counts = {kind: sum(item["evaluation_type"] == kind for item in cases["cases"])
                  for kind in ("SEARCH_LIST", "DOCUMENT_QA", "ELIGIBILITY")}
        self.assertEqual(counts, {"SEARCH_LIST": 4, "DOCUMENT_QA": 3, "ELIGIBILITY": 3})
        self.assertEqual((frozen["case_count"], frozen["runs_before_freeze"]), (10, 0))

    def test_frozen_baseline_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'{"cases": []}\n'
            root.joinpath("cases-v1.json").write_bytes(raw)
            root.joinpath("cases-v1.frozen.json").write_text(json.dumps(
                {"sha256": hashlib.sha256(raw).hexdigest(), "case_count": 0}), encoding="utf-8")
            load_frozen_cases(root / "cases-v1.json")
            root.joinpath("cases-v1.json").write_bytes(b'{"cases": [1]}\n')
            with self.assertRaisesRegex(SystemExit, "baseline_hash_mismatch"):
                load_frozen_cases(root / "cases-v1.json")

    def test_answer_judgement_uses_fact_groups_instead_of_exact_sentence(self):
        groups = [["20만원", "200000원"], ["240만원", "2400000원"], ["12개월"]]
        self.assertTrue(fact_groups_hit("매월 20만 원씩 최대 240만원이며, 최장 12개월입니다.", groups))
        self.assertFalse(fact_groups_hit("월 20만원, 최대 240만원입니다.", groups))

    def test_execution_error_is_counted_as_a_failed_baseline_case(self):
        rows = [{"evaluation_type": "ELIGIBILITY", "result": "PASS", "response_seconds": 2.0,
                 "checks": {"status_hit": True, "criterion_hit": True},
                 "actual": {"cross_program_citation_count": 0}}]
        errors = [{"evaluation_type": "ELIGIBILITY", "result": "FAIL"}]
        summary = summarize(rows, errors, expected_total=2)
        self.assertEqual((summary["total_cases"], summary["pass"], summary["fail"]), (2, 1, 1))
        self.assertEqual(summary["by_type"]["ELIGIBILITY"]["execution_errors"], 1)


if __name__ == "__main__":
    unittest.main()
