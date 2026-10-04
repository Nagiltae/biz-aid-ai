"""V2 시험 동결·채점은 실제 LLM 호출 없이 검증한다."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cases_v2_evaluation', ROOT / 'evals/cases-v2/evaluate.py')
eval_v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_v2)


class CasesV2Tests(unittest.TestCase):
    def test_frozen_twenty_cases_and_no_silent_expectation_change(self):
        path = ROOT / 'evals/cases-v2/cases-v2.json'
        data, frozen = eval_v2.load_cases(path)
        self.assertEqual(len(data['cases']), 20)
        self.assertEqual(frozen['case_count'], 20)
        self.assertEqual({c['evaluation_type'] for c in data['cases']}, {'SEARCH_LIST', 'DOCUMENT_QA', 'PERSONALIZED', 'ELIGIBILITY'})
        with tempfile.TemporaryDirectory() as folder:
            altered = Path(folder) / path.name
            altered.write_bytes(path.read_bytes() + b'\n')
            altered.with_name('cases-v2.frozen.json').write_bytes(path.with_name('cases-v2.frozen.json').read_bytes())
            with self.assertRaisesRegex(ValueError, 'freeze_mismatch'):
                eval_v2.load_cases(altered)

    def test_compact_workflow_completed_does_not_mean_failed_or_fake_chunk_check(self):
        case = {'evaluation_type': 'PERSONALIZED', 'expected': {'search_status': 'LISTED', 'program_ids': ['p']}}
        output = {'search': {'status': 'LISTED', 'programs': [{'pblanc_id': 'p'}]},
                  'evaluations': [{'pblanc_id': 'p', 'evaluation_status': 'COMPLETED',
                    'eligibility': {'criteria': [{'citations': [{'pblanc_id': 'p', 'evidence_id': 'E1'}]}]}}]}
        self.assertTrue(all(eval_v2.judge(case, output, None).values()))
        output['evaluations'][0]['evaluation_status'] = 'FAILED'
        self.assertFalse(eval_v2.judge(case, output, None)['evaluations_completed'])
        output['evaluations'][0]['eligibility']['criteria'][0]['citations'][0]['pblanc_id'] = 'other'
        self.assertFalse(eval_v2.judge(case, output, None)['p.cross_program_zero'])

    def test_cost_and_failure_tokens_are_explicit(self):
        rows = [{'evaluation_type': 'ELIGIBILITY', 'result': 'FAIL', 'seconds': 3,
                 'error_code': 'llm_output_schema_mismatch', 'llm_calls': [
                    {'status': 'SUCCESS', 'input_tokens': 1000, 'output_tokens': 200},
                    {'status': 'FAILED', 'tokens': 'UNMEASURED'}]}]
        summary = eval_v2.summarize(rows)
        self.assertEqual(summary['format_errors'], 1)
        self.assertEqual(summary['unmeasured_token_calls'], 1)
        self.assertEqual(summary['haiku_public_standard_cost_usd'], .002)
