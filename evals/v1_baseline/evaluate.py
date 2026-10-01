"""동결한 작은 V1 세트로 SEARCH_LIST·DOCUMENT_QA·Eligibility를 각 1회 측정한다.

생산 ServiceRuntime을 그대로 호출하되 결과를 고치거나 prompt를 조정하지 않는다. 자연어 전체 문장 대신
공고 ID·근거 문서와 조각 순번·citation·상태·조건 결과처럼 재현 가능한 항목을 판정한다.
"""
import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
EVIDENCE_MATCH = "source_sha256+chunk_index"
EVALUATION_TYPES = ("SEARCH_LIST", "DOCUMENT_QA", "ELIGIBILITY")


def load_frozen_cases(cases_path):
    cases_path = Path(cases_path)
    raw = cases_path.read_bytes()
    frozen_path = cases_path.with_name("cases-v1.frozen.json")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != frozen["sha256"]:
        raise SystemExit("baseline_hash_mismatch: cases-v1.json changed after freeze")
    cases = json.loads(raw)
    if len(cases.get("cases", [])) != frozen["case_count"]:
        raise SystemExit("baseline_case_count_mismatch")
    return cases, frozen


def compact(value):
    normalized = unicodedata.normalize("NFKC", str(value)).lower()
    return re.sub(r"[\s,]", "", normalized)


def fact_groups_hit(answer, groups):
    value = compact(answer)
    return all(any(compact(alternative) in value for alternative in group) for group in groups)


def candidate_filter_from_output(output):
    from biz_aid_pipeline.candidates.service import ProgramCandidateFilter
    value = output["natural_filter"]["candidate_filter"]
    day = date.fromisoformat(value["not_closed_on"]) if value.get("not_closed_on") else None
    return ProgramCandidateFilter(tuple(value.get("categories", ())), tuple(value.get("targets", ())),
                                  tuple(value.get("jurisdictions", ())), day)


def payloads_for_chunks(runtime, chunk_ids):
    if not chunk_ids:
        return {}
    points = runtime.qdrant.retrieve(runtime.retriever().collection, list(dict.fromkeys(chunk_ids)),
                                     with_payload=True, with_vectors=False)
    return {str(point.id): dict(point.payload or {}) for point in points}


def judge_search(case, output, runtime):
    expected = case["expected"]
    programs = output.get("programs", [])
    ids = [program.get("pblanc_id") for program in programs]
    candidate_ids = set(runtime.repository.find(candidate_filter_from_output(output)).pblanc_ids)
    expected_ids = expected["program_ids"]
    included = all(item in ids for item in expected_ids)
    order_hit = ids == expected_ids if expected["exact_order"] else included
    duplicate_count = len(ids) - len(set(ids))
    out_of_scope = [item for item in ids if item not in candidate_ids]
    checks = {
        "status_hit": output.get("status") == expected["status"],
        "expected_programs_hit": included,
        "expected_order_hit": order_hit,
        "result_count_hit": len(ids) == expected["result_count"],
        "duplicates_zero": duplicate_count == 0,
        "outside_candidate_scope_zero": not out_of_scope,
    }
    actual = {"request_mode": output.get("request_mode"), "status": output.get("status"),
              "program_ids": ids, "result_count": len(ids), "candidate_count": output.get("candidate_count"),
              "duplicate_count": duplicate_count, "outside_candidate_scope_ids": out_of_scope,
              "applied_filter": output.get("natural_filter", {}).get("applied", {}),
              "unapplied_constraints": output.get("natural_filter", {}).get("unapplied_constraints", [])}
    return actual, checks


