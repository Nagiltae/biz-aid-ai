"""AI 개선 1단계: 기업정보 문장 가중치 후보 비교(IMP-019 A안). 계약 값은 바꾸지 않고 이 실행 안에서만 후보 값을 바꿔 본다.

- 질문 조건 추출(LLM, Bedrock)은 질문마다 1회만 부르고 결과를 재사용한다(가중치 후보마다 다시 부르지 않음).
- 0단계 예시 회사 4개 × 질문 2개, cases-v2 V2-16~18 원래 입력, V2-16~18에 예시 회사 A의 순위용 항목을 더한 입력을 비교한다.
- cases-v2 기대 공고(expected.program_ids)는 읽기만 한다.
"""
import argparse
import copy
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "evals/ai-improvement-0"))
sys.path.insert(0, str(ROOT / "evals/cases-v2"))

AS_OF = "2026-10-04"
# (이름, 일반 질문이 아닐 때 가중치, 일반 질문일 때 가중치). None = 기업정보 문장 끔(질문만, 0단계와 같은 결과).
CANDIDATES = (("off", None, None), ("w0.3", 0.3, 0.3), ("w0.5", 0.5, 0.5), ("w0.3_g0.6", 0.3, 0.6), ("w0.5_g0.8", 0.5, 0.8))
RANKING_FIELDS = ("industry", "business_entity_type", "business_start_date", "employee_count", "annual_revenue_krw", "exporter",
                  "venture_certified", "research_institute")


def main():
    parser = argparse.ArgumentParser(description="Company-sentence weight comparison; Bedrock once per question, no overwrite")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output_exists")
    os.environ["LLM_PROVIDER"] = "bedrock"
    # BOUNDARY: 자격 증명은 SDK credential chain의 로컬 profile 이름만 지정한다(키 값은 읽지 않음).
    os.environ["AWS_PROFILE"] = "bizaid-dev"
    from biz_aid_pipeline.candidates import natural, personalized
    from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
    from biz_aid_pipeline.eligibility.top_programs import search_profile
    from biz_aid_pipeline.rag.service import rag_contract
    from biz_aid_pipeline.runtime import ServiceRuntime
    from evaluate import MeteredProvider
    from measure_company_ranking import COMPANIES, QUESTIONS

    cases = {case["case_id"]: case for case in json.loads((ROOT / "evals/cases-v2/cases-v2.json").read_text(encoding="utf-8"))["cases"]}
    inputs = [(question, name, company, None) for question in QUESTIONS for name, company in COMPANIES.items()]
    enrich = {key: value for key, value in COMPANIES["A_경기_소상공인_음식점"].items() if key in RANKING_FIELDS}
    for case_id in ("V2-16", "V2-17", "V2-18"):
        case = cases[case_id]
        expected = case["expected"].get("program_ids") or []
        inputs.append((case["question"], case_id, case["company_profile"], expected))
        inputs.append((case["question"], case_id + "+A순위항목", dict(case["company_profile"], **enrich), expected))

    # 질문 조건 추출은 질문마다 한 번만 한다(같은 실행 안 재사용, 가중치 비교가 LLM 변동에 섞이지 않게).
    original_extract, memo = natural.NaturalLanguageFilterService.extract, {}

    def memo_extract(self, query, as_of=None, **options):
        if query not in memo:
            memo[query] = original_extract(self, query, as_of, **options)
        return memo[query]

    natural.NaturalLanguageFilterService.extract = memo_extract
    base_contract = rag_contract()
    runtime = ServiceRuntime("dev", collection_namespace="v2", tracer=None)
    runtime.provider = MeteredProvider(runtime.provider)
    rows = []
    try:
        for label, weight, generic_weight in CANDIDATES:
            contract = copy.deepcopy(base_contract)
            if weight is not None:
                contract["personalized_ranking"]["company_query"].update(company_weight=weight, generic_question_weight=generic_weight)
            personalized.rag_contract = lambda contract=contract: contract
            for question, name, company, expected in inputs:
                profile = search_profile(CompanyProfileSnapshot.from_dict(company))
                if weight is None:
                    # 끔: 순위용 항목을 지운 같은 입력 = 0단계 경로. 개업일은 후보 조건에서 unapplied일 뿐이지만 순위 문장에는 쓰이므로 함께 뺀다.
                    profile = personalized.CompanySearchProfile(profile.company_size, profile.business_status, profile.region)
                result = runtime.personalized_search(question, profile, date.fromisoformat(AS_OF))
                top3 = result.get("programs", [])
                row = {"candidate": label, "question": question, "input": name, "status": result.get("status"),
                       "candidate_count": result.get("candidate_count"),
                       "company_query": result["applied_conditions"]["company"].get("company_query") if result.get("applied_conditions") else None,
                       "top3": [{key: item.get(key) for key in ("rank", "pblanc_id", "name", "target", "jurisdiction_name", "question_rank",
                                                                "company_rank", "blended_score", "region_bonus")} for item in top3]}
                if expected is not None:
                    row["expected"] = expected
                    row["expected_in_top3"] = all(pblanc in [item["pblanc_id"] for item in top3] for pblanc in expected)
                rows.append(row)
                print(json.dumps({"c": label, "in": name, "q": question[:10], "top3": [item["pblanc_id"][-6:] for item in top3],
                                  "ok": row.get("expected_in_top3")}, ensure_ascii=False), flush=True)
    finally:
        personalized.rag_contract = rag_contract
        natural.NaturalLanguageFilterService.extract = original_extract
        runtime.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(), "as_of": AS_OF, "llm_calls": runtime.provider.calls,
                                      "candidates": CANDIDATES, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
