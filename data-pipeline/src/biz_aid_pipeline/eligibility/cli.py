import argparse
import json
from datetime import date
from pathlib import Path

from biz_aid_pipeline.config.settings import PipelineError


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only single-program eligibility: pblanc_id + company profile JSON → criteria (JSON)")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--pblanc-id", required=True)
    parser.add_argument("--company-profile", required=True, help="CompanyProfileSnapshot JSON 파일")
    parser.add_argument("--as-of", type=date.fromisoformat, help="YYYY-MM-DD 업력 계산 기준일(기본: Asia/Seoul 오늘)")
    args = parser.parse_args(argv)
    from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
    from biz_aid_pipeline.runtime import ServiceRuntime
    try:
        company = CompanyProfileSnapshot.from_dict(json.loads(Path(args.company_profile).read_text(encoding="utf-8")))
        runtime = ServiceRuntime(args.profile)
        try:
            result = runtime.evaluate_eligibility(args.pblanc_id, company, args.as_of)
        finally:
            runtime.close()
    except (PipelineError, ValueError) as error:
        print(json.dumps({"status": "FAILED", "failure_code": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