def judge_document_qa(case, output, runtime):
    expected = case["expected"]
    retrieved = output.get("retrieved", [])
    citations = output.get("citations", [])
    payloads = payloads_for_chunks(runtime, [item.get("chunk_id") for item in retrieved if item.get("chunk_id")])
    expected_pairs = {(expected["source_sha256"], index) for index in expected["evidence_chunk_indexes"]}
    retrieved_pairs = {(payload.get("source_sha256"), payload.get("chunk_index")) for payload in payloads.values()}
    expected_evidence_hit = bool(expected_pairs & retrieved_pairs)
    retrieved_ids = {item.get("chunk_id") for item in retrieved}
    citation_valid = all(item.get("chunk_id") in retrieved_ids for item in citations)
    cross_program = [item for item in citations if item.get("pblanc_id") != case["target_pblanc_id"]]
    expected_document_found = any(item.get("pblanc_id") == case["target_pblanc_id"] for item in retrieved)
    facts_hit = fact_groups_hit(output.get("answer", ""), expected["fact_groups"])
    citation_presence = bool(citations) if expected["citation_required"] else not citations
    no_speculation = output.get("status") != "INSUFFICIENT_EVIDENCE" or not citations
    checks = {
        "status_hit": output.get("status") == expected["status"],
        "expected_document_found": expected_document_found,
        "expected_evidence_hit": expected_evidence_hit,
        "expected_facts_hit": facts_hit,
        "citation_presence_hit": citation_presence,
        "citation_valid": citation_valid,
        "cross_program_citations_zero": not cross_program,
        "insufficient_evidence_does_not_cite": no_speculation,
    }
    actual = {"request_mode": output.get("request_mode"), "status": output.get("status"),
              "answer": output.get("answer"), "retrieved_chunk_ids": [item.get("chunk_id") for item in retrieved],
              "retrieved_evidence_pairs": sorted([list(pair) for pair in retrieved_pairs if pair[0] is not None]),
              "citation_chunk_ids": [item.get("chunk_id") for item in citations],
              "citation_pblanc_ids": [item.get("pblanc_id") for item in citations],
              "cross_program_citation_count": len(cross_program), "llm_seconds": output.get("llm_seconds")}
    return actual, checks


def criterion_hit(criteria, expected):
    return any(expected["profile_field"] in item.get("profile_fields", ()) and item.get("result") == expected["result"]
               for item in criteria)


def judge_eligibility(case, output, runtime):
    expected = case["expected"]
    criteria = output.get("criteria", [])
    citations = [citation for item in criteria for citation in item.get("citations", [])]
    retrieved_ids = {item.get("chunk_id") for item in output.get("retrieved", [])}
    citation_valid = all(item.get("chunk_id") in retrieved_ids for item in citations)
    cross_program = [item for item in citations if item.get("pblanc_id") != case["target_pblanc_id"]]
    checks = {
        "status_hit": output.get("status") == expected["status"],
        "criterion_hit": criterion_hit(criteria, expected["criterion"]),
        "missing_information_hit": sorted(output.get("missing_information", [])) == sorted(expected["missing_information"]),
        "citation_valid": citation_valid,
        "cross_program_citations_zero": not cross_program,
    }
    if "all_criterion_results" in expected:
        checks["all_criterion_results_hit"] = bool(criteria) and {item.get("result") for item in criteria}.issubset(
            set(expected["all_criterion_results"]))
    if "minimum_criterion_count" in expected:
        checks["minimum_criterion_count_hit"] = len(criteria) >= expected["minimum_criterion_count"]
    actual = {"status": output.get("status"), "criterion_count": len(criteria),
              "criteria": [{"criterion": item.get("criterion"), "result": item.get("result"),
                            "profile_fields": item.get("profile_fields", []),
                            "missing_profile_fields": item.get("missing_profile_fields", [])} for item in criteria],
              "missing_information": output.get("missing_information", []),
              "citation_chunk_ids": [item.get("chunk_id") for item in citations],
              "cross_program_citation_count": len(cross_program), "llm_seconds": output.get("llm_seconds")}
    return actual, checks


def run_case(runtime, case, as_of):
    from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
    kind = case["evaluation_type"]
    started = time.monotonic()
    if kind in ("SEARCH_LIST", "DOCUMENT_QA"):
        output = runtime.answer_query(case["question"], as_of)
        actual, checks = judge_search(case, output, runtime) if kind == "SEARCH_LIST" else judge_document_qa(case, output, runtime)
    elif kind == "ELIGIBILITY":
        profile = CompanyProfileSnapshot.from_dict(case["company_profile"])
        output = runtime.evaluate_eligibility(case["target_pblanc_id"], profile, as_of)
        actual, checks = judge_eligibility(case, output, runtime)
    else:
        raise ValueError(f"unsupported_evaluation_type:{kind}")
    elapsed = time.monotonic() - started
    return {"case_id": case["case_id"], "evaluation_type": kind, "question": case["question"],
            "target_pblanc_id": case.get("target_pblanc_id"), "expected": case["expected"], "actual": actual,
            "checks": checks, "result": "PASS" if all(checks.values()) else "FAIL",
            "response_seconds": round(elapsed, 3)}


