"""동결 V2 소규모 시험. 생산 runtime과 V1 채점 도구를 재사용하고 provider당 한 번만 순차 실행한다."""
import argparse
import hashlib
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'data-pipeline/src'))
spec = importlib.util.spec_from_file_location('v1_judge_helpers', ROOT / 'evals/v1_baseline/evaluate.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def load_cases(path):
    raw = path.read_bytes()
    frozen = json.loads(path.with_name('cases-v2.frozen.json').read_text())
    data = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != frozen['sha256'] or len(data['cases']) != frozen['case_count']:
        raise ValueError('cases_v2_freeze_mismatch')
    if not 20 <= len(data['cases']) <= 30 or len({c['case_id'] for c in data['cases']}) != len(data['cases']):
        raise ValueError('cases_v2_count_invalid')
    return data, frozen


class MeteredProvider:
    def __init__(self, provider):
        self.provider, self.name, self.model, self.calls = provider, provider.name, provider.model, []

    def generate(self, request):
        started = time.monotonic()
        try:
            response = self.provider.generate(request)
        except Exception:
            self.calls.append({'status': 'FAILED', 'seconds': round(time.monotonic() - started, 3), 'tokens': 'UNMEASURED'})
            raise
        usage = response.usage
        self.calls.append({'status': 'SUCCESS', 'seconds': response.elapsed_seconds,
                           'input_tokens': usage.get('input_tokens', usage.get('prompt_eval_count')),
                           'output_tokens': usage.get('output_tokens', usage.get('eval_count'))})
        return response


def citations_check(output, pid):
    cites = output.get('citations', []) or [c for item in output.get('criteria', []) for c in item.get('citations', [])]
    ids = {r['chunk_id'] for r in output.get('retrieved', [])}
    return {'citation_valid': all(c['chunk_id'] in ids for c in cites),
            'cross_program_zero': all(c['pblanc_id'] == pid for c in cites)}


def judge(case, output, runtime):
    kind, gold = case['evaluation_type'], case['expected']
    if kind == 'SEARCH_LIST':
        from biz_aid_pipeline.candidates.service import ProgramCandidateFilter
        data = output.get('natural_filter', {}).get('candidate_filter', {})
        fields = ProgramCandidateFilter.__dataclass_fields__
        kwargs = {k: date.fromisoformat(v) if k.endswith('_on') and v else tuple(v) if isinstance(v, list) else v
                  for k, v in data.items() if k in fields}
        scope = set(runtime.repository.find(ProgramCandidateFilter(**kwargs)).pblanc_ids)
        ids = [p['pblanc_id'] for p in output.get('programs', [])]
        return {'mode': output.get('request_mode') == kind, 'status': output.get('status') == gold['status'],
                'expected_programs': set(gold['program_ids']).issubset(ids), 'no_duplicates': len(ids) == len(set(ids)),
                'scope': set(ids).issubset(scope), 'count': 0 < len(ids) <= gold['max_results']}
    if kind == 'DOCUMENT_QA':
        pid = case['target_pblanc_id']
        checks = dict(mode=output.get('request_mode') == kind, status=output.get('status') == gold['status'],
                      **citations_check(output, pid))
        cites = output.get('citations', [])
        checks['citation_presence'] = bool(cites) if gold['citation_required'] else not cites
        if gold['citation_required']:
            payloads = helpers.payloads_for_chunks(runtime, [r['chunk_id'] for r in output.get('retrieved', [])])
            pairs = {(p.get('source_sha256'), p.get('chunk_index')) for p in payloads.values()}
            checks.update(document=output.get('selected_pblanc_id') == pid,
                          evidence=bool({(gold['source_sha256'], i) for i in gold['evidence_chunk_indexes']} & pairs),
                          facts=helpers.fact_groups_hit(output.get('answer', ''), gold['fact_groups']))
        if gold.get('region_warning_required'):
            checks['region_warning'] = bool(output.get('region_warning'))
        return checks
    if kind == 'ELIGIBILITY':
        criteria = output.get('criteria', [])
        checks = dict(status=output.get('status') == gold['status'], criteria=len(criteria) >= gold['minimum_criteria'],
                      **citations_check(output, case['target_pblanc_id']))
        if gold.get('criterion'):
            checks['criterion'] = helpers.criterion_hit(criteria, gold['criterion'])
        if gold.get('unknown_required'):
            checks['unknown'] = any(c['result'] == 'UNKNOWN' for c in criteria)
        return checks
    search, evaluations = output.get('search') or {}, output.get('evaluations') or []
    ids = [p['pblanc_id'] for p in search.get('programs', [])]
    checks = {'search_status': search.get('status') == gold['search_status'],
              'expected_programs': set(gold['program_ids']).issubset(ids),
              'evaluations_completed': len(evaluations) == len(ids) and all(e['evaluation_status'] == 'COMPLETED' for e in evaluations)}
    for e in evaluations:
        result = e.get('eligibility') or {}
        # BOUNDARY: workflow 성공만으로 채점하지 않고 각 공고의 근거 격리와 실제 판정 상태를 확인한다.
        cites = [c for item in result.get('criteria', []) for c in item.get('citations', [])]
        checks[f'{e["pblanc_id"]}.cross_program_zero'] = all(c['pblanc_id'] == e['pblanc_id'] for c in cites)
        checks[f'{e["pblanc_id"]}.citation_refs_present'] = all(c.get('evidence_id') for c in cites)
    return checks


def execute(runtime, case, day):
    from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
    kind = case['evaluation_type']
    if kind in ('SEARCH_LIST', 'DOCUMENT_QA'):
        return runtime.answer_query(case['question'], day, selected_pblanc_id=case.get('selected_pblanc_id'),
                                    company_region=case.get('company_region'))
    if kind == 'ELIGIBILITY':
        return runtime.evaluate_eligibility(case['target_pblanc_id'], CompanyProfileSnapshot.from_dict(case['company_profile']), day)
    state = runtime.workflow_start(case['question'], case['company_profile'], day)
    for _ in range(3):
        if state['next_action'] != 'CONTINUE':
            break
        state = runtime.workflow_advance(state, 'continue')
    return state


def summarize(rows):
    by_type = {}
    for kind in ('SEARCH_LIST', 'DOCUMENT_QA', 'PERSONALIZED', 'ELIGIBILITY'):
        selected = [r for r in rows if r['evaluation_type'] == kind]
        by_type[kind] = {'cases': len(selected), 'pass': sum(r['result'] == 'PASS' for r in selected)}
    calls = [c for r in rows for c in r.get('llm_calls', [])]
    incoming = sum(c.get('input_tokens') or 0 for c in calls)
    outgoing = sum(c.get('output_tokens') or 0 for c in calls)
    latency = [r['seconds'] for r in rows]
    errors = [code for r in rows for code in ([r.get('error_code')] +
              [e.get('error_code') for e in r.get('actual', {}).get('evaluations', [])]) if code]
    failures = {code: errors.count(code) for code in sorted(set(errors))}
    judgments = [e for r in rows for e in r.get('actual', {}).get('evaluations', [])]
    single = [r for r in rows if r['evaluation_type'] == 'ELIGIBILITY']
    return {'cases': len(rows), 'pass': sum(r['result'] == 'PASS' for r in rows), 'by_type': by_type,
            'seconds_mean': round(statistics.mean(latency), 2) if latency else None,
            'seconds_max': max(latency, default=None), 'format_errors': sum('schema' in code or 'not_json' in code or 'invalid_evidence' in code for code in errors),
            'failure_codes': failures, 'execution_errors': sum(bool(r.get('error_code')) for r in rows),
            'workflow_judgments_observed': len(judgments),
            'workflow_judgments_completed': sum(e['evaluation_status'] == 'COMPLETED' for e in judgments),
            'single_judgments_completed': sum('actual' in r and r['actual'].get('status') in ('ELIGIBLE', 'INELIGIBLE', 'NEEDS_MORE_INFO') for r in single),
            'input_tokens': incoming, 'output_tokens': outgoing, 'llm_calls': len(calls),
            'unmeasured_token_calls': sum(c['status'] != 'SUCCESS' for c in calls),
            'haiku_public_standard_cost_usd': round((incoming + outgoing * 5) / 1_000_000, 6),
            'cost_basis': 'Haiku 4.5 공개 표준단가 $1/MTok input, $5/MTok output; 실제 AWS 청구 아님. 실패 호출 token은 UNMEASURED.'}


def main():
    parser = argparse.ArgumentParser(description='Frozen dev V2 cases; sequential, no retry, no overwrite')
    parser.add_argument('--provider', choices=['ollama', 'bedrock'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output_exists')
    data, frozen = load_cases(Path(__file__).with_name('cases-v2.json'))
    os.environ['LLM_PROVIDER'] = args.provider
    if args.provider == 'bedrock':
        os.environ['AWS_PROFILE'] = 'bizaid-dev'
    from biz_aid_pipeline.runtime import ServiceRuntime
    from biz_aid_pipeline.config.settings import PipelineError
    runtime = ServiceRuntime('dev', collection_namespace='v2', tracer=None)
    runtime.provider = MeteredProvider(runtime.provider)
    rows, started = [], datetime.now(timezone.utc).isoformat()
    result = {'provider': args.provider, 'case_sha256': frozen['sha256'], 'started_at': started, 'cases': rows,
              'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result['identity'] = helpers.runtime_identity(runtime)
        for case in data['cases']:
            begin, offset = time.monotonic(), len(runtime.provider.calls)
            try:
                actual = execute(runtime, case, date.fromisoformat(data['as_of']))
                try:
                    checks = judge(case, actual, runtime)
                except Exception as error:
                    # RISK: 채점기 오류가 생겨도 실제 모델 결과는 보존한다. 같은 질문을 다시 호출할 필요가 없어야 한다.
                    row = dict(case_id=case['case_id'], evaluation_type=case['evaluation_type'], actual=actual,
                               result='FAIL', error_code='evaluation_scoring_error:' + type(error).__name__)
                else:
                    row = dict(case_id=case['case_id'], evaluation_type=case['evaluation_type'], question=case['question'],
                           actual=actual, checks=checks, result='PASS' if all(checks.values()) else 'FAIL')
            except Exception as error:
                # BOUNDARY: SDK·SQL 예외 원문은 secret을 포함할 수 있어 고정 PipelineError 코드만 결과에 기록한다.
                code = str(error) if isinstance(error, PipelineError) else type(error).__name__
                row = dict(case_id=case['case_id'], evaluation_type=case['evaluation_type'], result='FAIL', error_code=code)
            row.update(seconds=round(time.monotonic() - begin, 2), llm_calls=runtime.provider.calls[offset:])
            rows.append(row)
            result.update(summary=summarize(rows), finished_at=datetime.now(timezone.utc).isoformat())
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + '\n')
            print(json.dumps({k: row[k] for k in ('case_id', 'evaluation_type', 'result', 'seconds')}, ensure_ascii=False), flush=True)
            if row.get('error_code') == 'llm_provider_unavailable':
                result['stopped_environment'] = True
                break
    finally:
        runtime.close()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + '\n')
    return 0 if len(rows) == len(data['cases']) else 1


if __name__ == '__main__':
    sys.exit(main())
