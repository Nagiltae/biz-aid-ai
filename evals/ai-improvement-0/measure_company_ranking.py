"""AI 개선 0단계(2): 같은 질문을 예시 회사별로 개인화 검색해 Top3가 회사마다 달라지는지 잰다.

현재 production 경로(runtime.personalized_search)와 맞춤 추천이 쓰는 기업정보 변환(search_profile)을 그대로 쓴다.
LLM은 질문 조건 추출에만 1회씩 쓰인다(Bedrock, 순차, 재시도 없음). 기존 코드는 바꾸지 않는다.
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "evals/cases-v2"))

AS_OF = "2026-10-04"
QUESTIONS = ("우리 회사가 신청할 수 있는 금융 지원사업 찾아줘", "우리 회사에 맞는 지원사업 추천해줘")
# 합성 예시 회사(실제 회사 아님). A와 A2는 지역·규모·영업상태가 같고 업종·업력·직원 수·매출·인증만 다르다.
COMPANIES = {
    "A_경기_소상공인_음식점": {"region": "경기도", "company_size": "소상공인", "business_status": "영업중", "industry": "음식점업",
                         "business_start_date": "2024-03-01", "employee_count": 3, "annual_revenue_krw": 150000000,
                         "business_entity_type": "개인사업자", "exporter": False, "venture_certified": False},
    "A2_경기_소상공인_제조": {"region": "경기도", "company_size": "소상공인", "business_status": "영업중", "industry": "금속가공 제조업",
                        "business_start_date": "2010-01-01", "employee_count": 9, "annual_revenue_krw": 900000000,
                        "business_entity_type": "법인", "exporter": True, "venture_certified": True},
    "B_경기_중소기업_수출제조": {"region": "경기도", "company_size": "중소기업", "business_status": "영업중", "industry": "전자부품 제조업",
                          "business_start_date": "2012-05-01", "employee_count": 45, "annual_revenue_krw": 8000000000,
                          "business_entity_type": "법인", "exporter": True, "venture_certified": True, "research_institute": True},
    "C_부산_중소기업_SW창업": {"region": "부산광역시", "company_size": "중소기업", "business_status": "영업중", "industry": "소프트웨어 개발",
                         "business_start_date": "2025-01-15", "employee_count": 4, "annual_revenue_krw": 200000000,
                         "business_entity_type": "법인", "exporter": False, "venture_certified": False},
}


def main():
    parser = argparse.ArgumentParser(description="Top3 by company profile; sequential Bedrock, no retry, no overwrite")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output_exists")
    os.environ["LLM_PROVIDER"] = "bedrock"
    # BOUNDARY: 자격 증명은 SDK credential chain의 로컬 profile 이름만 지정한다(키 값은 읽지 않음).
    os.environ["AWS_PROFILE"] = "bizaid-dev"
    from biz_aid_pipeline.config.settings import PipelineError
    from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
    from biz_aid_pipeline.eligibility.top_programs import search_profile
    from biz_aid_pipeline.runtime import ServiceRuntime
    from evaluate import MeteredProvider
    runtime = ServiceRuntime("dev", collection_namespace="v2", tracer=None)
    runtime.provider = MeteredProvider(runtime.provider)
    rows, started = [], datetime.now(timezone.utc).isoformat()
    try:
        for question in QUESTIONS:
            for name, company in COMPANIES.items():
                offset, begin = len(runtime.provider.calls), time.monotonic()
                # 맞춤 추천과 같은 변환: 판정용 전체 기업정보 → 검색용 4개 값(규모·영업상태·지역·개업일).
                profile = search_profile(CompanyProfileSnapshot.from_dict(company))
                row = {"question": question, "company": name, "search_profile": {k: str(v) if v is not None else None
                                                                                  for k, v in vars(profile).items()}}
                try:
                    result = runtime.personalized_search(question, profile, date.fromisoformat(AS_OF))
                    row.update(status=result.get("status"), candidate_count=result.get("candidate_count"),
                               top3=[{key: item.get(key) for key in ("rank", "pblanc_id", "name", "jurisdiction_name", "original_rank",
                                                                     "region_bonus", "final_score")} for item in result.get("programs", [])],
                               unapplied=result.get("unapplied_conditions"))
                except PipelineError as error:
                    row.update(status="FAILED", error_code=str(error))
                row.update(seconds=round(time.monotonic() - begin, 2), llm_calls=runtime.provider.calls[offset:])
                rows.append(row)
                print(json.dumps({"q": question[:12], "company": name, "status": row.get("status"), "candidates": row.get("candidate_count"),
                                  "top3": [item["pblanc_id"] for item in row.get("top3", [])]}, ensure_ascii=False), flush=True)
    finally:
        runtime.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"started_at": started, "as_of": AS_OF, "companies": COMPANIES, "rows": rows},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
