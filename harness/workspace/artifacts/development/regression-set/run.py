#!/usr/bin/env python3
"""고정 질문 10개를 순차 실행한다. 인증은 컨테이너 환경에서만 읽고 결과에는 공개 공고 정보만 남긴다."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_cases(cases):
    import os
    import requests
    headers = {"X-Internal-Api-Key": os.environ["INTERNAL_AI_API_KEY"]}
    base = "http://127.0.0.1:8000/internal/"
    output = []
    for case in cases:
        response = None
        started = time.monotonic()
        try:
            query = case["query"]
            timings = []
            if case["kind"] == "personalized":
                stage_start = time.monotonic()
                response = requests.post(base + "v2/workflows/start", json={"query": query, "company_profile": case["company_profile"],
                                         "as_of": "2026-10-03"}, headers=headers, timeout=90)
                response.raise_for_status()
                state = response.json()["state"]
                timings.append(round(time.monotonic() - stage_start, 2))
                # BOUNDARY: 공고 판정은 기존 workflow 한 단계씩, 최대 Top3만 실행한다. 추가 질문에는 사실을 만들지 않는다.
                for _ in range(3):
                    if state["next_action"] != "CONTINUE":
                        break
                    stage_start = time.monotonic()
                    response = requests.post(base + "v2/workflows/advance", json={"state": state, "command": "continue"},
                                             headers=headers, timeout=90)
                    response.raise_for_status()
                    state = response.json()["state"]
                    timings.append(round(time.monotonic() - stage_start, 2))
                search = state.get("search") or {}
                programs = search.get("programs", [])
                evaluations = [{"pblanc_id": item["pblanc_id"], "evaluation_status": item["evaluation_status"],
                                "status": (item.get("eligibility") or {}).get("status"), "error_code": item.get("error_code"),
                                "criteria_count": len((item.get("eligibility") or {}).get("criteria", []))}
                               for item in state.get("evaluations", [])]
                row = {"request_mode": "PERSONALIZED", "status": state["status"], "answer_present": False,
                       "evidence_count": sum(len(criterion.get("citations", [])) for item in state.get("evaluations", [])
                                             for criterion in (item.get("eligibility") or {}).get("criteria", [])),
                       "evaluations": evaluations,
                       "search_status": search.get("status"),
                       "same_region_top3": any(item.get("jurisdiction_name") == case["company_profile"]["region"] for item in programs)}
            else:
                response = requests.post(base + "v1/query", json={"query": query, "as_of": "2026-10-03"}, headers=headers, timeout=165)
                response.raise_for_status()
                result = response.json()
                programs = result.get("programs") or result.get("selection_candidates") or []
                row = {"request_mode": result.get("request_mode"), "mode_basis": result.get("mode_basis"), "status": result.get("status"),
                       "answer_present": bool(result.get("answer")), "evidence_count": len(result.get("citations", [])),
                       "selected_pblanc_id": result.get("selected_pblanc_id"),
                       "citation_program_ids": sorted({x["pblanc_id"] for x in result.get("citations", [])}),
                       "same_region_top3": None}
            row.update(case_id=case["case_id"], query=query, kind=case["kind"], seconds=round(time.monotonic() - started, 2),
                       stage_seconds=timings, programs=programs)
        except requests.RequestException:
            # RISK: 예외 원문·요청 header·기업 snapshot을 로그에 남기지 않는다. 실패는 재시도하지 않는다.
            code = None
            if response is not None:
                try:
                    code = response.json().get("error", {}).get("code")
                except ValueError:
                    pass
            row = {"case_id": case["case_id"], "query": case["query"], "kind": case["kind"], "status": "FAILED",
                   "error_code": code or "http_or_transport_error", "seconds": round(time.monotonic() - started, 2)}
        output.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description="Fixed bundle1 dev regression questions; sequential, no retries")
    parser.add_argument("--cases", type=Path, default=HERE.parents[4] / "evals/bundle1-quality-questions.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())["cases"]
    if args.cases.name == "bundle1-quality-questions.json":
        (HERE / "questions.json").write_text(args.cases.read_text())
    if len(cases) != 10 or len({case["case_id"] for case in cases}) != 10:
        parser.error("expected exactly 10 distinct fixed cases")
    # BOUNDARY: 실제 인증정보는 stdout으로 꺼내지 않고 기존 dev FastAPI 환경 안에서 요청한다.
    worker = "import json,sys; source=__import__('ast').literal_eval(sys.stdin.readline()); cases=json.loads(sys.stdin.readline()); ns={'__name__':'worker','__file__':'/artifacts/development/regression-set/run.py'}; exec(source,ns); ns['run_cases'](cases)"
    process = subprocess.Popen(["docker", "exec", "-i", "biz-aid-ai-fastapi-1", "python", "-u", "-c", worker],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    source = HERE.joinpath("run.py").read_text()
    process.stdin.write(repr(source) + "\n" + json.dumps(cases, ensure_ascii=False) + "\n")
    process.stdin.close()
    rows = []
    for line in process.stdout:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        rows.append(row)
        print(json.dumps({key: row.get(key) for key in ("case_id", "status", "request_mode", "seconds")}, ensure_ascii=False), flush=True)
        args.output.write_text(json.dumps({"version": "bundle1-20261003", "results": rows}, ensure_ascii=False, indent=2) + "\n")
    stderr = process.stderr.read()
    code = process.wait()
    if code or len(rows) != 10:
        print(json.dumps({"runner_exit": code, "completed_cases": len(rows), "stderr_present": bool(stderr)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