def summarize(rows, errors=(), expected_total=None):
    by_type = {}
    for kind in EVALUATION_TYPES:
        selected = [row for row in rows if row["evaluation_type"] == kind]
        failed = [item for item in errors if item["evaluation_type"] == kind]
        by_type[kind] = {"cases": len(selected) + len(failed), "pass": sum(row["result"] == "PASS" for row in selected),
                         "fail": sum(row["result"] == "FAIL" for row in selected) + len(failed),
                         "execution_errors": len(failed)}
    searches = [row for row in rows if row["evaluation_type"] == "SEARCH_LIST"]
    questions = [row for row in rows if row["evaluation_type"] == "DOCUMENT_QA"]
    eligibility = [row for row in rows if row["evaluation_type"] == "ELIGIBILITY"]
    return {
        "total_cases": expected_total if expected_total is not None else len(rows) + len(errors),
        "pass": sum(row["result"] == "PASS" for row in rows),
        "fail": sum(row["result"] == "FAIL" for row in rows) + len(errors), "by_type": by_type,
        "search_list": {"expected_program_hit": sum(row["checks"]["expected_programs_hit"] for row in searches),
                        "duplicate_count": sum(row["actual"]["duplicate_count"] for row in searches),
                        "outside_candidate_scope_count": sum(len(row["actual"]["outside_candidate_scope_ids"]) for row in searches)},
        "document_qa": {"expected_evidence_hit": sum(row["checks"]["expected_evidence_hit"] for row in questions),
                        "citation_valid": sum(row["checks"]["citation_valid"] for row in questions),
                        "cross_program_citation_count": sum(row["actual"]["cross_program_citation_count"] for row in questions)},
        "eligibility": {"status_hit": sum(row["checks"]["status_hit"] for row in eligibility),
                        "criterion_hit": sum(row["checks"]["criterion_hit"] for row in eligibility),
                        "cross_program_citation_count": sum(row["actual"]["cross_program_citation_count"] for row in eligibility)},
        "response_seconds_median": round(statistics.median(row["response_seconds"] for row in rows), 3),
        "latency_measured_cases": len(rows), "latency_unmeasured_cases": len(errors),
    }


def runtime_identity(runtime):
    retriever = runtime.retriever()
    collection = runtime.qdrant.get_collection(retriever.collection)
    embedding = retriever.embedder.identity
    return {"llm_provider": runtime.provider.name, "llm_model": runtime.provider.model,
            "embedding_model": embedding["model_repo_id"], "embedding_revision": embedding["model_revision"],
            "embedding_key": embedding["embedding_key"], "qdrant_collection": retriever.collection,
            "qdrant_points_count": collection.points_count}


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only frozen V1 AI baseline evaluation")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--cases", default=str(Path(__file__).with_name("cases-v1.json")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output_path = Path(args.output)
    if output_path.exists():
        raise SystemExit("baseline_output_exists: refusing to overwrite a completed run")
    cases, frozen = load_frozen_cases(args.cases)
    from biz_aid_pipeline.runtime import ServiceRuntime
    # BOUNDARY: V1 baseline은 V1 collection으로만 재현한다. 서비스 설정(QDRANT_COLLECTION_NAMESPACE=v2)과 무관하게 고정한다.
    runtime = ServiceRuntime(args.profile, collection_namespace=None)
    started = datetime.now(ZoneInfo("Asia/Seoul"))
    rows, errors = [], []
    try:
        as_of = date.fromisoformat(cases["as_of"])
        for case in cases["cases"]:
            case_started = time.monotonic()
            try:
                rows.append(run_case(runtime, case, as_of))
            except Exception as error:
                errors.append({"case_id": case["case_id"], "evaluation_type": case["evaluation_type"],
                               "question": case["question"], "result": "FAIL", "error_type": type(error).__name__,
                               "failure_code": str(error), "response_seconds": round(time.monotonic() - case_started, 3)})
        identity = runtime_identity(runtime)
    finally:
        runtime.close()
    finished = datetime.now(ZoneInfo("Asia/Seoul"))
    result = {"baseline_id": cases["baseline_id"], "baseline_version": cases["baseline_version"],
              "baseline_sha256": frozen["sha256"], "evidence_match": EVIDENCE_MATCH,
              "run_status": "COMPLETED" if not errors and len(rows) == frozen["case_count"] else "FAILED",
              "quality_status": "PASS" if rows and all(row["result"] == "PASS" for row in rows) else "FAIL",
              "profile": args.profile,
              "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True,
                                           check=True).stdout.strip(),
              "started_at": started.isoformat(), "finished_at": finished.isoformat(),
              "runtime_seconds": round((finished - started).total_seconds(), 3), "identity": identity,
              "summary": summarize(rows, errors, frozen["case_count"]) if rows else None,
              "cases": rows, "execution_errors": errors}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_status": result["run_status"], "quality_status": result["quality_status"],
                      "summary": result["summary"]}, ensure_ascii=False))
    print(f"result: {output_path}")
    return 0 if result["run_status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
